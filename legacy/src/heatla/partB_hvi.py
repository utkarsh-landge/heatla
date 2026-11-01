"""Part B(a-b): build the Heat Vulnerability Index and validate it.

HVI follows the CCHVI framing: a tract's score is the mean percentile rank of
four inputs, one per pathway.

    exposure          peak summer land-surface temperature
    sensitivity       % residents aged 65+
    adaptive capacity % below the poverty line
                      % without tree canopy

Percentile ranks, not z-scores, so one very hot tract cannot drag the whole
index, and so the four inputs combine on a common 0-100 scale despite having
different units.

Part B is built before Part C uses it, but note the two are decoupled: HVI
needs no model fit, so the optimiser can run against a real HVI immediately.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import geopandas as gpd

from .config import Config
from .stats_utils import pct_rank, spearman, top_share_overlap

# Higher input value -> more vulnerable, after this sign flip.
HVI_COMPONENTS = {
    "lst_f": ("exposure", +1),
    "pct_age65p": ("sensitivity", +1),
    "pct_poverty": ("adaptive_capacity", +1),
    "pct_no_canopy": ("adaptive_capacity", +1),
}


def compute_hvi(df: pd.DataFrame, components: dict | None = None) -> pd.DataFrame:
    comps = components or HVI_COMPONENTS
    out = pd.DataFrame(index=df.index)
    ranks = []
    for col, (_, sign) in comps.items():
        if col not in df.columns:
            raise KeyError(f"HVI input missing from master table: {col}")
        r = pct_rank(df[col] * sign)
        out[f"hvi_rank_{col}"] = r.round(2)
        ranks.append(r)
    R = pd.concat(ranks, axis=1)
    # Mean of available components: a tract missing one input still gets a
    # score rather than dropping out of the map entirely.
    out["hvi"] = R.mean(axis=1, skipna=True).round(2)
    out["hvi_n_components"] = R.notna().sum(axis=1)
    out.loc[out["hvi_n_components"] < 2, "hvi"] = np.nan
    return out


def add_hvi(df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = df.copy()
    hvi = compute_hvi(out)
    for c in hvi.columns:
        out[c] = hvi[c]
    out["hvi_quartile"] = pd.qcut(out["hvi"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
    out["hvi_top10"] = out["hvi"] >= out["hvi"].quantile(0.90)
    out["hvi_top25"] = out["hvi"] >= out["hvi"].quantile(0.75)
    return out


def validate_hvi(df: pd.DataFrame, cfg: Config) -> dict:
    """Two external checks: heat-related ER visits, and the CDC SVI."""
    res: dict[str, object] = {}

    if "heat_er_rate_per100k" in df.columns and df["heat_er_rate_per100k"].notna().any():
        rho, p, n = spearman(df["hvi"], df["heat_er_rate_per100k"])
        res["er_visits"] = {
            "spearman_rho": rho, "p_value": p, "n_tracts": n,
            "caveat": ("ER visits are published by ZIP code, not by census tract. "
                       "Rates were pushed down to tracts by population-weighted "
                       "apportionment, so every tract inside one ZIP shares a "
                       "value and the correlation is attenuated and partly "
                       "mechanical. Treat it as a weak corroboration, not a test."),
        }
        # Same comparison at the ZIP level of aggregation, which is the level the
        # outcome is actually measured at.
        if "ZCTA_mock" in df.columns:
            g = df.groupby("ZCTA_mock").agg(hvi=("hvi", "mean"),
                                            er=("heat_er_rate_per100k", "mean"))
            rho2, p2, n2 = spearman(g["hvi"], g["er"])
            res["er_visits_zip_level"] = {"spearman_rho": rho2, "p_value": p2,
                                          "n_zips": n2}

    if "svi" in df.columns and df["svi"].notna().any():
        rho, p, n = spearman(df["hvi"], df["svi"])
        ov10 = top_share_overlap(df["hvi"], df["svi"], 0.10)
        ov25 = top_share_overlap(df["hvi"], df["svi"], 0.25)
        res["svi"] = {"spearman_rho": rho, "p_value": p, "n_tracts": n,
                      "top10_overlap": ov10, "top25_overlap": ov25,
                      "note": ("SVI is a general social-vulnerability index with no "
                               "heat exposure term, so agreement should be partial: "
                               "identical rankings would mean HVI adds nothing, and "
                               "no agreement would suggest the social inputs are "
                               "not behaving.")}

    if "ces_score" in df.columns and df["ces_score"].notna().any():
        rho, p, n = spearman(df["hvi"], df["ces_score"])
        res["calenviroscreen"] = {"spearman_rho": rho, "p_value": p, "n_tracts": n,
                                  "top10_overlap": top_share_overlap(
                                      df["hvi"], df["ces_score"], 0.10)}

    # Internal check: does any single input dominate the composite?
    comp_cols = [c for c in df.columns if c.startswith("hvi_rank_")]
    res["component_correlations"] = {
        c.replace("hvi_rank_", ""): spearman(df["hvi"], df[c])[0] for c in comp_cols}
    res["component_intercorrelation"] = (
        df[comp_cols].corr(method="spearman").round(3).to_dict())
    return res


def run(cfg: Config, df: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict]:
    df = add_hvi(df)
    val = validate_hvi(df, cfg)
    out = cfg.paths.processed
    df.to_file(out / "tracts_hvi.gpkg", layer="tracts", driver="GPKG")
    df.drop(columns="geometry").to_csv(out / "tracts_hvi.csv", index=False)
    (cfg.paths.tables / "partB_hvi_validation.json").write_text(
        json.dumps(val, indent=2, default=float))

    rows = []
    for key, label in (("er_visits", "Heat-related ER visits (ZIP-apportioned)"),
                       ("svi", "CDC/ATSDR SVI"),
                       ("calenviroscreen", "CalEnviroScreen score")):
        if key in val:
            v = val[key]
            rows.append({"comparison": label,
                         "spearman_rho": round(v["spearman_rho"], 3),
                         "p_value": f"{v['p_value']:.2e}",
                         "n": v["n_tracts"],
                         "top10_overlap": (f"{v['top10_overlap']['overlap_frac']:.0%}"
                                           if "top10_overlap" in v else "")})
    pd.DataFrame(rows).to_csv(cfg.paths.tables / "partB_hvi_validation.csv", index=False)
    print(f"  HVI built for {df['hvi'].notna().sum()} tracts; "
          f"validation: " + ", ".join(
              f"{r['comparison'].split('(')[0].strip()} rho={r['spearman_rho']}"
              for r in rows))
    return df, val
