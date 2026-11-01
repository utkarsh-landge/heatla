"""Steps 3-4 runner: build groups, run leave-one-group-out models, save results.

Outputs:
  data/processed/model_table_grouped.csv  - model rows + assigned spatial group
  results/metrics.json                    - all metrics (overall, per-group, baselines, importances)
  results/metrics_no90095.json            - same, with ZIP 90095 removed (robustness)
  results/predictions_oof.csv             - out-of-fold prediction per ZIP per model
  results/figures/*.png                   - diagnostic figures
"""

from __future__ import annotations

import os

# Deterministic BLAS reductions -> metrics.json reproduces exactly (set before numpy).
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")  # benign GLM/BLAS runtime + constant-input warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from heatla import model as M  # noqa: E402

RES = pathlib.Path("results")
FIG = RES / "figures"


def figures(oof, results) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    # 1) observed vs predicted per model
    names = [c[5:] for c in oof.columns if c.startswith("pred_")]
    fig, axes = plt.subplots(1, len(names), figsize=(5 * len(names), 4.6))
    if len(names) == 1:
        axes = [axes]
    for ax, nm in zip(axes, names):
        ax.scatter(oof["y_true"], oof[f"pred_{nm}"], s=16, alpha=0.6)
        lim = [0, max(oof["y_true"].max(), oof[f"pred_{nm}"].max()) * 1.05]
        ax.plot(lim, lim, "k--", lw=1)
        r2 = results["models"][nm]["overall"]["r2"]
        sp = results["models"][nm]["overall"]["spearman"]
        ax.set_title(f"{nm}\nR2={r2:.2f}  rho={sp:.2f}")
        ax.set_xlabel("observed excess ER rate /10k")
        ax.set_ylabel("OOF predicted")
    fig.tight_layout()
    fig.savefig(FIG / "observed_vs_predicted.png", dpi=130)
    plt.close(fig)

    # 2) permutation importance (RF)
    imp = results.get("permutation_importance", {}).get("random_forest", {})
    if imp:
        fig, ax = plt.subplots(figsize=(7, 5))
        ks = list(imp.keys())[::-1]
        ax.barh(ks, [imp[k] for k in ks])
        ax.set_title("Permutation importance (Random Forest, held-out)")
        ax.set_xlabel("mean increase in error")
        fig.tight_layout()
        fig.savefig(FIG / "permutation_importance_rf.png", dpi=130)
        plt.close(fig)

    # 3) group map
    fig, ax = plt.subplots(figsize=(6, 6))
    sc = ax.scatter(oof_lon, oof_lat, c=oof["group"], cmap="tab10", s=18)
    ax.set_title("Spatial groups (leave-one-group-out folds)")
    ax.set_xlabel("lon"); ax.set_ylabel("lat")
    fig.colorbar(sc, ax=ax, label="group")
    fig.tight_layout()
    fig.savefig(FIG / "spatial_groups.png", dpi=130)
    plt.close(fig)


def clean(obj):
    """Recursively replace non-finite floats with None so output is valid JSON."""
    import math
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


def run(df, tag) -> dict:
    groups = M.assign_groups(df)
    oof, results = M.run_logo(df, groups)
    results["permutation_importance"] = M.permutation_importances(df, groups)
    results["target"] = M.TARGET
    results["features"] = M.FEATURES
    results["n_rows"] = int(len(df))
    results["seed"] = M.SEED
    if tag == "main":
        global oof_lat, oof_lon
        oof_lat = df["lat"].to_numpy()
        oof_lon = df["lon"].to_numpy()
        df.assign(group=groups.values).to_csv(
            "data/processed/model_table_grouped.csv", index=False)
        oof.to_csv(RES / "predictions_oof.csv", index=False)
        figures(oof, results)
    return results


def summary(results) -> None:
    print("\n================ STEP 3-4 MODEL SUMMARY ================")
    print(f"rows={results['n_rows']} groups={results['n_groups']} target={results['target']}")
    print(f"{'model':18s} {'R2':>7s} {'R2 CI':>16s} {'rho':>6s} {'top10':>6s} {'top20':>6s}")
    for nm, r in results["models"].items():
        o = r["overall"]
        ci = o["r2_ci"]
        print(f"{nm:18s} {o['r2']:7.3f} [{ci[0]:.2f},{ci[1]:.2f}]"
              f"   {o['spearman']:6.3f} {o['top10_recall']:6.2f} {o['top20_recall']:6.2f}")
    print("-- baselines --")
    for nm, b in results["baselines"].items():
        print(f"{nm:18s} rho={b.get('spearman')}  top10={b.get('top10_recall')}")
    print("-- RF permutation importance (top 5) --")
    for k, v in list(results["permutation_importance"]["random_forest"].items())[:5]:
        print(f"   {k:26s} {v:.3f}")
    print("=======================================================\n")


def main() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    df = M.load_table()
    main_res = run(df, "main")
    (RES / "metrics.json").write_text(json.dumps(clean(main_res), indent=2))
    summary(main_res)

    df2 = df[df["is_ucla_campus_90095"].astype(str).isin(["0", "0.0"])].reset_index(drop=True)
    res2 = run(df2, "no90095")
    (RES / "metrics_no90095.json").write_text(json.dumps(clean(res2), indent=2))
    print(f"[robustness] without 90095: rows={res2['n_rows']}  "
          f"RF R2={res2['models']['random_forest']['overall']['r2']:.3f}")


if __name__ == "__main__":
    main()
