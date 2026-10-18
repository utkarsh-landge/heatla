import numpy as np
import pandas as pd
import pytest

from heatla.partB_hvi import compute_hvi, HVI_COMPONENTS


def test_hvi_is_bounded_and_ranked(tracts):
    df, _ = tracts
    h = df["hvi"].dropna()
    assert h.between(0, 100).all()
    assert len(h) == len(df)


def test_hvi_is_monotone_in_each_input():
    """Raising one input while holding the others fixed must not lower HVI."""
    n = 200
    rng = np.random.default_rng(0)
    base = pd.DataFrame({
        "lst_f": rng.normal(95, 6, n), "pct_age65p": rng.normal(14, 4, n),
        "pct_poverty": rng.normal(17, 6, n), "pct_no_canopy": rng.normal(85, 8, n)})
    h0 = compute_hvi(base)["hvi"]
    for col in HVI_COMPONENTS:
        bumped = base.copy()
        # Push one tract to the top of that input's distribution.
        bumped.loc[0, col] = bumped[col].max() + 10
        h1 = compute_hvi(bumped)["hvi"]
        assert h1.iloc[0] >= h0.iloc[0] - 1e-9


def test_hvi_ignores_units():
    """Percentile ranks mean a monotone rescale of an input changes nothing."""
    n = 150
    rng = np.random.default_rng(1)
    base = pd.DataFrame({
        "lst_f": rng.normal(95, 6, n), "pct_age65p": rng.normal(14, 4, n),
        "pct_poverty": rng.normal(17, 6, n), "pct_no_canopy": rng.normal(85, 8, n)})
    scaled = base.copy()
    scaled["lst_f"] = (scaled["lst_f"] - 32) * 5 / 9      # F -> C
    assert np.allclose(compute_hvi(base)["hvi"], compute_hvi(scaled)["hvi"])


def test_hvi_survives_a_missing_component():
    n = 100
    rng = np.random.default_rng(2)
    base = pd.DataFrame({
        "lst_f": rng.normal(95, 6, n), "pct_age65p": rng.normal(14, 4, n),
        "pct_poverty": rng.normal(17, 6, n), "pct_no_canopy": rng.normal(85, 8, n)})
    base.loc[0, "pct_canopy_missing"] = np.nan
    base.loc[0, "lst_f"] = np.nan
    out = compute_hvi(base)
    assert out.loc[0, "hvi_n_components"] == 3
    assert np.isfinite(out.loc[0, "hvi"])
