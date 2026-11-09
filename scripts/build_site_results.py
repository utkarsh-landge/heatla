"""Point the website at the final, corrected model results (integration step).

The site was first built from the original pipeline at commit 0980d9a, whose inputs had
the CalEnviroScreen -999 error. This script replaces every model number and prediction
the page shows with the corrected results of Parts 1 and 2. It needs no network.

Sources
  part2/results/feature_comparison/predictions_oof.csv
      LA-only 5-fold spatial CV, level 4, augmented model (11 CES inputs + 4 ACS 2014-2018)
  part2/results/feature_comparison/metrics_all_287.csv, metrics_CES_matched_273.csv
  part2/data/la_base.csv                               corrected CES percentile per ZIP
  results/member1/ces40_fixed/predictions_la_holdout.csv, metrics_member1.json
      trained on California outside LA, corrected CES 4.0 inputs, all-level models
  results/member1/ces40_fixed_level_only/metrics_member1.json
      same, target = excess on level-4 days alone (level 4 - level 3)

Writes
  site/data/zips.geojson            pred_* (LA out-of-fold), hold_* (LA holdout), ces4_percentile
  site/data/prediction_sources.json what each prediction version is
  site/data/metrics.json            LA-only table (section 04), with bootstrap CIs
  site/data/metrics_ca.json         out-of-region table (section 05), with matched CES baseline
  site/data/meta.json               headline, data years and caveats

Run:  .venv/bin/python scripts/build_site_results.py   (scripts/build_site_data.py calls it)
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heatla import model as M  # noqa: E402

SITE = ROOT / "site/data"
P2 = ROOT / "part2"
M1 = ROOT / "results/member1"
OOF = P2 / "results/feature_comparison/predictions_oof.csv"
HOLD = M1 / "ces40_fixed/predictions_la_holdout.csv"
MODELS = ("poisson", "random_forest", "gradient_boosting")
SHORT = {"poisson": "poisson", "random_forest": "rf", "gradient_boosting": "gbm"}
LEVEL = 4


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def clean(o):
    """NaN/Inf -> None so the output is valid JSON for browsers."""
    if isinstance(o, float):
        return o if np.isfinite(o) else None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    return o


def update_zips(oof: pd.DataFrame, hold: pd.DataFrame) -> int:
    gj = json.loads((SITE / "zips.geojson").read_text())
    ces = pd.read_csv(P2 / "data/la_base.csv", dtype={"zip": str}).set_index("zip")["ces4_percentile"]
    for f in gj["features"]:
        p = f["properties"]
        z = str(p["zip"]).zfill(5)
        assert abs(oof.at[z, "y_true"] - p["observed_rate"]) < 0.006, z
        assert abs(hold.at[z, "ucla_label"] - p["observed_rate"]) < 0.051, z
        for long, short in SHORT.items():
            p[f"pred_{short}"] = round(float(oof.at[z, f"pred_{long}_augmented"]), 2)
            p[f"hold_{short}"] = round(float(hold.at[z, f"pred_{long}_all_level"]), 2)
        p["ces4_percentile"] = None if pd.isna(ces.get(z)) else round(float(ces[z]), 1)
    (SITE / "zips.geojson").write_text(json.dumps(gj))
    return len(gj["features"])


def prediction_sources(n: int) -> None:
    sources = {
        "label": {
            "name": "UCLA label", "property": "observed_rate",
            "description": "UCLA Heat Maps estimated excess ER visits per 10,000 residents, "
                           "CalHeatScore level 4 layer, total over May-October 2008-2018",
            "unit": "excess ER visits per 10,000 residents (total, May-Oct 2008-2018)",
        },
        "sources": {
            "oof": {
                "name": "LA out-of-fold", "long_name": "LA out-of-fold predictions",
                "description": "Each ZIP is predicted by a model trained on the other four spatial "
                               "folds of LA County (heat level 4 only). 15 inputs: 10 corrected "
                               "CalEnviroScreen inputs and population density, plus 4 ACS 2014-2018 "
                               "features (Part 2).",
                "properties": {k: f"pred_{v}" for k, v in SHORT.items()},
                "file": rel(OOF), "sha256_16": sha(OOF),
            },
            "holdout": {
                "name": "LA holdout", "long_name": "LA holdout predictions",
                "description": "Every LA ZIP is predicted by one model trained on all California ZIPs "
                               "outside LA County (heat levels 1-4, 12 inputs, corrected "
                               "CalEnviroScreen); level-4 predictions shown (Part 1).",
                "properties": {k: f"hold_{v}" for k, v in SHORT.items()},
                "file": rel(HOLD), "sha256_16": sha(HOLD),
            },
        },
        "models": {"poisson": "Poisson", "random_forest": "Random forest",
                   "gradient_boosting": "Gradient boosting"},
        "error_definition": "error = prediction - UCLA label; positive = overprediction, "
                            "negative = underprediction; same unit as the label",
        "status": "Final versions at integration: corrected CalEnviroScreen inputs (-999 treated as missing).",
        "n_zips": n, "heat_level": LEVEL,
    }
    (SITE / "prediction_sources.json").write_text(json.dumps(sources, indent=2))


def la_metrics(oof: pd.DataFrame) -> dict:
    """Section 04 table: Part 2 augmented models, LA-only spatial CV, level 4."""
    table = pd.read_csv(P2 / "results/feature_comparison/metrics_all_287.csv")
    matched = pd.read_csv(P2 / "results/feature_comparison/metrics_CES_matched_273.csv")
    y = oof["y_true"].to_numpy(float)
    out = {"models": {}, "baselines": {}}
    for name in MODELS:
        row = table[(table.config == "augmented") & (table.model == name)].iloc[0]
        p = oof[f"pred_{name}_augmented"].to_numpy(float)
        out["models"][name] = {"overall": {
            "n": int(row.n), "r2": float(row.r2), "spearman": float(row.spearman),
            "top10_recall": float(row.top10_recall), "top20_recall": float(row.top20_recall),
            "r2_ci": M.bootstrap_ci(y, p, lambda a, b: r2_score(a, b)),
            "spearman_ci": M.bootstrap_ci(y, p, lambda a, b: spearmanr(a, b).statistic)}}
    mean = table[table.model == "training_fold_mean"].iloc[0]
    out["baselines"]["predict_mean"] = {"n": int(mean.n), "r2": float(mean.r2),
                                        "note": "mean label of the training folds"}
    ces = matched[matched.model == "CES_percentile"].iloc[0]
    pois = matched[(matched.config == "augmented") & (matched.model == "poisson")].iloc[0]
    out["baselines"]["ces4_percentile"] = {
        "n": int(ces.n), "spearman": float(ces.spearman), "top10_recall": float(ces.top10_recall),
        "top20_recall": float(ces.top20_recall), "poisson_spearman_same_zips": float(pois.spearman),
        "poisson_top10_same_zips": float(pois.top10_recall),
        "note": "corrected CES 4.0 percentile on the 273 ZIPs that have one; rank metrics only"}
    out.update({"design": "LA-only 5-fold spatial cross-validation, heat level 4, Part 2 augmented "
                          "configuration (15 inputs)",
                "n_groups": int(oof["group"].nunique()), "n_rows": int(len(oof)),
                "source": rel(P2 / "results/feature_comparison/metrics_all_287.csv")})
    return out


def ca_metrics() -> dict:
    """Section 05 table: Part 1, corrected inputs, all-level models."""
    def rec(run: str) -> pd.DataFrame:
        return pd.DataFrame(json.loads((M1 / run / "metrics_member1.json").read_text())["metrics"])

    def ces(run: str) -> pd.DataFrame:
        return pd.DataFrame(json.loads((M1 / run / "metrics_member1.json").read_text())["ces_baseline_matched"])

    def pick(df, evaluation, model, scope):
        r = df[(df.evaluation == evaluation) & (df.config == "all_level")
               & (df.model == model) & (df.scope == scope)].iloc[0]
        return {k: float(r[k]) for k in ("r2", "spearman", "top10_recall", "top20_recall")} | {"n": int(r.n)}

    cum, lvl = rec("ces40_fixed"), rec("ces40_fixed_level_only")
    out = {"test_a_spatial_cv": {"models": {m: pick(cum, "spatial_cv", m, "pooled (levels 1-4)")
                                            for m in MODELS}},
           "test_b_la_holdout": {"models": {}, "baselines": {}}}
    for m in MODELS:
        out["test_b_la_holdout"]["models"][m] = {
            "all_chs": pick(cum, "la_holdout", m, "pooled (levels 1-4)"),
            "chs4": pick(cum, "la_holdout", m, "level 4"),
            "chs4_days_only": pick(lvl, "la_holdout", m, "level 4")}
    for key, run in (("chs4", "ces40_fixed"), ("chs4_days_only", "ces40_fixed_level_only")):
        c = ces(run)
        c = c[(c.evaluation == "la_holdout") & (c.scope == "level 4")]
        idx = c[c.config == "index"].iloc[0]
        pois = c[(c.config == "all_level") & (c.predictor == "poisson")].iloc[0]
        out["test_b_la_holdout"]["baselines"][f"ces4_percentile_{key}"] = {
            "n": int(idx.n_matched), "spearman": float(idx.spearman),
            "top10_recall": float(idx.top10_recall),
            "poisson_spearman_same_zips": float(pois.spearman),
            "poisson_top10_same_zips": float(pois.top10_recall)}
    out["inputs"] = "CalEnviroScreen 4.0 with -999 treated as missing (Part 1, results/member1/ces40_fixed)"
    return out


def meta(ca: dict) -> None:
    path = SITE / "meta.json"
    m = json.loads(path.read_text())
    b = ca["test_b_la_holdout"]["models"]["poisson"]
    m["data_years"]["ACS"] = "2014-2018 5-year (four added LA features)"
    m["data_years"]["population"] = "UCLA layer, 2020 Census"
    m["headline"] = (f"Out-of-region skill within heat level 4 (LA hold-out, Poisson): Spearman "
                     f"{b['chs4']['spearman']:.2f} for UCLA's level-4 label, "
                     f"{b['chs4_days_only']['spearman']:.2f} for level-4 days alone.")
    caveats = [c for c in m["caveats"] if "within-level measure" not in c]
    caveats.insert(6, "Pooled all-CHS hold-out numbers mostly reflect the gap between heat levels; "
                      "the within-level measures are the level-4 rows above.")
    if not any("asthma" in c for c in caveats):
        caveats.insert(7, "Two inputs, the asthma and heart-attack ER-visit rates, come from the same "
                          "state ER records as the label. Without them, level-4 skill drops and, for "
                          "level-4 days alone, is about level with the CalEnviroScreen index.")
    if not any("Cooling-center weights" in c for c in caveats):
        caveats.append("Cooling-center weights use the earlier LA out-of-fold predictions (13-input "
                       "model, pre-correction inputs) and have not been rerun.")
    m["caveats"] = caveats
    path.write_text(json.dumps(m, indent=2))


def main() -> None:
    oof = pd.read_csv(OOF, dtype={"zip": str}).set_index("zip", drop=False)
    hold = pd.read_csv(HOLD, dtype={"zip": str})
    hold = hold[hold["chs_level"] == LEVEL].set_index("zip")
    n = update_zips(oof, hold)
    prediction_sources(n)
    (SITE / "metrics.json").write_text(json.dumps(clean(la_metrics(oof.reset_index(drop=True))), indent=2))
    ca = ca_metrics()
    (SITE / "metrics_ca.json").write_text(json.dumps(clean(ca), indent=2))
    meta(ca)
    print(f"site results updated for {n} ZIPs")


if __name__ == "__main__":
    main()
