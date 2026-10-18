"""GEOID normalisation and join integrity: the failure mode that silently
poisons everything downstream."""
import numpy as np
import pandas as pd
import pytest

from heatla.ingest import (norm_geoid, in_la_county, apportion_zip_to_tract,
                           _apportion_2010_to_2020)


def test_norm_geoid_handles_the_usual_breakages():
    s = pd.Series(["6037101110", "06037101110", "6037101110.0",
                   " 06037101110 ", "06037-1011-10"])
    out = norm_geoid(s)
    assert (out == "06037101110").all()
    assert out.str.len().eq(11).all()


def test_in_la_county_filters():
    s = norm_geoid(pd.Series(["06037101110", "06059001100", "36061000100"]))
    assert in_la_county(s).tolist() == [True, False, False]


def test_master_table_is_one_row_per_tract(tracts):
    df, _ = tracts
    assert df["GEOID"].is_unique
    assert df["GEOID"].str.len().eq(11).all()
    assert in_la_county(df["GEOID"]).all()


def test_zip_apportionment_is_population_weighted():
    # One ZIP with two tracts: the tract rate equals the ZIP rate.
    xw = pd.DataFrame({"zcta": ["90001", "90001"],
                       "GEOID": ["06037000001", "06037000002"],
                       "w_pop": [1000, 3000]})
    rates = pd.DataFrame({"zcta": ["90001"], "heat_er_rate_per100k": [40.0]})
    out = apportion_zip_to_tract(rates, xw, "heat_er_rate_per100k")
    assert len(out) == 2
    assert np.allclose(out["heat_er_rate_per100k"], 40.0)

    # A tract split across two ZIPs gets the population-weighted mean.
    xw2 = pd.DataFrame({"zcta": ["90001", "90002"],
                        "GEOID": ["06037000001", "06037000001"],
                        "w_pop": [1000, 3000]})
    rates2 = pd.DataFrame({"zcta": ["90001", "90002"],
                           "heat_er_rate_per100k": [40.0, 80.0]})
    out2 = apportion_zip_to_tract(rates2, xw2, "heat_er_rate_per100k")
    assert len(out2) == 1
    assert np.isclose(out2["heat_er_rate_per100k"].iloc[0], 70.0)


def test_2010_to_2020_crosswalk_conserves_values():
    # Two 2010 tracts merge into one 2020 tract; the value is a weighted mean.
    xw = pd.DataFrame({"GEOID20": ["06037000001", "06037000001"],
                       "GEOID10": ["06037000011", "06037000012"],
                       "w": [0.25, 0.75]})
    src = pd.DataFrame({"GEOID_src": ["06037000011", "06037000012"],
                        "ces_score": [20.0, 60.0]})
    out = _apportion_2010_to_2020(src, xw)
    assert len(out) == 1
    assert np.isclose(out["ces_score"].iloc[0], 0.25 * 20 + 0.75 * 60)
