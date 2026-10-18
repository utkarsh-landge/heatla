"""Export everything the dashboard needs as static JSON/GeoJSON.

The dashboard runs no Python: it reads these files. Geometry is simplified
and coordinates rounded, because a 2,498-polygon GeoJSON at full precision is
~30 MB and makes the page crawl on a phone.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import geopandas as gpd

from .config import Config, CRS_WORK, CRS_GEO

TRACT_FIELDS = ["GEOID", "pop", "hvi", "lst_f", "pct_canopy", "pct_impervious",
                "pct_age65p", "pct_under5", "pct_under18", "pct_poverty",
                "median_income", "svi", "ces_score", "pct_hispanic", "pct_black",
                "pct_asian", "pct_white_nh", "dist_center_m", "served",
                "hvi_top25", "hvi_top10", "heat_er_rate_per100k"]


def _round_geom(gdf: gpd.GeoDataFrame, tol_m: float = 40.0,
                ndigits: int = 5) -> gpd.GeoDataFrame:
    g = gdf.to_crs(CRS_WORK)
    g["geometry"] = g.geometry.simplify(tol_m, preserve_topology=True)
    g = g.to_crs(CRS_GEO)
    g["geometry"] = g.geometry.set_precision(10 ** -ndigits)
    return g


def run(cfg: Config, df: gpd.GeoDataFrame,
        centers: gpd.GeoDataFrame | None) -> None:
    out = cfg.paths.dashboard_data
    out.mkdir(parents=True, exist_ok=True)

    cols = [c for c in TRACT_FIELDS if c in df.columns]
    g = _round_geom(df[cols + ["geometry"]].copy())
    for c in cols:
        if g[c].dtype.kind == "f":
            g[c] = g[c].round(2)
        elif g[c].dtype == bool:
            g[c] = g[c].astype(int)
    g.to_file(out / "tracts.geojson", driver="GeoJSON")

    if centers is not None and len(centers):
        c = centers.to_crs(CRS_GEO).copy()
        c["lon"] = c.geometry.x.round(5)
        c["lat"] = c.geometry.y.round(5)
        keep = [x for x in ("center_id", "name", "source", "lon", "lat")
                if x in c.columns]
        (out / "centers_existing.json").write_text(
            c[keep].to_json(orient="records"))

    for name in ("partC_solutions.json",):
        p = cfg.paths.processed / name
        if p.exists():
            (out / name).write_text(p.read_text())

    for name in ("partC_results_grid.csv", "partC_budget_curve.csv",
                 "partC_headline.csv", "partA_distribution_comparison.csv",
                 "partB_hvi_validation.csv",
                 "partB_assoc_hvi_shap.csv", "partB_assoc_hvi_importance.csv",
                 "partB_assoc_hvi_pdp.csv", "partB_assoc_hvi_ale.csv",
                 "partB_assoc_heat_er_rate_per100k_shap.csv"):
        p = cfg.paths.tables / name
        if p.exists():
            d = pd.read_csv(p)
            (out / name.replace(".csv", ".json")).write_text(
                d.to_json(orient="records"))

    # The CSV loop above already wrote partB_hvi_validation.json (the tidy
    # table the dashboard renders), so the richer nested version goes out
    # under its own name rather than clobbering it.
    for name, dest in (("partA_summary.json", "partA_summary.json"),
                       ("partB_hvi_validation.json", "partB_hvi_validation_full.json"),
                       ("partB_association.json", "partB_association.json")):
        p = cfg.paths.tables / name
        if p.exists():
            (out / dest).write_text(p.read_text())

    prov = cfg.paths.processed / "provenance.json"
    if prov.exists():
        (out / "provenance.json").write_text(prov.read_text())

    vint = cfg.paths.data / "vintages.md"
    meta = {
        "data_mode": cfg.data_mode,
        "lst_source": cfg.lst_source,
        "radius_default_m": cfg.radius_m,
        "radius_grid_m": list(cfg.radius_grid_m),
        "k_grid": list(cfg.k_grid),
        "k_default": cfg.k_default,
        "objectives": list(cfg.objectives),
        "n_tracts": int(len(df)),
        "n_existing_centers": 0 if centers is None else int(len(centers)),
        "total_population": float(np.nansum(df["pop"])),
        "vintages_markdown": vint.read_text() if vint.exists() else "",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=float))
    n = len(list(out.glob("*")))
    print(f"  dashboard data: {n} files in {out}")
