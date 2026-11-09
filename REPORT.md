# HEATLA — Technical Report

Predicting heat-related excess emergency-room (ER) visits across California ZIP codes, validating on Los Angeles County, downscaling to census tracts, and running a 2030 scaling scenario. The label is a 2008–2018 total that is cumulative across heat levels (see §2). All numbers below are computed from real, documented sources (see `DATA_SOURCES.md`). No value in the data files is invented or interpolated. Missing model inputs are left blank in the data files and are filled with the training-fold median when a model is fitted: 394 of the 1,675 statewide ZIPs have at least one input filled this way (337 of them have no CalEnviroScreen data at all), and 17 of the 287 modelled LA ZIPs (21 once the four ACS features are added).

**Date:** 2026-11-09 · **Branch:** `integration/midterm`

---

## 1. Problem

During hot weather, ER visits rise unevenly across neighborhoods. HEATLA estimates the *heat-related excess* ER-visit rate per ZIP code (a 2008–2018 total, cumulative across heat levels; see §2), so that cooling-center placement can be prioritized by need. The original design (tract-level, self-built heat-vulnerability index) is archived under `legacy/`; the current design uses an external, published target and real feature data.

## 2. Target

- **Source:** UCLA Heat Maps (ArcGIS hosted FeatureServers on `services7.arcgis.com/2hYXmwteFLemN5bW`, public, no key).
- **Variable:** UCLA's estimated excess heat-related ER visits per 10,000 residents, from the CalHeatScore level 4 layer (`zip_ER`, `categry = 4`), 2008–2018.
- **What the number is:** a total over the eleven May–October seasons of 2008–2018, not a daily or yearly rate. It accumulates every heat day up to and including level 4, not only level-4 days. It is a model-based estimate (observed visits minus the visits a spatial Bayesian model expects at typical temperatures), not a raw count. Details and sources: `reports/member3_labels_website_siting.md`, section 1.
- **Coverage (LA):** 289 ZIPs; UCLA label 2.5–19.7 per 10k. 287 ZIPs map cleanly to geometry.
- **Note:** ZIP 90095 (UCLA campus, residential pop ≈ 1) is flagged for possible mis-attributed patients.

The statewide extraction pulls all California ZIPs across all four CHS levels (`chs_level` becomes a feature): 6,744 raw ZIP × CHS rows (1,686 ZIPs), and 6,700 rows (1,675 ZIPs) after cleaning.

## 3. Features

| Configuration | Inputs | Used in |
|---|---|---|
| Statewide (Model A) | 12: heat level, 10 CalEnviroScreen 4.0 fields, population density | Spatial cross-validation and LA hold-out |
| LA base | 11: the statewide inputs without heat level, which is constant at level 4 | LA-only comparison |
| LA augmented | 15: LA base plus % renters, % no-vehicle, % uninsured, % construction (ACS 2014–2018) | LA-only comparison |

CalEnviroScreen values use the −999 correction and are aggregated from tract to ZIP by population weight. Total population is not a model input. UCLA's population (2020 Census) is used for density and as the Poisson weight. Full definitions and reference periods: `part2/FEATURE_COMPARISON_TABLE.md` and `reports/member1_statewide.md`, section 3.

> **Caveat:** the asthma and cardiovascular inputs are ER-visit rates from the same state records as the label, so they are partly ER-utilization proxies. `reports/member1_statewide.md`, section 11, reports results without them.

## 4. Models

Three model families throughout: Poisson GLM, random forest, gradient boosting. Spatial cross-validation uses leave-one-geographic-group-out (k-means on lat/lon) so that no ZIP is scored by a model trained on its immediate neighbors.

### 4a. LA-only (spatial cross-validation, 287 ZIPs, CHS-4 label)

Five geographic folds within LA County; every ZIP is predicted once by a model trained on the other four folds. Corrected CalEnviroScreen inputs.

| Model | Inputs | R² | Spearman ρ | Top-10 recall | Top-20 recall |
|---|---|---|---|---|---|
| Poisson | LA base (11) | 0.403 | 0.718 | 0.34 | 0.58 |
| Poisson | **LA augmented (15)** | **0.483** | **0.780** | **0.34** | **0.60** |
| Random forest | LA base (11) | 0.421 | 0.685 | 0.17 | 0.46 |
| Random forest | LA augmented (15) | 0.460 | 0.710 | 0.21 | 0.46 |
| Gradient boosting | LA base (11) | 0.425 | 0.718 | 0.31 | 0.51 |
| Gradient boosting | LA augmented (15) | 0.468 | 0.731 | 0.28 | 0.44 |
| Baseline: predict the training-fold mean | — | −0.111 | — | — | — |

On the same 273 ZIPs with a corrected CalEnviroScreen percentile, the percentile has ρ = 0.566 and top-10 recall 0.15; Poisson augmented has ρ = 0.811 and top-10 recall 0.33.

