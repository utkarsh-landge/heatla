import numpy as np
import pytest

from heatla.config import Config
from heatla.build_table import build_mock_table
from heatla.partB_hvi import add_hvi
from heatla.partA_statusquo import attach_distance


@pytest.fixture(scope="session")
def cfg():
    c = Config.load()
    c.data_mode = "mock"
    c.mock_n_tracts = 400          # small county: tests stay fast
    c.mock_n_centers_augmented = 20
    c.k_grid = (3, 5)
    c.k_report = (5,)
    c.radius_grid_m = (2000,)
    c.n_random_draws = 10
    return c


@pytest.fixture(scope="session")
def tracts(cfg):
    df, centers, er, _ = build_mock_table(cfg)
    df = df.merge(er, on="GEOID", how="left")
    df["pct_no_canopy"] = 100 - df["pct_canopy"]
    df["pop_density_km2"] = df["pop"] / df["land_area_sqkm"]
    df = add_hvi(df)
    return attach_distance(df, centers, cfg), centers
