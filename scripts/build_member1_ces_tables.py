"""Member 1 - build corrected statewide model tables for CalEnviroScreen 4.0 and 3.0.

Why this exists
  CalEnviroScreen marks a missing tract value with the sentinel -999. The original
  aggregation (scripts/fetch_statewide.py) averaged those sentinels into the ZIP-level
  population-weighted means, producing impossible values (e.g. negative percentages).
  This script treats -999 as missing BEFORE aggregating, per feature and per tract.

What it builds (the original data/processed/model_table_ca.csv is not modified)
  data/processed/model_table_ca_ces40_fixed.csv  CES 4.0 inputs, sentinel-corrected
  data/processed/model_table_ca_ces30.csv        CES 3.0 inputs (2011-2015 vintage)
  results/member1/input_checks/*.csv             audit tables

Inputs
  data/raw/ces40_ca_tracts.csv                     CES 4.0 tracts (project snapshot)
  data/raw/ces30/ces30_results_june2018.csv        CES 3.0 results, June 2018 update
  data/raw/ces30/shp/CES3Results.dbf               CES 3.0 shapefile attributes; used ONLY
                                                   for "Elderly > 65 (%)", which the CSV lacks
  Both 3.0 files are published by OEHHA on data.ca.gov (dataset calenviroscreen-3-0-results).

Label, population, centroid and density columns are copied unchanged from the original
table, so the three tables differ only in their CalEnviroScreen inputs.

Run:  .venv/bin/python scripts/build_member1_ces_tables.py
"""
from __future__ import annotations

import pathlib
import struct

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

RAW = pathlib.Path("data/raw")
PROC = pathlib.Path("data/processed")
CHECK = pathlib.Path("results/member1/input_checks")
SENTINEL = -999

FEATURES = ["pm25", "ozone", "asthma_ed_per10k", "cardiovascular_ed_per10k", "poverty_pct",
            "elderly65_pct", "edu_lt_hs_pct", "ling_isol_pct", "unemployment_pct",
            "housing_burden_pct"]
BASE_COLS = ["zip", "chs_level", "county", "years", "excess_er_rate_per_10k",
             "excess_er_number", "population", "n_heat_days", "lat", "lon", "aland_sqmi",
             "pop_density_per_sqmi"]

CES40_MAP = {"PM2_5": "pm25", "Ozone": "ozone", "Asthma": "asthma_ed_per10k",
             "Cardiovas": "cardiovascular_ed_per10k", "Poverty": "poverty_pct",
             "Elderly65": "elderly65_pct", "Educatn": "edu_lt_hs_pct",
             "Ling_Isol": "ling_isol_pct", "Unempl": "unemployment_pct",
             "HousBurd": "housing_burden_pct", "CIscoreP": "ces4_percentile"}
CES30_MAP = {"PM2.5": "pm25", "Ozone": "ozone", "Asthma": "asthma_ed_per10k",
             "Cardiovascular Disease": "cardiovascular_ed_per10k", "Poverty": "poverty_pct",
             "Elderly65_shp": "elderly65_pct", "Education": "edu_lt_hs_pct",
             "Linguistic Isolation": "ling_isol_pct", "Unemployment": "unemployment_pct",
             "Housing Burden": "housing_burden_pct", "CES 3.0 Percentile": "ces3_percentile"}


