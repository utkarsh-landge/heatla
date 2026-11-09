# HEATLA — Technical Report

Predicting extreme-heat excess emergency-room (ER) visits across California ZIP codes, validating on Los Angeles County, downscaling to census tracts, and projecting a 2030 outlook. All numbers below are computed from real, documented sources (see `DATA_SOURCES.md`). No value in the data files is invented or interpolated. Missing model inputs are left blank in the data files and are filled with the training-fold median when a model is fitted: 18 of the 287 modelled LA ZIPs, and 337 of the 1,675 statewide ZIPs, have at least one input filled this way.

**Date:** 2026-11-02 · **Repo:** `/Users/utkarsh/heatla` (`master`)

---

## 1. Problem

During extreme-heat events, ER visits rise unevenly across neighborhoods. HEATLA estimates the *excess* ER-visit rate attributable to extreme heat per ZIP code, so that cooling-center placement can be prioritized by need. The original design (tract-level, self-built heat-vulnerability index) is archived under `legacy/`; the current design uses an external, published target and real feature data.

## 2. Target

- **Source:** UCLA Heat Maps (ArcGIS hosted FeatureServers on `services7.arcgis.com/2hYXmwteFLemN5bW`, public, no key).
- **Variable:** UCLA's estimated excess heat-related ER visits per 10,000 residents, from the CalHeatScore level 4 layer (`zip_ER`, `categry = 4`), 2008–2018.
- **What the number is:** a total over the eleven May–October seasons of 2008–2018, not a daily or yearly rate. It accumulates every heat day up to and including level 4, not only level-4 days. It is a model-based estimate (observed visits minus the visits a spatial Bayesian model expects at typical temperatures), not a raw count. Details and sources: `reports/member3_labels_website_siting.md`, section 1.
- **Coverage (LA):** 289 ZIPs; observed rate 2.5–19.7 per 10k. 287 ZIPs map cleanly to geometry.
- **Note:** ZIP 90095 (UCLA campus, residential pop ≈ 1) is flagged for possible mis-attributed patients.

The statewide extraction pulls all California ZIPs across all four CHS levels (`chs_level` becomes a feature), giving 6,700 ZIP × CHS rows.

## 3. Features (17)

- **CalEnviroScreen 4.0** (UCLA ArcGIS, tract → ZIP population-weighted): pm25, ozone, asthma ED rate, cardiovascular ED rate, CES 4.0 percentile.
- **Census Gazetteer 2023 ZCTA:** lat, lon, land area.
- **Census ACS 2022 5-year** (free API key, read from `CENSUS_API_KEY` env, never stored): income, % poverty, % 65+, % renters, % no-vehicle, % uninsured, % construction, total pop, density.

Final LA model table: `data/processed/model_table.csv`, 289 rows, 269 complete-case. The 20 incomplete rows are institutional or very small ZIPs. Statewide table: `data/processed/model_table_ca.csv`.

> **Caveat:** `asthma_ed_per10k` dominates random-forest importance and is partly an ER-utilization proxy, not a pure exposure signal. Treat its contribution with care.

## 4. Models

Three model families throughout: Poisson GLM, random forest, gradient boosting. Spatial cross-validation uses leave-one-geographic-group-out (k-means on lat/lon) so that no ZIP is scored by a model trained on its immediate neighbors.

### 4a. LA-only (out-of-fold, 287 ZIPs, CHS-4)

| Model | R² | Spearman ρ | Top-10 recall |
|---|---|---|---|
| Poisson | 0.445 | 0.785 | 0.34 |
| Random forest | 0.449 | 0.703 | 0.21 |
| Gradient boosting | 0.438 | 0.713 | — |
| CES 4.0 percentile (baseline) | — | 0.524 | — |

The models beat the existing CES index on rank correlation but explain under half the variance. Small sample and mismatched data years limit this.

### 4b. Statewide spatial CV (1,675 ZIPs × 4 heat levels = 6,700 rows, 10 geographic folds)

Corrected CalEnviroScreen inputs (the −999 missing-value marker is treated as missing; see `reports/member1_statewide.md`, section 1). Every ZIP is predicted by a model that did not see its fold.

| Model | Scope | R² | Spearman ρ | Top-10 recall | Top-20 recall |
|---|---|---|---|---|---|
| Poisson | all CHS levels pooled | 0.525 | 0.871 | 0.56 | 0.81 |
| Random forest | all CHS levels pooled | 0.629 | 0.900 | 0.61 | 0.81 |
| Gradient boosting | all CHS levels pooled | 0.665 | 0.888 | 0.64 | 0.81 |
| Poisson | CHS-4 label only (n=1,675) | −0.015 | 0.512 | 0.16 | 0.35 |
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

