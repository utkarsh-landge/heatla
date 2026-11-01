"""Shared spatial helpers: centroids, distances, coverage sets.

Kept in one place because Parts A and C must agree on what "within 2 km"
means. Everything happens in EPSG:3310 (California Albers, metres).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import cKDTree

from .config import CRS_WORK, CRS_GEO


def centroids_xy(tracts: gpd.GeoDataFrame) -> np.ndarray:
    """Projected tract centroids as an (n, 2) array of metres.

    Uses the published internal point (INTPTLON/INTPTLAT) when available: the
    Census guarantees it falls inside the polygon, which a geometric centroid
    does not for the horseshoe-shaped tracts along the coast."""
    if {"INTPTLON", "INTPTLAT"}.issubset(tracts.columns):
        pts = gpd.GeoSeries(
            gpd.points_from_xy(tracts["INTPTLON"], tracts["INTPTLAT"]),
            crs=CRS_GEO).to_crs(CRS_WORK)
    else:
        pts = tracts.to_crs(CRS_WORK).representative_point()
    return np.c_[pts.x.to_numpy(), pts.y.to_numpy()]


def points_xy(gdf: gpd.GeoDataFrame) -> np.ndarray:
    p = gdf.to_crs(CRS_WORK)
    return np.c_[p.geometry.x.to_numpy(), p.geometry.y.to_numpy()]


def nearest_distance_m(src_xy: np.ndarray, dst_xy: np.ndarray) -> np.ndarray:
    """Distance from each source point to the nearest destination point."""
    if len(dst_xy) == 0:
        return np.full(len(src_xy), np.inf)
    d, _ = cKDTree(dst_xy).query(src_xy, k=1)
    return d


def coverage_sets(cand_xy: np.ndarray, tract_xy: np.ndarray,
                  radius_m: float) -> list[np.ndarray]:
    """For each candidate site, the indices of tracts it covers."""
    tree = cKDTree(tract_xy)
    return [np.asarray(sorted(ix), dtype=np.int64)
            for ix in tree.query_ball_point(cand_xy, r=radius_m)]


def covered_mask(cand_xy: np.ndarray, tract_xy: np.ndarray,
                 radius_m: float) -> np.ndarray:
    """Boolean mask of tracts within radius of any candidate."""
    if len(cand_xy) == 0:
        return np.zeros(len(tract_xy), dtype=bool)
    return nearest_distance_m(tract_xy, cand_xy) <= radius_m
