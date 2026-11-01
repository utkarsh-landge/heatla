"""One command rebuilds everything: `python -m heatla.run_all`.

Order matters: the master table feeds the HVI, the HVI feeds Parts A, B and C,
and the dashboard export reads all of them.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

import numpy as np

from .config import Config
from . import build_table, partA_statusquo, partB_hvi, partB_association
from . import partC_optimize, figures, export_dashboard


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the whole HEATLA pipeline.")
    ap.add_argument("--data-mode", choices=["mock", "real"], default=None)
    ap.add_argument("--lst-source", choices=["landsat", "ecostress"], default=None)
    ap.add_argument("--radius", type=int, default=None)
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--quick", action="store_true",
                    help="small K grid and fewer random draws, for CI")
    ap.add_argument("--skip", nargs="*", default=[],
                    choices=["A", "B", "C", "figures", "dashboard"])
    args = ap.parse_args(argv)

    cfg = Config.load()
    if args.data_mode:
        cfg.data_mode = args.data_mode
    if args.lst_source:
        cfg.lst_source = args.lst_source
    if args.radius:
        cfg.radius_m = args.radius
    if args.k:
        cfg.k_default = args.k
    if args.quick:
        cfg.k_grid = (5, 10, 20)
        cfg.k_report = (10, 20)
        cfg.radius_grid_m = (cfg.radius_m,)
        cfg.n_random_draws = 25
        cfg.ilp_time_limit_s = 60

    np.random.seed(cfg.seed)
    t0 = time.time()
    print(f"HEATLA pipeline | mode={cfg.data_mode} lst={cfg.lst_source} "
          f"r={cfg.radius_m}m K={cfg.k_default}")

    print("[1/6] master tract table")
    df = build_table.build(cfg)
    centers = build_table.load_centers_existing(cfg)

    print("[2/6] Part B: heat vulnerability index")
    df, hvi_val = partB_hvi.run(cfg, df)

    summaryA = {}
    if "A" not in args.skip:
        print("[3/6] Part A: status-quo coverage")
        df, summaryA = partA_statusquo.run(cfg, df, centers)
    else:
        df = partA_statusquo.attach_distance(df, centers, cfg)

    assoc = {}
    if "B" not in args.skip:
        print("[4/6] Part B: association study")
        assoc = partB_association.run(cfg, df)

    partC = {}
    if "C" not in args.skip:
        print("[5/6] Part C: optimisation")
        partC = partC_optimize.run_grid(cfg, df, centers)

    if "figures" not in args.skip:
        print("[6/6] figures")
        figures.run(cfg, df, centers)

    if "dashboard" not in args.skip:
        export_dashboard.run(cfg, df, centers)

    manifest = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "config": cfg.to_dict(),
        "elapsed_seconds": round(time.time() - t0, 1),
        "n_tracts": int(len(df)),
        "n_existing_centers": 0 if centers is None else int(len(centers)),
        "hvi_validation": hvi_val,
        "partA_summary": summaryA,
        "partB_association_outcomes": list(assoc),
    }
    (cfg.paths.reports / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=float))
    print(f"done in {manifest['elapsed_seconds']}s -> reports/ and dashboard/public/data/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
