"""Part C: where should K new cooling centres go?

This is a maximum-coverage location problem (MCLP). Candidate sites are tract
centroids; a site covers every tract whose centroid falls within the service
radius; we pick K sites to maximise covered benefit.

Two things are kept deliberately separate, the way a model is trained on one
loss but reported on many metrics:

    OPTIMISE FOR   the objective handed to greedy/ILP (count, or Pop x HVI)
    EVALUATE ON    every metric in `evaluate()`, for every solution

So a solution that optimises raw count is still scored on how much
high-vulnerability population it reaches and on coverage by demographic
subgroup, and vice versa.

Greedy is the natural heuristic here: coverage is a monotone submodular set
function, so greedy is guaranteed within (1 - 1/e) ~ 63% of the optimum. The
ILP gives the exact optimum, which lets us report the real gap rather than
the worst-case bound.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
import geopandas as gpd
import pulp

from .config import Config
from .spatial import centroids_xy, points_xy, coverage_sets, covered_mask


# ----------------------------------------------------------- objectives -----
def tract_weights(df: pd.DataFrame, objective: str) -> np.ndarray:
    """Benefit of covering each tract, under a given objective."""
    if objective == "count":
        return np.ones(len(df))
    if objective == "pop_x_hvi":
        return (df["pop"].to_numpy(float)
                * np.nan_to_num(df["hvi"].to_numpy(float)) / 100.0)
    if objective == "pop":
        return df["pop"].to_numpy(float)
    if objective == "pop_x_hvi_x_age65":
        return (df["pop"].to_numpy(float)
                * np.nan_to_num(df["hvi"].to_numpy(float)) / 100.0
                * (1.0 + np.nan_to_num(df["pct_age65p"].to_numpy(float)) / 100.0))
    raise ValueError(f"unknown objective: {objective}")


# -------------------------------------------------------------- solvers -----
def greedy_mclp(cov: list[np.ndarray], weights: np.ndarray, k: int,
                already: np.ndarray | None = None) -> list[int]:
    """Add the site that covers the most still-uncovered weight, K times."""
    n = len(weights)
    covered = np.zeros(n, bool) if already is None else already.copy()
    chosen: list[int] = []
    gain_cache = np.array([weights[c].sum() if len(c) else 0.0 for c in cov])
    for _ in range(k):
        best, best_gain = -1, 0.0
        # Lazy evaluation: a site's marginal gain can only shrink as coverage
        # grows, so a cached gain below the current best can be skipped.
        order = np.argsort(-gain_cache)
        for e in order:
            if e in chosen:
                continue
            if gain_cache[e] <= best_gain:
                break
            c = cov[e]
            g = weights[c][~covered[c]].sum() if len(c) else 0.0
            gain_cache[e] = g
            if g > best_gain:
                best, best_gain = int(e), float(g)
        if best < 0 or best_gain <= 0:
            break
        chosen.append(best)
        covered[cov[best]] = True
    return chosen


def ilp_mclp(cov: list[np.ndarray], weights: np.ndarray, k: int,
             already: np.ndarray | None = None,
             time_limit_s: int = 120) -> tuple[list[int], dict]:
    """Exact MCLP:  max sum_j w_j y_j  s.t.  y_j <= sum_{e covers j} x_e,
    sum_e x_e = K,  x, y binary."""
    n = len(weights)
    pre = np.zeros(n, bool) if already is None else already
    tract_cands: list[list[int]] = [[] for _ in range(n)]
    for e, c in enumerate(cov):
        for j in c:
            tract_cands[j].append(e)

    prob = pulp.LpProblem("mclp", pulp.LpMaximize)
    x = {e: pulp.LpVariable(f"x_{e}", cat="Binary") for e in range(len(cov))}
    open_j = [j for j in range(n) if not pre[j] and tract_cands[j] and weights[j] > 0]
    y = {j: pulp.LpVariable(f"y_{j}", cat="Binary") for j in open_j}

    prob += pulp.lpSum(weights[j] * y[j] for j in open_j)
    prob += pulp.lpSum(x.values()) == k
    for j in open_j:
        prob += y[j] <= pulp.lpSum(x[e] for e in tract_cands[j])

    t0 = time.time()
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_s)
    prob.solve(solver)
    chosen = sorted(e for e, v in x.items() if v.value() and v.value() > 0.5)
    meta = {"status": pulp.LpStatus[prob.status],
            "objective": float(pulp.value(prob.objective) or 0.0),
            "solve_seconds": round(time.time() - t0, 2),
            "proven_optimal": pulp.LpStatus[prob.status] == "Optimal"}
    return chosen, meta


# ------------------------------------------------------------ baselines -----
def baseline_top_k(df: pd.DataFrame, col: str, k: int,
                   ascending: bool = False) -> list[int]:
    """Rank tracts by an index and take the top K. This is what agencies do
    today; its weakness is redundancy - the #1 and #2 tracts are often
    neighbours, so the second site mostly re-covers the first one's area."""
    s = df[col]
    idx = s.sort_values(ascending=ascending, na_position="last").index[:k]
    return [int(df.index.get_loc(i)) for i in idx]


