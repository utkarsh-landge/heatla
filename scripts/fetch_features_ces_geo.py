"""Step 2a - features that need NO API key: CalEnviroScreen 4.0 + Census Gazetteer.

CalEnviroScreen 4.0 (UCLA-hosted copy, calenviroscreen_test3 FeatureServer):
  tract-level rows, each tagged with a ZIP. Aggregated to ZIP by population
  weight (TotPop19). Provides pollution, health and some social features, plus
  the CES percentile used later as a baseline index.
Census Gazetteer 2023 (ZCTA national file): centroid lat/lon and land area.

Writes:
  data/raw/ces40_la_tracts.csv            - raw CES tract rows for LA (untouched)
  data/raw/2023_Gaz_zcta_national.txt     - raw Gazetteer file (untouched)
  data/processed/features_ces_geo.csv     - one row per ZIP (CES + geography)

Population-weighted averaging of CES percentiles is an approximation; it is
documented in DATA_SOURCES.md. No values are invented. Missing stays missing.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import pathlib
import sys
import urllib.request
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from heatla import arcgis  # noqa: E402

RAW = pathlib.Path("data/raw")
PROC = pathlib.Path("data/processed")
RETRIEVED = dt.date.today().isoformat()

# CES raw fields pulled (keep the names as the layer defines them).
CES_FIELDS = [
    "ZIP", "Tract", "County", "TotPop19",
    "PM2_5", "Ozone",              # pollution (raw values)
    "Asthma", "Cardiovas",         # health (ED visits per 10k, age-adjusted)
    "Poverty", "Elderly65",        # social / demographic (%)
    "CIscoreP",                    # CES 4.0 percentile (baseline index)
]
GAZ_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_zcta_national.zip"


def _wmean(pairs: list[tuple[float, float]]) -> float | None:
    """Population-weighted mean of (value, weight), ignoring missing values."""
    num = den = 0.0
    for v, w in pairs:
        if v is None or w is None:
            continue
        num += v * w
        den += w
    return round(num / den, 4) if den > 0 else None


def fetch_ces() -> dict[int, dict]:
    rows = arcgis.query_all(
        "calenviroscreen_test3",
        where="County='Los Angeles'",
        out_fields=",".join(CES_FIELDS),
        page=2000,
    )
    # save raw
    with (RAW / "ces40_la_tracts.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by_zip: dict[int, list[dict]] = {}
    for r in rows:
        z = r.get("ZIP")
        if z is None:
            continue
        by_zip.setdefault(int(z), []).append(r)

    out: dict[int, dict] = {}
    for z, recs in by_zip.items():
        pop = sum(r["TotPop19"] for r in recs if r.get("TotPop19"))
        out[z] = {
            "zip": z,
            "ces_pop19": pop,
            "ces_tracts": len(recs),
            "pm25": _wmean([(r.get("PM2_5"), r.get("TotPop19")) for r in recs]),
            "ozone": _wmean([(r.get("Ozone"), r.get("TotPop19")) for r in recs]),
            "asthma_ed_per10k": _wmean([(r.get("Asthma"), r.get("TotPop19")) for r in recs]),
            "cardiovascular_ed_per10k": _wmean([(r.get("Cardiovas"), r.get("TotPop19")) for r in recs]),
            "poverty_pct_ces": _wmean([(r.get("Poverty"), r.get("TotPop19")) for r in recs]),
            "elderly65_pct_ces": _wmean([(r.get("Elderly65"), r.get("TotPop19")) for r in recs]),
            "ces4_percentile": _wmean([(r.get("CIscoreP"), r.get("TotPop19")) for r in recs]),
        }
    return out


def fetch_gazetteer() -> dict[str, dict]:
    raw_zip = urllib.request.urlopen(GAZ_URL, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        name = [n for n in zf.namelist() if n.endswith(".txt")][0]
        text = zf.read(name).decode("latin-1")
    (RAW / "2023_Gaz_zcta_national.txt").write_text(text)

    out: dict[str, dict] = {}
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    for row in reader:
        row = {k.strip(): v for k, v in row.items()}
        geoid = row["GEOID"].strip()
        out[geoid] = {
            "aland_sqmi": float(row["ALAND_SQMI"]),
            "lat": float(row["INTPTLAT"]),
            "lon": float(row["INTPTLONG"].strip()),
        }
    return out


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    ces = fetch_ces()
    gaz = fetch_gazetteer()

    # target ZIPs drive the row set
    with (PROC / "target.csv").open() as fh:
        target_zips = [int(r["zip"]) for r in csv.DictReader(fh)]

    rows = []
    no_zcta = []
    for z in sorted(target_zips):
        g = gaz.get(f"{z:05d}")
        if g is None:
            no_zcta.append(z)
        c = ces.get(z, {})
        rows.append(
            {
                "zip": z,
                "lat": g["lat"] if g else None,
                "lon": g["lon"] if g else None,
                "aland_sqmi": g["aland_sqmi"] if g else None,
                "pm25": c.get("pm25"),
                "ozone": c.get("ozone"),
                "asthma_ed_per10k": c.get("asthma_ed_per10k"),
                "cardiovascular_ed_per10k": c.get("cardiovascular_ed_per10k"),
                "poverty_pct_ces": c.get("poverty_pct_ces"),
                "elderly65_pct_ces": c.get("elderly65_pct_ces"),
                "ces4_percentile": c.get("ces4_percentile"),
                "ces_pop19": c.get("ces_pop19"),
            }
        )

    with (PROC / "features_ces_geo.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # report
    def miss(col):
        return sum(1 for r in rows if r[col] is None)

    print("\n============ STEP 2a (CES + GEOGRAPHY) ============")
    print(f"Retrieved: {RETRIEVED}")
    print(f"Target ZIPs: {len(rows)}")
    print(f"ZIPs with no matching ZCTA in Gazetteer: {len(no_zcta)} -> {no_zcta}")
    for col in ["lat", "pm25", "ozone", "asthma_ed_per10k", "cardiovascular_ed_per10k",
                "poverty_pct_ces", "elderly65_pct_ces", "ces4_percentile"]:
        print(f"  missing {col}: {miss(col)}")
    print("Sample rows:")
    for r in rows[:3]:
        print("   ", r)
    print("===================================================\n")


if __name__ == "__main__":
    main()
