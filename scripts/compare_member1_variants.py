"""Member 1 - compare the three input variants of the statewide experiments.

Variants (each produced by scripts/run_member1_statewide.py):
  ces40_original  results/member1/              CES 4.0 as first built (-999 averaged in)
  ces40_fixed     results/member1/ces40_fixed/  CES 4.0, -999 treated as missing
  ces30           results/member1/ces30/        CES 3.0 (2009-2015 data), -999/blank as missing

Two comparisons are written to results/member1/comparison/:
  metrics_all_rows.csv        each variant on its full test set (as reported per variant)
  metrics_common_complete.csv each variant re-scored on the SAME ZIPs: those with all ten
                              CalEnviroScreen inputs and the percentile present in both the
                              corrected 4.0 table and the 3.0 table. This separates the
                              effect of the inputs from the effect of who is in the sample.
Models are not refitted here; only row-level predictions are re-scored.

Run:  .venv/bin/python scripts/compare_member1_variants.py
"""
from __future__ import annotations

import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heatla import model as M  # noqa: E402

BASE = pathlib.Path("results/member1")
OUT = BASE / "comparison"
VARIANTS = {"ces40_original": (BASE, "ces4_percentile", "CES 4.0, original (uncorrected)"),
            "ces40_fixed": (BASE / "ces40_fixed", "ces4_percentile", "CES 4.0, corrected"),
            "ces30": (BASE / "ces30", "ces3_percentile", "CES 3.0")}
MODELS = ("poisson", "random_forest", "gradient_boosting")
CONFIGS = ("all_level", "level_specific")
LEVELS = (1, 2, 3, 4)
FEATS = ["pm25", "ozone", "asthma_ed_per10k", "cardiovascular_ed_per10k", "poverty_pct",
         "elderly65_pct", "edu_lt_hs_pct", "ling_isol_pct", "unemployment_pct",
         "housing_burden_pct"]
INK2, SURFACE, GRID, AXIS = "#52514e", "#fcfcfb", "#e1e0d9", "#c3c2b7"
COLORS = {"ces40_original": "#898781", "ces40_fixed": "#2a78d6", "ces30": "#eb6834"}


def common_complete_zips() -> set[str]:
    def ok(path, pct):
        d = pd.read_csv(path, dtype={"zip": str}).drop_duplicates("zip")
        d["zip"] = d["zip"].str.zfill(5)
        return set(d.loc[d[FEATS + [pct]].notna().all(axis=1), "zip"])
    return (ok("data/processed/model_table_ca_ces40_fixed.csv", "ces4_percentile")
            & ok("data/processed/model_table_ca_ces30.csv", "ces3_percentile"))


def score(pred: pd.DataFrame, pct: str, evaluation: str, variant: str) -> list[dict]:
    recs = []
    y_all, lvl = pred["ucla_label"].to_numpy(float), pred["chs_level"].to_numpy()
    scopes = [("pooled (levels 1-4)", np.ones(len(pred), bool))]
    scopes += [(f"level {lv}", lvl == lv) for lv in LEVELS]
    for scope, m in scopes:
        y = y_all[m]
        for config in CONFIGS:
            for model in MODELS:
                p = pred[f"pred_{model}_{config}"].to_numpy(float)[m]
                recs.append({"variant": variant, "evaluation": evaluation, "predictor": model,
                             "config": config, "scope": scope, "unique_zips":
                             int(pred.loc[m, "zip"].nunique()), **M.metric_block(y, p)})
        ces = pred[pct].to_numpy(float)[m]
        okc = ~np.isnan(ces)
        if okc.sum() > 3:
            from scipy.stats import spearmanr
            recs.append({"variant": variant, "evaluation": evaluation,
                         "predictor": "ces_percentile", "config": "index", "scope": scope,
                         "unique_zips": int(pred.loc[m, "zip"][okc].nunique()),
                         "n": int(okc.sum()), "r2": np.nan,
                         "spearman": float(spearmanr(y[okc], ces[okc]).statistic),
                         "top10_recall": M.top_k_recall(y[okc], ces[okc], 0.10),
                         "top20_recall": M.top_k_recall(y[okc], ces[okc], 0.20)})
    return recs


