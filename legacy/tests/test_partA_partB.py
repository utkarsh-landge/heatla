import numpy as np
import pandas as pd

from heatla.partA_statusquo import compare_distributions, unmet_need
from heatla.stats_utils import standardized_mean_difference, top_share_overlap
from heatla.partB_association import feature_sets, spatial_folds


def test_distribution_comparison_detects_a_planted_shift(tracts, cfg):
    df, _ = tracts
    d = df.copy()
    # Force "served" onto the hottest tracts: the comparison must notice.
    d["served"] = d["lst_f"] >= d["lst_f"].quantile(0.75)
    t = compare_distributions(d, "served").set_index("column")
    assert t.loc["lst_f", "std_mean_diff"] > 0.5
    assert t.loc["lst_f", "shift"] == "higher in served"


def test_no_shift_when_served_is_a_random_sample(tracts, cfg):
    df, _ = tracts
    d = df.copy()
    rng = np.random.default_rng(7)
    d["served"] = rng.random(len(d)) < 0.4
    t = compare_distributions(d, "served").set_index("column")
    assert abs(t.loc["hvi", "std_mean_diff"]) < 0.25


def test_smd_sign_and_scale():
    a = np.random.default_rng(0).normal(1, 1, 500)
    b = np.random.default_rng(1).normal(0, 1, 500)
    assert 0.7 < standardized_mean_difference(a, b) < 1.3
    assert standardized_mean_difference(b, a) < 0


def test_unmet_need_percentages_are_sane(tracts, cfg):
    df, _ = tracts
    un = unmet_need(df, cfg)[f"r{cfg.radius_m}"]
    for k in ("pop_served_pct", "high_hvi_pop_unserved_pct",
              "top10_hvi_pop_unserved_pct"):
        assert 0 <= un[k] <= 100


def test_association_features_exclude_hvi_inputs(tracts):
    df, _ = tracts
    social, phys = feature_sets(df, "hvi")
    leaking = {"lst_f", "pct_age65p", "pct_poverty", "pct_canopy", "pct_no_canopy"}
    assert not (set(social) | set(phys)) & leaking
    # The ER outcome has no such constraint.
    social2, phys2 = feature_sets(df, "heat_er_rate_per100k")
    assert "lst_f" in phys2


def test_spatial_folds_are_contiguous_blocks(tracts, cfg):
    df, _ = tracts
    folds = spatial_folds(df, 5, cfg.seed)
    assert len(np.unique(folds)) == 5
    # Each fold should be geographically tight: within-fold centroid spread
    # must be clearly smaller than the county-wide spread.
    from heatla.spatial import centroids_xy
    xy = centroids_xy(df)
    overall = xy.std(0).mean()
    within = np.mean([xy[folds == f].std(0).mean() for f in np.unique(folds)])
    assert within < 0.7 * overall


def test_top_share_overlap_bounds():
    s = pd.Series(np.arange(100.0))
    assert top_share_overlap(s, s, 0.1)["overlap_frac"] == 1.0
    assert top_share_overlap(s, -s, 0.1)["overlap_frac"] == 0.0
