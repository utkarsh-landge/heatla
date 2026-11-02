"""Step 5a - pull projected extreme-heat days for every LA ZIP from Cal-Adapt.

Source : Cal-Adapt API (UC Berkeley Geospatial Innovation Facility), series
         `exheat_year_ens32avg_rcp45` and `exheat_year_ens32avg_rcp85`
         = average number of extreme heat days per year across 32 LOCA-downscaled
         climate models, 1/16 degree grid (~6 km), one value per year 2006-2100.
Definition (Cal-Adapt API docs, "Climate Indicators"): an extreme heat day is a day
         when daily maximum temperature exceeds the 98th percentile of observed
         1961-1990 April-October maximum temperature at that grid cell.

For each ZIP we query the grid cell under the ZCTA centroid (lat/lon from the 2023
Census Gazetteer, already in features_ces_geo.csv). ZIPs with no centroid are skipped
and reported, never filled in.

Raw API responses are saved untouched to data/raw/caladapt_exheat/<scenario>/<zip>.json
and reused on re-runs. Output: data/processed/heat_days_la.csv (long format:
zip, scenario, year, extreme_heat_days).
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.parse
import urllib.request

import pandas as pd

API = "https://api.cal-adapt.org/api/series/{slug}/events/?g={geom}&format=json"
SCENARIOS = {"rcp45": "exheat_year_ens32avg_rcp45", "rcp85": "exheat_year_ens32avg_rcp85"}
RAW = pathlib.Path("data/raw/caladapt_exheat")
OUT = pathlib.Path("data/processed/heat_days_la.csv")


def fetch(slug: str, lon: float, lat: float) -> dict:
    geom = urllib.parse.quote(f"POINT({lon} {lat})")
    url = API.format(slug=slug, geom=geom)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def main() -> None:
    geo = pd.read_csv("data/processed/features_ces_geo.csv", dtype={"zip": str})
    geo["zip"] = geo["zip"].str.zfill(5)
    missing = geo[geo["lat"].isna() | geo["lon"].isna()]["zip"].tolist()
    geo = geo.dropna(subset=["lat", "lon"])

    rows = []
    for scen, slug in SCENARIOS.items():
        d = RAW / scen
        d.mkdir(parents=True, exist_ok=True)
        for i, r in enumerate(geo.itertuples(index=False), 1):
            f = d / f"{r.zip}.json"
            if not f.exists():
                payload = fetch(slug, round(r.lon, 6), round(r.lat, 6))
                payload["_query"] = {"slug": slug, "lon": r.lon, "lat": r.lat,
                                     "retrieved": time.strftime("%Y-%m-%d")}
                f.write_text(json.dumps(payload))
                time.sleep(0.15)
            p = json.loads(f.read_text())
            for ts, v in zip(p["index"], p["data"]):
                rows.append({"zip": r.zip, "scenario": scen, "year": int(ts[:4]),
                             "extreme_heat_days": v})
            if i % 50 == 0:
                print(f"  {scen}: {i}/{len(geo)}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    nulls = out["extreme_heat_days"].isna().sum()
    print(f"wrote {OUT}: {len(out)} rows, {out['zip'].nunique()} ZIPs, "
          f"null values={nulls}")
    print(f"ZIPs skipped (no centroid): {missing}")


if __name__ == "__main__":
    main()
