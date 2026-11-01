"""Step 5 - cooling-center selection: greedy vs exact (ILP) maximal coverage.

Candidate sites: real LA County Regional Cooling Centers (153, official layer).
Demand: the 287 modeled ZIPs. Benefit of covering a ZIP = its out-of-fold
predicted excess ER *number* (predicted rate x population / 10,000). A ZIP counts
as covered if any selected site lies within the radius of its centroid.

Selection is the Maximal Covering Location Problem (MCLP):
  maximize   sum_z benefit_z * y_z
  subject to y_z <= sum_{s covers z} x_s      (a ZIP is covered only if an open
             sum_s x_s <= k                     site covers it; at most k sites)
Solved both greedily and exactly (PuLP/CBC). Selections are also scored against
OBSERVED excess ER, and coverage equity is reported by income and CES quartile.

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
PRIMARY_MODEL = "poisson"  # best rank correlation / top-10% recall in Step 4


def haversine_miles(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return EARTH_MI * 2 * np.arcsin(np.sqrt(a))


def load_sites(path: str = "data/raw/cooling_centers_lacounty.json") -> pd.DataFrame:
    import json
    d = json.load(open(path))
    rows = []
    for f in d["features"]:
        g = f.get("geometry") or {}
        if g.get("x") is None:
            continue
        rows.append({"site": f["attributes"].get("Site_Name"),
                     "lat": g["y"], "lon": g["x"]})
    return pd.DataFrame(rows)


def build_demand() -> pd.DataFrame:
    zips = pd.read_csv("data/processed/model_table_grouped.csv")
    oof = pd.read_csv("results/predictions_oof.csv")
    df = zips.merge(oof[["zip", f"pred_{PRIMARY_MODEL}"]], on="zip")
    pop = df["ucla_population"].to_numpy(float)
    df["pred_excess_number"] = np.clip(df[f"pred_{PRIMARY_MODEL}"], 0, None) * pop / 1e4
    df["obs_excess_number"] = df["excess_er_number"].to_numpy(float)
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
    """Covered share of benefit within each quartile of `value_col`."""
    v = df[value_col]
    q = pd.qcut(v.rank(method="first"), 4, labels=[1, 2, 3, 4])
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
        "n_zips": int(len(df)),
        "n_candidate_sites": int(len(sites)),
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
