"""Assemble the one-row-per-tract master table.

Everything downstream (Parts A, B, C, the figures, the dashboard) reads
data/processed/tracts_master.gpkg and nothing else. If a column is missing
here, it is missing because the source was unavailable, and provenance.json
records which source filled each field.
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import geopandas as gpd

from .config import Config, CRS_GEO, CRS_WORK
from . import ingest
from .mock import build_mock

# Columns every downstream module may assume exist.
REQUIRED = [
    "GEOID", "pop", "pct_age65p", "pct_under5", "pct_under18", "pct_poverty",
    "median_income", "pct_hispanic", "pct_black", "pct_asian", "pct_white_nh",
    "lst_f", "pct_canopy", "pct_impervious", "svi",
]


def _pct(n, d):
    n = pd.to_numeric(n, errors="coerce")
    d = pd.to_numeric(d, errors="coerce")
    return np.where((d > 0) & n.notna(), 100.0 * n / d, np.nan)


def build_real(cfg: Config) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame | None,
                                     pd.DataFrame | None, dict]:
    prov: dict[str, str] = {}
    tracts = ingest.load_tracts(cfg)
    if tracts is None:
        raise RuntimeError("TIGER tract geometry is required for real mode; "
                           "see data/README.md")
    prov["geometry"] = "TIGER/Line 2023 tracts (Census)"
    df = tracts.copy()

    acs = ingest.load_acs(cfg)
    svi = ingest.load_svi(cfg)

    if acs is not None:
        df = df.merge(acs, on="GEOID", how="left")
        df["pct_white_nh"] = df.get("pct_white_nh_all")
        for c in ("pop", "pct_age65p", "pct_under5", "pct_under18", "pct_poverty",
                  "median_income", "pct_hispanic", "pct_black", "pct_asian",
                  "pct_white_nh"):
            prov[c] = "ACS 2019-2023 5-year (DP03/DP05)"

    if svi is not None:
        svi_cols = [c for c in svi.columns if c != "GEOID"]
        df = df.merge(svi[["GEOID"] + svi_cols], on="GEOID", how="left",
                      suffixes=("", "_svi"))
        prov["svi"] = "CDC/ATSDR SVI 2022 (RPL_THEMES)"
        # SVI backfills the demographic block when no Census API key is set.
        pop_svi = df["pop_svi"] if "pop_svi" in df.columns else df.get("pop")
        if acs is None:
            df["pop"] = pop_svi
            df["pct_age65p"] = _pct(df["n_age65p"], pop_svi)
            df["pct_under18"] = _pct(df["n_under18"], pop_svi)
            df["pct_poverty"] = _pct(df["n_pov150"], pop_svi)
            df["pct_hispanic"] = _pct(df["n_hispanic"], pop_svi)
            df["pct_black"] = _pct(df["n_black"], pop_svi)
            df["pct_asian"] = _pct(df["n_asian"], pop_svi)
            nonwhite = df[["n_hispanic", "n_black", "n_asian", "n_aian",
                           "n_nhpi", "n_twomore", "n_otherrace"]].sum(axis=1,
                                                                      min_count=1)
            df["pct_white_nh"] = _pct(pop_svi - nonwhite, pop_svi)
            for c in ("pop", "pct_age65p", "pct_under18", "pct_poverty",
                      "pct_hispanic", "pct_black", "pct_asian", "pct_white_nh"):
                prov[c] = "CDC/ATSDR SVI 2022 counts (ACS 2018-2022) - ACS fallback"
            # SVI publishes no under-5 count and no median income.
            df["pct_under5"] = np.nan
            df["median_income"] = np.nan
            prov["pct_under5"] = "UNAVAILABLE - needs ACS DP05_0005PE (set CENSUS_API_KEY)"
            prov["median_income"] = "UNAVAILABLE - needs ACS DP03_0062E (set CENSUS_API_KEY)"

    ces = ingest.load_ces(cfg, "4.0")
    if ces is not None:
        df = df.merge(ces, on="GEOID", how="left")
        for c in ces.columns:
            if c != "GEOID":
                prov[c] = "CalEnviroScreen 4.0 (2021), 2010 tracts crosswalked to 2020"

    gee = ingest.load_gee_tract_summaries(cfg)
    if gee is not None:
        df = df.merge(gee, on="GEOID", how="left")
        src = ("Landsat 8/9 C2L2 ST_B10, Jun-Sep 2021-2025 max"
               if cfg.lst_source == "landsat" else "ECOSTRESS L2T_LSTE")
        prov["lst_f"] = f"Earth Engine export: {src}"
        prov["pct_canopy"] = "Earth Engine export: USFS/NLCD tree canopy"
        prov["pct_impervious"] = "Earth Engine export: NLCD 2021 impervious"

    for c in REQUIRED:
        if c not in df.columns:
            df[c] = np.nan
            prov.setdefault(c, "UNAVAILABLE")

    centers = ingest.load_centers(cfg)

    er_tract = None
    er_zip = ingest.load_heat_er(cfg)
    xw = ingest.load_zcta_tract_crosswalk(cfg)
    if er_zip is not None and xw is not None:
        er_tract = ingest.apportion_zip_to_tract(er_zip, xw, "heat_er_rate_per100k")
        prov["heat_er_rate_per100k"] = ("CDPH/CalBRACE heat ER visits by ZIP, "
                                        "population-weighted to 2020 tracts")
    return df, centers, er_tract, prov


def build_mock_table(cfg: Config) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame,
                                           pd.DataFrame, dict]:
    m = build_mock(cfg)
    tracts, centers, er_zip = m["tracts"], m["centers"], m["er_zip"]
    # Exercise the same ZIP->tract apportionment path the real data uses.
    xw = pd.DataFrame({"zcta": tracts["ZCTA_mock"], "GEOID": tracts["GEOID"],
                       "w_pop": tracts["pop"]})
    er_tract = ingest.apportion_zip_to_tract(er_zip, xw, "heat_er_rate_per100k")
    prov = {c: "SYNTHETIC MOCK" for c in REQUIRED}
    prov["heat_er_rate_per100k"] = "SYNTHETIC MOCK (ZIP-level, apportioned to tracts)"
    tracts = tracts.drop(columns=["ZCTA_mock"])
    tracts["land_area_sqkm"] = tracts.to_crs(CRS_WORK).area / 1e6
    return tracts, centers, er_tract, prov


def build(cfg: Config) -> gpd.GeoDataFrame:
    if cfg.data_mode == "mock":
        df, centers, er_tract, prov = build_mock_table(cfg)
    else:
        df, centers, er_tract, prov = build_real(cfg)

    if er_tract is not None and len(er_tract):
        df = df.merge(er_tract, on="GEOID", how="left")

    # Integrity checks: a duplicated or malformed GEOID silently fans out every
    # later join, so fail loudly here instead.
    assert df["GEOID"].is_unique, "duplicate GEOIDs in master table"
    assert df["GEOID"].str.len().eq(11).all(), "non-11-digit GEOID present"
    assert df.crs is not None and df.crs.to_string() == CRS_GEO

    df["pop_density_km2"] = np.where(df["land_area_sqkm"] > 0,
                                     df["pop"] / df["land_area_sqkm"], np.nan)
    df["pct_no_canopy"] = 100.0 - df["pct_canopy"]

    out = cfg.paths.processed
    df.to_file(out / "tracts_master.gpkg", layer="tracts", driver="GPKG")
    df.drop(columns="geometry").to_csv(out / "tracts_master.csv", index=False)
    if centers is not None:
        centers.to_file(out / "centers_existing.gpkg", layer="centers", driver="GPKG")

    meta = {
        "built": date.today().isoformat(),
        "data_mode": cfg.data_mode,
        "lst_source": cfg.lst_source,
        "centers_set": cfg.centers_set,
        "n_tracts": int(len(df)),
        "n_centers": int(len(centers)) if centers is not None else 0,
        "total_population": float(np.nansum(df["pop"])),
        "coverage": {c: float(df[c].notna().mean()) for c in REQUIRED
                     if c != "GEOID"},
        "provenance": prov,
    }
    (out / "provenance.json").write_text(json.dumps(meta, indent=2))
    print(f"  master table: {len(df)} tracts, "
          f"{meta['total_population']:,.0f} residents, mode={cfg.data_mode}")
    missing = [c for c, v in meta["coverage"].items() if v < 0.5]
    if missing:
        print(f"  [warn] <50% coverage: {', '.join(missing)}")
    return df


def load_master(cfg: Config) -> gpd.GeoDataFrame:
    p = cfg.paths.processed / "tracts_master.gpkg"
    if not p.exists():
        return build(cfg)
    return gpd.read_file(p, layer="tracts")


def load_centers_existing(cfg: Config) -> gpd.GeoDataFrame | None:
    p = cfg.paths.processed / "centers_existing.gpkg"
    return gpd.read_file(p, layer="centers") if p.exists() else None
