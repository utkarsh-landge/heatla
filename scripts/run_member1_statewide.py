"""Member 1 - statewide models and geographic transfer (revision experiments).

Answers the professor's feedback items 5-7 for the statewide module without touching
the existing outputs in results/. Everything is written to results/member1/.

Evaluations (same data, models, seed and folds as scripts/run_models_ca.py):
  spatial_cv   leave-one-geographic-group-out over all of California (10 k-means groups)
  la_holdout   train on every county except Los Angeles, test on Los Angeles

Model configurations compared in each evaluation:
  all_level       one model trained on heat levels 1-4, heat level is an input
  level_specific  one model per heat level, trained only on that level's rows,
                  heat-level input removed (it is constant), other inputs unchanged

What is reported:
  - sample counts: unique ZIPs and rows at each cleaning step, per level, per fold
  - check that all heat-level rows of a ZIP sit in the same fold
  - pooled and per-level R2, Spearman, top-10% and top-20% recall
  - CES 4.0 percentile baseline on the SAME ZIPs and heat level as the models
    (rank metrics only: CES is an index, not a rate, so R2 is not defined for it)
  - row-level labels, predictions and errors (error = prediction - UCLA label)

Run (original CES 4.0 inputs, as committed in results/member1/):
  .venv/bin/python scripts/run_member1_statewide.py

Run on another input table (same columns; see scripts/build_member1_ces_tables.py):
  .venv/bin/python scripts/run_member1_statewide.py --tag ces40_fixed \
      --table data/processed/model_table_ca_ces40_fixed.csv --out results/member1/ces40_fixed
  .venv/bin/python scripts/run_member1_statewide.py --tag ces30 --baseline ces3_percentile \
      --table data/processed/model_table_ca_ces30.csv --out results/member1/ces30
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.cluster import KMeans
from sklearn.metrics import r2_score
from sklearn.preprocessing import StandardScaler

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from heatla import model as M  # noqa: E402
from run_models_ca import FEATURES, N_GROUPS, SEED, TARGET, fit_predict  # noqa: E402

DEFAULT_TABLE = pathlib.Path("data/processed/model_table_ca.csv")
OUT = pathlib.Path("results/member1")   # overridden by --out
TABLE = DEFAULT_TABLE                   # overridden by --table
BASELINE = "ces4_percentile"            # overridden by --baseline
TAG = "ces40_original"                  # overridden by --tag
MODELS = ("poisson", "random_forest", "gradient_boosting")
LEVELS = (1, 2, 3, 4)
LEVEL_FEATURES = [f for f in FEATURES if f != "chs_level"]
CES_INPUTS = [f for f in FEATURES if f not in ("chs_level", "pop_density_per_sqmi")]
LA = "Los Angeles"


# ---------------------------------------------------------------- helpers
def load() -> pd.DataFrame:
    """Same cleaning as run_models_ca.load(), for whichever table is selected."""
    df = pd.read_csv(TABLE)
    for c in FEATURES + [TARGET, "lat", "lon", "population", BASELINE]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=[TARGET, "lat", "lon", "population"]).reset_index(drop=True)
    df["zip"] = df["zip"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    return df


def baseline_label() -> str:
    return {"ces4_percentile": "CES 4.0 percentile",
            "ces3_percentile": "CES 3.0 percentile"}.get(BASELINE, BASELINE)


def metrics(y, p, ci: bool = True) -> dict:
    """R2, Spearman, top-10% / top-20% recall, with bootstrap CIs for R2 and Spearman."""
    o = M.metric_block(y, p)
    o["top10_k"] = max(1, int(round(0.10 * len(y))))
    if ci:
        o["r2_ci"] = M.bootstrap_ci(y, p, lambda a, b: r2_score(a, b))
        o["spearman_ci"] = M.bootstrap_ci(y, p, lambda a, b: spearmanr(a, b).statistic)
    return o


def rank_metrics(y, s) -> dict:
    """Rank-only metrics for an index that is not on the target's scale."""
    return {"n": int(len(y)),
            "spearman": float(spearmanr(y, s).statistic),
            "top10_recall": M.top_k_recall(y, s, 0.10),
            "top20_recall": M.top_k_recall(y, s, 0.20)}


