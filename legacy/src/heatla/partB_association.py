"""Part B(c): association study - which social factors go with heat
vulnerability, net of the physical heat of a place?

A note on framing, because it is the whole point of this module.

The original plan was to *predict* HVI from a second feature set. That is not
a meaningful exercise: HVI is a deterministic function of four inputs, so any
model handed features correlated with those inputs simply relearns the
formula and reports a high R^2 that means nothing. We are not deploying a
forecaster.

What we do instead is an association analysis in the social-science sense:
fit flexible models to describe relationships, and read the structure out of
them. Physical heat (surface temperature, impervious surface, canopy, density)
goes in as CONTROLS - the immutable physical reality of a location - and the
socio-demographic variables are the ones of interest. The question is: among
places that are physically similar, which populations end up most vulnerable?

Two guards keep this honest:

1. The HVI-input leakage problem. Three of the four HVI inputs are features
   we would otherwise want on the right-hand side. We therefore run the
   analysis on two outcomes: (a) the leakage-free outcome, heat-related ER
   visits; and (b) HVI with its own input columns excluded from the predictor
   set, which is an association study of the *residual* social structure. The
   adequacy metrics are reported separately and never headlined.
2. Spatial leakage. Neighbouring tracts are near-copies of each other, so a
   random train/test split lets the model memorise a neighbourhood and look
   far better than it is. Folds are k-means clusters of tract centroids, so a
   whole contiguous region is held out at a time.

References for fitting flexible models for inference rather than forecasting:
  Breiman (2001) "Statistical modeling: the two cultures", Statist. Sci. 16(3).
  Molnar (2022) Interpretable Machine Learning, 2nd ed., chs. 8-9 (PDP/ALE/SHAP).
  Roberts et al. (2017) "Cross-validation strategies for data with temporal,
    spatial, hierarchical, or phylogenetic structure", Ecography 40(8).
  Athey & Imbens (2019) "Machine learning methods economists should know
    about", Annual Review of Economics 11.
"""
from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import partial_dependence, permutation_importance
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler
from sklearn.impute import SimpleImputer

from .config import Config
from .spatial import centroids_xy

warnings.filterwarnings("ignore", category=UserWarning)
# Apple's Accelerate BLAS raises spurious divide/overflow warnings inside
# sklearn's matmuls on this platform; they do not affect the results.
np.seterr(divide="ignore", over="ignore", invalid="ignore")

# Variables of interest: the social story.
SOCIAL = ["pct_age65p", "pct_under5", "pct_under18", "pct_poverty",
          "median_income", "pct_hispanic", "pct_black", "pct_asian",
          "pct_white_nh", "svi"]
# Controls: the physical reality of the location, held fixed.
PHYSICAL = ["lst_f", "pct_impervious", "pct_canopy", "pop_density_km2",
            "land_area_sqkm", "ces_pollution_pctl"]


def feature_sets(df: pd.DataFrame, outcome: str) -> tuple[list[str], list[str]]:
    social = [c for c in SOCIAL if c in df.columns and df[c].notna().sum() > 50]
    phys = [c for c in PHYSICAL if c in df.columns and df[c].notna().sum() > 50]
    if outcome == "hvi":
        # Drop the HVI inputs themselves: regressing an index on its own
        # ingredients is arithmetic, not analysis.
        drop = {"lst_f", "pct_age65p", "pct_poverty", "pct_canopy", "pct_no_canopy"}
        social = [c for c in social if c not in drop]
        phys = [c for c in phys if c not in drop]
    return social, phys


def spatial_folds(df: pd.DataFrame, n_folds: int, seed: int) -> np.ndarray:
    """k-means clusters of tract centroids. Holding out a contiguous block is
    the honest test: a random split leaves each test tract's neighbours in
    training, and the model can interpolate rather than generalise."""
    xy = centroids_xy(df)
    km = KMeans(n_clusters=n_folds, random_state=seed, n_init=10)
    return km.fit_predict(xy)


def _models(seed: int):
    yield "ridge_splines", Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        # Natural-spline basis makes the linear baseline additive-but-curved,
        # which is the GAM role here without pulling in another dependency.
        ("spline", SplineTransformer(n_knots=5, degree=3, include_bias=False)),
        ("model", RidgeCV(alphas=np.logspace(-3, 3, 25))),
    ])
    yield "random_forest", Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("model", RandomForestRegressor(
            n_estimators=600, min_samples_leaf=3, max_features=0.5,
            random_state=seed, n_jobs=-1)),
    ])
    try:
        from xgboost import XGBRegressor
        yield "xgboost", Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("model", XGBRegressor(
                n_estimators=700, learning_rate=0.03, max_depth=4,
                subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
                random_state=seed, n_jobs=-1, tree_method="hist")),
        ])
    except Exception as exc:                       # pragma: no cover
        print(f"  [partB] xgboost unavailable ({exc}); continuing without it")


