"""Small statistical helpers used across Parts A and B."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def standardized_mean_difference(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d with a pooled SD: how far the served group sits from the
    county as a whole, in standard deviations. |d| < 0.1 is 'no shift'."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return np.nan
    na, nb = len(a), len(b)
    sp = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    return float((a.mean() - b.mean()) / sp) if sp > 0 else np.nan


def ks_test(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return np.nan, np.nan
    r = stats.ks_2samp(a, b)
    return float(r.statistic), float(r.pvalue)


def quantiles(x: np.ndarray, qs=(0.1, 0.25, 0.5, 0.75, 0.9)) -> dict:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return {f"p{int(q*100)}": np.nan for q in qs}
    return {f"p{int(q*100)}": float(np.quantile(x, q)) for q in qs}


def spearman(a, b) -> tuple[float, float, int]:
    s = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(s) < 3:
        return np.nan, np.nan, len(s)
    r = stats.spearmanr(s["a"], s["b"])
    return float(r.statistic), float(r.pvalue), len(s)


def pct_rank(x: pd.Series) -> pd.Series:
    """Percentile rank in [0, 100]; NaNs stay NaN rather than sinking to 0."""
    return x.rank(pct=True, na_option="keep") * 100.0


def top_share_overlap(a: pd.Series, b: pd.Series, frac: float = 0.10) -> dict:
    """How much the top-x% sets of two indices agree."""
    d = pd.DataFrame({"a": a, "b": b}).dropna()
    k = max(1, int(round(len(d) * frac)))
    ta = set(d["a"].nlargest(k).index)
    tb = set(d["b"].nlargest(k).index)
    inter = len(ta & tb)
    return {"k": k, "overlap_n": inter, "overlap_frac": inter / k if k else np.nan,
            "jaccard": inter / len(ta | tb) if (ta | tb) else np.nan}
