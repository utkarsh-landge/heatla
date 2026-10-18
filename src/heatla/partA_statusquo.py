"""Part A: who do the cooling centres we already have actually serve?

The method is a close-vs-far distribution comparison. For every indicator we
hold two distributions side by side: the whole county, and only the tracts
within the service radius of an existing centre. Three readings are possible:

  * the two distributions are nearly identical -> siting is effectively
    uncorrelated with need (centres went where buildings already were);
  * the served distribution is shifted towards older, poorer, hotter ->
    siting is corrective;
  * it is shifted towards wealthier and greener -> an equity problem.

The shift is quantified (standardised mean difference, KS statistic, decile
comparison) rather than eyeballed off a histogram, and population-weighted as
well as tract-weighted, because tracts are equal-ish in people but very
unequal in area.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import geopandas as gpd

from .config import Config
from .spatial import centroids_xy, points_xy, nearest_distance_m
from .stats_utils import standardized_mean_difference, ks_test, quantiles

INDICATORS = [
    ("hvi", "Heat Vulnerability Index"),
    ("lst_f", "Peak summer surface temp (F)"),
    ("pct_canopy", "Tree canopy (%)"),
    ("pct_impervious", "Impervious surface (%)"),
    ("pct_age65p", "Age 65+ (%)"),
    ("pct_under5", "Under 5 (%)"),
    ("pct_under18", "Under 18 (%)"),
    ("pct_poverty", "Below poverty (%)"),
    ("median_income", "Median household income ($)"),
    ("svi", "CDC SVI (0-1)"),
    ("ces_score", "CalEnviroScreen score"),
    ("pct_hispanic", "Hispanic/Latino (%)"),
    ("pct_black", "Black (%)"),
    ("pct_asian", "Asian (%)"),
    ("pct_white_nh", "White, non-Hispanic (%)"),
    ("pop_density_km2", "Population density (/km2)"),
]


def attach_distance(df: gpd.GeoDataFrame, centers: gpd.GeoDataFrame | None,
                    cfg: Config) -> gpd.GeoDataFrame:
    out = df.copy()
    txy = centroids_xy(out)
    if centers is None or len(centers) == 0:
        out["dist_center_m"] = np.inf
    else:
        out["dist_center_m"] = nearest_distance_m(txy, points_xy(centers))
    for r in cfg.radius_grid_m:
        out[f"served_{r}m"] = out["dist_center_m"] <= r
    out["served"] = out["dist_center_m"] <= cfg.radius_m
    return out


def _wmean(x: pd.Series, w: pd.Series) -> float:
    m = x.notna() & w.notna() & (w > 0)
    return float(np.average(x[m], weights=w[m])) if m.any() else np.nan


def compare_distributions(df: pd.DataFrame, served_col: str) -> pd.DataFrame:
    """One row per indicator: all tracts vs served tracts, with effect sizes."""
    rows = []
    served = df[df[served_col]]
    for col, label in INDICATORS:
        if col not in df.columns or df[col].notna().sum() < 10:
            continue
        a_all, a_srv = df[col], served[col]
        d = standardized_mean_difference(a_srv.to_numpy(), a_all.to_numpy())
        ks, ksp = ks_test(a_srv.to_numpy(), a_all.to_numpy())
        qa, qs = quantiles(a_all.to_numpy()), quantiles(a_srv.to_numpy())
        rows.append({
            "indicator": label, "column": col,
            "all_mean": a_all.mean(), "served_mean": a_srv.mean(),
            "all_mean_popw": _wmean(a_all, df["pop"]),
            "served_mean_popw": _wmean(a_srv, served["pop"]),
            "difference": a_srv.mean() - a_all.mean(),
            "pct_difference": (100 * (a_srv.mean() - a_all.mean()) / a_all.mean()
                               if a_all.mean() else np.nan),
            "std_mean_diff": d,
            "ks_stat": ks, "ks_p": ksp,
            "all_p10": qa["p10"], "served_p10": qs["p10"],
            "all_p50": qa["p50"], "served_p50": qs["p50"],
            "all_p90": qa["p90"], "served_p90": qs["p90"],
            "shift": ("none (|d|<0.1)" if abs(d) < 0.1 else
                      ("higher in served" if d > 0 else "lower in served")),
        })
    return pd.DataFrame(rows)


def unmet_need(df: pd.DataFrame, cfg: Config) -> dict:
    """The headline numbers: how many vulnerable people have no centre near."""
    res = {}
    for r in cfg.radius_grid_m:
        s = df[f"served_{r}m"]
        tot_pop = df["pop"].sum()
        hi = df["hvi_top25"] if "hvi_top25" in df else df["hvi"] >= df["hvi"].quantile(.75)
        hi10 = df["hvi_top10"] if "hvi_top10" in df else df["hvi"] >= df["hvi"].quantile(.90)
        block = {
            "radius_m": r,
            "tracts_served": int(s.sum()),
            "tracts_served_pct": float(100 * s.mean()),
            "pop_served": float(df.loc[s, "pop"].sum()),
            "pop_served_pct": float(100 * df.loc[s, "pop"].sum() / tot_pop),
            "high_hvi_pop_unserved": float(df.loc[hi & ~s, "pop"].sum()),
            "high_hvi_pop_unserved_pct": float(
                100 * df.loc[hi & ~s, "pop"].sum() / df.loc[hi, "pop"].sum()),
            "top10_hvi_pop_unserved_pct": float(
                100 * df.loc[hi10 & ~s, "pop"].sum() / df.loc[hi10, "pop"].sum()),
        }
        # Who, by subgroup, is left outside the radius.
        for col, nm in (("pct_age65p", "age65p"), ("pct_under5", "under5"),
                        ("pct_under18", "under18"), ("pct_poverty", "poverty")):
            if col in df.columns and df[col].notna().any():
                n = df[col] / 100.0 * df["pop"]
                block[f"{nm}_served_pct"] = float(100 * n[s].sum() / n.sum())
        res[f"r{r}"] = block
    return res


def gap_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Canopy / pavement / temperature gaps between tract quartiles.

    Two cuts the advisor asked for: hottest vs coolest, and poorest vs
    wealthiest. The income cut uses median household income where available
    and falls back to the poverty rate."""
    out = {}
    cuts = [("lst_f", "Surface temperature quartile", False)]
    if df.get("median_income") is not None and df["median_income"].notna().any():
        cuts.append(("median_income", "Median income quartile", False))
    else:
        cuts.append(("pct_poverty", "Poverty-rate quartile", True))

    cols = [c for c in ("lst_f", "pct_canopy", "pct_impervious", "hvi",
                        "pct_poverty", "median_income", "pct_age65p",
                        "dist_center_m") if c in df.columns]
    for col, label, _ in cuts:
        d = df.dropna(subset=[col]).copy()
        d["q"] = pd.qcut(d[col], 4, labels=["Q1 (lowest)", "Q2", "Q3", "Q4 (highest)"])
        g = d.groupby("q", observed=True).agg(
            {**{c: "mean" for c in cols}, "pop": "sum",
             "served": "mean"}).round(2)
        g["served"] = (100 * g["served"]).round(1)
        g = g.rename(columns={"served": "pct_tracts_served"})
        g.index.name = label
        gap = g.loc["Q4 (highest)"] - g.loc["Q1 (lowest)"]
        g.loc["Q4 - Q1 gap"] = gap.round(2)
        out[col] = g.reset_index()
    return out


