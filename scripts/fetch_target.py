"""Step 1 - pull the real UCLA Heat Maps target (excess ER visits) for LA County.

Source: UCLA Heat Maps ArcGIS Experience app
  https://experience.arcgis.com/experience/4c158842b5c94857a06c3a85c7aa02de
Hosted layers (services7.arcgis.com/2hYXmwteFLemN5bW):
  - zip_ER                               : excess ER by ZIP, by CalHeatScore (CHS 1-4),
                                           Rate/Number, year ranges 2008-2018 & 2014-2018
  - Daily_Excess_ER_ZIPCODE_with_county  : daily excess ER rate/number per ZIP (secondary)

Primary modeling target (confirmed with user, 2026-10-28):
  zip_ER, CalHeatScore category 4 (most extreme heat), Years = 2008-2018,
  for Los Angeles County. Both the Rate (per 10,000) and Number variants are kept.

Writes:
  data/raw/ucla_excess_er_zip.csv        - every LA zip_ER row, untouched
  data/raw/ucla_excess_er_zip.meta.json  - layer field definitions (provenance)
  data/raw/ucla_daily_excess_er_zip.csv  - LA Daily layer rows (secondary, untouched)
  data/processed/target.csv              - one row per ZIP, CHS-4 2008-2018, labeled
  data/processed/target_all_chs.csv      - one row per ZIP x CHS level (sensitivity)

NO values are invented, imputed or interpolated. Anything missing is left blank.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from heatla import arcgis  # noqa: E402

RAW = pathlib.Path("data/raw")
PROC = pathlib.Path("data/processed")
COUNTY = "Los Angeles"
PRIMARY_YEARS = "2008-2018"
PRIMARY_CHS = 4
UCLA_CAMPUS_ZIP = 90095  # flagged: ER patients may be mis-attributed here

RETRIEVED = dt.date.today().isoformat()


def _write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    if not rows:
        raise SystemExit(f"Refusing to write empty file: {path}")
    cols = list(rows[0].keys())
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def fetch_raw() -> list[dict]:
    """Pull every LA County zip_ER row, save untouched, return the rows."""
    where = f"cnty_nm='{COUNTY}'"
    n = arcgis.count("zip_ER", where)
    rows = arcgis.query_all("zip_ER", where=where)
    assert len(rows) == n, f"paging mismatch: expected {n}, got {len(rows)}"
    _write_csv(RAW / "ucla_excess_er_zip.csv", rows)
    meta = arcgis.layer_metadata("zip_ER")
    (RAW / "ucla_excess_er_zip.meta.json").write_text(
        json.dumps(
            {
                "retrieved": RETRIEVED,
                "service": f"{arcgis.UCLA_SERVICES}/zip_ER/FeatureServer/0",
                "county_filter": where,
                "row_count": len(rows),
                "fields": meta.get("fields"),
                "maxRecordCount": meta.get("maxRecordCount"),
            },
            indent=2,
        )
    )
    return rows


def fetch_daily_reference() -> list[dict]:
    """Pull the LA Daily-layer rows (secondary reference), save untouched."""
    where = f"county_2='{COUNTY}'"
    rows = arcgis.query_all("Daily_Excess_ER_ZIPCODE_with_county", where=where)
    _write_csv(RAW / "ucla_daily_excess_er_zip.csv", rows)
    return rows


def build_targets(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Pivot raw rows into the primary target and the all-CHS sensitivity table."""
    # key: (zip, chs, years) -> {rate, number, pop, heat_days}
    by_key: dict[tuple[int, int, str], dict] = {}
    for r in rows:
        zc = r.get("zip")
        chs = r.get("categry")
        yrs = r.get("Years")
        if zc is None or chs is None or yrs is None:
            continue
        key = (int(zc), int(chs), str(yrs))
        rec = by_key.setdefault(
            key,
            {
                "zip": int(zc),
                "chs_category": int(chs),
                "years": str(yrs),
                "population": r.get("popultn"),
                "n_heat_days": r.get("n_ht_dy"),
                "excess_er_rate_per_10k": None,
                "excess_er_number": None,
            },
        )
        value = r.get("excs_ER")
        if r.get("NumRate") == "Rate":
            rec["excess_er_rate_per_10k"] = value
        elif r.get("NumRate") == "Number":
            rec["excess_er_number"] = value

    all_chs = sorted(by_key.values(), key=lambda d: (d["zip"], d["years"], d["chs_category"]))
    for rec in all_chs:
        rec["is_ucla_campus_90095"] = int(rec["zip"] == UCLA_CAMPUS_ZIP)

    primary = [
        {
            "zip": rec["zip"],
            "excess_er_rate_per_10k": rec["excess_er_rate_per_10k"],
            "excess_er_number": rec["excess_er_number"],
            "population": rec["population"],
            "n_heat_days": rec["n_heat_days"],
            "chs_category": rec["chs_category"],
            "years": rec["years"],
            "is_ucla_campus_90095": rec["is_ucla_campus_90095"],
        }
        for rec in all_chs
        if rec["chs_category"] == PRIMARY_CHS and rec["years"] == PRIMARY_YEARS
    ]
    zips = [p["zip"] for p in primary]
    assert len(zips) == len(set(zips)), "duplicate ZIP in primary target"
    primary.sort(key=lambda d: d["zip"])
    return primary, all_chs


def summary(primary: list[dict], daily: list[dict]) -> None:
    rates = [p["excess_er_rate_per_10k"] for p in primary if p["excess_er_rate_per_10k"] is not None]
    nums = [p["excess_er_number"] for p in primary if p["excess_er_number"] is not None]
    miss_rate = sum(1 for p in primary if p["excess_er_rate_per_10k"] is None)
    miss_num = sum(1 for p in primary if p["excess_er_number"] is None)
    print("\n================ STEP 1 TARGET SUMMARY ================")
    print(f"Source: UCLA Heat Maps zip_ER, CHS-{PRIMARY_CHS}, {PRIMARY_YEARS}, {COUNTY} County")
    print(f"Retrieved: {RETRIEVED}")
    print(f"Target ZIP rows: {len(primary)}")
    print(f"  excess_er_rate_per_10k : min {min(rates):.1f}  max {max(rates):.1f}  "
          f"mean {sum(rates)/len(rates):.2f}  (missing {miss_rate})")
    print(f"  excess_er_number       : min {min(nums):.1f}  max {max(nums):.1f}  "
          f"mean {sum(nums)/len(nums):.2f}  (missing {miss_num})")
    print(f"  unit (rate): excess ER visits per 10,000 persons, per the layer 'Rate (per 10,000)'")
    print(f"Secondary Daily-layer rows pulled: {len(daily)}")
    campus = [p for p in primary if p["is_ucla_campus_90095"]]
    print(f"UCLA campus ZIP 90095 present: {'yes' if campus else 'no'}"
          + (f" (rate {campus[0]['excess_er_rate_per_10k']})" if campus else ""))
    print("Sample rows:")
    for p in primary[:5]:
        print("   ", p)
    print("======================================================\n")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    rows = fetch_raw()
    daily = fetch_daily_reference()
    primary, all_chs = build_targets(rows)
    _write_csv(PROC / "target.csv", primary)
    _write_csv(PROC / "target_all_chs.csv", all_chs)
    summary(primary, daily)


if __name__ == "__main__":
    main()
