"""Member 1 - report figures for the statewide module.

Reads only the row-level outputs of scripts/run_member1_statewide.py, so figures can
be regenerated without refitting any model. Writes PNGs to results/member1/figures/.

Conventions used in every figure:
  label       = UCLA Heat Maps excess ER visits per 10,000 (2008-2018)
  prediction  = model output on the same scale
  error       = prediction - label; red = overprediction, blue = underprediction

Run:  .venv/bin/python scripts/make_member1_figures.py
"""
from __future__ import annotations

import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402
from sklearn.metrics import r2_score  # noqa: E402

OUT = pathlib.Path("results/member1")
FIG = OUT / "figures"
LEVELS = (1, 2, 3, 4)
UNIT = "excess ER visits per 10,000"
MODEL_NAME = {"poisson": "Poisson", "random_forest": "Random forest",
              "gradient_boosting": "Gradient boosting"}
CONFIG_NAME = {"all_level": "All-level model", "level_specific": "Level-specific model"}
EVAL_NAME = {"la_holdout": "LA holdout (train: rest of California, test: LA County)",
             "spatial_cv": "Statewide spatial cross-validation (10 folds)"}

# palette (see the dataviz reference palette): ink, surface, series, ramps
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
SURFACE, GRID, AXIS = "#fcfcfb", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE = "#2a78d6", "#eb6834"
FOLD_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
               "#008300", "#6250d6", "#e34948", "#52514e", "#a8a69f"]
SEQ = LinearSegmentedColormap.from_list(
    "seq_blue", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
DIV = LinearSegmentedColormap.from_list(
    "div_blue_red", ["#104281", "#2a78d6", "#9ec5f4", "#f0efec", "#f4b0af", "#e34948", "#9c1f1e"])

plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 9, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlesize": 10,
    "axes.titleweight": "bold", "axes.facecolor": SURFACE, "figure.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelcolor": INK2, "ytick.labelcolor": INK2, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False,
})


def save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / name, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("  wrote", FIG / name)


# ---------------------------------------------------------------- fold map
def fold_map() -> None:
    z = pd.read_csv(OUT / "fold_assignment_statewide.csv", dtype={"zip": str})
    fc = pd.read_csv(OUT / "fold_counts_statewide.csv")
    fig, ax = plt.subplots(figsize=(7.2, 8.2))
    for f in sorted(z["fold"].unique()):
        g = z[z["fold"] == f]
        ax.scatter(g["lon"], g["lat"], s=9, color=FOLD_COLORS[f], linewidths=0,
                   label=f"Fold {f}: {len(g)} ZIPs")
    la = z[z["county"] == "Los Angeles"]
    ax.scatter(la["lon"], la["lat"], s=16, facecolors="none", edgecolors=INK,
               linewidths=0.35, label=f"Los Angeles County ({len(la)} ZIPs)")
    for r in fc.itertuples():
        ax.annotate(f"{r.fold}", (r.centroid_lon, r.centroid_lat), ha="center", va="center",
                    fontsize=11, fontweight="bold", color=INK,
                    bbox=dict(boxstyle="circle,pad=0.25", fc=SURFACE, ec=INK, lw=0.8))
    ax.set_aspect(1 / np.cos(np.radians(37.0)))
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True)
    ax.text(0, 1.065, f"Statewide spatial folds: {len(z):,} ZIPs in {z['fold'].nunique()} "
            "geographic groups", transform=ax.transAxes, va="bottom", fontsize=11,
            fontweight="bold", color=INK)
    ax.text(0, 1.01, "One point per ZIP (ZCTA centroid). k-means on latitude/longitude; "
            "each fold is held out once.\nAll four heat-level rows of a ZIP are in the same fold.",
            transform=ax.transAxes, va="bottom", fontsize=8, color=INK2)
    ax.legend(loc="upper right", fontsize=8, markerscale=1.8, handletextpad=0.3)
    save(fig, "fold_map_statewide.png")


