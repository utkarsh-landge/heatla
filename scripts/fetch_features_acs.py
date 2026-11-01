"""Step 2b - Census ACS 2022 5-year features at ZCTA level.

Requires a free Census Data API key in env var CENSUS_API_KEY
(https://api.census.gov/data/key_signup.html). The key is read from the
environment only; it is never written to a file or committed.

Variables (ACS 2022 5-year):
  Detailed tables (acs5):
    B19013_001E  median household income (dollars)
    B01003_001E  total population
    B17001_001E / B17001_002E   poverty universe / below poverty  -> % poverty
    B01001 (age/sex)            65+ counts -> % age 65+
    B25003_001E / B25003_003E   occupied / renter-occupied -> % renters
    B25044_001E / _003E / _010E no-vehicle households -> % no vehicle
    C24050_001E / C24050_003E   civ. employed / construction industry -> % construction
  Subject table (acs5/subject):
    S2701_C05_001E  percent uninsured (civilian noninstitutionalized)

Population density = total population / ZCTA land area (Gazetteer, sq mi).

Writes:
  data/raw/acs5_2022_zcta_la.json     - raw API rows (untouched)
  data/processed/features_acs.csv     - one row per target ZIP
  data/processed/model_table.csv      - target + all features joined (final Step 2 table)

NOTE: "% living alone age 65+" from the original feature wish-list is intentionally
omitted: no single ACS variable maps to it unambiguously, and the hard rules forbid
guessing a column's meaning. It can be added later once the exact table is confirmed.
No values are invented. Missing stays blank.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

RAW = pathlib.Path("data/raw")
PROC = pathlib.Path("data/processed")
RETRIEVED = dt.date.today().isoformat()
KEY = os.environ.get("CENSUS_API_KEY")

ACS = "https://api.census.gov/data/2022/acs/acs5"
ACS_SUBJ = "https://api.census.gov/data/2022/acs/acs5/subject"

AGE65 = [  # B01001 male 65+ then female 65+
    "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",
    "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",
]
DETAIL_VARS = [
    "B19013_001E", "B01003_001E",
    "B17001_001E", "B17001_002E",
    "B01001_001E", *AGE65,
    "B25003_001E", "B25003_003E",
    "B25044_001E", "B25044_003E", "B25044_010E",
    "C24050_001E", "C24050_003E",
]


def _fetch(base: str, variables: list[str], zips: list[int]) -> dict[str, dict]:
    """Query the API for the given variables, chunking the ZIP list for URL length."""
    out: dict[str, dict] = {}
    for i in range(0, len(zips), 40):
        chunk = zips[i : i + 40]
        params = {
            "get": ",".join(variables),
            "for": "zip code tabulation area:" + ",".join(f"{z:05d}" for z in chunk),
            "key": KEY,
        }
        url = base + "?" + urllib.parse.urlencode(params)
        raw = urllib.request.urlopen(url, timeout=120).read()
        if b"Invalid Key" in raw or b"Missing Key" in raw:
            raise SystemExit("Census API key invalid/missing. Set CENSUS_API_KEY.")
        data = json.loads(raw)
        header, *rows = data
        for row in rows:
            rec = dict(zip(header, row))
            out[rec["zip code tabulation area"]] = rec
    return out


def _num(rec: dict, var: str) -> float | None:
    """Parse an ACS value, treating Census null/annotation codes as missing."""
    if rec is None:
        return None
    v = rec.get(var)
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    # ACS uses large negative sentinels (e.g. -666666666) for suppressed values
    if f <= -666666:
        return None
    return f


def _pct(num, den):
    if num is None or den in (None, 0):
        return None
    return round(100.0 * num / den, 3)


def main() -> None:
    if not KEY:
        raise SystemExit("CENSUS_API_KEY not set.")
    with (PROC / "target.csv").open() as fh:
        target = list(csv.DictReader(fh))
    zips = [int(r["zip"]) for r in target]

    detail = _fetch(ACS, DETAIL_VARS, zips)
    subject = _fetch(ACS_SUBJ, ["S2701_C05_001E"], zips)
    (RAW / "acs5_2022_zcta_la.json").write_text(
        json.dumps({"detail": detail, "subject": subject, "retrieved": RETRIEVED}, indent=0)
    )

    # geography (for density) from the CES+geo table already built
    geo = {}
    with (PROC / "features_ces_geo.csv").open() as fh:
        for r in csv.DictReader(fh):
            geo[int(r["zip"])] = r

    rows = []
    for z in zips:
        d = detail.get(f"{z:05d}")
        s = subject.get(f"{z:05d}")
        total_pop = _num(d, "B01003_001E")
        age65 = sum(v for v in (_num(d, a) for a in AGE65) if v is not None) if d else None
        age_univ = _num(d, "B01001_001E")
        aland = geo.get(z, {}).get("aland_sqmi")
        aland = float(aland) if aland not in (None, "", "None") else None
        rows.append(
            {
                "zip": z,
                "total_pop": total_pop,
                "median_hh_income": _num(d, "B19013_001E"),
                "pct_poverty": _pct(_num(d, "B17001_002E"), _num(d, "B17001_001E")),
                "pct_age_65plus": _pct(age65, age_univ),
                "pct_renters": _pct(_num(d, "B25003_003E"), _num(d, "B25003_001E")),
                "pct_no_vehicle": _pct(
                    (_num(d, "B25044_003E") or 0) + (_num(d, "B25044_010E") or 0)
                    if d else None,
                    _num(d, "B25044_001E"),
                ),
                "pct_uninsured": _num(s, "S2701_C05_001E"),
                "pct_construction": _pct(_num(d, "C24050_003E"), _num(d, "C24050_001E")),
                "pop_density_per_sqmi": round(total_pop / aland, 1)
                if (total_pop is not None and aland) else None,
            }
        )

    with (PROC / "features_acs.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    build_model_table(target, rows, geo)
    report(rows)


def build_model_table(target, acs_rows, geo) -> None:
    """Join target + CES/geo + ACS into the final one-row-per-ZIP modeling table."""
    acs = {r["zip"]: r for r in acs_rows}
    ces_cols = ["pm25", "ozone", "asthma_ed_per10k", "cardiovascular_ed_per10k",
                "ces4_percentile", "lat", "lon", "aland_sqmi"]
    out = []
    for t in target:
        z = int(t["zip"])
        g = geo.get(z, {})
        a = acs.get(z, {})
        row = {
            "zip": z,
            "excess_er_rate_per_10k": t["excess_er_rate_per_10k"],
            "excess_er_number": t["excess_er_number"],
            "ucla_population": t["population"],
            "is_ucla_campus_90095": t["is_ucla_campus_90095"],
        }
        for c in ces_cols:
            v = g.get(c)
            row[c] = v if v not in ("", "None") else None
        for c in ["total_pop", "median_hh_income", "pct_poverty", "pct_age_65plus",
                  "pct_renters", "pct_no_vehicle", "pct_uninsured", "pct_construction",
                  "pop_density_per_sqmi"]:
            row[c] = a.get(c)
        out.append(row)
    with (PROC / "model_table.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)


def report(rows) -> None:
    def miss(c):
        return sum(1 for r in rows if r[c] is None)
    print("\n============ STEP 2b (ACS 2022 5-year) ============")
    print(f"Retrieved: {RETRIEVED}  | ZIPs: {len(rows)}")
    for c in rows[0]:
        if c == "zip":
            continue
        vals = [r[c] for r in rows if r[c] is not None]
        if vals:
            print(f"  {c:22s} missing {miss(c):3d}  min {min(vals):.1f}  max {max(vals):.1f}")
        else:
            print(f"  {c:22s} missing {miss(c):3d}  (all missing)")
    print("Sample:", rows[0])
    print("===================================================\n")


if __name__ == "__main__":
    main()