The four added ACS features improve R² and Spearman for all three models, most clearly for Poisson. Top-10 recall does not improve consistently. Details: `part2/PART2_MODEL_COMPARISON_REPORT.md`.

Follow-up (`part2/FOLLOWUP_EXPERIMENTS.md`, same ZIPs, folds and models): on the excess for level-4 days alone, the ACS features no longer improve ranking (Poisson ρ 0.637 → 0.648), though augmented Poisson still beats the CalEnviroScreen percentile on matched ZIPs (0.674 against 0.498). Without the asthma and cardiovascular inputs, the ACS features help more on the published label (Poisson ρ 0.553 → 0.691), but on level-4 days alone no model clearly beats the percentile (augmented Poisson 0.432 against 0.498).

### 4b. Statewide spatial CV (1,675 ZIPs × 4 heat levels = 6,700 rows, 10 geographic folds)

Corrected CalEnviroScreen inputs (the −999 missing-value marker is treated as missing; see `reports/member1_statewide.md`, section 1). Every ZIP is predicted by a model that did not see its fold.

| Model | Scope | R² | Spearman ρ | Top-10 recall | Top-20 recall |
|---|---|---|---|---|---|
| Poisson | all CHS levels pooled | 0.525 | 0.871 | 0.56 | 0.81 |
| Random forest | all CHS levels pooled | 0.629 | 0.900 | 0.61 | 0.81 |
| Gradient boosting | all CHS levels pooled | 0.665 | 0.888 | 0.64 | 0.81 |
| Poisson | CHS-4 label (level-4 rows, n=1,675) | −0.015 | 0.512 | 0.16 | 0.35 |
| Random forest | CHS-4 label only | 0.199 | 0.567 | 0.32 | 0.43 |
| Gradient boosting | CHS-4 label only | 0.284 | 0.585 | 0.33 | 0.41 |

The pooled scores mostly measure the gap between heat levels. Within one level, no model reaches ρ = 0.6.

### 4c. LA hold-out (train on non-LA California, test on LA)

Train: 1,388 ZIPs, 5,552 rows. Test: 287 LA ZIPs, 1,148 rows. Corrected CalEnviroScreen inputs.

| Model | Scope | R² | Spearman ρ | Top-10 recall |
|---|---|---|---|---|
| Poisson | all CHS levels pooled | 0.781 | 0.905 | 0.75 |
| Poisson | **CHS-4 label (n=287)** | **0.349** | **0.730** | **0.34** |
| Poisson | **CHS-4 days only (n=287)** | **0.089** | **0.681** | **0.34** |
| Random forest | all CHS levels pooled | 0.619 | 0.911 | 0.66 |
| Random forest | CHS-4 label | −0.483 | 0.688 | 0.14 |
| Random forest | CHS-4 days only | −2.748 | 0.650 | 0.28 |
| Gradient boosting | all CHS levels pooled | 0.642 | 0.898 | 0.70 |
| Gradient boosting | CHS-4 label | −0.291 | 0.683 | 0.24 |
| Gradient boosting | CHS-4 days only | −2.143 | 0.646 | 0.38 |
| Baseline: predict the training mean | all CHS levels pooled | −0.061 | — | — |

"CHS-4 label" is UCLA's published level-4 value, which totals every heat level. "CHS-4 days only" is the excess on level-4 days alone (level 4 minus level 3), from a model trained on that target; it is the quantity that corresponds to extreme heat.

CalEnviroScreen 4.0 percentile as a baseline, on the same LA ZIPs and the same heat level (273 ZIPs with a percentile; rank metrics only, since the percentile is an index and not a rate):

| Target | CES percentile ρ | Poisson ρ | CES top-10 | Poisson top-10 |
|---|---|---|---|---|
| CHS-4 label | 0.566 | 0.757 | 0.15 | 0.30 |
| CHS-4 days only | 0.498 | 0.707 | 0.15 | 0.37 |

> **Headline.** The pooled all-CHS numbers (ρ ≈ 0.9) mostly reflect the gap between heat levels: `chs_level` carries most of the signal. Within level 4, a model trained on the rest of California ranks LA ZIPs with **ρ = 0.73 for the published level-4 label and ρ = 0.68 for extreme-heat days alone**. The amount of excess transfers poorly for extreme-heat days (Poisson R² = 0.09; tree models are strongly negative), because extreme-day excess averages 7.75 per 10,000 in the rest of California against 3.11 in LA. On matched ZIPs the Poisson model beats the CalEnviroScreen percentile on both targets.
>
> **Caveat on the inputs.** Two inputs, the asthma and cardiovascular ER-visit rates, come from the same state ER records as the label. Without them, LA level-4 rank correlation falls from 0.73 to 0.63 for the published label and from 0.68 to 0.50 for extreme-heat days, where the model is then about level with the CalEnviroScreen percentile (0.535 against 0.498).
>
> An earlier version of this section reported ρ = 0.674 against a CalEnviroScreen baseline of 0.237. Both were computed on inputs affected by the −999 error, and the baseline was computed across all four heat levels, so the two were not comparable. Details, per-level results, the level-specific comparison and a CalEnviroScreen 3.0 sensitivity check are in `reports/member1_statewide.md`.

