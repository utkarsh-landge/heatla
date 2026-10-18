"""Every figure in the report. Output goes to reports/figures/.

Design choices: a colour-blind-safe sequential ramp (viridis/cividis) for all
choropleths, one message per figure, and no chart junk. Maps are drawn with
geopandas rather than a web map so the report is self-contained.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from .config import Config, CRS_WORK

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "savefig.bbox": "tight",
    "font.size": 9, "axes.titlesize": 11, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
    "grid.linewidth": 0.5,
})
SEQ = "cividis"          # colour-blind safe, prints legibly in greyscale
OK = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
      "red": "#D55E00", "purple": "#CC79A7", "grey": "#7a7a7a",
      "yellow": "#F0E442"}


def _save(fig, cfg: Config, name: str):
    p = cfg.paths.figures / name
    fig.savefig(p)
    plt.close(fig)
    return p


def _basemap(ax, gdf):
    ax.set_axis_off()
    ax.set_aspect("equal")
    gdf.boundary.plot(ax=ax, linewidth=0.05, color="white", alpha=0.35)


# ------------------------------------------------------------- Part A/B ----
def fig_choropleth(cfg: Config, gdf: gpd.GeoDataFrame, col: str, title: str,
                   name: str, cmap: str = SEQ, label: str | None = None):
    g = gdf.to_crs(CRS_WORK)
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    g.plot(column=col, cmap=cmap, ax=ax, legend=True, missing_kwds={
        "color": "#dddddd", "label": "no data"},
        legend_kwds={"shrink": 0.6, "label": label or col})
    _basemap(ax, g)
    ax.set_title(title)
    return _save(fig, cfg, name)


def fig_centers_and_buffers(cfg: Config, gdf: gpd.GeoDataFrame,
                            centers: gpd.GeoDataFrame | None, radius_m: int):
    g = gdf.to_crs(CRS_WORK)
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    g.plot(column="hvi", cmap=SEQ, ax=ax, legend=True,
           legend_kwds={"shrink": 0.6, "label": "HVI (0-100)"})
    if centers is not None and len(centers):
        c = centers.to_crs(CRS_WORK)
        c.buffer(radius_m).boundary.plot(ax=ax, color=OK["red"], linewidth=0.6,
                                         alpha=0.75)
        c.plot(ax=ax, color=OK["red"], markersize=7, marker="o")
    _basemap(ax, g)
    ax.set_title(f"Existing cooling centres and {radius_m/1000:.1f} km service "
                 f"radius, over heat vulnerability")
    ax.legend(handles=[
        Line2D([], [], marker="o", color=OK["red"], linestyle="",
               label=f"existing centre (n={0 if centers is None else len(centers)})"),
        Line2D([], [], color=OK["red"], label=f"{radius_m} m radius")],
        loc="lower left", frameon=False, fontsize=8)
    return _save(fig, cfg, "A1_existing_centers_buffers.png")


def fig_unserved_vulnerable(cfg: Config, gdf: gpd.GeoDataFrame,
                            centers: gpd.GeoDataFrame | None):
    g = gdf.to_crs(CRS_WORK).copy()
    g["cls"] = np.where(g["hvi_top25"] & ~g["served"], 3,
                        np.where(g["hvi_top25"], 2,
                                 np.where(g["served"], 1, 0)))
    colors = {0: "#efefef", 1: "#bcd6e8", 2: "#f3c38a", 3: OK["red"]}
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    for k, c in colors.items():
        sub = g[g["cls"] == k]
        if len(sub):
            sub.plot(ax=ax, color=c, linewidth=0)
    if centers is not None and len(centers):
        centers.to_crs(CRS_WORK).plot(ax=ax, color="black", markersize=5)
    _basemap(ax, g)
    n = int((g["cls"] == 3).sum())
    pop = g.loc[g["cls"] == 3, "pop"].sum()
    ax.set_title(f"Unserved and vulnerable: {n} top-quartile-HVI tracts "
                 f"({pop:,.0f} residents) beyond {cfg.radius_m} m of any centre")
    ax.legend(handles=[
        Line2D([], [], marker="s", color=colors[3], linestyle="", label="high HVI, unserved"),
        Line2D([], [], marker="s", color=colors[2], linestyle="", label="high HVI, served"),
        Line2D([], [], marker="s", color=colors[1], linestyle="", label="served"),
        Line2D([], [], marker="s", color=colors[0], linestyle="", label="neither"),
        Line2D([], [], marker="o", color="black", linestyle="", label="existing centre")],
        loc="lower left", frameon=False, fontsize=8)
    return _save(fig, cfg, "A2_unserved_vulnerable.png")


def fig_close_vs_far(cfg: Config, df: pd.DataFrame):
    """The core Part A picture: county-wide vs served distributions."""
    cols = [("hvi", "HVI"), ("lst_f", "Peak surface temp (F)"),
            ("pct_age65p", "Age 65+ (%)"), ("pct_under5", "Under 5 (%)"),
            ("pct_poverty", "Below poverty (%)"), ("median_income", "Median income ($)"),
            ("pct_canopy", "Tree canopy (%)"), ("pct_impervious", "Impervious (%)"),
            ("svi", "CDC SVI")]
    cols = [(c, l) for c, l in cols if c in df.columns and df[c].notna().sum() > 20]
    ncol = 3
    nrow = int(np.ceil(len(cols) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(10.5, 2.6 * nrow))
    for ax, (c, label) in zip(np.ravel(axes), cols):
        a = df[c].dropna()
        b = df.loc[df["served"], c].dropna()
        bins = np.histogram_bin_edges(a, bins=36)
        ax.hist(a, bins=bins, density=True, color=OK["grey"], alpha=0.5,
                label="all tracts")
        ax.hist(b, bins=bins, density=True, histtype="step", linewidth=1.6,
                color=OK["blue"], label=f"within {cfg.radius_m} m")
        ax.axvline(a.mean(), color=OK["grey"], linestyle="--", linewidth=1)
        ax.axvline(b.mean(), color=OK["blue"], linestyle="--", linewidth=1)
        ax.set_title(label)
        ax.set_yticks([])
    for ax in np.ravel(axes)[len(cols):]:
        ax.set_visible(False)
    np.ravel(axes)[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Part A: county-wide vs served-tract distributions "
                 "(dashed lines = means)", y=1.0)
    fig.tight_layout()
    return _save(fig, cfg, "A3_close_vs_far_distributions.png")


def fig_effect_sizes(cfg: Config):
    p = cfg.paths.tables / "partA_distribution_comparison.csv"
    if not p.exists():
        return None
    t = pd.read_csv(p).sort_values("std_mean_diff")
    fig, ax = plt.subplots(figsize=(7.4, 0.32 * len(t) + 1.4))
    colors = [OK["red"] if v > 0.1 else OK["blue"] if v < -0.1 else OK["grey"]
              for v in t["std_mean_diff"]]
    ax.barh(t["indicator"], t["std_mean_diff"], color=colors)
    for x in (-0.1, 0.1):
        ax.axvline(x, color="black", linewidth=0.6, linestyle=":")
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("standardised mean difference (served minus all tracts)")
    ax.set_title("How different are served tracts from the county?\n"
                 "|d| < 0.1 (dotted) is effectively no shift")
    return _save(fig, cfg, "A4_effect_sizes.png")


def fig_hvi_validation(cfg: Config, df: pd.DataFrame):
    pairs = [("svi", "CDC SVI"), ("heat_er_rate_per100k", "Heat ER visits / 100k"),
             ("ces_score", "CalEnviroScreen score")]
    pairs = [(c, l) for c, l in pairs if c in df.columns and df[c].notna().sum() > 20]
    if not pairs:
        return None
    fig, axes = plt.subplots(1, len(pairs), figsize=(4.0 * len(pairs), 3.6))
    axes = np.atleast_1d(axes)
    from scipy import stats as st
    for ax, (c, label) in zip(axes, pairs):
        d = df[["hvi", c]].dropna()
        ax.scatter(d["hvi"], d[c], s=5, alpha=0.3, color=OK["blue"],
                   edgecolors="none")
        rho = st.spearmanr(d["hvi"], d[c]).statistic
        # LOWESS-ish trend: bin means, which is enough to show the shape.
        q = pd.qcut(d["hvi"], 20, duplicates="drop")
        m = d.groupby(q, observed=True).mean()
        ax.plot(m["hvi"], m[c], color=OK["red"], linewidth=1.8)
        ax.set_xlabel("HVI")
        ax.set_ylabel(label)
        ax.set_title(f"{label}\nSpearman rho = {rho:.2f}")
    fig.suptitle("Part B: HVI validation against external measures", y=1.03)
    fig.tight_layout()
    return _save(fig, cfg, "B1_hvi_validation.png")


def fig_importance_shap(cfg: Config, outcome: str = "hvi"):
    p = cfg.paths.tables / f"partB_assoc_{outcome}_shap.csv"
    if not p.exists():
        p = cfg.paths.tables / f"partB_assoc_{outcome}_importance.csv"
        if not p.exists():
            return None
    t = pd.read_csv(p)
    val = "mean_abs_shap" if "mean_abs_shap" in t.columns else "perm_importance_mean"
    t = t.sort_values(val)
    fig, ax = plt.subplots(figsize=(7.2, 0.34 * len(t) + 1.4))
    colors = [OK["orange"] if r.startswith("social") else OK["grey"] for r in t["role"]]
    ax.barh(t["feature"], t[val], color=colors)
    ax.set_xlabel("mean |SHAP|" if "shap" in val else "permutation importance")
    ax.set_title(f"Part B: what is associated with {outcome}\n"
                 "orange = social variables of interest, grey = physical controls")
    ax.legend(handles=[Line2D([], [], marker="s", color=OK["orange"], linestyle="",
                              label="social (of interest)"),
                       Line2D([], [], marker="s", color=OK["grey"], linestyle="",
                              label="physical (control)")],
              loc="lower right", frameon=False, fontsize=8)
    return _save(fig, cfg, f"B2_association_importance_{outcome}.png")


def fig_pdp_ale(cfg: Config, outcome: str = "hvi"):
    pp = cfg.paths.tables / f"partB_assoc_{outcome}_pdp.csv"
    pa = cfg.paths.tables / f"partB_assoc_{outcome}_ale.csv"
    if not pp.exists():
        return None
    pdp, ale = pd.read_csv(pp), (pd.read_csv(pa) if pa.exists() else None)
    feats = list(dict.fromkeys(pdp["feature"]))
    fig, axes = plt.subplots(1, len(feats), figsize=(3.3 * len(feats), 3.1),
                             squeeze=False)
    for ax, f in zip(axes[0], feats):
        d = pdp[pdp["feature"] == f]
        ax.plot(d["x"], d["pdp"] - d["pdp"].mean(), color=OK["blue"], label="PDP")
        if ale is not None and (ale["feature"] == f).any():
            a = ale[ale["feature"] == f]
            ax.plot(a["x"], a["ale"], color=OK["orange"], linestyle="--", label="ALE")
        ax.set_title(f, fontsize=9)
        ax.set_xlabel("")
    axes[0][0].set_ylabel(f"centred effect on {outcome}")
    axes[0][0].legend(frameon=False, fontsize=8)
    fig.suptitle("Part B: shape of the association for the top social variables",
                 y=1.04)
    fig.tight_layout()
    return _save(fig, cfg, f"B3_pdp_ale_{outcome}.png")


# --------------------------------------------------------------- Part C ----
def fig_budget_curve(cfg: Config):
    p = cfg.paths.tables / "partC_budget_curve.csv"
    if not p.exists():
        return None
    t = pd.read_csv(p)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    series = [("greedy", "pop_x_hvi", OK["blue"], "-", "greedy (Pop x HVI)"),
              ("greedy", "count", OK["green"], "-", "greedy (count)"),
              ("ilp", "pop_x_hvi", OK["red"], "", "ILP (Pop x HVI)"),
              ("sort_by_hvi", "-", OK["orange"], "--", "sort by HVI (status-quo rule)"),
              ("hottest_tracts", "-", OK["purple"], ":", "hottest tracts"),
              ("random", "-", OK["grey"], "-.", "random placement")]
    for ax, ycol, ylab in (
            (axes[0], "vuln_weighted_pop_covered_pct",
             "vulnerability-weighted population covered (%)"),
            (axes[1], "top25_hvi_pop_covered_pct",
             "top-quartile-HVI population covered (%)")):
        for meth, obj, col, ls, lab in series:
            d = t[(t["method"] == meth) & ((t["objective"] == obj) | (obj == "-"))]
            d = d.sort_values("k")
            if d.empty:
                continue
            if meth == "ilp":
                ax.scatter(d["k"], d[ycol], color=col, marker="D", s=34,
                           zorder=5, label=lab)
            else:
                ax.plot(d["k"], d[ycol], color=col, linestyle=ls, marker="o",
                        markersize=3, label=lab)
        ax.set_xlabel("K (number of new cooling centres)")
        ax.set_ylabel(ylab)
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.suptitle(f"Part C: budget vs coverage at r = {cfg.radius_m} m "
                 "(slope = marginal benefit of one more centre)", y=1.02)
    fig.tight_layout()
    return _save(fig, cfg, "C1_budget_curve.png")


def fig_chosen_sites(cfg: Config, gdf: gpd.GeoDataFrame,
                     centers: gpd.GeoDataFrame | None,
                     key: str | None = None):
    p = cfg.paths.processed / "partC_solutions.json"
    if not p.exists():
        return None
    sols = json.loads(p.read_text())
    key = key or f"greedy|pop_x_hvi|{cfg.radius_m}|{cfg.k_default}"
    if key not in sols:
        key = next(iter(sols))
    sel = sols[key]
    g = gdf.to_crs(CRS_WORK)
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    g.plot(column="hvi", cmap=SEQ, ax=ax, legend=True,
           legend_kwds={"shrink": 0.6, "label": "HVI (0-100)"})
    new = gpd.GeoDataFrame(geometry=gpd.points_from_xy(sel["lon"], sel["lat"]),
                           crs="EPSG:4326").to_crs(CRS_WORK)
    if centers is not None and len(centers):
        c = centers.to_crs(CRS_WORK)
        c.plot(ax=ax, color="black", markersize=5, alpha=0.6)
    new.buffer(cfg.radius_m).boundary.plot(ax=ax, color=OK["red"], linewidth=0.9)
    new.plot(ax=ax, color=OK["red"], markersize=34, marker="*")
    _basemap(ax, g)
    meth, obj, rad, k = key.split("|")
    ax.set_title(f"Part C: {k} new sites chosen by {meth} ({obj}), r = {rad} m")
    ax.legend(handles=[
        Line2D([], [], marker="*", color=OK["red"], linestyle="", label="new site"),
        Line2D([], [], marker="o", color="black", linestyle="", label="existing centre")],
        loc="lower left", frameon=False, fontsize=8)
    return _save(fig, cfg, "C2_chosen_sites.png")


def fig_fairness(cfg: Config):
    p = cfg.paths.tables / "partC_results_grid.csv"
    if not p.exists():
        return None
    t = pd.read_csv(p)
    t = t[(t["radius_m"] == cfg.radius_m) &
          (t["k"].isin([cfg.k_default]) | (t["method"] == "existing_only"))]
    rows = [("existing_only", "-", "existing only"),
            ("random", "-", "random"),
            ("sort_by_hvi", "-", "sort by HVI"),
            ("greedy", "count", "greedy (count)"),
            ("greedy", "pop_x_hvi", "greedy (Pop x HVI)"),
            ("ilp", "pop_x_hvi", "ILP (Pop x HVI)")]
    groups = [c for c in t.columns if c.startswith("fair_")
              and c not in ("fair_max_minus_min_pp",)]
    labels = [g.replace("fair_", "").replace("_", " ") for g in groups]
    fig, ax = plt.subplots(figsize=(max(8, 0.9 * len(groups) + 3), 4.2))
    width = 0.8 / len(rows)
    xs = np.arange(len(groups))
    for i, (meth, obj, lab) in enumerate(rows):
        d = t[(t["method"] == meth) & ((t["objective"] == obj) | (obj == "-"))]
        if d.empty:
            continue
        vals = d.iloc[0][groups].astype(float).to_numpy()
        ax.bar(xs + i * width, vals, width=width, label=lab)
    ax.set_xticks(xs + 0.4 - width / 2)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("% of group's population within service radius")
    ax.set_title(f"Part C fairness: coverage by demographic subgroup "
                 f"(K = {cfg.k_default}, r = {cfg.radius_m} m)")
    ax.legend(frameon=False, fontsize=8, ncol=3)
    return _save(fig, cfg, "C3_fairness_by_subgroup.png")


def fig_radius_sensitivity(cfg: Config):
    p = cfg.paths.tables / "partC_results_grid.csv"
    if not p.exists():
        return None
    t = pd.read_csv(p)
    t = t[(t["method"] == "greedy") & (t["objective"] == "pop_x_hvi")]
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    for r, c in zip(sorted(t["radius_m"].unique()),
                    [OK["blue"], OK["orange"], OK["green"], OK["purple"]]):
        d = t[t["radius_m"] == r].sort_values("k")
        lab = {1609: "1 mile", 2000: "2 km", 3219: "2 miles"}.get(r, f"{r} m")
        ax.plot(d["k"], d["vuln_weighted_pop_covered_pct"], marker="o",
                markersize=3, color=c, label=lab)
    ax.set_xlabel("K (new centres)")
    ax.set_ylabel("vulnerability-weighted population covered (%)")
    ax.set_title("Part C sensitivity: service radius")
    ax.legend(frameon=False, title="radius")
    return _save(fig, cfg, "C4_radius_sensitivity.png")


def run(cfg: Config, gdf: gpd.GeoDataFrame,
        centers: gpd.GeoDataFrame | None) -> list[str]:
    made = []
    made += [fig_choropleth(cfg, gdf, "hvi", "Heat Vulnerability Index by census tract",
                            "B0_hvi_map.png", label="HVI (0-100)")]
    for col, title, name, lab in (
            ("lst_f", "Peak summer land-surface temperature", "A0_lst_map.png", "degrees F"),
            ("pct_canopy", "Tree canopy cover", "A0_canopy_map.png", "% canopy"),
            ("pct_impervious", "Impervious surface", "A0_impervious_map.png", "% impervious"),
            ("pct_poverty", "Population below the poverty line", "A0_poverty_map.png", "%"),
            ("pct_age65p", "Residents aged 65+", "A0_age65_map.png", "%")):
        if col in gdf.columns and gdf[col].notna().any():
            made.append(fig_choropleth(cfg, gdf, col, title, name, label=lab))
    made += [fig_centers_and_buffers(cfg, gdf, centers, cfg.radius_m),
             fig_unserved_vulnerable(cfg, gdf, centers),
             fig_close_vs_far(cfg, gdf), fig_effect_sizes(cfg),
             fig_hvi_validation(cfg, gdf),
             fig_importance_shap(cfg, "hvi"), fig_pdp_ale(cfg, "hvi"),
             fig_importance_shap(cfg, "heat_er_rate_per100k"),
             fig_budget_curve(cfg), fig_chosen_sites(cfg, gdf, centers),
             fig_fairness(cfg), fig_radius_sensitivity(cfg)]
    made = [str(m) for m in made if m]
    print(f"  figures: {len(made)} written to {cfg.paths.figures}")
    return made