def baseline_random(n_cand: int, k: int, rng: np.random.Generator) -> list[int]:
    return sorted(rng.choice(n_cand, size=k, replace=False).tolist())


# ----------------------------------------------------------- evaluation -----
def evaluate(df: pd.DataFrame, cov: list[np.ndarray], chosen: list[int],
             already: np.ndarray, cfg: Config) -> dict:
    """Score a chosen site set on every metric, regardless of what it
    optimised. `already` is the coverage from existing centres."""
    n = len(df)
    new = np.zeros(n, bool)
    for e in chosen:
        new[cov[e]] = True
    total = already | new

    pop = df["pop"].to_numpy(float)
    hvi = np.nan_to_num(df["hvi"].to_numpy(float))
    w_vuln = pop * hvi / 100.0
    top25 = df["hvi_top25"].to_numpy(bool) if "hvi_top25" in df else hvi >= np.nanquantile(hvi, .75)
    top10 = df["hvi_top10"].to_numpy(bool) if "hvi_top10" in df else hvi >= np.nanquantile(hvi, .90)
    low = hvi <= np.nanquantile(hvi, .25)

    def share(mask_pop, sel):
        tot = mask_pop.sum()
        return float(100 * mask_pop[sel].sum() / tot) if tot > 0 else np.nan

    res = {
        "n_new_sites": len(chosen),
        "tracts_covered": int(total.sum()),
        "tracts_covered_pct": float(100 * total.mean()),
        "tracts_newly_covered": int((new & ~already).sum()),
        "pop_covered": float(pop[total].sum()),
        "pop_covered_pct": share(pop, total),
        "pop_newly_covered": float(pop[new & ~already].sum()),
        "vuln_weighted_pop_covered": float(w_vuln[total].sum()),
        "vuln_weighted_pop_covered_pct": share(w_vuln, total),
        "top25_hvi_pop_covered_pct": share(pop * top25, total),
        "top10_hvi_pop_covered_pct": share(pop * top10, total),
        "low_hvi_pop_covered_pct": share(pop * low, total),
    }
    res["hvi_coverage_gap_pp"] = (res["top25_hvi_pop_covered_pct"]
                                  - res["low_hvi_pop_covered_pct"])

    # Fairness = coverage rate per demographic subgroup. A solution can cover
    # a lot of people and still leave one group behind; this is where that
    # shows up.
    fair = {}
    for col, nm in (("pct_age65p", "age_65_plus"), ("pct_under5", "under_5"),
                    ("pct_under18", "under_18"), ("pct_poverty", "below_poverty"),
                    ("pct_hispanic", "hispanic"), ("pct_black", "black"),
                    ("pct_asian", "asian"), ("pct_white_nh", "white_nh")):
        if col in df.columns and df[col].notna().any():
            grp = np.nan_to_num(df[col].to_numpy(float)) / 100.0 * pop
            fair[nm] = share(grp, total)
    fair["all_residents"] = res["pop_covered_pct"]
    if len(fair) > 1:
        vals = [v for k_, v in fair.items() if k_ != "all_residents" and np.isfinite(v)]
        fair["max_minus_min_pp"] = float(max(vals) - min(vals)) if vals else np.nan
    res["fairness_coverage_pct_by_group"] = fair
    return res