### Reproducibility

Bit-exact results require `n_jobs=1` and single-thread BLAS (`OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1` set before importing numpy); joblib parallelism caused sub-ULP drift. Seed = 42.

## 5. ZIP → tract downscale

Each ZIP's excess-ER count is split across its census tracts in proportion to (model-predicted rate × tract population), then rescaled so the tract sum equals the ZIP's UCLA value. The weights come from a Poisson model trained on the corrected statewide table (`data/corrected/model_table_ca_corrected.csv`, −999 treated as missing) with Los Angeles County left out, so the LA weights come from a model that never saw LA. At tract level −999 is also treated as missing; 82 tracts have at least one input missing, and the model fills it with the training median as it does for ZIPs.

**Tracts.** The output uses real 2020 census tracts (11-digit GEOID). CalEnviroScreen 4.0 is published on 2010 tracts, so each CES tract's population (`TotPop19`) is moved to 2020 tracts by land-area share using the Census 2010→2020 tract relationship file, and each 2020 tract takes the population-weighted mean of its 2010 pieces' inputs. Tracts are then matched to ZIPs with the Census 2020 ZCTA–tract relationship file. A tract that crosses a ZIP boundary is cut into pieces by land area, and each piece belongs to one ZIP. Both steps assume people are spread evenly over the land in a tract. We chose 2020 tracts over the 2010 CES tracts because 2020 tracts match current maps and Census data, and because the relationship file lets one tract contribute to several ZIPs instead of being assigned to a single ZIP. The ZIP's population density is still used for every tract in it, since the model was trained on ZIP density.

The result covers all 287 LA ZIPs: 3,737 tract–ZIP pieces from 2,493 tracts (2,482 in LA County, 11 in neighboring counties that LA ZIPs reach into); 988 tracts are split across two or more ZIPs. The pieces of every ZIP add back to its UCLA value (largest difference 3 × 10⁻¹⁴). Outputs: `results/tract_risk_la.csv` (one row per tract–ZIP piece) and `results/tract_risk_la_by_tract.csv` (pieces summed to one row per tract, for mapping).

There is no tract-level health data, so the tract estimates cannot be validated directly. The splitting rule is checked one level up with a pseudo-ZIP recovery test: the 287 LA ZIPs are merged into 47 spatial groups, each group's known total is split back to its member ZIPs by the same rule, and the result is compared with the real ZIP values (ZIP-level MAE in excess visits, and Spearman rank correlation):

| Split method | MAE | Spearman |
|---|---|---|
| Model-weighted | **3.985** | **0.975** |
| Population-only | 5.181 | 0.960 |

On this test the model-weighted split has 23.1% lower error than a population-only split. This supports the weighting rule; it does not measure the accuracy of the tract estimates. The earlier run on uncorrected inputs gave 4.309 for the model-weighted split; the population-only split does not use model inputs and is unchanged.

## 6. 2030 scaling scenario (Cal-Adapt)

This section is a what-if calculation. It is not a prediction from the models in section 4 and is not part of their evaluation.

- **Source:** Cal-Adapt `exheat_year_ens32avg` (average extreme-heat days/yr, 32-model LOCA ensemble; 98th-percentile 1961–1990 April–October threshold), RCP 4.5 and RCP 8.5, sampled at each LA ZIP centroid. 287 ZIPs (91123, 91522 skipped — no centroid).
- **Method:** `heat_factor = mean exheat days 2026–2035 ÷ mean exheat days 2008–2018` (same series, no splice). `scenario_rate_2030 = UCLA_label × heat_factor`.

| Scenario | Heat-factor median (range) | Mean rate 2008–18 → 2030 | Change |
|---|---|---|---|
| RCP 4.5 | 1.40 (1.20–1.75) | 10.04 → 14.19 | +41% |
| RCP 8.5 | 1.56 (1.29–1.95) | 10.04 → 15.73 | +57% |

Highest-projected ZIP in both scenarios is **91767** (Pomona area): 19.7 → 28.8 (RCP 4.5) / 31.9 (RCP 8.5). Output: `results/projection_2030.json` and `data/processed/heat_factor_2030.csv` (written by `scripts/run_projection_2030.py`; not committed).