def spatial_cv(X: pd.DataFrame, y: pd.Series, folds: np.ndarray,
               seed: int) -> pd.DataFrame:
    """Model-adequacy check only. These numbers say whether the fitted surface
    is worth interpreting; they are not the deliverable."""
    rows = []
    for name, pipe in _models(seed):
        preds = np.full(len(y), np.nan)
        for f in np.unique(folds):
            tr, te = folds != f, folds == f
            if tr.sum() < 50 or te.sum() < 5:
                continue
            m = pipe.fit(X[tr], y[tr])
            preds[te] = m.predict(X[te])
        ok = np.isfinite(preds) & y.notna().to_numpy()
        rows.append({
            "model": name,
            "cv": f"spatial k-means ({len(np.unique(folds))} folds)",
            "rmse": float(np.sqrt(mean_squared_error(y[ok], preds[ok]))),
            "mae": float(mean_absolute_error(y[ok], preds[ok])),
            "r2": float(r2_score(y[ok], preds[ok])),
            "n": int(ok.sum()),
        })
        # Random-split R2 alongside, purely to show how much the spatial split
        # costs: the difference is the leakage a random split would hide.
        rs = np.random.default_rng(seed).integers(0, 5, len(y))
        pr = np.full(len(y), np.nan)
        for f in range(5):
            tr, te = rs != f, rs == f
            pr[te] = pipe.fit(X[tr], y[tr]).predict(X[te])
        ok2 = np.isfinite(pr) & y.notna().to_numpy()
        rows[-1]["r2_random_split"] = float(r2_score(y[ok2], pr[ok2]))
        rows[-1]["r2_optimism_from_random_split"] = round(
            rows[-1]["r2_random_split"] - rows[-1]["r2"], 4)
    return pd.DataFrame(rows)


def fit_full(X: pd.DataFrame, y: pd.Series, seed: int, which: str = "random_forest"):
    for name, pipe in _models(seed):
        if name == which:
            return pipe.fit(X, y)
    raise ValueError(which)


def importances(model, X: pd.DataFrame, y: pd.Series, social: list[str],
                seed: int) -> pd.DataFrame:
    """Permutation importance on the fitted surface, flagged by role."""
    r = permutation_importance(model, X, y, n_repeats=15, random_state=seed,
                               n_jobs=-1, scoring="r2")
    return (pd.DataFrame({
        "feature": X.columns,
        "role": ["social (of interest)" if c in social else "physical (control)"
                 for c in X.columns],
        "perm_importance_mean": r.importances_mean,
        "perm_importance_std": r.importances_std,
    }).sort_values("perm_importance_mean", ascending=False).reset_index(drop=True))