# ---------------------------------------------------------------- scatter
def scatter_by_level(kind: str, model: str) -> None:
    p = pd.read_csv(OUT / f"predictions_{kind}.csv", dtype={"zip": str})
    fig, axes = plt.subplots(2, 4, figsize=(13, 6.6))
    for i, config in enumerate(("all_level", "level_specific")):
        for j, lv in enumerate(LEVELS):
            ax = axes[i, j]
            g = p[p["chs_level"] == lv]
            y, yhat = g["ucla_label"].to_numpy(), g[f"pred_{model}_{config}"].to_numpy()
            hi = float(max(y.max(), yhat.max()) * 1.05)
            ax.plot([0, hi], [0, hi], color=MUTED, lw=1, ls="--", zorder=1)
            ax.scatter(y, yhat, s=10, color=BLUE if i == 0 else ORANGE, alpha=0.55,
                       linewidths=0, zorder=2)
            over = float((yhat > y).mean())
            ax.text(0.04, 0.96,
                    f"n = {len(g):,}\nR² = {r2_score(y, yhat):.2f}\n"
                    f"ρ = {spearmanr(y, yhat).statistic:.2f}\n"
                    f"overpredicted: {over:.0%}",
                    transform=ax.transAxes, va="top", fontsize=8, color=INK)
            ax.set_xlim(0, hi); ax.set_ylim(0, hi); ax.set_aspect("equal"); ax.grid(True)
            ax.set_title(f"Heat level {lv}" if i == 0 else "", loc="left")
            if j == 0:
                ax.set_ylabel(f"{CONFIG_NAME[config]}\nprediction")
            if i == 1:
                ax.set_xlabel("UCLA label")
    fig.suptitle(f"UCLA label vs prediction by heat level — {MODEL_NAME[model]}, "
                 f"{EVAL_NAME[kind]}", x=0.01, ha="left", fontsize=11, fontweight="bold")
    fig.text(0.01, 0.935, f"Both axes: {UNIT}. Dashed line = perfect prediction; points above "
             "it are overpredictions. One point per ZIP.", fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    save(fig, f"scatter_{kind}_{model}.png")


# ---------------------------------------------------------------- LA choropleths
def la_polygons() -> dict[str, list[np.ndarray]]:
    gj = json.loads(pathlib.Path("site/data/zips.geojson").read_text())
    out: dict[str, list[np.ndarray]] = {}
    for f in gj["features"]:
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        out[str(f["properties"]["zip"]).zfill(5)] = [np.asarray(p[0]) for p in polys]
    return out


def draw_la(ax, polys, values: dict[str, float], cmap, norm):
    patches, vals = [], []
    for z, rings in polys.items():
        if z not in values or not np.isfinite(values[z]):
            continue
        for ring in rings:
            patches.append(Polygon(ring, closed=True))
            vals.append(values[z])
    pc = PatchCollection(patches, cmap=cmap, norm=norm, edgecolor=SURFACE, linewidth=0.25)
    pc.set_array(np.asarray(vals))
    ax.add_collection(pc)
    ax.set_xlim(-118.96, -117.63); ax.set_ylim(33.68, 34.84)  # mainland LA County
    ax.set_aspect(1 / np.cos(np.radians(34.2)))
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    return pc


def la_label_vs_prediction(model: str, level: int) -> None:
    p = pd.read_csv(OUT / "predictions_la_holdout.csv", dtype={"zip": str})
    g = p[p["chs_level"] == level].set_index("zip")
    polys = la_polygons()
    cols = [("ucla_label", "UCLA label"),
            (f"pred_{model}_all_level", f"{MODEL_NAME[model]}, all-level model"),
            (f"pred_{model}_level_specific", f"{MODEL_NAME[model]}, level-specific model")]
    vmax = float(np.nanpercentile(g[[c for c, _ in cols]].to_numpy(), 99.5))
    norm = plt.Normalize(0, vmax)
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.2))
    for ax, (c, title) in zip(axes, cols):
        pc = draw_la(ax, polys, g[c].to_dict(), SEQ, norm)
        ax.set_title(title, loc="left")
    cb = fig.colorbar(pc, ax=axes, orientation="horizontal", fraction=0.045, pad=0.03,
                      aspect=50, extend="max")
    cb.set_label(f"{UNIT} (same colour scale in all three maps)")
    cb.outline.set_visible(False)
    fig.suptitle(f"UCLA label and predictions side by side — heat level {level}, LA holdout "
                 f"({g.shape[0]} LA ZIPs; models trained on the rest of California)",
                 x=0.01, ha="left", fontsize=11, fontweight="bold")
    save(fig, f"map_la_holdout_L{level}_{model}_label_vs_prediction.png")


def la_error_map(model: str, level: int) -> None:
    p = pd.read_csv(OUT / "predictions_la_holdout.csv", dtype={"zip": str})
    g = p[p["chs_level"] == level].set_index("zip")
    polys = la_polygons()
    cols = [(f"error_{model}_{c}", CONFIG_NAME[c]) for c in ("all_level", "level_specific")]
    lim = float(np.nanpercentile(np.abs(g[[c for c, _ in cols]].to_numpy()), 98))
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.6))
    for ax, (c, title) in zip(axes, cols):
        e = g[c]
        pc = draw_la(ax, polys, e.to_dict(), DIV, norm)
        ax.set_title(f"{title}\nmean error {e.mean():+.2f}, mean |error| {e.abs().mean():.2f}, "
                     f"overpredicted in {(e > 0).mean():.0%} of ZIPs", loc="left", fontsize=9)
    cb = fig.colorbar(pc, ax=axes, orientation="horizontal", fraction=0.045, pad=0.03,
                      aspect=50, extend="both")
    cb.set_label(f"Error = prediction − UCLA label ({UNIT}).   "
                 "Blue = underprediction   |   grey = no error   |   red = overprediction")
    cb.outline.set_visible(False)
    fig.suptitle(f"Prediction error by ZIP — {MODEL_NAME[model]}, heat level {level}, LA holdout "
                 f"({g.shape[0]} LA ZIPs)", x=0.01, ha="left", fontsize=11, fontweight="bold")
    save(fig, f"map_la_holdout_L{level}_{model}_error.png")