def assign_folds(df: pd.DataFrame) -> np.ndarray:
    """Identical to run_models_ca.test_a_spatial: k-means on standardized lat/lon."""
    xy = StandardScaler().fit_transform(df[["lat", "lon"]].to_numpy())
    return KMeans(n_clusters=N_GROUPS, random_state=SEED, n_init=10).fit_predict(xy)


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------- sample counts
def sample_counts(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_csv(TABLE)
    raw["zip"] = raw["zip"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    dropped = sorted(set(raw["zip"]) - set(df["zip"]))
    has_ces = df[CES_INPUTS].notna().all(axis=1)      # all ten CES inputs present
    any_ces = df[CES_INPUTS].notna().any(axis=1)
    partial = any_ces & ~has_ces                      # some, not all, present
    has_pct = df[BASELINE].notna()
    is_la = df["county"] == LA

    def row(stage, sub):
        return {"stage": stage, "unique_zips": int(sub["zip"].nunique()), "rows": int(len(sub))}

    rows = [row("Raw statewide table (ZIP x heat level)", raw),
            row("After cleaning: label, centroid and population present", df),
            row("  of which CalEnviroScreen inputs present", df[has_ces]),
            row("  of which CalEnviroScreen inputs missing (median-imputed in training fold)",
                df[~has_ces]),
            row("Los Angeles County (LA holdout test set)", df[is_la]),
            row("  of which CalEnviroScreen inputs present", df[is_la & has_ces]),
            row("  of which CalEnviroScreen inputs missing", df[is_la & ~has_ces]),
            row("Rest of California (LA holdout training set)", df[~is_la]),
            row("  of which CalEnviroScreen inputs present", df[~is_la & has_ces]),
            row("  of which CalEnviroScreen inputs missing", df[~is_la & ~has_ces])]
    if partial.any() or (has_pct != has_ces).any():
        # only arises once -999 sentinels are treated as missing per feature
        rows += [row("Detail: some but not all CalEnviroScreen inputs missing, statewide",
                     df[partial]),
                 row("Detail: some but not all CalEnviroScreen inputs missing, Los Angeles",
                     df[is_la & partial]),
                 row("Detail: all CalEnviroScreen inputs missing, statewide", df[~any_ces]),
                 row("Detail: all CalEnviroScreen inputs missing, Los Angeles",
                     df[is_la & ~any_ces]),
                 row("Detail: CalEnviroScreen percentile present (baseline sample), statewide",
                     df[has_pct]),
                 row("Detail: CalEnviroScreen percentile present (baseline sample), Los Angeles",
                     df[is_la & has_pct])]
    for lv in LEVELS:
        m = df["chs_level"] == lv
        rows.append(row(f"Heat level {lv}: statewide", df[m]))
        rows.append(row(f"Heat level {lv}: Los Angeles", df[m & is_la]))
        rows.append(row(f"Heat level {lv}: rest of California", df[m & ~is_la]))
    per_zip = df.groupby("zip")["chs_level"].nunique()
    info = {
        "raw_rows": int(len(raw)), "raw_unique_zips": int(raw["zip"].nunique()),
        "clean_rows": int(len(df)), "clean_unique_zips": int(df["zip"].nunique()),
        "exclusion_rule": "drop rows missing the label, ZCTA centroid (lat/lon) or population; "
                          "rows missing CalEnviroScreen inputs are KEPT and median-imputed "
                          "inside each training fold",
        "zips_dropped_by_cleaning": dropped,
        "every_zip_has_all_4_levels": bool((per_zip == 4).all()),
        "n_counties": int(df["county"].nunique()),
        "la_zips_missing_ces": sorted(df.loc[is_la & ~has_ces, "zip"].unique().tolist()),
        "la_zips_missing_ces_percentile": sorted(
            df.loc[is_la & ~has_pct, "zip"].unique().tolist()),
        "missing_rows_per_input": {c: int(df[c].isna().sum()) for c in CES_INPUTS + [BASELINE]},
        "negative_rows_per_input": {c: int((df[c] < 0).sum()) for c in CES_INPUTS + [BASELINE]},
    }
    return pd.DataFrame(rows), info


def fold_counts(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    folds_per_zip = df.groupby("zip")["fold"].nunique()
    zip_in_one_fold = bool((folds_per_zip == 1).all())
    has_ces = df[CES_INPUTS].notna().all(axis=1)
    rows = []
    for f, g in df.groupby("fold"):
        la = g[g["county"] == LA]
        top = g.drop_duplicates("zip")["county"].value_counts().head(3)
        rows.append({
            "fold": int(f), "unique_zips": int(g["zip"].nunique()), "rows": int(len(g)),
            "rows_per_level": int(len(g) / 4),
            "zips_missing_ces": int(g.loc[~has_ces.loc[g.index], "zip"].nunique()),
            "la_county_zips": int(la["zip"].nunique()),
            "n_counties": int(g["county"].nunique()),
            "largest_counties": "; ".join(f"{c} ({n})" for c, n in top.items()),
            "centroid_lat": round(float(g["lat"].mean()), 3),
            "centroid_lon": round(float(g["lon"].mean()), 3),
        })
    return pd.DataFrame(rows), zip_in_one_fold


# ---------------------------------------------------------------- experiments
def spatial_cv_predict(df: pd.DataFrame, feats: list[str], rows: np.ndarray) -> dict:
    """Leave-one-fold-out predictions for the rows in `rows` (boolean mask)."""
    sub = df[rows]
    X, y = sub[feats], sub[TARGET].to_numpy(float)
    pop, folds = sub["population"].to_numpy(float), sub["fold"].to_numpy()
    out = {}
    for name in MODELS:
        model = M.make_models()[name]
        pred = np.full(len(sub), np.nan)
        for f in np.unique(folds):
            tr, te = folds != f, folds == f
            pred[te] = fit_predict(model, X[tr], y[tr], X[te], name, pop[tr])
        out[name] = pred
    return out


def holdout_predict(df: pd.DataFrame, feats: list[str], rows: np.ndarray) -> dict:
    """Train on non-LA rows in `rows`, predict LA rows in `rows`."""
    sub = df[rows]
    is_la = (sub["county"] == LA).to_numpy()
    tr, te = sub[~is_la], sub[is_la]
    out = {"_n_train": int(len(tr)), "_n_test": int(len(te)),
           "_train_label_mean": float(tr[TARGET].mean())}
    for name in MODELS:
        model = M.make_models()[name]
        out[name] = fit_predict(model, tr[feats], tr[TARGET].to_numpy(float), te[feats],
                                name, tr["population"].to_numpy(float))
    return out


def run_evaluation(df: pd.DataFrame, kind: str) -> tuple[pd.DataFrame, list[dict], dict]:
    """Run all-level and level-specific configs for one evaluation; return row-level preds."""
    predict = spatial_cv_predict if kind == "spatial_cv" else holdout_predict
    test_mask = np.ones(len(df), bool) if kind == "spatial_cv" else (df["county"] == LA).to_numpy()
    pred = df.loc[test_mask, ["zip", "county", "chs_level", "fold", "lat", "lon",
                              "population", TARGET, BASELINE]].copy()
    pred = pred.rename(columns={TARGET: "ucla_label"})
    pred["has_ces_inputs"] = df.loc[test_mask, CES_INPUTS].notna().all(axis=1).astype(int)
    train_sizes = {}

    # all-level model: one fit, heat level is an input
    allp = predict(df, FEATURES, np.ones(len(df), bool))
    for name in MODELS:
        pred[f"pred_{name}_all_level"] = allp[name]
    if kind == "la_holdout":
        train_sizes["all_level"] = {"n_train_rows": allp["_n_train"],
                                    "n_test_rows": allp["_n_test"],
                                    "train_label_mean": allp["_train_label_mean"]}
        pred["pred_trainmean_all_level"] = allp["_train_label_mean"]

    # level-specific models: one fit per level, heat-level input removed
    for name in MODELS:
        pred[f"pred_{name}_level_specific"] = np.nan
    if kind == "la_holdout":
        pred["pred_trainmean_level_specific"] = np.nan
    for lv in LEVELS:
        rows = (df["chs_level"] == lv).to_numpy()
        lp = predict(df, LEVEL_FEATURES, rows)
        sel = (pred["chs_level"] == lv).to_numpy()
        for name in MODELS:
            pred.loc[sel, f"pred_{name}_level_specific"] = lp[name]
        if kind == "la_holdout":
            train_sizes[f"level_specific_L{lv}"] = {
                "n_train_rows": lp["_n_train"], "n_test_rows": lp["_n_test"],
                "train_label_mean": lp["_train_label_mean"]}
            pred.loc[sel, "pred_trainmean_level_specific"] = lp["_train_label_mean"]

    for c in [c for c in pred.columns if c.startswith("pred_")]:
        pred[c.replace("pred_", "error_", 1)] = pred[c] - pred["ucla_label"]

    # metrics: pooled + per level, for every model x config
    y = pred["ucla_label"].to_numpy(float)
    lvl = pred["chs_level"].to_numpy()
    recs = []
    names = list(MODELS) + (["trainmean"] if kind == "la_holdout" else [])
    for config in ("all_level", "level_specific"):
        for name in names:
            p = pred[f"pred_{name}_{config}"].to_numpy(float)
            scopes = [("pooled (levels 1-4)", np.ones(len(y), bool))]
            scopes += [(f"level {lv}", lvl == lv) for lv in LEVELS]
            for scope, m in scopes:
                blk = metrics(y[m], p[m], ci=name != "trainmean")
                if name == "trainmean":  # a constant has no ranking
                    blk["spearman"] = None
                    blk["top10_recall"] = blk["top20_recall"] = None
                recs.append({"evaluation": kind, "config": config, "model": name,
                             "scope": scope, **blk})
    return pred, recs, train_sizes


def ces_matched(pred: pd.DataFrame, kind: str) -> list[dict]:
    """CES percentile vs the models on identical rows (same ZIPs, same heat level)."""
    recs = []
    lvl = pred["chs_level"].to_numpy()
    ok = pred[BASELINE].notna().to_numpy()
    y = pred["ucla_label"].to_numpy(float)
    ces = pred[BASELINE].to_numpy(float)
    scopes = [(f"level {lv}", lvl == lv) for lv in LEVELS]
    scopes.append(("pooled (levels 1-4)", np.ones(len(y), bool)))
    for scope, m in scopes:
        mm = m & ok
        base = {"evaluation": kind, "scope": scope, "n_all": int(m.sum()),
                "n_matched": int(mm.sum()), "n_dropped_no_ces": int((m & ~ok).sum())}
        recs.append({**base, "predictor": baseline_label(), "config": "index",
                     **{k: v for k, v in rank_metrics(y[mm], ces[mm]).items() if k != "n"}})
        for config in ("all_level", "level_specific"):
            for name in MODELS:
                p = pred[f"pred_{name}_{config}"].to_numpy(float)
                recs.append({**base, "predictor": name, "config": config,
                             **{k: v for k, v in rank_metrics(y[mm], p[mm]).items() if k != "n"}})
    return recs


# ---------------------------------------------------------------- main
def main() -> None:
    global OUT, TABLE, BASELINE, TAG
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--table", default=str(DEFAULT_TABLE), help="model table CSV")
    ap.add_argument("--out", default="results/member1", help="output directory")
    ap.add_argument("--baseline", default="ces4_percentile",
                    help="column holding the CalEnviroScreen percentile used as baseline")
    ap.add_argument("--tag", default="ces40_original", help="name of this input variant")
    a = ap.parse_args()
    OUT, TABLE, BASELINE, TAG = pathlib.Path(a.out), pathlib.Path(a.table), a.baseline, a.tag

    OUT.mkdir(parents=True, exist_ok=True)
    df = load()
    df["fold"] = assign_folds(df)

    counts, info = sample_counts(df)
    folds, zip_in_one_fold = fold_counts(df)
    info["all_levels_of_a_zip_in_same_fold"] = zip_in_one_fold
    counts.to_csv(OUT / "sample_counts.csv", index=False)
    folds.to_csv(OUT / "fold_counts_statewide.csv", index=False)
    df.drop_duplicates("zip")[["zip", "county", "lat", "lon", "fold"]].to_csv(
        OUT / "fold_assignment_statewide.csv", index=False)
    print(f"cleaned table: {len(df)} rows, {df['zip'].nunique()} ZIPs; "
          f"all levels of a ZIP in one fold: {zip_in_one_fold}")

    all_metrics, all_ces, train_sizes = [], [], {}
    for kind in ("la_holdout", "spatial_cv"):
        print(f"running {kind} ...", flush=True)
        pred, recs, sizes = run_evaluation(df, kind)
        pred.to_csv(OUT / f"predictions_{kind}.csv", index=False)
        all_metrics += recs
        all_ces += ces_matched(pred, kind)
        if sizes:
            train_sizes = sizes

    mdf = pd.DataFrame(all_metrics)
    cdf = pd.DataFrame(all_ces)
    mdf.drop(columns=["r2_ci", "spearman_ci"]).to_csv(OUT / "metrics_by_level.csv", index=False)
    cdf.to_csv(OUT / "baseline_ces_matched.csv", index=False)

    # regression check: the all-level pooled numbers must equal the committed results
    old = json.loads(pathlib.Path("results/metrics_ca.json").read_text())
    checks = {}
    for name in MODELS if TABLE == DEFAULT_TABLE else ():
        for kind, ref in (("spatial_cv", old["test_a_spatial_cv"]["models"][name]),
                          ("la_holdout", old["test_b_la_holdout"]["models"][name]["all_chs"])):
            new = mdf[(mdf.evaluation == kind) & (mdf.config == "all_level")
                      & (mdf.model == name) & (mdf.scope == "pooled (levels 1-4)")].iloc[0]
            checks[f"{kind}/{name}"] = bool(abs(new["r2"] - ref["r2"]) < 1e-9
                                            and abs(new["spearman"] - ref["spearman"]) < 1e-9)
    if checks:
        print("matches committed results/metrics_ca.json:", all(checks.values()))

    config = {
        "module": "Member 1 - statewide models and geographic transfer",
        "input_variant": TAG,
        "starting_commit": "0980d9a", "code_commit_at_run": git_commit(),
        "data_version": {"file": str(TABLE),
                         "sha256": hashlib.sha256(TABLE.read_bytes()).hexdigest(),
                         "snapshot": "heatla_data_0980d9a.zip"},
        "seed": SEED, "target": TARGET, "label_years": "2008-2018",
        "error_definition": "error = prediction - UCLA label (per 10,000); "
                            "positive = overprediction, negative = underprediction",
        "models": {k: str(v.steps[-1][1]) for k, v in M.make_models().items()},
        "preprocessing": "median imputation (and standardization for Poisson) fitted on the "
                         "training rows of each split only",
        "features_all_level": FEATURES, "features_level_specific": LEVEL_FEATURES,
        "baseline_index": BASELINE,
        "evaluations": {
            "spatial_cv": {
                "train": "nine of ten geographic folds (California)",
                "test": "the held-out fold; every ZIP is predicted exactly once",
                "folds": N_GROUPS, "fold_method": "k-means on standardized ZCTA centroid lat/lon",
                "heat_levels": list(LEVELS)},
            "la_holdout": {
                "train": "all California counties except Los Angeles",
                "test": "Los Angeles County", "heat_levels": list(LEVELS),
                "train_sizes": train_sizes}},
        "samples": info,
        "matches_committed_metrics_ca": checks,
        "outputs": sorted(p.name for p in OUT.glob("*.csv")),
        "command": ".venv/bin/python scripts/run_member1_statewide.py"
                   + ("" if TABLE == DEFAULT_TABLE else
                      f" --tag {TAG} --table {TABLE} --out {OUT} --baseline {BASELINE}"),
    }
    (OUT / "config.json").write_text(json.dumps(config, indent=2))
    (OUT / "metrics_member1.json").write_text(json.dumps(
        {"metrics": json.loads(mdf.to_json(orient="records")),
         "ces_baseline_matched": json.loads(cdf.to_json(orient="records"))}, indent=2))

    show = mdf[(mdf.evaluation == "la_holdout") & (mdf.model == "poisson")]
    print("\nLA holdout, Poisson:")
    print(show[["config", "scope", "n", "r2", "spearman", "top10_recall", "top20_recall"]]
          .round(3).to_string(index=False))
    print(f"\nwrote {OUT}/")


if __name__ == "__main__":
    main()
