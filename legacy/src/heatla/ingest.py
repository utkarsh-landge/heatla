"""Loading and normalising every input source.

Two rules run through this module:

1. Everything is keyed on an 11-digit 2020 census tract GEOID (state 2 +
   county 3 + tract 6). Sources that ship 2010 tract IDs (CalEnviroScreen 4.0)
   or ZIP codes (the ER-visit data) go through an explicit crosswalk, never a
   silent string match.
2. If a download is unavailable, we say so and return None rather than
   inventing a column. build_table decides what to do with a missing source.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import requests

from .config import (Config, CENSUS_API_KEY, COUNTY_GEOID_PREFIX, COUNTY_FIPS,
                     STATE_FIPS, CRS_GEO)

# Exact download locations, mirrored in data/README.md.
URLS = {
    "tiger_tracts_2023": "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_06_tract.zip",
    "svi_2022_ca": "https://svi.cdc.gov/Documents/Data/2022/csv/states/California.csv",
    "ces40": "https://gis.data.ca.gov/api/download/v1/items/b6e0a01c423b489f8d98af641445da28/csv?layers=0",
    "ces50": ("https://publish.data.ca.gov/dataset/72b28c84-ceac-4886-9f71-d422470d2223/"
              "resource/c4e277e0-cf23-4a8f-b07e-c8544c5d3d2b/download/calenviroscreen50_070126.csv"),
    "zcta_tract_rel_2020": ("https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
                            "tab20_zcta520_tract20_natl.txt"),
    "tract_2010_to_2020": ("https://www2.census.gov/geo/docs/maps-data/data/rel2020/tract/"
                           "tab20_tract20_tract10_natl.txt"),
    "acs_api": "https://api.census.gov/data/2023/acs/acs5/profile",
}


# ---------------------------------------------------------------- helpers ---
def norm_geoid(s: pd.Series) -> pd.Series:
    """Coerce anything tract-ish to an 11-character GEOID string.

    Handles the two usual breakages: Excel stripping the leading zero off
    '06037...' and float round-tripping ('6037101110.0')."""
    out = (s.astype(str).str.strip()
            .str.replace(r"\.0$", "", regex=True)
            .str.replace(r"[^0-9]", "", regex=True))
    return out.str.zfill(11)


def in_la_county(geoid: pd.Series) -> pd.Series:
    return geoid.str.startswith(COUNTY_GEOID_PREFIX)


def _cache_get(cfg: Config, name: str, url: str, timeout: int = 600) -> Path | None:
    """Download once into data/raw and reuse thereafter. Returns None if the
    fetch fails, so callers can degrade instead of crashing."""
    suffix = ".zip" if url.endswith(".zip") else (".csv" if "csv" in url else ".txt")
    dest = cfg.paths.raw / f"{name}{suffix}"
    if dest.exists() and dest.stat().st_size > 1024:
        return dest
    try:
        r = requests.get(url, timeout=timeout, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    except Exception as exc:                       # network, 403, Incapsula...
        print(f"  [ingest] could not fetch {name}: {exc}")
        if dest.exists():
            dest.unlink()
        return None
    return dest


def _first_existing(cfg: Config, *names: str) -> Path | None:
    for n in names:
        p = cfg.paths.raw / n
        if p.exists() and p.stat().st_size > 1024:
            return p
    return None


# ------------------------------------------------------------- geometries ---
def load_tracts(cfg: Config) -> gpd.GeoDataFrame | None:
    """LA County 2020 tract polygons from TIGER/Line 2023."""
    src = _first_existing(cfg, "tl_2023_06_tract.zip") or _cache_get(
        cfg, "tl_2023_06_tract", URLS["tiger_tracts_2023"])
    if src is None:
        return None
    gdf = gpd.read_file(f"zip://{src}")
    gdf = gdf[gdf["COUNTYFP"] == COUNTY_FIPS].copy()
    gdf["GEOID"] = norm_geoid(gdf["GEOID"])
    gdf["INTPTLON"] = gdf["INTPTLON"].astype(float)
    gdf["INTPTLAT"] = gdf["INTPTLAT"].astype(float)
    gdf["land_area_sqkm"] = gdf["ALAND"].astype(float) / 1e6
    keep = ["GEOID", "NAMELSAD", "INTPTLON", "INTPTLAT", "land_area_sqkm", "geometry"]
    return gdf[keep].to_crs(CRS_GEO).reset_index(drop=True)


# ------------------------------------------------------------------- ACS ----
ACS_VARS = {
    "DP05_0001E": "pop",
    "DP05_0024PE": "pct_age65p",      # 65 years and over, percent
    "DP05_0005PE": "pct_under5",      # under 5 years, percent
    "DP05_0019PE": "pct_under18",     # under 18 years, percent
    "DP05_0037PE": "pct_white_nh_all",
    "DP05_0038PE": "pct_black",
    "DP05_0044PE": "pct_asian",
    "DP05_0073PE": "pct_hispanic",
    "DP03_0119PE": "pct_poverty",     # families and people below poverty level
    "DP03_0062E": "median_income",
}


def load_acs(cfg: Config) -> pd.DataFrame | None:
    """ACS 5-year profile tables DP05 (demographics) and DP03 (economics).

    Needs a free Census API key in CENSUS_API_KEY; the public endpoint started
    rejecting keyless calls. Without one we return None and build_table falls
    back to CDC SVI, which carries most of the same counts."""
    cache = cfg.paths.raw / "acs_la_tracts.csv"
    if cache.exists():
        df = pd.read_csv(cache, dtype={"GEOID": str})
        df["GEOID"] = norm_geoid(df["GEOID"])
        return df
    if not CENSUS_API_KEY:
        print("  [ingest] no CENSUS_API_KEY set; skipping ACS (see data/README.md)")
        return None
    frames = []
    for table in ("DP05", "DP03"):
        cols = [v for v in ACS_VARS if v.startswith(table)]
        params = {"get": "NAME," + ",".join(cols), "for": "tract:*",
                  "in": f"state:{STATE_FIPS} county:{COUNTY_FIPS}",
                  "key": CENSUS_API_KEY}
        try:
            r = requests.get(URLS["acs_api"], params=params, timeout=180)
            r.raise_for_status()
            rows = r.json()
        except Exception as exc:
            print(f"  [ingest] ACS {table} fetch failed: {exc}")
            return None
        d = pd.DataFrame(rows[1:], columns=rows[0])
        d["GEOID"] = norm_geoid(d["state"] + d["county"] + d["tract"])
        d = d[["GEOID"] + cols].apply(
            lambda c: pd.to_numeric(c, errors="coerce") if c.name != "GEOID" else c)
        frames.append(d)
    out = frames[0].merge(frames[1], on="GEOID", how="outer").rename(columns=ACS_VARS)
    # Census uses large negative sentinels for suppressed cells.
    num = out.columns.drop("GEOID")
    out[num] = out[num].mask(out[num] < -1e6)
    out.to_csv(cache, index=False)
    return out


# ------------------------------------------------------------------- SVI ----
SVI_COLS = {
    "E_TOTPOP": "pop", "E_AGE65": "n_age65p", "E_AGE17": "n_under18",
    "E_POV150": "n_pov150", "E_HISP": "n_hispanic", "E_AFAM": "n_black",
    "E_ASIAN": "n_asian", "E_AIAN": "n_aian", "E_NHPI": "n_nhpi",
    "E_TWOMORE": "n_twomore", "E_OTHERRACE": "n_otherrace",
    "E_MINRTY": "n_minority", "E_NOVEH": "n_noveh", "E_DAYPOP": "daytime_pop",
    "RPL_THEMES": "svi",
}


def load_svi(cfg: Config) -> pd.DataFrame | None:
    """CDC/ATSDR Social Vulnerability Index 2022, California tract file."""
    src = _first_existing(cfg, "svi_2022_CA.csv") or _cache_get(
        cfg, "svi_2022_CA", URLS["svi_2022_ca"])
    if src is None:
        return None
    df = pd.read_csv(src, dtype={"FIPS": str}, low_memory=False)
    df["GEOID"] = norm_geoid(df["FIPS"])
    df = df[in_la_county(df["GEOID"])].copy()
    have = {k: v for k, v in SVI_COLS.items() if k in df.columns}
    out = df[["GEOID"] + list(have)].rename(columns=have)
    # CDC encodes missing as -999.
    num = out.columns.drop("GEOID")
    out[num] = out[num].mask(out[num] <= -999)
    out["svi"] = out["svi"].mask(out["svi"] < 0)
    return out


# --------------------------------------------------------- CalEnviroScreen ---
def load_ces(cfg: Config, version: str = "4.0") -> pd.DataFrame | None:
    """CalEnviroScreen pollution/health indicators.

    4.0 is published on 2010 tract boundaries, so it is crosswalked to 2020
    GEOIDs here; 5.0 already uses 2020 tracts. Which one we use is recorded in
    data/vintages.md."""
    name = "ces40" if version.startswith("4") else "ces50"
    src = _first_existing(cfg, f"{name}.csv") or _cache_get(cfg, name, URLS[name])
    if src is None:
        return None
    df = pd.read_csv(src, low_memory=False)
    cmap = {c.lower().strip(): c for c in df.columns}

    def pick(*cands):
        for c in cands:
            if c in cmap:
                return cmap[c]
        return None

    tract_col = pick("tract", "census tract", "censustract", "geoid")
    score_col = pick("ciscorep", "calenviroscreen 4.0 score", "ces 4.0 score",
                     "calenviroscreen 5.0 score", "ces 5.0 score", "cesscore")
    pctl_col = pick("ciscorep_pctl", "calenviroscreen 4.0 percentile",
                    "calenviroscreen 5.0 percentile", "ces 4.0 percentile",
                    "ces 5.0 percentile")
    pm_col = pick("pm2.5 pctl", "pm2.5_pctl", "pm25 pctl")
    oz_col = pick("ozone pctl", "ozone_pctl")
    tr_col = pick("traffic pctl", "traffic_pctl")
    poll_col = pick("pollution burden score", "pollutionscore",
                    "pollution burden pctl", "pollution burden")
    asth_col = pick("asthma pctl", "asthma_pctl")
    cvd_col = pick("cardiovascular disease pctl", "cardiovascular disease")
    if tract_col is None:
        print("  [ingest] CES: no recognisable tract column")
        return None

    out = pd.DataFrame({"GEOID_src": norm_geoid(df[tract_col])})
    for col, nm in ((score_col, "ces_score"), (pctl_col, "ces_pctl"),
                    (pm_col, "ces_pm25_pctl"), (oz_col, "ces_ozone_pctl"),
                    (tr_col, "ces_traffic_pctl"), (poll_col, "ces_pollution_pctl"),
                    (asth_col, "ces_asthma_pctl"), (cvd_col, "ces_cvd_pctl")):
        if col is not None:
            out[nm] = pd.to_numeric(df[col], errors="coerce")
    out = out[in_la_county(out["GEOID_src"])].copy()
    if out.empty:
        return None

    if version.startswith("4"):
        xw = load_tract_2010_2020_crosswalk(cfg)
        if xw is None:
            print("  [ingest] CES 4.0: 2010->2020 crosswalk unavailable; "
                  "falling back to identity match (documented limitation)")
            out = out.rename(columns={"GEOID_src": "GEOID"})
        else:
            out = _apportion_2010_to_2020(out, xw)
    else:
        out = out.rename(columns={"GEOID_src": "GEOID"})
    return out.groupby("GEOID", as_index=False).mean(numeric_only=True)


def load_tract_2010_2020_crosswalk(cfg: Config) -> pd.DataFrame | None:
    """Census 2020<->2010 tract relationship file, trimmed to LA County."""
    src = _first_existing(cfg, "tract_2010_to_2020.txt") or _cache_get(
        cfg, "tract_2010_to_2020", URLS["tract_2010_to_2020"])
    if src is None:
        return None
    df = pd.read_csv(src, sep="|", dtype=str, low_memory=False)
    cols = {c.upper(): c for c in df.columns}
    g20 = cols.get("GEOID_TRACT_20") or cols.get("GEOID_20")
    g10 = cols.get("GEOID_TRACT_10") or cols.get("GEOID_10")
    area = cols.get("AREALAND_PART") or cols.get("AREALAND_20")
    if not (g20 and g10):
        return None
    out = pd.DataFrame({"GEOID20": norm_geoid(df[g20]),
                        "GEOID10": norm_geoid(df[g10]),
                        "w": pd.to_numeric(df[area], errors="coerce").fillna(0.0)
                        if area else 1.0})
    out = out[in_la_county(out["GEOID20"])].copy()
    # Weight each 2010 piece by its share of the 2020 tract's land area.
    tot = out.groupby("GEOID20")["w"].transform("sum")
    out["w"] = np.where(tot > 0, out["w"] / tot, 1.0)
    tot2 = out.groupby("GEOID20")["w"].transform("sum")
    out["w"] = np.where(tot2 > 0, out["w"] / tot2, 1.0)
    return out


def _apportion_2010_to_2020(src: pd.DataFrame, xw: pd.DataFrame) -> pd.DataFrame:
    m = xw.merge(src, left_on="GEOID10", right_on="GEOID_src", how="inner")
    val_cols = [c for c in src.columns if c != "GEOID_src"]
    for c in val_cols:
        m[c] = m[c] * m["w"]
    agg = m.groupby("GEOID20")[val_cols + ["w"]].sum()
    for c in val_cols:
        agg[c] = np.where(agg["w"] > 0, agg[c] / agg["w"], np.nan)
    return agg.drop(columns="w").reset_index().rename(columns={"GEOID20": "GEOID"})


# --------------------------------------------------- ZIP -> tract crosswalk --
def load_zcta_tract_crosswalk(cfg: Config) -> pd.DataFrame | None:
    """2020 ZCTA<->tract relationship file.

    Heat-related ER visits are published by ZIP, not by tract, so a ZIP rate is
    pushed down to tracts weighted by the population each tract contributes to
    the ZCTA. That is an apportionment, not a measurement: the limitation is
    stated wherever the ER numbers appear."""
    src = _first_existing(cfg, "zcta_tract_rel.txt") or _cache_get(
        cfg, "zcta_tract_rel", URLS["zcta_tract_rel_2020"])
    if src is None:
        return None
    df = pd.read_csv(src, sep="|", dtype=str, low_memory=False)
    cols = {c.upper(): c for c in df.columns}
    z = cols.get("GEOID_ZCTA5_20")
    t = cols.get("GEOID_TRACT_20")
    pop = cols.get("POPULATION_PART") or cols.get("POP_PART")
    area = cols.get("AREALAND_PART")
    if not (z and t):
        return None
    w = (pd.to_numeric(df[pop], errors="coerce") if pop else
         pd.to_numeric(df[area], errors="coerce"))
    out = pd.DataFrame({"zcta": df[z].astype(str).str.zfill(5),
                        "GEOID": norm_geoid(df[t]),
                        "w_pop": w.fillna(0.0)})
    return out[in_la_county(out["GEOID"])].copy()


def apportion_zip_to_tract(zip_rates: pd.DataFrame, xw: pd.DataFrame,
                           value_col: str, zip_col: str = "zcta") -> pd.DataFrame:
    """Population-weighted ZIP -> tract apportionment of a rate."""
    z = zip_rates.copy()
    z[zip_col] = z[zip_col].astype(str).str.extract(r"(\d{5})")[0].str.zfill(5)
    m = xw.merge(z, left_on="zcta", right_on=zip_col, how="inner").dropna(subset=[value_col])
    if m.empty:
        return pd.DataFrame(columns=["GEOID", value_col])
    m["w"] = m["w_pop"].clip(lower=0)
    # A tract split across ZIPs gets the population-weighted mean of their rates.
    g = m.groupby("GEOID").apply(
        lambda d: np.average(d[value_col], weights=d["w"]) if d["w"].sum() > 0
        else d[value_col].mean(), include_groups=False)
    out = g.reset_index()
    out.columns = ["GEOID", value_col]
    out["er_zip_apportioned"] = True
    return out


# -------------------------------------------------------- cooling centres ---
def load_centers(cfg: Config) -> gpd.GeoDataFrame | None:
    """Existing cooling centres.

    LA County and the City publish these as point layers that move around (and
    are seasonal). We read whatever CSV/GeoJSON is sitting in data/raw; the
    expected schema is one row per site with name and lat/lon."""
    for cand in ("cooling_centers.geojson", "cooling_centers.json"):
        p = cfg.paths.raw / cand
        if p.exists() and p.stat().st_size > 256:
            gdf = gpd.read_file(p).to_crs(CRS_GEO)
            gdf["center_id"] = [f"EX-{i:03d}" for i in range(1, len(gdf) + 1)]
            if "name" not in gdf.columns:
                name_col = next((c for c in gdf.columns
                                 if "name" in c.lower() or "site" in c.lower()), None)
                gdf["name"] = gdf[name_col] if name_col else gdf["center_id"]
            gdf["source"] = cand
            return gdf[["center_id", "name", "source", "geometry"]]
    p = cfg.paths.raw / "cooling_centers.csv"
    if p.exists():
        df = pd.read_csv(p)
        lat = next((c for c in df.columns if c.lower() in
                    ("lat", "latitude", "y", "point_y")), None)
        lon = next((c for c in df.columns if c.lower() in
                    ("lon", "lng", "long", "longitude", "x", "point_x")), None)
        if lat and lon:
            df = df.dropna(subset=[lat, lon])
            gdf = gpd.GeoDataFrame(
                df, geometry=gpd.points_from_xy(df[lon], df[lat]), crs=CRS_GEO)
            gdf["center_id"] = [f"EX-{i:03d}" for i in range(1, len(gdf) + 1)]
            name_col = next((c for c in df.columns if "name" in c.lower()), None)
            gdf["name"] = gdf[name_col] if name_col else gdf["center_id"]
            gdf["source"] = "cooling_centers.csv"
            return gdf[["center_id", "name", "source", "geometry"]]
    print("  [ingest] no cooling-centre file in data/raw (see data/README.md)")
    return None


# -------------------------------------------- Earth Engine raster summaries --
def load_gee_tract_summaries(cfg: Config) -> pd.DataFrame | None:
    """Tract-level LST / canopy / impervious means exported from Earth Engine.

    gee/ holds the export scripts. Drop the resulting CSVs into data/raw as
    gee_lst_landsat.csv, gee_lst_ecostress.csv, gee_canopy.csv,
    gee_impervious.csv; each needs a GEOID column plus one value column."""
    wanted = {
        f"gee_lst_{cfg.lst_source}.csv": "lst_f",
        "gee_canopy.csv": "pct_canopy",
        "gee_impervious.csv": "pct_impervious",
    }
    frames = []
    for fname, col in wanted.items():
        p = cfg.paths.raw / fname
        if not p.exists():
            continue
        d = pd.read_csv(p, dtype={"GEOID": str})
        d["GEOID"] = norm_geoid(d["GEOID"])
        vcol = col if col in d.columns else next(
            (c for c in d.columns if c not in ("GEOID", "system:index", ".geo")), None)
        if vcol is None:
            continue
        frames.append(d[["GEOID", vcol]].rename(columns={vcol: col}))
    if not frames:
        print("  [ingest] no Earth Engine exports in data/raw (see gee/README.md)")
        return None
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on="GEOID", how="outer")
    return out


def load_heat_er(cfg: Config) -> pd.DataFrame | None:
    """Heat-related ER visit rates by ZIP (CDPH / CalBRACE)."""
    p = cfg.paths.raw / "heat_er_zip.csv"
    if not p.exists():
        print("  [ingest] no heat_er_zip.csv in data/raw (see data/README.md)")
        return None
    df = pd.read_csv(p)
    zc = next((c for c in df.columns if "zip" in c.lower() or "zcta" in c.lower()), None)
    rc = next((c for c in df.columns if "rate" in c.lower()), None)
    if not (zc and rc):
        return None
    return pd.DataFrame({"zcta": df[zc].astype(str),
                         "heat_er_rate_per100k": pd.to_numeric(df[rc], errors="coerce")})