# ---------------------------------------------------------------- statewide error map
def statewide_error_map(model: str, level: int) -> None:
    p = pd.read_csv(OUT / "predictions_spatial_cv.csv", dtype={"zip": str})
    g = p[p["chs_level"] == level]
    e = g[f"error_{model}_all_level"]
    lim = float(np.nanpercentile(np.abs(e), 98))
    fig, ax = plt.subplots(figsize=(7.2, 8.2))
    order = np.argsort(np.abs(e.to_numpy()))  # largest errors drawn last
    sc = ax.scatter(g["lon"].to_numpy()[order], g["lat"].to_numpy()[order],
                    c=e.to_numpy()[order], cmap=DIV,
                    norm=TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim), s=11, linewidths=0)
    ax.set_aspect(1 / np.cos(np.radians(37.0)))
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude"); ax.grid(True)
    cb = fig.colorbar(sc, ax=ax, orientation="horizontal", fraction=0.04, pad=0.08,
                      aspect=45, extend="both")
    cb.set_label(f"Error = prediction − UCLA label ({UNIT}).\n"
                 "Blue = underprediction   |   grey = no error   |   red = overprediction")
    cb.outline.set_visible(False)
    ax.set_title(f"Prediction error by ZIP — {MODEL_NAME[model]} all-level model,\n"
                 f"heat level {level}, statewide spatial cross-validation ({len(g):,} ZIPs)",
                 loc="left")
    save(fig, f"map_spatial_cv_L{level}_{model}_error.png")


# ---------------------------------------------------------------- metric comparison
def metric_comparison(kind: str, model: str) -> None:
    m = pd.read_csv(OUT / "metrics_by_level.csv")
    m = m[(m.evaluation == kind) & (m.model == model) & m.scope.str.startswith("level")]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharex=True)
    panels = [("r2", "R²"), ("spearman", "Spearman ρ"), ("top10_recall", "Top-10% recall")]
    x = np.arange(len(LEVELS))
    for ax, (col, title) in zip(axes, panels):
        vals = {}
        for config, color in (("all_level", BLUE), ("level_specific", ORANGE)):
            v = m[m.config == config].sort_values("scope")[col].to_numpy(float)
            vals[config] = v
            ax.plot(x, v, color=color, lw=2, marker="o", ms=6, label=CONFIG_NAME[config])
        # value labels: at each level the higher value is labelled above, the lower below
        for config, other in (("all_level", "level_specific"), ("level_specific", "all_level")):
            for xi, vi, vo in zip(x, vals[config], vals[other]):
                above = vi > vo or (vi == vo and config == "all_level")
                ax.annotate(f"{vi:.2f}", (xi, vi), textcoords="offset points",
                            xytext=(0, 7 if above else -13), ha="center", fontsize=7.5,
                            color=INK2)
        ax.axhline(0, color=AXIS, lw=0.8)
        ax.set_xticks(x, [f"Level {lv}" for lv in LEVELS]); ax.grid(True, axis="y")
        ax.set_xlim(-0.35, len(LEVELS) - 0.65)
        ax.set_title(title, loc="left")
        lo, hi = ax.get_ylim(); pad = 0.14 * (hi - lo)
        ax.set_ylim(lo - pad, hi + pad)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", bbox_to_anchor=(0.995, 0.93), ncol=2,
               fontsize=8.5)
    fig.suptitle(f"All-level vs level-specific {MODEL_NAME[model]} model by heat level — "
                 f"{EVAL_NAME[kind]}", x=0.01, ha="left", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    save(fig, f"metrics_by_level_{kind}_{model}.png")


def main() -> None:
    fold_map()
    for kind in ("la_holdout", "spatial_cv"):
        for model in MODEL_NAME:
            scatter_by_level(kind, model)
            metric_comparison(kind, model)
    for model in MODEL_NAME:
        la_label_vs_prediction(model, 4)
        la_error_map(model, 4)
        statewide_error_map(model, 4)


if __name__ == "__main__":
    main()