def run(cfg: Config, df: gpd.GeoDataFrame,
        centers: gpd.GeoDataFrame | None) -> tuple[gpd.GeoDataFrame, dict]:
    df = attach_distance(df, centers, cfg)

    dist_tbl = compare_distributions(df, "served")
    dist_tbl.round(3).to_csv(cfg.paths.tables / "partA_distribution_comparison.csv",
                             index=False)

    by_radius = {}
    for r in cfg.radius_grid_m:
        t = compare_distributions(df, f"served_{r}m")
        t.insert(0, "radius_m", r)
        by_radius[r] = t
    pd.concat(by_radius.values()).round(3).to_csv(
        cfg.paths.tables / "partA_distribution_by_radius.csv", index=False)

    un = unmet_need(df, cfg)
    gaps = gap_tables(df)
    for k, g in gaps.items():
        g.to_csv(cfg.paths.tables / f"partA_gap_by_{k}_quartile.csv", index=False)

    n_centers = 0 if centers is None else len(centers)
    summary = {
        "n_existing_centers": n_centers,
        "centers_set": cfg.centers_set,
        "radius_default_m": cfg.radius_m,
        "unmet_need": un,
        "distribution_shift": dist_tbl.set_index("column")[
            ["all_mean", "served_mean", "std_mean_diff", "ks_stat", "ks_p", "shift"]
        ].round(4).to_dict("index"),
        "median_distance_to_center_m": float(df["dist_center_m"].median()),
        "p90_distance_to_center_m": float(df["dist_center_m"].quantile(0.9)),
    }
    # Plain-language verdict, driven by the effect sizes rather than a glance.
    key = [c for c in ("hvi", "pct_poverty", "pct_age65p", "lst_f") if c in
           dist_tbl["column"].values]
    ds = dist_tbl.set_index("column").loc[key, "std_mean_diff"]
    if (ds.abs() < 0.1).all():
        verdict = ("Existing centres sit in tracts that look like the county "
                   "average on every vulnerability indicator: placement is "
                   "effectively uncorrelated with need.")
    elif ds.get("hvi", 0) > 0.1:
        verdict = ("Existing centres skew towards higher-vulnerability tracts, "
                   "so placement is at least partly corrective.")
    else:
        verdict = ("Existing centres skew towards lower-vulnerability tracts - "
                   "cooler, wealthier, greener than the county as a whole.")
    summary["verdict"] = verdict

    (cfg.paths.tables / "partA_summary.json").write_text(
        json.dumps(summary, indent=2, default=float))
    df.to_file(cfg.paths.processed / "tracts_partA.gpkg", layer="tracts", driver="GPKG")

    d2 = un[f"r{cfg.radius_m}"]
    print(f"  Part A: {n_centers} existing centres; "
          f"{d2['pop_served_pct']:.1f}% of residents within {cfg.radius_m} m; "
          f"{d2['high_hvi_pop_unserved_pct']:.1f}% of top-quartile-HVI residents "
          f"are beyond it")
    print(f"  verdict: {verdict}")
    return df, summary
