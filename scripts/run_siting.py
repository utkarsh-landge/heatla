"""Step 5 runner - cooling-center selection, greedy vs exact, coverage & equity."""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from heatla import siting as S  # noqa: E402

RES = pathlib.Path("results")


def main() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    res = S.run_all()
    (RES / "coolingcenter_solutions.json").write_text(json.dumps(res, indent=2))

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


if __name__ == "__main__":
    main()
