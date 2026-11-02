"""Step 2 - train on California, test honestly, especially on held-out LA County.

Two tests:
  A. Spatial cross-validation (leave-one-geographic-group-out) over the whole state.
  B. LA hold-out: train on every county EXCEPT Los Angeles, then predict LA. LA has no
     part in training, so this is an honest external test of transfer to LA.

Target : excess ER rate per 10,000 (CHS 1-4, 2008-2018), one row per ZIP x CHS level.
Models : Poisson (rate GLM, population-weighted, ridge), Random Forest, Gradient Boosting.
Baselines: predict-the-mean and the existing CalEnviroScreen 4.0 percentile index.

All preprocessing is fit inside the training fold only. Seed fixed. No fabrication.
"""
from __future__ import annotations

import json
import os
import pathlib
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
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from heatla import model as M  # reuse make_models, metric_block, bootstrap_ci, top_k_recall  # noqa: E402

RES = pathlib.Path("results")
SEED = 42
N_GROUPS = 10
TARGET = "excess_er_rate_per_10k"
FEATURES = [
    "chs_level", "pm25", "ozone", "asthma_ed_per10k", "cardiovascular_ed_per10k",
    "poverty_pct", "elderly65_pct", "edu_lt_hs_pct", "ling_isol_pct",
    "unemployment_pct", "housing_burden_pct", "pop_density_per_sqmi",
]
BASELINE = "ces4_percentile"


def load() -> pd.DataFrame:
    df = pd.read_csv("data/processed/model_table_ca.csv")
    for c in FEATURES + [TARGET, "lat", "lon", "population", BASELINE]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=[TARGET, "lat", "lon", "population"]).reset_index(drop=True)
    df["zip"] = df["zip"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    return df


def fit_predict(model, Xtr, ytr, Xte, name, poptr):
    if name == "poisson":
        model.fit(Xtr, ytr, glm__sample_weight=poptr)
    else:
        model.fit(Xtr, ytr)
    return model.predict(Xte)


def metrics_with_ci(y, p):
    o = M.metric_block(y, p)
    o["r2_ci"] = M.bootstrap_ci(y, p, lambda a, b: r2_score(a, b))
    o["spearman_ci"] = M.bootstrap_ci(y, p, lambda a, b: spearmanr(a, b).statistic)
    return o


def test_a_spatial(df) -> dict:
    xy = StandardScaler().fit_transform(df[["lat", "lon"]].to_numpy())
    groups = KMeans(n_clusters=N_GROUPS, random_state=SEED, n_init=10).fit_predict(xy)
    X, y = df[FEATURES], df[TARGET].to_numpy(float)
    pop = df["population"].to_numpy(float)
    logo = LeaveOneGroupOut()
    out = {}
    for name in ("poisson", "random_forest", "gradient_boosting"):
        model = M.make_models()[name]
        pred = np.full(len(df), np.nan)
        for tr, te in logo.split(X, y, groups):
            pred[te] = fit_predict(model, X.iloc[tr], y[tr], X.iloc[te], name, pop[tr])
        out[name] = metrics_with_ci(y, pred)
    return {"n": int(len(df)), "n_groups": N_GROUPS, "models": out}


def test_b_la_holdout(df) -> dict:
    is_la = df["county"] == "Los Angeles"
    tr_df, te_df = df[~is_la], df[is_la]
    Xtr, ytr, poptr = tr_df[FEATURES], tr_df[TARGET].to_numpy(float), tr_df["population"].to_numpy(float)
    Xte, yte = te_df[FEATURES], te_df[TARGET].to_numpy(float)
    res = {"n_train_nonLA": int(len(tr_df)), "n_test_LA": int(len(te_df)), "models": {}}

    preds_out = te_df[["zip", "chs_level", "county", TARGET]].copy()
    for name in ("poisson", "random_forest", "gradient_boosting"):
        model = M.make_models()[name]
        p = fit_predict(model, Xtr, ytr, Xte, name, poptr)
        preds_out[f"pred_{name}"] = p
        block = {"all_chs": metrics_with_ci(yte, p)}
        for chs in (4,):
            m = te_df["chs_level"].to_numpy() == chs
            if m.sum() > 3:
                block[f"chs{chs}"] = M.metric_block(yte[m], p[m])
        res["models"][name] = block

    # baselines on LA test rows
    mean_pred = np.full(len(te_df), ytr.mean())
    res["baselines"] = {"predict_mean": M.metric_block(yte, mean_pred)}
    idx = te_df[BASELINE].to_numpy(float)
    mask = ~np.isnan(idx)
    res["baselines"]["ces4_percentile"] = {
        "n": int(mask.sum()),
        "spearman": float(spearmanr(yte[mask], idx[mask]).statistic),
        "top10_recall": M.top_k_recall(yte[mask], idx[mask], 0.10),
        "top20_recall": M.top_k_recall(yte[mask], idx[mask], 0.20),
        "note": "existing index vs observed LA target (rank only)",
    }
    preds_out.to_csv(RES / "predictions_la_holdout.csv", index=False)
    return res


def main() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    df = load()
    print(f"loaded {len(df)} rows ({df['zip'].nunique()} ZIPs x CHS), "
          f"LA rows: {(df['county']=='Los Angeles').sum()}")
    results = {
        "seed": SEED, "target": TARGET, "features": FEATURES,
        "test_a_spatial_cv": test_a_spatial(df),
        "test_b_la_holdout": test_b_la_holdout(df),
    }
    (RES / "metrics_ca.json").write_text(json.dumps(results, indent=2))

    b = results["test_b_la_holdout"]
    print("\n===== TEST B: train on CA minus LA, predict LA =====")
    print(f"train={b['n_train_nonLA']}  test(LA)={b['n_test_LA']}")
    hdr = f"{'model':>18} {'spearman':>9} {'top10%':>7} {'top20%':>7} {'R2':>7}"
    print(hdr)
    for name, blk in b["models"].items():
        a = blk["all_chs"]
        print(f"{name:>18} {a['spearman']:>9.3f} {a['top10_recall']:>7.2f} "
              f"{a['top20_recall']:>7.2f} {a['r2']:>7.3f}")
    cp = b["baselines"]["ces4_percentile"]
    print(f"{'CES4 percentile':>18} {cp['spearman']:>9.3f} {cp['top10_recall']:>7.2f} "
          f"{cp['top20_recall']:>7.2f} {'--':>7}")


if __name__ == "__main__":
    main()
