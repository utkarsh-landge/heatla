"""Steps 3-4 - geographic groups, leave-one-group-out models, and metrics.

Target: excess ER visit rate per 10,000 (CHS-4, 2008-2018), per ZIP.
Models: Poisson (rate GLM, population-weighted, ridge), Random Forest, Gradient
Boosting. Cross-validation: leave-one-geographic-group-out over 5 spatial groups.

All preprocessing (impute, scale) is fit inside the training fold only, so there
is no leakage from held-out ZIPs. Fixed seeds make the run reproducible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.cluster import KMeans
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import r2_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42
TARGET = "excess_er_rate_per_10k"
N_GROUPS = 5

FEATURES = [
    "pm25", "ozone", "asthma_ed_per10k", "cardiovascular_ed_per10k",
    "median_hh_income", "pct_poverty", "pct_age_65plus", "pct_renters",
    "pct_no_vehicle", "pct_uninsured", "pct_construction",
    "total_pop", "pop_density_per_sqmi",
]
BASELINE_INDEX = "ces4_percentile"  # existing index comparator (not a model feature)


# ---------------------------------------------------------------- data / groups
def load_table(path: str = "data/processed/model_table.csv") -> pd.DataFrame:
    df = pd.read_csv(path)
    # modeling needs target + coordinates (for spatial groups); drop rows missing them
    df = df.dropna(subset=[TARGET, "lat", "lon"]).reset_index(drop=True)
    return df


def assign_groups(df: pd.DataFrame, n: int = N_GROUPS, seed: int = SEED) -> pd.Series:
    """K-means on standardized centroid coordinates -> fixed spatial groups.

    Grouping uses only lat/lon, never the target, so it introduces no leakage.
    """
    xy = StandardScaler().fit_transform(df[["lat", "lon"]].to_numpy())
    km = KMeans(n_clusters=n, random_state=seed, n_init=10)
    return pd.Series(km.fit_predict(xy), index=df.index, name="group")


# ---------------------------------------------------------------- model zoo
def make_models() -> dict[str, object]:
    num = Pipeline([("impute", SimpleImputer(strategy="median"))])
    scaled = Pipeline([("impute", SimpleImputer(strategy="median")),
                       ("scale", StandardScaler())])
    poisson = Pipeline([("prep", scaled),
                        ("glm", PoissonRegressor(alpha=1.0, max_iter=5000))])
    rf = Pipeline([("prep", num),
                   ("rf", RandomForestRegressor(n_estimators=500, random_state=SEED,
                                                n_jobs=1, min_samples_leaf=2))])
    gbm = Pipeline([("prep", num),
                    ("gbm", GradientBoostingRegressor(random_state=SEED))])
    return {"poisson": poisson, "random_forest": rf, "gradient_boosting": gbm}


# ---------------------------------------------------------------- metrics
def top_k_recall(y_true, y_pred, frac: float) -> float:
    """Share of the truly top-`frac` ZIPs that fall in the predicted top-`frac`."""
    n = len(y_true)
    k = max(1, int(round(frac * n)))
    true_top = set(np.argsort(y_true)[-k:])
    pred_top = set(np.argsort(y_pred)[-k:])
    return len(true_top & pred_top) / k


def metric_block(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    return {
        "n": int(len(y_true)),
        "r2": float(r2_score(y_true, y_pred)) if len(y_true) > 1 else None,
        "spearman": float(spearmanr(y_true, y_pred).statistic) if len(y_true) > 2 else None,
        "top10_recall": top_k_recall(y_true, y_pred, 0.10),
        "top20_recall": top_k_recall(y_true, y_pred, 0.20),
    }


def bootstrap_ci(y_true, y_pred, fn, n_boot: int = 1000, seed: int = SEED) -> list[float]:
    rng = np.random.default_rng(seed)
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    n = len(y_true)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        try:
            vals.append(fn(y_true[idx], y_pred[idx]))
        except Exception:
            continue
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return [float(lo), float(hi)]


# ---------------------------------------------------------------- CV driver
def run_logo(df: pd.DataFrame, groups: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Leave-one-group-out CV for every model; return OOF predictions + metrics."""
    X = df[FEATURES]
    y = df[TARGET].to_numpy(float)
    pop = df["ucla_population"].to_numpy(float)
    logo = LeaveOneGroupOut()
    models = make_models()

    oof = pd.DataFrame({"zip": df["zip"], "group": groups.values, "y_true": y})
    results: dict = {"models": {}, "baselines": {}, "n_groups": int(groups.nunique())}

    for name, model in models.items():
        preds = np.full(len(df), np.nan)
        for tr, te in logo.split(X, y, groups):
            if name == "poisson":
                model.fit(X.iloc[tr], y[tr], glm__sample_weight=pop[tr])
            else:
                model.fit(X.iloc[tr], y[tr])
            preds[te] = model.predict(X.iloc[te])
        oof[f"pred_{name}"] = preds

        overall = metric_block(y, preds)
        overall["r2_ci"] = bootstrap_ci(y, preds, lambda a, b: r2_score(a, b))
        overall["spearman_ci"] = bootstrap_ci(
            y, preds, lambda a, b: spearmanr(a, b).statistic)
        per_group = {}
        for g in sorted(np.unique(groups)):
            m = groups.values == g
            per_group[str(int(g))] = metric_block(y[m], preds[m])
        results["models"][name] = {"overall": overall, "per_group": per_group}

    # baselines -------------------------------------------------------------
    mean_pred = np.full(len(df), y.mean())
    results["baselines"]["predict_mean"] = metric_block(y, mean_pred)
    if BASELINE_INDEX in df:
        idx = df[BASELINE_INDEX].to_numpy(float)
        mask = ~np.isnan(idx)
        results["baselines"]["ces4_percentile"] = {
            "n": int(mask.sum()),
            "spearman": float(spearmanr(y[mask], idx[mask]).statistic),
            "top10_recall": top_k_recall(y[mask], idx[mask], 0.10),
            "top20_recall": top_k_recall(y[mask], idx[mask], 0.20),
            "note": "existing index vs observed target (rank only; higher pctile = higher risk)",
        }
    return oof, results


def permutation_importances(df: pd.DataFrame, groups: pd.Series) -> dict:
    """Permutation importance on held-out folds, averaged, for RF and GBM."""
    X, y = df[FEATURES], df[TARGET].to_numpy(float)
    logo = LeaveOneGroupOut()
    out: dict = {}
    for name in ("random_forest", "gradient_boosting"):
        model = make_models()[name]
        acc = np.zeros(len(FEATURES))
        folds = 0
        for tr, te in logo.split(X, y, groups):
            if len(te) < 5:
                continue
            model.fit(X.iloc[tr], y[tr])
            r = permutation_importance(model, X.iloc[te], y[te],
                                       n_repeats=20, random_state=SEED, n_jobs=1)
            acc += r.importances_mean
            folds += 1
        out[name] = dict(sorted(zip(FEATURES, (acc / max(folds, 1)).tolist()),
                                 key=lambda kv: -kv[1]))
    return out