def zip5(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("Int64").astype(str).str.zfill(5)


def read_dbf(path: pathlib.Path, wanted: list[str]) -> pd.DataFrame:
    """Minimal dBase reader (no extra dependency) for a few numeric fields."""
    with path.open("rb") as f:
        nrec, hlen, rlen = struct.unpack("<xxxxIHH20x", f.read(32))
        fields, off = [], 1
        while True:
            b = f.read(32)
            if b[0] == 0x0D:
                break
            name = b[:11].split(b"\x00")[0].decode()
            fields.append((name, off, b[16]))
            off += b[16]
        f.seek(hlen)
        out = {w: [] for w in wanted}
        for _ in range(nrec):
            rec = f.read(rlen)
            for name, o, ln in fields:
                if name in out:
                    txt = rec[o:o + ln].decode("latin-1").strip()
                    out[name].append(float(txt) if txt else np.nan)
    return pd.DataFrame(out)


def clean_sentinel(tracts: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replace the -999 sentinel with NaN; return cleaned frame and a per-column audit."""
    t = tracts.copy()
    rows = []
    for c in cols:
        t[c] = pd.to_numeric(t[c], errors="coerce")
        n_sent = int((t[c] == SENTINEL).sum())
        n_other_neg = int(((t[c] < 0) & (t[c] != SENTINEL)).sum())
        n_blank = int(t[c].isna().sum())
        t.loc[t[c] == SENTINEL, c] = np.nan
        rows.append({"source_field": c, "tracts": len(t), "tracts_sentinel_-999": n_sent,
                     "tracts_blank": n_blank, "tracts_other_negative": n_other_neg,
                     "tracts_missing_after_cleaning": int(t[c].isna().sum())})
    return t, pd.DataFrame(rows)


def aggregate(tracts: pd.DataFrame, pop_col: str, fmap: dict[str, str]) -> pd.DataFrame:
    """Population-weighted ZIP mean per feature, over tracts that HAVE a value.

    A tract contributes to a feature only if its value is present and its population
    is positive, so a missing value neither enters the numerator nor the weight.
    """
    t = tracts[tracts["zip"].notna()].copy()
    pop = pd.to_numeric(t[pop_col], errors="coerce").fillna(0.0)
    out = pd.DataFrame({"zip": sorted(t["zip"].unique())}).set_index("zip")
    out["ces_pop"] = pop.groupby(t["zip"]).sum()
    out["n_tracts"] = t.groupby("zip").size()
    for raw, name in fmap.items():
        ok = t[raw].notna() & (pop > 0)
        w = pop.where(ok, 0.0)
        num = (t[raw].fillna(0.0) * w).groupby(t["zip"]).sum()
        den = w.groupby(t["zip"]).sum()
        out[name] = (num / den.where(den > 0)).round(4)
        out[f"n_tracts_used__{name}"] = ok.groupby(t["zip"]).sum()
    return out.reset_index()


def build_table(base: pd.DataFrame, feats: pd.DataFrame, pct_col: str) -> pd.DataFrame:
    keep = ["zip"] + FEATURES + [pct_col, "ces_pop"]
    return base.merge(feats[keep], on="zip", how="left")


def main() -> None:
    CHECK.mkdir(parents=True, exist_ok=True)
    orig = pd.read_csv(PROC / "model_table_ca.csv")
    orig["zip"] = zip5(orig["zip"])
    base = orig[BASE_COLS].copy()

    # ------------------------------------------------------------ CES 4.0, corrected
    t4 = pd.read_csv(RAW / "ces40_ca_tracts.csv")
    t4["zip"] = zip5(t4["ZIP"])
    t4c, audit4 = clean_sentinel(t4, list(CES40_MAP))
    audit4.insert(0, "version", "CES 4.0")
    f4 = aggregate(t4c, "TotPop19", CES40_MAP)
    f4.to_csv(PROC / "features_ces40_fixed_ca.csv", index=False)
    m4 = build_table(base, f4, "ces4_percentile")
    m4.to_csv(PROC / "model_table_ca_ces40_fixed.csv", index=False)

    # ------------------------------------------------------------ CES 3.0
    t3 = pd.read_csv(RAW / "ces30" / "ces30_results_june2018.csv")
    t3.columns = [" ".join(c.split()) for c in t3.columns]
    shp = read_dbf(RAW / "ces30" / "shp" / "CES3Results.dbf", ["Tract_1", "Elderly___"])
    shp["Census Tract"] = shp["Tract_1"].round().astype("int64")
    n_before = len(t3)
    t3 = t3.merge(shp[["Census Tract", "Elderly___"]].rename(
        columns={"Elderly___": "Elderly65_shp"}), on="Census Tract", how="left",
        validate="one_to_one")
    assert len(t3) == n_before
    elderly_joined = int(t3["Elderly65_shp"].notna().sum())
    t3["zip"] = zip5(t3["ZIP"])
    t3c, audit3 = clean_sentinel(t3, list(CES30_MAP))
    audit3.insert(0, "version", "CES 3.0")
    f3 = aggregate(t3c, "Total Population", CES30_MAP)
    f3.to_csv(PROC / "features_ces30_ca.csv", index=False)
    m3 = build_table(base, f3, "ces3_percentile")
    m3.to_csv(PROC / "model_table_ca_ces30.csv", index=False)

    pd.concat([audit4, audit3]).to_csv(CHECK / "sentinel_audit_tracts.csv", index=False)

    # ------------------------------------------------------------ checks
    one = lambda d: d.drop_duplicates("zip").set_index("zip")  # noqa: E731
    o, a4, a3 = one(orig), one(m4), one(m3)
    pct_orig = "ces4_percentile"
    rows = []
    for name in FEATURES + ["percentile"]:
        c_o = pct_orig if name == "percentile" else name
        c_4 = "ces4_percentile" if name == "percentile" else name
        c_3 = "ces3_percentile" if name == "percentile" else name
        both = a4[c_4].notna() & a3[c_3].notna()
        changed = (o[c_o] - a4[c_4]).abs() > 1e-3
        rows.append({
            "feature": name,
            "zips_original_4.0_present": int(o[c_o].notna().sum()),
            "zips_original_4.0_negative": int((o[c_o] < 0).sum()),
            "zips_changed_by_sentinel_fix": int((changed & o[c_o].notna() & a4[c_4].notna()).sum()),
            "zips_missing_after_fix_4.0": int(a4[c_4].isna().sum()),
            "zips_missing_3.0": int(a3[c_3].isna().sum()),
            "zips_present_both": int(both.sum()),
            "median_4.0_fixed": round(float(a4.loc[both, c_4].median()), 4),
            "median_3.0": round(float(a3.loc[both, c_3].median()), 4),
            "min_4.0_fixed": round(float(a4[c_4].min()), 4),
            "min_3.0": round(float(a3[c_3].min()), 4),
            "spearman_3.0_vs_4.0": round(float(spearmanr(a4.loc[both, c_4],
                                                         a3.loc[both, c_3]).statistic), 3),
        })
    cmp = pd.DataFrame(rows)
    cmp.to_csv(CHECK / "feature_comparison_zip_level.csv", index=False)

    affected = (o[FEATURES + [pct_orig]] < 0).any(axis=1)
    la = o["county"] == "Los Angeles"
    summary = pd.DataFrame([
        {"check": "ZIPs in raw statewide table", "value": int(len(o))},
        {"check": "ZIPs with at least one negative CES value in ORIGINAL table",
         "value": int(affected.sum())},
        {"check": "  of which Los Angeles County", "value": int((affected & la).sum())},
        {"check": "ZIPs with all 10 CES inputs present: original 4.0",
         "value": int(o[FEATURES].notna().all(axis=1).sum())},
        {"check": "ZIPs with all 10 CES inputs present: corrected 4.0",
         "value": int(a4[FEATURES].notna().all(axis=1).sum())},
        {"check": "ZIPs with all 10 CES inputs present: 3.0",
         "value": int(a3[FEATURES].notna().all(axis=1).sum())},
        {"check": "ZIPs with no CES input at all: corrected 4.0",
         "value": int(a4[FEATURES].isna().all(axis=1).sum())},
        {"check": "ZIPs with no CES input at all: 3.0",
         "value": int(a3[FEATURES].isna().all(axis=1).sum())},
        {"check": "ZIPs with some but not all CES inputs: corrected 4.0",
         "value": int((a4[FEATURES].isna().any(axis=1) & a4[FEATURES].notna().any(axis=1)).sum())},
        {"check": "ZIPs with some but not all CES inputs: 3.0",
         "value": int((a3[FEATURES].isna().any(axis=1) & a3[FEATURES].notna().any(axis=1)).sum())},
        {"check": "CES 3.0 tracts", "value": int(len(t3))},
        {"check": "CES 3.0 tracts with Elderly value joined from shapefile",
         "value": elderly_joined},
        {"check": "Any negative value left in corrected 4.0 table",
         "value": int((a4[FEATURES + ['ces4_percentile']] < 0).any(axis=1).sum())},
        {"check": "Any negative value in 3.0 table",
         "value": int((a3[FEATURES + ['ces3_percentile']] < 0).any(axis=1).sum())},
    ])
    summary.to_csv(CHECK / "table_checks.csv", index=False)

    # base columns must be identical across the three tables
    for m in (m4, m3):
        assert len(m) == len(orig)
        pd.testing.assert_frame_equal(m[BASE_COLS].reset_index(drop=True),
                                      orig[BASE_COLS].reset_index(drop=True))
    pd.set_option("display.width", 250)
    print(pd.concat([audit4, audit3]).to_string(index=False))
    print(cmp.to_string(index=False))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
