"""Rebuild the LA and statewide modeling tables with the CalEnviroScreen -999 fix.

Problem
  CalEnviroScreen marks a missing tract value as -999. fetch_features_ces_geo.py (LA)
  and fetch_statewide.py (California) averaged those markers into the ZIP-level
  population-weighted means, so some ZIP features are distorted or even negative.

What this script does
  1. Reads the ORIGINAL tract-level files in data/raw/ (never the processed tables as
     a source of CES values).
  2. Proves it understands the old pipeline: re-aggregating WITHOUT the fix must
     reproduce the existing processed feature files.
  3. Re-aggregates WITH the fix (see src/heatla/ces.py): -999 -> missing; missing values
     and their population weights are excluded; ZIPs with no valid tract stay empty.
  4. Writes corrected feature files and corrected modeling tables to data/corrected/.
     Only CalEnviroScreen-derived columns change; every other cell is copied verbatim.
  5. Writes a comparison of original vs corrected values and the list of affected ZIP
     codes to results/ces_sentinel_fix/.
  6. Verifies the outputs and that no original file was modified.

Nothing in data/raw/ or data/processed/ is written. No network access is needed.

Run:  .venv/bin/python scripts/build_corrected_ces_tables.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from heatla import ces  # noqa: E402

RAW = pathlib.Path("data/raw")
PROC = pathlib.Path("data/processed")
OUT = pathlib.Path("data/corrected")
REP = pathlib.Path("results/ces_sentinel_fix")
TOL = 1e-4          # the original files are rounded to 4 decimals

PIPELINES = {
    "la": {
        "label": "Los Angeles County table (Member 2 inputs)",
        "tracts": RAW / "ces40_la_tracts.csv",
        "features": PROC / "features_ces_geo.csv",
        "model": PROC / "model_table.csv",
        "features_out": OUT / "features_ces_geo_corrected.csv",
        "model_out": OUT / "model_table_corrected.csv",
        "field_map": {"PM2_5": "pm25", "Ozone": "ozone", "Asthma": "asthma_ed_per10k",
                      "Cardiovas": "cardiovascular_ed_per10k", "Poverty": "poverty_pct_ces",
                      "Elderly65": "elderly65_pct_ces", "CIscoreP": "ces4_percentile"},
        "pop_col": "ces_pop19",
    },
    "ca": {
        "label": "Statewide table (Member 1 inputs)",
        "tracts": RAW / "ces40_ca_tracts.csv",
        "features": PROC / "features_ces_ca.csv",
        "model": PROC / "model_table_ca.csv",
        "features_out": OUT / "features_ces_ca_corrected.csv",
        "model_out": OUT / "model_table_ca_corrected.csv",
        "field_map": {"PM2_5": "pm25", "Ozone": "ozone", "Asthma": "asthma_ed_per10k",
                      "Cardiovas": "cardiovascular_ed_per10k", "Poverty": "poverty_pct",
                      "Elderly65": "elderly65_pct", "Educatn": "edu_lt_hs_pct",
                      "Ling_Isol": "ling_isol_pct", "Unempl": "unemployment_pct",
                      "HousBurd": "housing_burden_pct", "CIscoreP": "ces4_percentile"},
        "pop_col": "ces_pop",
    },
}
PERCENTILE = "ces4_percentile"


# ---------------------------------------------------------------- small helpers
def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: pathlib.Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="") as fh:
        rd = csv.DictReader(fh)
        return list(rd.fieldnames), list(rd)


def write_csv(path: pathlib.Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def fmt(v: float | None) -> str:
    """Format like the original files: str(float), empty string when missing."""
    return "" if v is None else str(v)


def num(s) -> float | None:
    return ces.to_raw_number(s)


def differs(a: float | None, b: float | None) -> bool:
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    return abs(a - b) > TOL


# ---------------------------------------------------------------- one pipeline
def run(key: str, cfg: dict) -> dict:
    fmap = cfg["field_map"]
    names = list(fmap.values())
    _, tracts = read_csv(cfg["tracts"])
    f_header, f_rows = read_csv(cfg["features"])
    m_header, m_rows = read_csv(cfg["model"])

    old = ces.aggregate_tracts(tracts, fmap, treat_sentinel_as_missing=False)
    new = ces.aggregate_tracts(tracts, fmap, treat_sentinel_as_missing=True)

    # ---- tract-level audit
    tract_audit = []
    for raw, name in fmap.items():
        vals = [num(t.get(raw)) for t in tracts]
        tract_audit.append({
            "table": key, "raw_field": raw, "feature": name, "tracts": len(tracts),
            "tracts_sentinel_-999": sum(1 for v in vals if v == ces.SENTINEL),
            "tracts_blank": sum(1 for v in vals if v is None),
            "tracts_other_negative": sum(1 for v in vals if v is not None and v < 0
                                         and v != ces.SENTINEL)})
    any_sentinel = sum(1 for t in tracts
                       if any(num(t.get(raw)) == ces.SENTINEL for raw in fmap))

    # ---- step 2: the un-fixed aggregation must reproduce the existing feature file
    repro_cells = repro_bad = 0
    for r in f_rows:
        z = ces.zip_key(r["zip"])
        for name in names:
            if name not in r:
                continue
            repro_cells += 1
            if differs(num(r[name]), old.get(z, {}).get(name)):
                repro_bad += 1
    if repro_bad:
        raise SystemExit(f"[{key}] cannot reproduce the original feature file: "
                         f"{repro_bad} of {repro_cells} cells differ. Not writing outputs.")

    # ---- step 4: corrected feature file (same rows, same columns, same order)
    f_out = []
    for r in f_rows:
        z = ces.zip_key(r["zip"])
        o = dict(r)
        for name in names:
            if name in o and differs(num(r[name]), new.get(z, {}).get(name)):
                o[name] = fmt(new.get(z, {}).get(name))
        f_out.append(o)
    write_csv(cfg["features_out"], f_header, f_out)

    # ---- corrected modeling table: only CES-derived columns are replaced
    ces_cols = [c for c in names if c in m_header]
    m_out, changes = [], []
    zip_meta: dict[str, dict] = {}
    for r in m_rows:
        z = ces.zip_key(r["zip"])
        o = dict(r)
        for name in ces_cols:
            before, after = num(r[name]), new.get(z, {}).get(name)
            if differs(before, after):
                o[name] = fmt(after)
        m_out.append(o)
        zip_meta.setdefault(z, {"county": r.get("county", "Los Angeles")})
    write_csv(cfg["model_out"], m_header, m_out)

    # ---- step 5: comparison, one row per (ZIP, feature) that changed.
    # Compared on every feature in the FEATURE file (a superset of the model columns).
    seen = set()
    for r in f_rows:
        z = ces.zip_key(r["zip"])
        if z in seen:
            continue
        seen.add(z)
        rec = new.get(z, {})
        for name in names:
            if name not in r:
                continue
            before, after = num(r[name]), rec.get(name)
            if not differs(before, after):
                continue
            changes.append({
                "table": key, "zip": z,
                "county": zip_meta.get(z, {}).get("county", ""),
                "feature": name,
                "in_model_table": int(name in ces_cols),
                "original": fmt(before), "corrected": fmt(after),
                "difference": "" if after is None or before is None
                else round(after - before, 4),
                "original_negative": int(before is not None and before < 0),
                "status": "became missing" if after is None else "corrected",
                "tracts_in_zip": rec.get("n_tracts", ""),
                "tracts_missing_this_field": rec.get(f"n_missing__{name}", ""),
                "tracts_used": rec.get(f"n_used__{name}", "")})

    by_zip: dict[str, list[dict]] = {}
    for c in changes:
        by_zip.setdefault(c["zip"], []).append(c)
    model_zips = {ces.zip_key(r["zip"]) for r in m_rows}
    affected = []
    for z in sorted(by_zip):
        cs = by_zip[z]
        affected.append({
            "table": key, "zip": z, "county": cs[0]["county"],
            "in_model_table": int(z in model_zips),
            "features_changed": len(cs),
            "model_columns_changed": sum(c["in_model_table"] for c in cs),
            "had_negative_value": int(any(c["original_negative"] for c in cs)),
            "became_missing": sum(1 for c in cs if c["status"] == "became missing"),
            "percentile_changed": int(any(c["feature"] == PERCENTILE for c in cs)),
            "tracts_in_zip": cs[0]["tracts_in_zip"],
            "which_features": "; ".join(c["feature"] for c in cs)})

    # ---- step 6: verification
    def scan(rows, cols):
        neg = sent = 0
        for r in rows:
            for c in cols:
                v = num(r.get(c))
                if v is not None and v < 0:
                    neg += 1
                if v == ces.SENTINEL:
                    sent += 1
        return neg, sent

    f_cols = [c for c in names if c in f_header]
    neg_f_old, _ = scan(f_rows, f_cols)
    neg_m_old, _ = scan(m_rows, ces_cols)
    neg_f, sent_f = scan(f_out, f_cols)
    neg_m, sent_m = scan(m_out, ces_cols)
    pct_bad = sum(1 for r in f_out + m_out
                  if PERCENTILE in r and num(r[PERCENTILE]) is not None
                  and not (0 <= num(r[PERCENTILE]) <= 100))
    pct_bad_old = sum(1 for r in m_rows
                      if PERCENTILE in r and num(r[PERCENTILE]) is not None
                      and not (0 <= num(r[PERCENTILE]) <= 100))
    other_cols = [c for c in m_header if c not in ces_cols]
    untouched_ok = all(a[c] == b[c] for a, b in zip(m_rows, m_out) for c in other_cols)
    same_rows = (len(m_rows) == len(m_out)
                 and all(a["zip"] == b["zip"] for a, b in zip(m_rows, m_out)))
    # every cell that did not need correcting is the identical string
    unchanged_identical = all(
        a[c] == b[c] for a, b in zip(m_rows, m_out) for c in ces_cols
        if not differs(num(a[c]), new.get(ces.zip_key(a["zip"]), {}).get(c)))
    # NaN preserved: a ZIP with tracts but no valid tract value must be empty
    must_be_empty = [(z, n) for z, rec in new.items() for n in names
                     if rec[f"n_used__{n}"] == 0]
    f_index = {ces.zip_key(r["zip"]): r for r in f_out}
    nan_preserved = all(f_index[z].get(n, "") == "" for z, n in must_be_empty
                        if z in f_index and n in f_index[z])
    newly_missing = sum(1 for c in changes if c["status"] == "became missing")

    n_model_zips = len(model_zips)
    affected_model = [a for a in affected if a["in_model_table"] and a["model_columns_changed"]]
    checks = {
        "table": cfg["label"],
        "tract_file": str(cfg["tracts"]), "tracts": len(tracts),
        "tracts_with_any_-999": any_sentinel,
        "old_aggregation_reproduces_feature_file": f"{repro_cells - repro_bad} of {repro_cells} cells",
        "zips_in_feature_file": len({ces.zip_key(r['zip']) for r in f_rows}),
        "zips_in_model_table": n_model_zips,
        "rows_in_model_table": len(m_rows),
        "zips_affected_any_ces_feature": len(affected),
        "zips_affected_in_model_table_columns": len(affected_model),
        "zips_with_negative_value_originally": sum(a["had_negative_value"] for a in affected),
        "zip_feature_cells_changed": len(changes),
        "zip_feature_cells_became_missing": newly_missing,
        "negative_ces_cells_original_feature_file": neg_f_old,
        "negative_ces_cells_original_model_table": neg_m_old,
        "percentiles_outside_0_100_original_model_table": pct_bad_old,
        "negative_ces_cells_corrected_feature_file": neg_f,
        "negative_ces_cells_corrected_model_table": neg_m,
        "sentinel_cells_corrected": sent_f + sent_m,
        "percentiles_outside_0_100_corrected": pct_bad,
        "missing_preserved_where_no_valid_tract": nan_preserved,
        "same_rows_and_order_as_original": same_rows,
        "non_ces_columns_identical_to_original": untouched_ok,
        "unaffected_ces_cells_identical_to_original": unchanged_identical,
        "ces_columns_replaced_in_model_table": ces_cols,
    }
    ok = (neg_f == 0 and neg_m == 0 and sent_f + sent_m == 0 and pct_bad == 0
          and nan_preserved and same_rows and untouched_ok and unchanged_identical)
    checks["all_checks_passed"] = ok
    return {"tract_audit": tract_audit, "changes": changes, "affected": affected,
            "checks": checks, "ok": ok}


# ---------------------------------------------------------------- written summary
def md_table(rows: list[dict]) -> str:
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join(out)


def write_summary(results: dict, originals_unchanged: bool) -> None:
    """results/ces_sentinel_fix/SUMMARY.md - generated, so it always matches the CSVs."""
    L = ["# CalEnviroScreen -999 fix: generated summary", "",
         "Generated by `scripts/build_corrected_ces_tables.py`. Do not edit by hand.", ""]
    for k, res in results.items():
        c, ch, af = res["checks"], res["changes"], res["affected"]
        L += [f"## {c['table']}", "",
              md_table([{"Check": n.replace("_", " "), "Value": v} for n, v in c.items()
                        if n not in ("table", "ces_columns_replaced_in_model_table")]), "",
              "### -999 values in the tract file", "",
              md_table([{"Raw field": a["raw_field"], "Feature": a["feature"],
                         "Tracts": a["tracts"], "Tracts with -999": a["tracts_sentinel_-999"],
                         "Blank": a["tracts_blank"],
                         "Other negative": a["tracts_other_negative"]}
                        for a in res["tract_audit"]]), "",
              "### ZIPs changed, by feature", ""]
        rows = []
        for a in res["tract_audit"]:
            cs = [x for x in ch if x["feature"] == a["feature"]]
            diffs = [abs(x["difference"]) for x in cs if x["difference"] != ""]
            rows.append({"Feature": a["feature"],
                         "In model table": "yes" if any(x["in_model_table"] for x in cs)
                         or a["feature"] in c["ces_columns_replaced_in_model_table"] else "no",
                         "ZIPs changed": len(cs),
                         "of which originally negative": sum(x["original_negative"] for x in cs),
                         "of which became missing": sum(x["status"] == "became missing" for x in cs),
                         "Largest absolute change": round(max(diffs), 2) if diffs else "—"})
        L += [md_table(rows), ""]
        if k == "la":
            L += ["### Every affected ZIP and value", "",
                  md_table([{"ZIP": x["zip"], "Feature": x["feature"],
                             "In model table": "yes" if x["in_model_table"] else "no",
                             "Original": x["original"] or "(empty)",
                             "Corrected": x["corrected"] or "(empty)",
                             "Tracts in ZIP": x["tracts_in_zip"],
                             "Tracts missing this field": x["tracts_missing_this_field"]}
                            for x in ch]), ""]
        else:
            by_county: dict[str, int] = {}
            for a in af:
                by_county[a["county"] or "(not in model table)"] = \
                    by_county.get(a["county"] or "(not in model table)", 0) + 1
            top = sorted(by_county.items(), key=lambda kv: -kv[1])
            L += ["### Affected ZIPs by county", "",
                  md_table([{"County": n, "Affected ZIPs": v} for n, v in top]), "",
                  f"The full list of {len(af)} ZIP codes is in `affected_zips_ca.csv`; every "
                  "changed value is in `feature_changes_ca.csv`.", "",
                  "### Affected ZIP codes", "",
                  ", ".join(a["zip"] for a in af), ""]
    L += [f"Original files unchanged by this run: **{originals_unchanged}**", ""]
    (REP / "SUMMARY.md").write_text("\n".join(L))


def main() -> None:
    ces._self_check()
    originals = sorted({p for cfg in PIPELINES.values()
                        for p in (cfg["tracts"], cfg["features"], cfg["model"])})
    before = {str(p): sha256(p) for p in originals}

    REP.mkdir(parents=True, exist_ok=True)
    results = {k: run(k, cfg) for k, cfg in PIPELINES.items()}

    after = {str(p): sha256(p) for p in originals}
    originals_unchanged = before == after

    write_csv(REP / "sentinel_counts_by_tract_field.csv",
              list(results["la"]["tract_audit"][0]),
              [r for k in results for r in results[k]["tract_audit"]])
    for k in results:
        ch, af = results[k]["changes"], results[k]["affected"]
        write_csv(REP / f"feature_changes_{k}.csv", list(ch[0]), ch)
        write_csv(REP / f"affected_zips_{k}.csv", list(af[0]), af)
    summary = {
        "sentinel": ces.SENTINEL, "tolerance": TOL,
        "originals_unchanged": originals_unchanged,
        "original_file_sha256": before,
        "corrected_file_sha256": {str(cfg[o]): sha256(cfg[o]) for cfg in PIPELINES.values()
                                  for o in ("features_out", "model_out")},
        "tables": {k: results[k]["checks"] for k in results},
    }
    (REP / "verification.json").write_text(json.dumps(summary, indent=2))
    write_summary(results, originals_unchanged)

    for k in results:
        print(f"\n=== {PIPELINES[k]['label']} ===")
        for name, v in results[k]["checks"].items():
            print(f"  {name}: {v}")
    print(f"\noriginal files unchanged: {originals_unchanged}")
    print(f"corrected tables: {OUT}/   comparison and checks: {REP}/")
    if not (originals_unchanged and all(r["ok"] for r in results.values())):
        raise SystemExit("VERIFICATION FAILED - see results/ces_sentinel_fix/verification.json")
    print("all checks passed")


if __name__ == "__main__":
    main()
