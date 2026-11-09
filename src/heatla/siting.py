"""Step 5 - cooling-center selection: greedy vs exact (ILP) maximal coverage.

Candidate sites: real LA County Regional Cooling Centers (153, official layer).
Demand: the 287 modeled ZIPs. Benefit of covering a ZIP = its out-of-fold
predicted excess ER *number* (predicted rate x population / 10,000). The rate is
the Part 2 augmented Poisson model's out-of-fold prediction. A ZIP counts as
covered if any selected site lies within the radius of its centroid.

Selection is the Maximal Covering Location Problem (MCLP):
  maximize   sum_z benefit_z * y_z
  subject to y_z <= sum_{s covers z} x_s      (a ZIP is covered only if an open
             sum_s x_s <= k                     site covers it; at most k sites)
Solved both greedily and exactly (PuLP/CBC). Selections are also scored against
OBSERVED excess ER, and coverage equity is reported by income and CES quartile.

Decision check: the same exact program is solved with other weights (the UCLA
label itself, population only, the level-4-only label) and with random site
sets, and every plan is scored on the UCLA-label burden.

Cost is a documented, adjustable assumption: a uniform cost per center (default
1 unit); the "budget" is the number of centers k. No dollar figures are invented.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pulp

EARTH_MI = 3958.7613
BUDGETS = [5, 10, 20, 40]
RADII_MI = [1, 2, 3, 5]
PRIMARY_MODEL = "poisson_augmented"  # Part 2 final LA configuration
OOF_PATH = "part2/results/feature_comparison/predictions_oof.csv"
BASE_PATH = "part2/data/la_base.csv"            # centroids, population, label, corrected CES
ZIPS_GEOJSON = "site/data/zips.geojson"          # median household income
LEVEL4_PATH = "results/member1/inputs/model_table_ca_ces40_fixed_level_only.csv"
CENTERS_PATH = "site/data/centers.json"
LIBRARIES_PATH = "data/raw/heatrisk/sites_libraries.geojson"
N_RANDOM, RANDOM_SEED = 100, 42


def haversine_miles(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return EARTH_MI * 2 * np.arcsin(np.sqrt(a))


def load_sites(path: str = CENTERS_PATH) -> pd.DataFrame:
    """The 153 LA County regional cooling centers (same layer as sites_regional.geojson)."""
    import json
    d = json.load(open(path))
    return pd.DataFrame([{"site": c["name"], "lat": c["lat"], "lon": c["lon"]} for c in d])


def load_libraries(sites: pd.DataFrame, path: str = LIBRARIES_PATH,
                   dedupe_mi: float = 0.1) -> pd.DataFrame:
    """Libraries in the LA County 211 layer that are not already cooling centers.

    Keeps features with cat2 == "Libraries", drops administrative offices, drops
    duplicates by name or by location (within `dedupe_mi`), and drops any library
    within `dedupe_mi` of an existing center.
    """
    import json
    d = json.load(open(path))
    rows = []
    for f in d["features"]:
        p = f["properties"]
        if p.get("cat2") != "Libraries" or "administrative" in (p.get("name") or "").lower():
            continue
        rows.append({"site": p["name"].strip(), "lat": p["latitude"], "lon": p["longitude"]})
    lib = pd.DataFrame(rows).drop_duplicates("site").reset_index(drop=True)
    keep = []
    for i, r in lib.iterrows():
        near_center = haversine_miles(r.lat, r.lon, sites["lat"], sites["lon"]).min() <= dedupe_mi
        near_kept = any(haversine_miles(r.lat, r.lon, lib.lat[j], lib.lon[j]) <= dedupe_mi
                        for j in keep)
        if not near_center and not near_kept:
            keep.append(i)
    return lib.loc[keep].reset_index(drop=True)


def build_demand() -> pd.DataFrame:
    """One row per LA ZIP: centroid, population, label, weights and equity fields."""
    import json
    base = pd.read_csv(BASE_PATH, dtype={"zip": str})
    oof = pd.read_csv(OOF_PATH, dtype={"zip": str})
    props = [f["properties"] for f in json.load(open(ZIPS_GEOJSON))["features"]]
    inc = pd.DataFrame({"zip": [str(p["zip"]) for p in props],
                        "median_hh_income": [p["median_hh_income"] for p in props]})
    lvl = pd.read_csv(LEVEL4_PATH, dtype={"zip": str})
    lvl = lvl[(lvl["county"] == "Los Angeles") & (lvl["chs_level"] == 4)]
    lvl = lvl[["zip", "excess_er_rate_per_10k"]].rename(
        columns={"excess_er_rate_per_10k": "level4_rate"})
    df = (base[["zip", "lat", "lon", "population", "excess_er_number", "ces4_percentile"]]
          .merge(oof[["zip", f"pred_{PRIMARY_MODEL}"]], on="zip", validate="1:1")
          .merge(inc, on="zip", how="left", validate="1:1")
          .merge(lvl, on="zip", how="left", validate="1:1"))
    pop = df["population"].to_numpy(float)
    df["pred_excess_number"] = np.clip(df[f"pred_{PRIMARY_MODEL}"], 0, None) * pop / 1e4
    df["obs_excess_number"] = df["excess_er_number"].to_numpy(float)
    df["level4_excess_number"] = np.clip(df["level4_rate"].fillna(0), 0, None) * pop / 1e4
    return df


def coverage_matrix(df: pd.DataFrame, sites: pd.DataFrame, radius: float) -> np.ndarray:
    """Boolean [n_zip, n_site] matrix: ZIP centroid within `radius` miles of site."""
    zlat = df["lat"].to_numpy()[:, None]
    zlon = df["lon"].to_numpy()[:, None]
    slat = sites["lat"].to_numpy()[None, :]
    slon = sites["lon"].to_numpy()[None, :]
    return haversine_miles(zlat, zlon, slat, slon) <= radius


def greedy(cover: np.ndarray, benefit: np.ndarray, k: int) -> list[int]:
    """Greedily pick k sites maximizing marginal covered benefit."""
    n_sites = cover.shape[1]
    chosen: list[int] = []
    covered = np.zeros(cover.shape[0], dtype=bool)
    for _ in range(min(k, n_sites)):
        best_gain, best_s = -1.0, -1
        for s in range(n_sites):
            if s in chosen:
                continue
            gain = benefit[cover[:, s] & ~covered].sum()
            if gain > best_gain:
                best_gain, best_s = gain, s
        if best_s < 0 or best_gain <= 0:
            break
        chosen.append(best_s)
        covered |= cover[:, best_s]
    return chosen


def exact(cover: np.ndarray, benefit: np.ndarray, k: int) -> list[int]:
    """Exact MCLP via PuLP/CBC."""
    n_zip, n_site = cover.shape
    prob = pulp.LpProblem("mclp", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x{s}", cat="Binary") for s in range(n_site)]
    y = [pulp.LpVariable(f"y{z}", cat="Binary") for z in range(n_zip)]
    prob += pulp.lpSum(benefit[z] * y[z] for z in range(n_zip))
    prob += pulp.lpSum(x) <= k
    for z in range(n_zip):
        covering = np.where(cover[z])[0]
        if len(covering):
            prob += y[z] <= pulp.lpSum(x[s] for s in covering)
        else:
            prob += y[z] == 0
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    return [s for s in range(n_site) if x[s].value() and x[s].value() > 0.5]


def _quartile_coverage(df, covered, value_col, benefit_col, ascending) -> dict:
    """Covered share of benefit within each quartile of `value_col` (ZIPs with a value)."""
    v = df[value_col]
    q = pd.qcut(v.rank(method="first"), 4, labels=[1, 2, 3, 4])  # NaN values stay unassigned
    out = {}
    for lab in [1, 2, 3, 4]:
        m = (q == lab).to_numpy()
        tot = df[benefit_col].to_numpy()[m].sum()
        cov = df[benefit_col].to_numpy()[m & covered].sum()
        out[f"q{lab}"] = round(float(cov / tot), 4) if tot > 0 else None
    out["worst_quartile_coverage"] = min(x for x in out.values() if x is not None)
    return out


def evaluate(df, sites, chosen, cover) -> dict:
    sel = np.zeros(cover.shape[1], dtype=bool)
    sel[chosen] = True
    covered = cover[:, sel].any(axis=1) if sel.any() else np.zeros(cover.shape[0], bool)
    pred = df["pred_excess_number"].to_numpy()
    obs = df["obs_excess_number"].to_numpy()
    return {
        "n_selected": int(sel.sum()),
        "zips_covered": int(covered.sum()),
        "pred_coverage": round(float(pred[covered].sum() / pred.sum()), 4),
        "obs_coverage": round(float(obs[covered].sum() / obs.sum()), 4),
        "equity_income_quartile": _quartile_coverage(
            df, covered, "median_hh_income", "pred_excess_number", ascending=True),
        "equity_ces_quartile": _quartile_coverage(
            df, covered, "ces4_percentile", "pred_excess_number", ascending=True),
    }


def run_all(cost_per_center: float = 1.0) -> dict:
    df = build_demand()
    sites = load_sites()
    benefit = df["pred_excess_number"].to_numpy()
    results = {
        "primary_model": PRIMARY_MODEL,
        "weights_source": f"{OOF_PATH} (pred_{PRIMARY_MODEL})",
        "n_zips": int(len(df)),
        "n_candidate_sites": int(len(sites)),
        "n_zips_with_ces": int(df["ces4_percentile"].notna().sum()),
        "cost_per_center": cost_per_center,
        "cost_note": "uniform cost per center; budget = number of centers k; adjustable",
        "budgets_k": BUDGETS,
        "radii_miles": RADII_MI,
        "runs": [],
    }
    for radius in RADII_MI:
        cover = coverage_matrix(df, sites, radius)
        for k in BUDGETS:
            g = greedy(cover, benefit, k)
            e = exact(cover, benefit, k)
            results["runs"].append({
                "radius_mi": radius, "k": k,
                "budget_cost": k * cost_per_center,
                "greedy": {"sites": [sites.iloc[s]["site"] for s in g], **evaluate(df, sites, g, cover)},
                "exact": {"sites": [sites.iloc[s]["site"] for s in e], **evaluate(df, sites, e, cover)},
            })
    return results


# weights each plan is chosen with; every plan is scored on the UCLA-label burden
PLAN_WEIGHTS = {
    "prediction": "pred_excess_number",       # (a) model out-of-fold predictions
    "label": "obs_excess_number",              # (b) UCLA label, perfect information
    "population": "population",                # (c) population only, ignores risk
    "label_level4": "level4_excess_number",    # level-4-only label, extreme days only
}


def decision_check(candidates: str = "centers") -> pd.DataFrame:
    """Score plans chosen with different weights on the true UCLA-label burden.

    candidates: "centers" (153 existing) or "centers_plus_libraries".
    """
    df = build_demand()
    sites = load_sites()
    if candidates == "centers_plus_libraries":
        sites = pd.concat([sites, load_libraries(sites)], ignore_index=True)
    obs = df["obs_excess_number"].to_numpy()
    rng = np.random.default_rng(RANDOM_SEED)
    rows = []
    for radius in RADII_MI:
        cover = coverage_matrix(df, sites, radius)
        ceiling = obs[cover.any(axis=1)].sum() / obs.sum()
        for k in BUDGETS:
            row = {"candidates": candidates, "n_candidate_sites": len(sites),
                   "radius_mi": radius, "k": k, "ceiling": round(float(ceiling), 4)}
            for name, col in PLAN_WEIGHTS.items():
                chosen = exact(cover, df[col].to_numpy(float), k)
                covered = cover[:, chosen].any(axis=1)
                row[f"{name}_label_coverage"] = round(float(obs[covered].sum() / obs.sum()), 4)
            rand = []
            for _ in range(N_RANDOM):
                chosen = rng.choice(len(sites), size=k, replace=False)
                rand.append(obs[cover[:, chosen].any(axis=1)].sum() / obs.sum())
            row["random_mean_label_coverage"] = round(float(np.mean(rand)), 4)
            row["random_p95_label_coverage"] = round(float(np.percentile(rand, 95)), 4)
            rows.append(row)
    return pd.DataFrame(rows)
