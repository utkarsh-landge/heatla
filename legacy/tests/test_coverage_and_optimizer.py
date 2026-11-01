import numpy as np
import pytest

from heatla.config import Config
from heatla.spatial import centroids_xy, coverage_sets, covered_mask, points_xy
from heatla.partC_optimize import (greedy_mclp, ilp_mclp, tract_weights,
                                   evaluate, build_candidates, baseline_top_k)


def test_coverage_sets_match_a_brute_force_count(tracts, cfg):
    df, _ = tracts
    xy = centroids_xy(df)
    cov = coverage_sets(xy[:20], xy, 2000)
    for i, c in enumerate(cov):
        d = np.hypot(*(xy - xy[i]).T)
        assert set(c.tolist()) == set(np.flatnonzero(d <= 2000).tolist())


def test_a_site_covers_its_own_tract(tracts, cfg):
    df, _ = tracts
    xy = centroids_xy(df)
    cov = coverage_sets(xy, xy, cfg.radius_m)
    assert all(i in cov[i] for i in range(len(df)))


def test_covered_mask_agrees_with_coverage_sets(tracts, cfg):
    df, centers = tracts
    xy = centroids_xy(df)
    cxy = points_xy(centers)
    mask = covered_mask(cxy, xy, cfg.radius_m)
    cov = coverage_sets(cxy, xy, cfg.radius_m)
    union = np.zeros(len(df), bool)
    for c in cov:
        union[c] = True
    assert (mask == union).all()


def test_greedy_coverage_is_monotone_in_k(tracts, cfg):
    df, centers = tracts
    _, cov, already = build_candidates(df, centers, cfg.radius_m)
    w = tract_weights(df, "pop_x_hvi")
    prev = -1.0
    for k in (1, 2, 4, 8, 12):
        sel = greedy_mclp(cov, w, k, already)
        got = evaluate(df, cov, sel, already, cfg)["vuln_weighted_pop_covered"]
        assert got >= prev - 1e-6, f"coverage dropped at K={k}"
        prev = got


def test_greedy_picks_are_nested_prefixes(tracts, cfg):
    """Greedy is deterministic, so K=5 must start with the K=3 picks."""
    df, centers = tracts
    _, cov, already = build_candidates(df, centers, cfg.radius_m)
    w = tract_weights(df, "count")
    assert greedy_mclp(cov, w, 5, already)[:3] == greedy_mclp(cov, w, 3, already)


def test_ilp_is_at_least_as_good_as_greedy(tracts, cfg):
    df, centers = tracts
    _, cov, already = build_candidates(df, centers, cfg.radius_m)
    for objective in ("count", "pop_x_hvi"):
        w = tract_weights(df, objective)
        k = 5
        g = greedy_mclp(cov, w, k, already)
        ilp, meta = ilp_mclp(cov, w, k, already, time_limit_s=120)
        gw = w[np.unique(np.concatenate([cov[e] for e in g]))].sum()
        iw = w[np.unique(np.concatenate([cov[e] for e in ilp]))].sum()
        if meta["proven_optimal"]:
            assert iw >= gw - 1e-6, f"{objective}: ILP below greedy"
            # And the submodular guarantee must hold.
            assert gw >= (1 - 1 / np.e) * iw - 1e-6


def test_greedy_beats_sort_by_index_on_its_own_objective(tracts, cfg):
    """The redundancy argument: ranking tracts by HVI picks neighbours."""
    df, centers = tracts
    _, cov, already = build_candidates(df, centers, cfg.radius_m)
    w = tract_weights(df, "pop_x_hvi")
    k = 8
    g = evaluate(df, cov, greedy_mclp(cov, w, k, already), already, cfg)
    s = evaluate(df, cov, baseline_top_k(df, "hvi", k), already, cfg)
    assert (g["vuln_weighted_pop_covered"] >= s["vuln_weighted_pop_covered"])


def test_evaluate_reports_every_metric_for_any_objective(tracts, cfg):
    df, centers = tracts
    _, cov, already = build_candidates(df, centers, cfg.radius_m)
    for objective in ("count", "pop_x_hvi"):
        sel = greedy_mclp(cov, tract_weights(df, objective), 5, already)
        ev = evaluate(df, cov, sel, already, cfg)
        for key in ("tracts_covered", "pop_covered_pct",
                    "vuln_weighted_pop_covered_pct", "top25_hvi_pop_covered_pct",
                    "hvi_coverage_gap_pp", "fairness_coverage_pct_by_group"):
            assert key in ev
        fair = ev["fairness_coverage_pct_by_group"]
        assert "age_65_plus" in fair and "under_5" in fair
        assert all(0 <= v <= 100 for k_, v in fair.items()
                   if k_ != "max_minus_min_pp" and np.isfinite(v))


def test_existing_centers_coverage_is_the_floor(tracts, cfg):
    """Adding sites can never reduce coverage below the status quo."""
    df, centers = tracts
    _, cov, already = build_candidates(df, centers, cfg.radius_m)
    base = evaluate(df, cov, [], already, cfg)
    for objective in ("count", "pop_x_hvi"):
        sel = greedy_mclp(cov, tract_weights(df, objective), 6, already)
        ev = evaluate(df, cov, sel, already, cfg)
        assert ev["pop_covered"] >= base["pop_covered"] - 1e-6
        assert ev["tracts_covered"] >= base["tracts_covered"]
