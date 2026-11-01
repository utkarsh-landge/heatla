"""Download every public source that can be fetched without credentials.

    python -m heatla.fetch_real

What this gets you: tract geometry, CDC SVI, CalEnviroScreen, the Census
crosswalks, LA County's cooling-centre layer, and LA County tree canopy.

What it cannot get: ACS (needs a free Census API key in CENSUS_API_KEY) and
the Earth Engine raster summaries (see gee/README.md). Both are documented in
data/README.md.
"""
from __future__ import annotations

import json
import sys

import pandas as pd
import requests

from .config import Config
from .ingest import URLS, _cache_get, norm_geoid

AGOL = "https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services"
CENTERS_LAYERS = {
    # The "Regional (Official)" layer is the augmented county-wide list; the
    # augmented-2023 view is seasonal and is usually empty out of season.
    "augmented": f"{AGOL}/Cooling_Centers_-_Los_Angeles_County_Regional_(Official_-_Updated_July_2022)_(View)/FeatureServer/0",
    "seasonal": f"{AGOL}/Cooling_Centers_-_Augmented_(2023)_view/FeatureServer/0",
}
CANOPY_LAYER = f"{AGOL}/tree_canopy_by_tract/FeatureServer/0"


def _agol_query(layer: str, geometry: bool = True, page: int = 1000) -> dict:
    """Page through an ArcGIS feature service; these cap at 1-2k records."""
    feats, offset = [], 0
    while True:
        params = {"where": "1=1", "outFields": "*", "f": "geojson",
                  "outSR": "4326", "returnGeometry": str(geometry).lower(),
                  "resultOffset": offset, "resultRecordCount": page}
        r = requests.get(layer + "/query", params=params, timeout=180)
        r.raise_for_status()
        d = r.json()
        batch = d.get("features", [])
        feats.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return {"type": "FeatureCollection", "features": feats}


def fetch_centers(cfg: Config) -> int:
    fc = _agol_query(CENTERS_LAYERS["augmented"])
    if not fc["features"]:
        fc = _agol_query(CENTERS_LAYERS["seasonal"])
    p = cfg.paths.raw / "cooling_centers.geojson"
    p.write_text(json.dumps(fc))
    return len(fc["features"])


def fetch_canopy(cfg: Config) -> int:
    """LA County publishes tree canopy per 2020 tract, so the canopy column
    can be filled without Earth Engine. The tract key is the 6-digit code."""
    fc = _agol_query(CANOPY_LAYER, geometry=False, page=2000)
    rows = []
    for f in fc["features"]:
        p = f["properties"]
        code = str(p.get("CT20") or p.get("CT_20") or "").strip()
        val = p.get("CanopyPercent")
        if code and val is not None:
            rows.append({"GEOID": norm_geoid(pd.Series([f"06037{code}"]))[0],
                         "pct_canopy": float(val)})
    if not rows:
        return 0
    df = pd.DataFrame(rows).drop_duplicates("GEOID")
    df.to_csv(cfg.paths.raw / "gee_canopy.csv", index=False)
    return len(df)


def main() -> int:
    cfg = Config.load()
    print("fetching public sources into data/raw/ ...")
    todo = [("tl_2023_06_tract", URLS["tiger_tracts_2023"]),
            ("svi_2022_CA", URLS["svi_2022_ca"]),
            ("ces40", URLS["ces40"]),
            ("zcta_tract_rel", URLS["zcta_tract_rel_2020"]),
            ("tract_2010_to_2020", URLS["tract_2010_to_2020"])]
    for name, url in todo:
        p = _cache_get(cfg, name, url)
        print(f"  {'ok  ' if p else 'FAIL'} {name}")

    try:
        n = fetch_centers(cfg)
        print(f"  ok   cooling_centers.geojson ({n} sites)")
    except Exception as exc:
        print(f"  FAIL cooling centres: {exc}")
    try:
        n = fetch_canopy(cfg)
        print(f"  ok   gee_canopy.csv from LA County tract canopy ({n} tracts)")
    except Exception as exc:
        print(f"  FAIL tree canopy: {exc}")

    print("\nStill needed for a complete real run:")
    print("  - ACS: set CENSUS_API_KEY (free, instant: "
          "https://api.census.gov/data/key_signup.html)")
    print("  - land-surface temperature + impervious surface: run the Earth "
          "Engine scripts in gee/ (see gee/README.md)")
    print("  - heat-related ER visits by ZIP: data/raw/heat_er_zip.csv "
          "(see data/README.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
