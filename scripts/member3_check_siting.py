"""Member 3 - independent check of the cooling-centre siting results.

Re-solves the integer program described in reports/member3_labels_website_siting.md
from the committed inputs, without calling src/heatla/siting.py, and compares the answer
with results/coolingcenter_solutions.json. Nothing in results/ is rewritten.

Inputs (read-only)
  part2/data/la_base.csv           ZIP centroids, UCLA population, observed excess number
  part2/results/feature_comparison/predictions_oof.csv
                                   out-of-fold augmented Poisson predictions (the burden weights)
  site/data/centers.json           the 153 candidate sites (existing cooling centres)
  results/coolingcenter_solutions.json  the committed solutions being checked
Outputs
  results/member3/siting/siting_check.csv         one row per radius x budget
  results/member3/siting/siting_instance.json     sizes and totals of the instance

Run:  .venv/bin/python scripts/member3_check_siting.py
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
import pulp

OUT = pathlib.Path("results/member3/siting")
EARTH_MI = 3958.7613


def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return EARTH_MI * 2 * np.arcsin(np.sqrt(a))


def solve(cover: np.ndarray, w: np.ndarray, k: int) -> tuple[float, list[int]]:
    """max sum_z w_z y_z  s.t.  y_z <= sum_{s covers z} x_s,  sum_s x_s <= k,  x, y binary."""
    n_zip, n_site = cover.shape
    prob = pulp.LpProblem("mclp_check", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x{s}", cat="Binary") for s in range(n_site)]
    y = [pulp.LpVariable(f"y{z}", cat="Binary") for z in range(n_zip)]
    prob += pulp.lpSum(float(w[z]) * y[z] for z in range(n_zip))
    prob += pulp.lpSum(x) <= k
    for z in range(n_zip):
        idx = np.where(cover[z])[0]
        prob += y[z] <= pulp.lpSum(x[s] for s in idx) if len(idx) else y[z] == 0
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    assert pulp.LpStatus[prob.status] == "Optimal"
    chosen = [s for s in range(n_site) if x[s].value() and x[s].value() > 0.5]
    return float(pulp.value(prob.objective)), chosen


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    zips = pd.read_csv("part2/data/la_base.csv", dtype={"zip": str}).dropna(
        subset=["excess_er_rate_per_10k", "lat", "lon"]).reset_index(drop=True)
    oof = pd.read_csv("part2/results/feature_comparison/predictions_oof.csv", dtype={"zip": str})
    df = zips.merge(oof[["zip", "pred_poisson_augmented"]], on="zip")
    sites = pd.DataFrame(json.loads(pathlib.Path("site/data/centers.json").read_text()))
    sol = json.loads(pathlib.Path("results/coolingcenter_solutions.json").read_text())

    w = (np.clip(df["pred_poisson_augmented"].to_numpy(float), 0, None)
         * df["population"].to_numpy(float) / 1e4)
    obs = df["excess_er_number"].to_numpy(float)
    dist = haversine(df["lat"].to_numpy()[:, None], df["lon"].to_numpy()[:, None],
                     sites["lat"].to_numpy()[None, :], sites["lon"].to_numpy()[None, :])

    rows = []
    for run in sol["runs"]:
        r, k = run["radius_mi"], run["k"]
        cover = dist <= r
        obj, chosen = solve(cover, w, k)
        covered = cover[:, chosen].any(axis=1)
        mine = round(float(w[covered].sum() / w.sum()), 4)
        ex, gr = run["exact"], run["greedy"]
        rows.append({
            "radius_mi": r, "k": k,
            "zips_coverable_by_any_site": int(cover.any(axis=1).sum()),
            "max_possible_coverage": round(float(w[cover.any(axis=1)].sum() / w.sum()), 4),
            "recomputed_exact_coverage": mine,
            "committed_exact_coverage": ex["pred_coverage"],
            "exact_matches": abs(mine - ex["pred_coverage"]) < 5e-4,
            "committed_greedy_coverage": gr["pred_coverage"],
            "exact_minus_greedy_pp": round(100 * (ex["pred_coverage"] - gr["pred_coverage"]), 2),
            "recomputed_zips_covered": int(covered.sum()),
            "committed_zips_covered": ex["zips_covered"],
            "recomputed_observed_coverage": round(float(obs[covered].sum() / obs.sum()), 4),
            "committed_observed_coverage": ex["obs_coverage"],
            "sites_selected": len(chosen), "budget_binding": len(chosen) == k,
            "same_site_set_as_committed":
                sorted(sites.iloc[chosen]["name"]) == sorted(ex["sites"]),
        })
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "siting_check.csv", index=False)

    nearest = dist.min(axis=1)
    inst = {
        "demand_zips": int(len(df)), "candidate_sites": int(len(sites)),
        "committed_n_zips": sol["n_zips"], "committed_n_candidate_sites": sol["n_candidate_sites"],
        "burden_weight": "max(0, Part 2 out-of-fold augmented Poisson rate) x UCLA population / 10,000",
        "total_predicted_burden": round(float(w.sum()), 1),
        "total_observed_burden": round(float(obs.sum()), 1),
        "zips_with_zero_weight": int((w <= 0).sum()),
        "miles_to_nearest_candidate_site": {
            "median": round(float(np.median(nearest)), 2), "p90": round(float(np.percentile(nearest, 90)), 2),
            "max": round(float(nearest.max()), 2)},
        "budgets_k": sol["budgets_k"], "radii_miles": sol["radii_miles"],
        "all_exact_coverages_reproduced": bool(out["exact_matches"].all()),
        "exact_at_least_greedy_everywhere": bool((out["exact_minus_greedy_pp"] >= -1e-9).all()),
        "max_exact_minus_greedy_pp": float(out["exact_minus_greedy_pp"].max()),
        "runs_with_identical_site_set": int(out["same_site_set_as_committed"].sum()),
        "runs": int(len(out)),
    }
    (OUT / "siting_instance.json").write_text(json.dumps(inst, indent=2))
    pd.set_option("display.width", 250)
    print(out.to_string(index=False))
    print(json.dumps(inst, indent=2))


if __name__ == "__main__":
    main()