Each ZIP's excess-ER count is split across its census tracts in proportion to (model-predicted rate × tract population), then rescaled so the tract sum equals the ZIP's UCLA value. There is no tract-level health data, so the tract estimates cannot be validated directly. The splitting rule is checked one level up with a pseudo-ZIP recovery test: the 287 LA ZIPs are merged into 47 spatial groups, each group's known total is split back to its member ZIPs by the same rule, and the result is compared with the real ZIP values (ZIP-level MAE, in excess visits):

| Split method | MAE |
|---|---|
| Model-weighted | **4.309** |
| Population-only | 5.181 |

On this test the model-weighted split has 16.8% lower error than a population-only split. This supports the weighting rule; it does not measure the accuracy of the tract estimates. Tract identifiers in the output are sequence numbers within each ZIP (`90001-1`, `90001-2`, …), not census tract IDs. Output: `results/tract_risk_la.csv`.

## 6. 2030 scaling scenario (Cal-Adapt)

This section is a what-if calculation. It is not a prediction from the models in section 4 and is not part of their evaluation.

- **Source:** Cal-Adapt `exheat_year_ens32avg` (average extreme-heat days/yr, 32-model LOCA ensemble; 98th-percentile 1961–1990 April–October threshold), RCP 4.5 and RCP 8.5, sampled at each LA ZIP centroid. 287 ZIPs (91123, 91522 skipped — no centroid).
- **Method:** `heat_factor = mean exheat days 2026–2035 ÷ mean exheat days 2008–2018` (same series, no splice). `projected_rate_2030 = observed_CHS4_rate × heat_factor`.

| Scenario | Heat-factor median (range) | Mean rate 2008–18 → 2030 | Change |
|---|---|---|---|
| RCP 4.5 | 1.40 (1.20–1.75) | 10.04 → 14.19 | +41% |
| RCP 8.5 | 1.56 (1.29–1.95) | 10.04 → 15.73 | +57% |

Highest-projected ZIP in both scenarios is **91767** (Pomona area): 19.7 → 28.8 (RCP 4.5) / 31.9 (RCP 8.5). Output: `results/projection_2030.json`, `data/processed/heat_factor_2030.csv`.

> **Formula and assumptions.** `scenario_rate_2030 = UCLA_label × (mean extreme-heat days 2026–2035 ÷ mean extreme-heat days 2008–2018)`. This is proportional scaling, not a re-fit epidemiological model. It assumes ER visits per heat day stay constant and that only the number of extreme-heat days changes; it does not model adaptation, population change, or healthcare-capacity change. Cal-Adapt's extreme-heat day (above the local 98th-percentile temperature) is a different heat definition from the CalHeatScore levels behind the label, and the label covers all heat levels, so applying this ratio to the whole label is an additional assumption.

## 7. Cooling centers

- **Source:** LA County Regional Cooling Centers (ArcGIS, July 2022), 153 sites.
- **Siting:** exact integer linear program (PuLP/CBC) to maximize risk-weighted coverage. Exact ILP ≥ greedy on every budget tested (gap ≤ 3.9 percentage points).
- **What is chosen:** the candidate sites are the 153 existing centers, so the program selects which existing centers to prioritize; it does not propose new locations. A ZIP counts as covered when its centroid is within the chosen straight-line radius of a selected center. The full formulation is in `reports/member3_labels_website_siting.md`, section 4.

## 8. Limitations

- ZIP-level only; no daily or individual records.
- Small LA sample (~287 ZIPs); data years differ across sources (target 2008–18, CES ~2021, ACS 2022).
- Out-of-fold / out-of-region predictions, not an operational tool.
- ZIP 90095 (UCLA) flagged for possible mis-attributed ER patients.
- `asthma_ed_per10k` is partly an ER-utilization proxy.
- 2030 scenario is a proportional scaling, not a refit model, and is not a model evaluation result.
- The target is UCLA's model-based estimate, totalled over 2008–2018 and cumulative across heat levels; it is not a direct count of ER visits on extreme-heat days.
- The ZIP → tract downscale has no tract-level ground truth and is checked only by a pseudo-ZIP recovery test.

## 9. Reproduce

Scripts in `scripts/`, run with `.venv/bin/python` (3.12: numpy, pandas, sklearn, scipy, pulp; no lightgbm). ACS scripts need `CENSUS_API_KEY` in the environment.

```
fetch_target.py              # UCLA Heat Maps CHS-4 excess-ER, LA
fetch_features_ces_geo.py    # CES 4.0 + Gazetteer geometry
fetch_features_acs.py        # Census ACS 2022 (needs CENSUS_API_KEY)
fetch_statewide.py           # all-CA ZIP x 4 CHS levels + CES
fetch_climate_caladapt.py    # Cal-Adapt exheat days per ZIP centroid
run_models.py                # LA-only OOF models
run_models_ca.py             # statewide spatial CV + LA hold-out
run_downscale.py             # ZIP -> tract
run_projection_2030.py       # 2030 outlook
run_siting.py                # cooling-center ILP (CBC)
build_site_data.py           # site/data/*.json for the website
```