# ------------------------------------------------------------- the grid -----
def build_candidates(df: gpd.GeoDataFrame, centers: gpd.GeoDataFrame | None,
                     radius_m: float):
    """Candidate sites are tract centroids; existing centres define the
    coverage we start from (new sites are additions, not replacements)."""
    txy = centroids_xy(df)
    cand_xy = txy.copy()
    cov = coverage_sets(cand_xy, txy, radius_m)
    already = (covered_mask(points_xy(centers), txy, radius_m)
               if centers is not None and len(centers) else np.zeros(len(df), bool))
    return cand_xy, cov, already


def run_grid(cfg: Config, df: gpd.GeoDataFrame,
             centers: gpd.GeoDataFrame | None) -> dict:
    rng = np.random.default_rng(cfg.seed)
    df = df.reset_index(drop=True)
    results, solutions, curves = [], {}, []

    for radius in cfg.radius_grid_m:
        cand_xy, cov, already = build_candidates(df, centers, radius)
        base_eval = evaluate(df, cov, [], already, cfg)
        base_eval.update({"radius_m": radius, "method": "existing_only",
                          "objective": "-", "k": 0})
        results.append(base_eval)

        for objective in cfg.objectives:
            w = tract_weights(df, objective)
            for k in cfg.k_grid:
                # --- greedy
                g = greedy_mclp(cov, w, k, already)
                ev = evaluate(df, cov, g, already, cfg)
                ev.update({"radius_m": radius, "method": "greedy",
                           "objective": objective, "k": k})
                results.append(ev)
                solutions[f"greedy|{objective}|{radius}|{k}"] = g

                # --- ILP, only on the reported radius/budgets: CBC on 2,498
                # candidates is slow and the curve does not need it everywhere.
                if radius == cfg.radius_m and k in cfg.k_report:
                    ilp, meta = ilp_mclp(cov, w, k, already, cfg.ilp_time_limit_s)
                    ev = evaluate(df, cov, ilp, already, cfg)
                    ev.update({"radius_m": radius, "method": "ilp",
                               "objective": objective, "k": k, **{
                                   f"ilp_{kk}": vv for kk, vv in meta.items()}})
                    results.append(ev)
                    solutions[f"ilp|{objective}|{radius}|{k}"] = ilp

        # --- baselines, evaluated on the same metrics
        for k in cfg.k_grid:
            for col, nm, asc in (("hvi", "sort_by_hvi", False),
                                 ("ces_score", "sort_by_ces", False),
                                 ("svi", "sort_by_svi", False),
                                 ("lst_f", "hottest_tracts", False),
                                 ("pop", "most_populous", False)):
                if col not in df.columns or df[col].isna().all():
                    continue
                sel = baseline_top_k(df, col, k, asc)
                ev = evaluate(df, cov, sel, already, cfg)
                ev.update({"radius_m": radius, "method": nm, "objective": "-", "k": k})
                results.append(ev)
                solutions[f"{nm}|-|{radius}|{k}"] = sel

            # Random placement, averaged over draws. This is the reference
            # point: absolute coverage numbers mean little, the gain over
            # random is what strategic siting actually buys.
            draws = [evaluate(df, cov, baseline_random(len(cov), k, rng), already, cfg)
                     for _ in range(cfg.n_random_draws)]
            avg = {kk: float(np.mean([d[kk] for d in draws]))
                   for kk in draws[0] if isinstance(draws[0][kk], (int, float))}
            avg["fairness_coverage_pct_by_group"] = {
                g: float(np.mean([d["fairness_coverage_pct_by_group"][g] for d in draws]))
                for g in draws[0]["fairness_coverage_pct_by_group"]}
            avg.update({"radius_m": radius, "method": "random", "objective": "-",
                        "k": k, "n_draws": cfg.n_random_draws})
            results.append(avg)

    res = pd.DataFrame(results)

    # Delta over random: every headline number is reported as a gain over the
    # random baseline at the same radius and K.
    rnd = (res[res["method"] == "random"]
           .set_index(["radius_m", "k"])[["vuln_weighted_pop_covered_pct",
                                          "pop_covered_pct",
                                          "top25_hvi_pop_covered_pct"]])
    for col in ("vuln_weighted_pop_covered_pct", "pop_covered_pct",
                "top25_hvi_pop_covered_pct"):
        res[f"{col}_vs_random_pp"] = res.apply(
            lambda r: (r[col] - rnd.loc[(r["radius_m"], r["k"]), col])
            if (r["radius_m"], r["k"]) in rnd.index else np.nan, axis=1).round(3)

    # Optimality gap for greedy where an exact solution exists.
    for objective in cfg.objectives:
        for k in cfg.k_report:
            m_i = ((res["method"] == "ilp") & (res["objective"] == objective)
                   & (res["k"] == k) & (res["radius_m"] == cfg.radius_m))
            m_g = ((res["method"] == "greedy") & (res["objective"] == objective)
                   & (res["k"] == k) & (res["radius_m"] == cfg.radius_m))
            if m_i.any() and m_g.any():
                col = ("vuln_weighted_pop_covered" if objective == "pop_x_hvi"
                       else "tracts_covered")
                gi, gg = res.loc[m_i, col].iloc[0], res.loc[m_g, col].iloc[0]
                res.loc[m_g, "greedy_vs_ilp_ratio"] = round(gg / gi, 5) if gi else np.nan

    fair = pd.json_normalize(res["fairness_coverage_pct_by_group"]).add_prefix("fair_")
    out = pd.concat([res.drop(columns="fairness_coverage_pct_by_group"), fair], axis=1)
    out.round(4).to_csv(cfg.paths.tables / "partC_results_grid.csv", index=False)

    # Budget-vs-coverage curve at the default radius.
    cur = out[(out["radius_m"] == cfg.radius_m) & (out["k"] > 0)]
    cur[["method", "objective", "k", "vuln_weighted_pop_covered_pct",
         "pop_covered_pct", "top25_hvi_pop_covered_pct"]].round(3).to_csv(
        cfg.paths.tables / "partC_budget_curve.csv", index=False)

    # Headline table at the reported budgets.
    rep = out[(out["radius_m"] == cfg.radius_m) & (out["k"].isin(cfg.k_report))]
    cols = ["method", "objective", "k", "tracts_covered", "pop_covered_pct",
            "vuln_weighted_pop_covered_pct", "top25_hvi_pop_covered_pct",
            "hvi_coverage_gap_pp", "vuln_weighted_pop_covered_pct_vs_random_pp",
            "fair_age_65_plus", "fair_under_5", "fair_below_poverty"]
    rep[[c for c in cols if c in rep.columns]].round(2).to_csv(
        cfg.paths.tables / "partC_headline.csv", index=False)

    chosen_out = {}
    for key, sel in solutions.items():
        chosen_out[key] = {
            "tract_index": [int(i) for i in sel],
            "GEOID": df.loc[sel, "GEOID"].tolist(),
            "lon": df.loc[sel, "INTPTLON"].round(6).tolist()
            if "INTPTLON" in df.columns else [],
            "lat": df.loc[sel, "INTPTLAT"].round(6).tolist()
            if "INTPTLAT" in df.columns else [],
        }
    (cfg.paths.processed / "partC_solutions.json").write_text(
        json.dumps(chosen_out, indent=1))

    key = out[(out["method"] == "greedy") & (out["objective"] == "pop_x_hvi")
              & (out["k"] == cfg.k_default) & (out["radius_m"] == cfg.radius_m)]
    if len(key):
        r = key.iloc[0]
        print(f"  Part C: greedy/pop_x_hvi K={cfg.k_default} r={cfg.radius_m}m -> "
              f"{r['pop_covered_pct']:.1f}% population covered, "
              f"{r['top25_hvi_pop_covered_pct']:.1f}% of top-quartile-HVI residents "
              f"(+{r['vuln_weighted_pop_covered_pct_vs_random_pp']:.1f} pp vs random)")
    return {"results": out, "solutions": chosen_out}
