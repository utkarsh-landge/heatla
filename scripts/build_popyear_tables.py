"""Population-year check: statewide tables with 2010 Census population.

The label covers 2008-2018, but the population field in UCLA's layer (used for
population density and as the Poisson sample weight) is from the 2020 Census. This
builds two copies of the corrected statewide table that use 2010 Census ZCTA population
(POP10 from the Census 2010 Gazetteer ZCTA file) instead:

  density2010  pop_density_per_sqmi = POP10 / aland_sqmi; 'population' unchanged
               (UCLA 2020 population stays the Poisson weight, it is the label's
               denominator)
  both2010     same density, and 'population' = POP10 as well

aland_sqmi is the land area already in the table (2023 Gazetteer). Every other column,
the rows and their order are unchanged, so cleaning and folds are the same as in the
ces40_fixed run. A ZIP with no POP10 keeps density NaN (median-imputed inside each
training fold) and, in both2010, keeps its UCLA population. A ZIP whose POP10 is 0
gets density 0, and in both2010 also keeps its UCLA population (a zero weight would
drop it from Poisson fitting).

Input:  data/raw/Gaz_zcta_national.txt
        (https://www2.census.gov/geo/docs/maps-data/data/gazetteer/Gaz_zcta_national.zip)
Writes: data/processed/model_table_ca_ces40_fixed_density2010.csv
        data/processed/model_table_ca_ces40_fixed_both2010.csv
        results/population_year_check/pop10_match_counts.csv

Run:  .venv/bin/python scripts/build_popyear_tables.py
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

SRC = pathlib.Path("results/member1/inputs/model_table_ca_ces40_fixed.csv")
GAZ = pathlib.Path("data/raw/Gaz_zcta_national.txt")
OUT = pathlib.Path("data/processed")
CHECK = pathlib.Path("results/population_year_check")


def load_pop10() -> pd.Series:
    g = pd.read_csv(GAZ, sep="\t", dtype={"GEOID": str})
    g.columns = g.columns.str.strip()
    assert g.GEOID.str.len().eq(5).all() and not g.GEOID.duplicated().any()
    return g.set_index("GEOID")["POP10"].astype(float)


def main() -> None:
    t = pd.read_csv(SRC, dtype={"zip": str})
    pop10 = load_pop10()
    p10 = t["zip"].map(pop10)

    a = t.copy()
    a["pop_density_per_sqmi"] = (p10 / a["aland_sqmi"]).round(2)
    b = a.copy()
    use = p10.notna() & (p10 > 0)
    b["population"] = np.where(use, p10, t["population"])
    a.to_csv(OUT / "model_table_ca_ces40_fixed_density2010.csv", index=False)
    b.to_csv(OUT / "model_table_ca_ces40_fixed_both2010.csv", index=False)

    # match counts on the ZIPs that survive the statewide cleaning (label, centroid, population)
    kept = t.dropna(subset=["excess_er_rate_per_10k", "lat", "lon", "population"])
    z = kept.drop_duplicates("zip").assign(pop10=lambda d: d["zip"].map(pop10))
    rows = []
    for scope, d in (("statewide", z), ("Los Angeles", z[z.county == "Los Angeles"])):
        rows.append({"scope": scope, "zips": len(d),
                     "pop10_found": int(d.pop10.notna().sum()),
                     "pop10_missing": int(d.pop10.isna().sum()),
                     "pop10_zero": int((d.pop10 == 0).sum()),
                     "missing_zips": " ".join(d.loc[d.pop10.isna(), "zip"]),
                     "zero_zips": " ".join(d.loc[d.pop10 == 0, "zip"]),
                     "median_pop10_over_ucla_pop": float((d.pop10 / d.population).median())})
    CHECK.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows)
    out.to_csv(CHECK / "pop10_match_counts.csv", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
