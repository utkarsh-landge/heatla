"""Step 5 runner - cooling-center selection, greedy vs exact, coverage & equity.

Also writes the decision check: plans chosen with predictions, the UCLA label,
population only, the level-4-only label and random site sets, all scored on the
UCLA-label burden, for the 153 existing centers and for centers plus libraries.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from heatla import siting as S  # noqa: E402

RES = pathlib.Path("results")
SITE = pathlib.Path("site/data")


def main() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    res = S.run_all()
    (RES / "coolingcenter_solutions.json").write_text(json.dumps(res, indent=2))
    (SITE / "solutions.json").write_text(json.dumps(res, indent=2))

    print("\n============== STEP 5 COOLING CENTERS ==============")
    print(f"candidate sites: {res['n_candidate_sites']} (real LA County regional)")
    print(f"demand ZIPs: {res['n_zips']}  | benefit = OOF predicted excess ER number "
          f"({res['primary_model']})")
    print(f"{'R(mi)':>5} {'k':>3} {'method':>7} {'pred_cov':>8} {'obs_cov':>7} {'worst_inc_q':>11}")
    for run in res["runs"]:
        for method in ("greedy", "exact"):
            m = run[method]
            print(f"{run['radius_mi']:>5} {run['k']:>3} {method:>7} "
                  f"{m['pred_coverage']:>8.2f} {m['obs_coverage']:>7.2f} "
                  f"{m['equity_income_quartile']['worst_quartile_coverage']:>11.2f}")
    # gap greedy vs exact
    gaps = [run["exact"]["pred_coverage"] - run["greedy"]["pred_coverage"] for run in res["runs"]]
    print(f"\nexact - greedy predicted-coverage gap: max {max(gaps):.3f}  mean {sum(gaps)/len(gaps):.3f}")
    print("===================================================\n")

    check = pd.concat([S.decision_check("centers"), S.decision_check("centers_plus_libraries")],
                      ignore_index=True)
    check.to_csv(RES / "siting_decision_check.csv", index=False)
    (RES / "siting_decision_check.json").write_text(json.dumps({
        "scored_on": "share of UCLA-label excess ER number (all heat levels) within reach",
        "plans": {"prediction": "exact plan, weights = Part 2 OOF augmented Poisson predictions",
                  "label": "exact plan, weights = UCLA label (perfect information)",
                  "population": "exact plan, weights = population only",
                  "label_level4": "exact plan, weights = level-4-only label (extreme days only)",
                  "random": f"{S.N_RANDOM} random k-sets, seed {S.RANDOM_SEED}; mean and 95th percentile"},
        "ceiling": "share reachable if every candidate site were open",
        "rows": check.to_dict(orient="records"),
    }, indent=2))
    pd.set_option("display.width", 250)
    print(check.to_string(index=False))


if __name__ == "__main__":
    main()
