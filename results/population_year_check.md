# Population year check: 2010 instead of 2020 Census population

The label covers 2008–2018, but the population in UCLA's layer is from the 2020 Census. We use it twice: for population density (a model input) and as the Poisson sample weight. To see whether this matters, we reran Part 1 and Part 2 with 2010 Census population.

## What we did

- **2010 population:** `POP10` from the Census 2010 Gazetteer ZCTA file (`Gaz_zcta_national.zip` on www2.census.gov, saved in `data/raw/`, not committed), joined on 5-digit ZIP = ZCTA code.
- **Matches:** 1,658 of the 1,675 statewide ZIPs and 285 of the 287 LA ZIPs have a 2010 population. The 17 without one are mostly campus or PO-box ZIPs (LA: 90639, 90840). Three LA ZIPs (90506, 90747, 91608) have a 2010 population of 0. The median ratio of 2010 to UCLA population is 0.96 statewide and 0.98 in LA. Details are in `results/population_year_check/pop10_match_counts.csv`.
- **Variant (a), density 2010:** density = POP10 / land area (the same 2023 Gazetteer land area as before). The Poisson weight stays the UCLA 2020 population, because that is the denominator of the label.
- **Variant (b), both 2010:** the same density, and the Poisson weight = POP10.
- Missing POP10: density left missing (median-imputed inside each training fold), and the UCLA weight kept. POP10 = 0: density 0, UCLA weight kept.
- Everything else is unchanged: rows, folds, models, seed and metrics. A rerun of the original inputs reproduced the committed Part 1 level-4 numbers exactly, and the Part 2 main run to within 0.0012 in Spearman (gradient boosting; Poisson was exact).
- The weight only enters Poisson, so random forest and gradient boosting are the same in (a) and (b).

Scripts: `scripts/build_popyear_tables.py` (Part 1 tables), `scripts/run_member1_statewide.py` (unchanged), `part2/run_population_year_check.py` (Part 2).

## Part 1: statewide models, heat level 4 (all-level models)

Compared with `results/member1/ces40_fixed`. Outputs: `results/member1/popyear_density2010/`, `results/member1/popyear_both2010/`, and `results/population_year_check/part1_level4_comparison.csv`.

| Evaluation | Model | R² 2020 | R² (a) | R² (b) | Spearman 2020 | Spearman (a) | Spearman (b) | Top-10% 2020 | Top-10% (a) | Top-10% (b) |
|---|---|---|---|---|---|---|---|---|---|---|
| LA holdout | Poisson | 0.349 | 0.360 | 0.343 | 0.730 | 0.746 | 0.741 | 0.34 | 0.34 | 0.31 |
| LA holdout | Random forest | −0.483 | −0.337 | −0.337 | 0.688 | 0.710 | 0.710 | 0.14 | 0.17 | 0.17 |
| LA holdout | Gradient boosting | −0.291 | −0.290 | −0.290 | 0.683 | 0.686 | 0.686 | 0.24 | 0.24 | 0.24 |
| Spatial CV | Poisson | −0.015 | −0.017 | −0.013 | 0.512 | 0.509 | 0.508 | 0.16 | 0.16 | 0.16 |
| Spatial CV | Random forest | 0.199 | 0.195 | 0.195 | 0.567 | 0.550 | 0.550 | 0.32 | 0.33 | 0.33 |
| Spatial CV | Gradient boosting | 0.284 | 0.284 | 0.284 | 0.585 | 0.576 | 0.576 | 0.33 | 0.33 | 0.33 |

In the LA holdout, one top-10% ZIP is 0.034 (29 ZIPs).

## Part 2: LA comparison, 287 ZIPs, five LA spatial folds

Compared with `part2/results/feature_comparison/metrics_all_287.csv`. Outputs: `part2/results/population_year_check/`.

| Inputs | Model | R² 2020 | R² (a) | R² (b) | Spearman 2020 | Spearman (a) | Spearman (b) |
|---|---|---|---|---|---|---|---|
| Base | Poisson | 0.403 | 0.408 | 0.404 | 0.718 | 0.722 | 0.722 |
| Base | Random forest | 0.421 | 0.412 | 0.412 | 0.685 | 0.673 | 0.673 |
| Base | Gradient boosting | 0.425 | 0.429 | 0.429 | 0.718 | 0.703 | 0.703 |
| Augmented | Poisson | 0.483 | 0.486 | 0.479 | 0.780 | 0.784 | 0.783 |
| Augmented | Random forest | 0.460 | 0.458 | 0.458 | 0.710 | 0.708 | 0.708 |
| Augmented | Gradient boosting | 0.468 | 0.456 | 0.456 | 0.731 | 0.719 | 0.719 |

The augmented-minus-base gain in Spearman is 0.061 / 0.025 / 0.013 (Poisson / random forest / gradient boosting) with 2020 population, 0.063 / 0.036 / 0.016 with (a), and 0.061 / 0.036 / 0.016 with (b).

## Conclusion

Using 2010 instead of 2020 population changes Spearman by at most 0.022 in Part 1 and 0.015 in Part 2, and R² by about 0.01 or less, with one exception: random forest's LA-holdout level-4 R² goes from −0.48 to −0.34, which is still far below zero and inside its wide bootstrap interval (−1.06 to −0.10). All Spearman changes are small next to the level-4 bootstrap intervals (about 0.14–0.16 wide for the LA-holdout values) and go in both directions, so they look like noise rather than a systematic effect. The conclusions do not change: the same models lead, and Part 2's augmented inputs still beat the base inputs for all three models. We keep the 2020 population in the main results and treat the population year as a checked, minor limitation.
