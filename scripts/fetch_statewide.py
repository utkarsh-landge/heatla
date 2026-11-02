"""Step 1 (statewide) - build the California-wide training table.

Target : UCLA Heat Maps excess ER rate per 10,000, every California ZIP, all four
         CalHeatScore (CHS) levels, Years = 2008-2018. One row per ZIP x CHS level.
Features: CHS level (heat intensity) + CalEnviroScreen 4.0 tract features aggregated
         to ZIP by population weight + population density + ZCTA centroid.

No Census API key is required: all social/health/pollution features come from the
public CalEnviroScreen layer. ACS enrichment is a later, optional step.

Writes:
  data/raw/ca_excess_er_zip.csv          - every CA zip_ER row (untouched)
  data/raw/ces40_ca_tracts.csv           - every CA CES tract row (untouched)
  data/processed/features_ces_ca.csv     - CES aggregated to ZIP (pop-weighted)
  data/processed/model_table_ca.csv      - target + features, one row per ZIP x CHS

NO values are invented, imputed or interpolated. Missing stays blank.
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

GAZ_URL = ("https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
           "2023_Gazetteer/2023_Gaz_zcta_national.zip")

# CalEnviroScreen fields we keep (raw name -> output name). Percentiles handled apart.
CES_FIELDS = {
    "ZIP": "zip", "TotPop19": "pop", "PM2_5": "pm25", "Ozone": "ozone",
    "Asthma": "asthma_ed_per10k", "Cardiovas": "cardiovascular_ed_per10k",
    "Poverty": "poverty_pct", "Elderly65": "elderly65_pct", "Educatn": "edu_lt_hs_pct",
    "Ling_Isol": "ling_isol_pct", "Unempl": "unemployment_pct", "HousBurd": "housing_burden_pct",
    "CIscoreP": "ces4_percentile",
}
# features fed to the model (ces4_percentile stays out - baseline comparator)
CES_FEATURES = [v for k, v in CES_FIELDS.items() if v not in ("zip", "pop", "ces4_percentile")]


def _w(path: pathlib.Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- target
def fetch_target() -> list[dict]:
    print("target: pulling statewide zip_ER (CHS 1-4, 2008-2018, Rate + Number)...")
    where = "Years='2008-2018'"
    rate = arcgis.query_all("zip_ER", f"{where} AND NumRate='Rate'", out_fields="*")
    num = arcgis.query_all("zip_ER", f"{where} AND NumRate='Number'", out_fields="*")
    numkey = {(r["zip"], r["categry"]): r.get("excs_ER") for r in num}
    _w(RAW / "ca_excess_er_zip.csv", sorted({k for r in rate for k in r}), rate)
    out = []
    for r in rate:
        z, chs = r["zip"], r["categry"]
        out.append({
            "zip": str(z).zfill(5), "chs_level": int(chs) if chs is not None else None,
            "excess_er_rate_per_10k": r.get("excs_ER"),
            "excess_er_number": numkey.get((z, chs)),
            "population": r.get("popultn"), "n_heat_days": r.get("n_ht_dy"),
            "county": r.get("cnty_nm"), "years": "2008-2018",
        })
    print(f"  target rows: {len(out)} ({len({r['zip'] for r in out})} ZIPs x CHS levels)")
    return out


# ---------------------------------------------------------------- CES -> ZIP
def fetch_ces_zip() -> dict[str, dict]:
    print("features: pulling statewide CalEnviroScreen tracts...")
    tracts = arcgis.query_all("calenviroscreen_test3", "1=1",
                              out_fields=",".join(CES_FIELDS))
    _w(RAW / "ces40_ca_tracts.csv", list(CES_FIELDS), tracts)
    print(f"  CES tracts: {len(tracts)}")

    # population-weighted aggregation tract -> ZIP
    agg: dict[str, dict] = {}
    for t in tracts:
        z = t.get("ZIP")
        if z is None:
            continue
        z = str(int(z)).zfill(5) if str(z).replace(".", "").isdigit() else str(z)
        pop = t.get("TotPop19") or 0
        a = agg.setdefault(z, {"zip": z, "_wsum": {}, "_w": {}, "ces_pop": 0.0})
        a["ces_pop"] += pop
        for raw, out in CES_FIELDS.items():
            if out in ("zip", "pop"):
                continue
            v = t.get(raw)
            if v is None or pop <= 0:
                continue
            a["_wsum"][out] = a["_wsum"].get(out, 0.0) + v * pop
            a["_w"][out] = a["_w"].get(out, 0.0) + pop

    rows = {}
    for z, a in agg.items():
        row = {"zip": z, "ces_pop": round(a["ces_pop"], 1)}
        for out in list(CES_FEATURES) + ["ces4_percentile"]:
            w = a["_w"].get(out, 0.0)
            row[out] = round(a["_wsum"][out] / w, 4) if w > 0 else ""
        rows[z] = row
    _w(PROC / "features_ces_ca.csv",
       ["zip", "ces_pop"] + CES_FEATURES + ["ces4_percentile"], list(rows.values()))
    print(f"  CES ZIPs: {len(rows)}")
    return rows


# ---------------------------------------------------------------- geography
def fetch_gazetteer() -> dict[str, dict]:
    print("geography: Census Gazetteer 2023 ZCTA...")
    path = RAW / "2023_Gaz_zcta_national.txt"
    if not path.exists():
        with urllib.request.urlopen(GAZ_URL, timeout=120) as resp:
            z = zipfile.ZipFile(io.BytesIO(resp.read()))
            name = [n for n in z.namelist() if n.endswith(".txt")][0]
            path.write_bytes(z.read(name))
    geo = {}
    with path.open(encoding="latin-1") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            row = {k.strip(): v for k, v in row.items()}
            zc = row["GEOID"].zfill(5)
            try:
                geo[zc] = {"lat": float(row["INTPTLAT"]), "lon": float(row["INTPTLONG"]),
                           "aland_sqmi": float(row["ALAND_SQMI"])}
            except ValueError:
                continue
    print(f"  ZCTAs: {len(geo)}")
    return geo


# ---------------------------------------------------------------- join
def main() -> None:
    target = fetch_target()
    ces = fetch_ces_zip()
    geo = fetch_gazetteer()

    header = (["zip", "chs_level", "county", "years", "excess_er_rate_per_10k",
               "excess_er_number", "population", "n_heat_days", "lat", "lon",
               "aland_sqmi", "pop_density_per_sqmi"] + CES_FEATURES
              + ["ces4_percentile", "ces_pop"])
    out = []
    for t in target:
        z = t["zip"]
        row = dict(t)
        g = geo.get(z, {})
        row["lat"] = g.get("lat", "")
        row["lon"] = g.get("lon", "")
        row["aland_sqmi"] = g.get("aland_sqmi", "")
        pop = t.get("population")
        row["pop_density_per_sqmi"] = (round(pop / g["aland_sqmi"], 2)
                                       if g.get("aland_sqmi") and pop else "")
        c = ces.get(z, {})
        for k in CES_FEATURES + ["ces4_percentile", "ces_pop"]:
            row[k] = c.get(k, "")
        out.append(row)
    _w(PROC / "model_table_ca.csv", header, out)
    n_full = sum(1 for r in out if r["excess_er_rate_per_10k"] not in (None, "")
                 and r["lat"] != "" and all(r[f] != "" for f in CES_FEATURES))
    print(f"\nmodel_table_ca.csv: {len(out)} rows, {n_full} complete-case")
    print(f"retrieved {RETRIEVED}")


if __name__ == "__main__":
    main()