> **Formula and assumptions.** `scenario_rate_2030 = UCLA_label × (mean extreme-heat days 2026–2035 ÷ mean extreme-heat days 2008–2018)`. This is proportional scaling, not a re-fit epidemiological model. It assumes ER visits per heat day stay constant and that only the number of extreme-heat days changes; it does not model adaptation, population change, or healthcare-capacity change. Cal-Adapt's extreme-heat day (above the local 98th-percentile temperature) is a different heat definition from the CalHeatScore levels behind the label, and the label covers all heat levels, so applying this ratio to the whole label is an additional assumption.

## 7. Cooling centers

- **Source:** LA County Regional Cooling Centers (ArcGIS, July 2022), 153 sites.
- **Siting:** exact integer linear program (PuLP/CBC) to maximize risk-weighted coverage. Exact ILP ≥ greedy on every budget tested (gap ≤ 3.9 percentage points).
- **What is chosen:** the candidate sites are the 153 existing centers, so the program selects which existing centers to prioritize; it does not propose new locations. A ZIP counts as covered when its centroid is within the chosen straight-line radius of a selected center. The full formulation is in `reports/member3_labels_website_siting.md`, section 4.
- **Weights:** the risk weights are the earlier LA out-of-fold Poisson predictions (`results/predictions_oof.csv`, the 13-input model on inputs before the −999 correction). Siting has not been rerun with the models in section 4.

## 8. Limitations

- ZIP-level only; no daily or individual records.
- Small LA sample (287 ZIPs). Data years differ across sources: label 2008–18, CalEnviroScreen 4.0 about 2013–2019, the four added ACS features 2014–2018, UCLA population 2020. The effect of the population year has not been tested.
- Out-of-fold / out-of-region predictions, not an operational tool.
- ZIP 90095 (UCLA) flagged for possible mis-attributed ER patients.
- The asthma and cardiovascular inputs (`asthma_ed_per10k`, `cardiovascular_ed_per10k`) come from the same state ER records as the label and are partly ER-utilization proxies; see the caveat in §4c.
- 2030 scenario is a proportional scaling, not a refit model, and is not a model evaluation result.
- The target is UCLA's model-based estimate, totalled over 2008–2018 and cumulative across heat levels; it is not a direct count of ER visits on extreme-heat days.
- The ZIP → tract downscale has no tract-level ground truth and is checked only by a pseudo-ZIP recovery test. Moving CES values to 2020 tracts and to ZIPs assumes people are spread evenly over each tract's land.

## 9. Reproduce

Run from the repository root with Python 3.12. Pinned versions: numpy 2.1.3, pandas 2.2.3, scipy 1.14.1, scikit-learn 1.5.2, pulp 2.9.0, matplotlib 3.9.2. Random forest and gradient boosting results can differ in the third decimal across operating systems; Poisson reproduces to 1e-11. Part 2 was run on Windows.

**Reported results (§4):**

```
# §4a  LA-only comparison (see part2/README.md)
part2/run_feature_comparison.py

# §4b, §4c  statewide spatial CV and LA hold-out
scripts/build_member1_ces_tables.py
scripts/build_member1_level_only_table.py
scripts/run_member1_statewide.py        # plus the --tag/--table/--out/--drop runs in reports/member1_statewide.md §15
scripts/compare_member1_variants.py
scripts/build_member1_tables.py

# −999 correction tables
scripts/build_corrected_ces_tables.py

# label EDA and siting check (reports/member3_labels_website_siting.md)
scripts/member3_label_eda.py
scripts/member3_check_siting.py
```

The four added ACS features come from `part2/fetch_acs2018.py` (ACS 2018 5-year, 2014–2018; needs `CENSUS_API_KEY`), not from the ACS 2022 pull.

**Original pipeline (used for §5–§7 and the website):**

```
fetch_target.py              # UCLA Heat Maps CHS-4 excess-ER, LA
fetch_features_ces_geo.py    # CES 4.0 + Gazetteer geometry
fetch_features_acs.py        # Census ACS 2022 (needs CENSUS_API_KEY); original source, superseded for the four added features
fetch_statewide.py           # all-CA ZIP x 4 CHS levels + CES
fetch_climate_caladapt.py    # Cal-Adapt exheat days per ZIP centroid
run_models.py                # LA-only OOF models (original 13-input model)
run_models_ca.py             # statewide spatial CV + LA hold-out (original inputs)
run_downscale.py             # ZIP -> 2020 census tract (corrected inputs)
run_projection_2030.py       # 2030 scaling scenario
run_siting.py                # cooling-center ILP (CBC)
build_site_data.py           # site/data/*.json for the website (needs network for ZIP polygons)
```

`scripts/build_site_results.py` then replaces the website's model numbers and predictions with the corrected Part 1 and Part 2 results; `build_site_data.py` calls it at the end, and it can also be run on its own (no network).