def shap_summary(model, X: pd.DataFrame, social: list[str],
                 seed: int, max_rows: int = 600) -> pd.DataFrame | None:
    try:
        import shap
    except Exception:
        return None
    est = model.named_steps["model"]
    Xi = pd.DataFrame(model.named_steps["impute"].transform(X), columns=X.columns)
    bg = Xi.sample(min(max_rows, len(Xi)), random_state=seed)
    try:
        expl = shap.TreeExplainer(est)
        sv = expl.shap_values(bg, check_additivity=False)
    except Exception:
        return None
    out = pd.DataFrame({
        "feature": X.columns,
        "role": ["social (of interest)" if c in social else "physical (control)"
                 for c in X.columns],
        "mean_abs_shap": np.abs(sv).mean(0),
        # Sign of the association: correlation between a feature's value and
        # its own SHAP contribution. Positive = more of it, more vulnerability.
        "direction_corr": [float(np.corrcoef(bg.iloc[:, j], sv[:, j])[0, 1])
                           if np.std(sv[:, j]) > 0 else np.nan
                           for j in range(X.shape[1])],
    }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    out["direction"] = np.where(out["direction_corr"] > 0.05, "higher -> more vulnerable",
                                np.where(out["direction_corr"] < -0.05,
                                         "higher -> less vulnerable", "non-monotone/flat"))
    return out


def pdp_curves(model, X: pd.DataFrame, features: list[str],
               grid: int = 30) -> pd.DataFrame:
    """Partial-dependence curves for the key social variables.

    PDP assumes the varied feature is independent of the rest, which is shaky
    for correlated demographics; the ALE curves below relax that."""
    rows = []
    for f in features:
        if f not in X.columns:
            continue
        pd_ = partial_dependence(model, X, [f], grid_resolution=grid,
                                 kind="average")
        for v, g in zip(pd_["grid_values"][0], pd_["average"][0]):
            rows.append({"feature": f, "x": float(v), "pdp": float(g)})
    return pd.DataFrame(rows)


def ale_curves(model, X: pd.DataFrame, features: list[str],
               n_bins: int = 20) -> pd.DataFrame:
    """First-order accumulated local effects.

    Within each quantile bin of the feature, we take the model's response to
    moving from the bin's lower to upper edge while every other variable stays
    at its observed value, then accumulate. Unlike PDP this never asks the
    model about combinations that do not exist in the data (a tract that is
    90% elderly and 90% children, say)."""
    rows = []
    for f in features:
        if f not in X.columns:
            continue
        x = X[f].to_numpy(float)
        edges = np.unique(np.nanquantile(x, np.linspace(0, 1, n_bins + 1)))
        if len(edges) < 3:
            continue
        idx = np.clip(np.searchsorted(edges, x, side="left") - 1, 0, len(edges) - 2)
        eff = np.zeros(len(edges) - 1)
        for b in range(len(edges) - 1):
            m = idx == b
            if m.sum() < 3:
                continue
            lo, hi = X[m].copy(), X[m].copy()
            lo[f], hi[f] = edges[b], edges[b + 1]
            eff[b] = np.mean(model.predict(hi) - model.predict(lo))
        acc = np.cumsum(eff)
        acc -= acc.mean()
        centers = (edges[:-1] + edges[1:]) / 2
        rows += [{"feature": f, "x": float(c), "ale": float(a)}
                 for c, a in zip(centers, acc)]
    return pd.DataFrame(rows)


def run_one(cfg: Config, df: pd.DataFrame, outcome: str) -> dict:
    social, phys = feature_sets(df, outcome)
    feats = social + phys
    d = df.dropna(subset=[outcome]).copy()
    if len(d) < 100 or not social:
        return {"outcome": outcome, "skipped": "insufficient data"}
    X, y = d[feats], d[outcome]
    folds = spatial_folds(d, cfg.n_spatial_folds, cfg.seed)

    cv = spatial_cv(X, y, folds, cfg.seed)
    best = cv.sort_values("r2", ascending=False)["model"].iloc[0]
    tree_model = "xgboost" if (cv["model"] == "xgboost").any() else "random_forest"
    model = fit_full(X, y, cfg.seed, tree_model)

    imp = importances(model, X, y, social, cfg.seed)
    sh = shap_summary(model, X, social, cfg.seed)
    key_social = [f for f in imp[imp["role"].str.startswith("social")]["feature"]][:4]
    pdp = pdp_curves(model, X, key_social)
    ale = ale_curves(model, X, key_social)

    tag = f"partB_assoc_{outcome}"
    cv.round(4).to_csv(cfg.paths.tables / f"{tag}_cv.csv", index=False)
    imp.round(5).to_csv(cfg.paths.tables / f"{tag}_importance.csv", index=False)
    if sh is not None:
        sh.round(5).to_csv(cfg.paths.tables / f"{tag}_shap.csv", index=False)
    pdp.round(4).to_csv(cfg.paths.tables / f"{tag}_pdp.csv", index=False)
    ale.round(4).to_csv(cfg.paths.tables / f"{tag}_ale.csv", index=False)

    ranked = (sh if sh is not None else imp.rename(
        columns={"perm_importance_mean": "mean_abs_shap"}))
    social_rank = ranked[ranked["role"].str.startswith("social")].head(6)
    return {
        "outcome": outcome,
        "n": int(len(d)),
        "features_social": social,
        "features_physical_controls": phys,
        "fitted_model": tree_model,
        "best_cv_model": best,
        "cv": cv.round(4).to_dict("records"),
        "top_social_associations": social_rank.round(4).to_dict("records"),
        "interpretation_note": (
            "Importance and SHAP describe the fitted surface, not a causal "
            "effect. Physical heat variables are controls; the ranking of the "
            "social variables is the deliverable, and the CV numbers only say "
            "whether the surface is stable enough to read."),
    }


def run(cfg: Config, df: pd.DataFrame) -> dict:
    out = {}
    # Outcome 1: HVI with its own inputs excluded.
    out["hvi"] = run_one(cfg, df, "hvi")
    # Outcome 2: leakage-free health outcome, where available.
    if ("heat_er_rate_per100k" in df.columns
            and df["heat_er_rate_per100k"].notna().sum() > 200):
        out["heat_er_rate_per100k"] = run_one(cfg, df, "heat_er_rate_per100k")
        out["heat_er_rate_per100k"]["caveat"] = (
            "ER rates are ZIP-level values apportioned to tracts, so tracts "
            "inside one ZIP share an outcome value. Treat the ranking as "
            "corroboration of the HVI-based one, not an independent result.")
    (cfg.paths.tables / "partB_association.json").write_text(
        json.dumps(out, indent=2, default=float))

    for k, v in out.items():
        if "skipped" in v:
            continue
        top = ", ".join(f"{r['feature']}" for r in v["top_social_associations"][:3])
        cvr2 = max(r["r2"] for r in v["cv"])
        print(f"  Part B association [{k}]: top social factors = {top} "
              f"(spatial-CV R2={cvr2:.2f}, adequacy only)")
    return out