def figure(df: pd.DataFrame, evaluation: str, model: str, title: str, name: str) -> None:
    plt.rcParams.update({"font.size": 9, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE,
                         "savefig.facecolor": SURFACE, "axes.edgecolor": AXIS,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "grid.color": GRID, "grid.linewidth": 0.6, "legend.frameon": False,
                         "axes.labelcolor": INK2, "xtick.labelcolor": INK2,
                         "ytick.labelcolor": INK2, "xtick.color": AXIS, "ytick.color": AXIS})
    d = df[(df.evaluation == evaluation) & (df.predictor == model) & (df.config == "all_level")
           & df.scope.str.startswith("level")]
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.9))
    x = np.arange(len(LEVELS)); w = 0.26
    for ax, (col, lab) in zip(axes, (("r2", "R²"), ("spearman", "Spearman ρ"),
                                     ("top10_recall", "Top-10% recall"))):
        for k, (v, (_, _, vlabel)) in enumerate(VARIANTS.items()):
            vals = d[d.variant == v].sort_values("scope")[col].to_numpy(float)
            bars = ax.bar(x + (k - 1) * w, vals, w - 0.03, color=COLORS[v], label=vlabel)
            for b, val in zip(bars, vals):
                ax.annotate(f"{val:.2f}", (b.get_x() + b.get_width() / 2, val),
                            xytext=(0, 3 if val >= 0 else -9), textcoords="offset points",
                            ha="center", fontsize=6.5, color=INK2)
        ax.axhline(0, color=AXIS, lw=0.8)
        ax.set_xticks(x, [f"Level {lv}" for lv in LEVELS]); ax.grid(True, axis="y")
        ax.set_axisbelow(True); ax.set_title(lab, loc="left", fontweight="bold", fontsize=10)
        lo, hi = ax.get_ylim(); pad = 0.1 * (hi - lo); ax.set_ylim(lo - pad, hi + pad)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper right", bbox_to_anchor=(0.995, 0.93), ncol=3, fontsize=8.5)
    fig.suptitle(title, x=0.01, ha="left", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight"); plt.close(fig)
    print("  wrote", OUT / name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    common = common_complete_zips()
    all_rows, common_rows, counts = [], [], []
    for variant, (folder, pct, _) in VARIANTS.items():
        for evaluation in ("la_holdout", "spatial_cv"):
            pred = pd.read_csv(folder / f"predictions_{evaluation}.csv", dtype={"zip": str})
            pred["zip"] = pred["zip"].str.zfill(5)
            all_rows += score(pred, pct, evaluation, variant)
            sub = pred[pred["zip"].isin(common)]
            common_rows += score(sub, pct, evaluation, variant)
            counts.append({"variant": variant, "evaluation": evaluation,
                           "test_zips": int(pred["zip"].nunique()), "test_rows": int(len(pred)),
                           "common_complete_zips": int(sub["zip"].nunique()),
                           "common_complete_rows": int(len(sub))})
    a, c = pd.DataFrame(all_rows), pd.DataFrame(common_rows)
    a.to_csv(OUT / "metrics_all_rows.csv", index=False)
    c.to_csv(OUT / "metrics_common_complete.csv", index=False)
    pd.DataFrame(counts).to_csv(OUT / "sample_counts_by_variant.csv", index=False)

    figure(a, "la_holdout", "poisson",
           "Effect of the input data on the LA holdout — Poisson all-level model, all 287 LA ZIPs",
           "variants_la_holdout_poisson.png")
    figure(c, "la_holdout", "poisson",
           "Effect of the input data on the LA holdout — Poisson all-level model, "
           "same LA ZIPs with complete inputs", "variants_la_holdout_poisson_common.png")
    figure(a, "spatial_cv", "gradient_boosting",
           "Effect of the input data on statewide spatial cross-validation — gradient boosting "
           "all-level model", "variants_spatial_cv_gradient_boosting.png")

    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
    print(pd.DataFrame(counts).to_string(index=False))
    show = a[(a.config.isin(["all_level", "index"])) & a.scope.isin(["level 4", "pooled (levels 1-4)"])]
    print(show.pivot_table(index=["evaluation", "scope", "predictor"], columns="variant",
                           values=["r2", "spearman", "top10_recall"]).round(3).to_string())


if __name__ == "__main__":
    main()
