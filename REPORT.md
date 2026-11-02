# HEATLA — Technical Report

Predicting extreme-heat excess emergency-room (ER) visits across California ZIP codes, validating on Los Angeles County, downscaling to census tracts, and projecting a 2030 outlook. All numbers below are computed from real, documented sources (see `DATA_SOURCES.md`). No value is imputed, interpolated, or fabricated.

**Date:** 2026-11-02 · **Repo:** `/Users/utkarsh/heatla` (`master`)

---

## 1. Problem

During extreme-heat events, ER visits rise unevenly across neighborhoods. HEATLA estimates the *excess* ER-visit rate attributable to extreme heat per ZIP code, so that cooling-center placement can be prioritized by need. The original design (tract-level, self-built heat-vulnerability index) is archived under `legacy/`; the current design uses an external, published target and real feature data.

## 2. Target

- **Source:** UCLA Heat Maps (ArcGIS hosted FeatureServers on `services7.arcgis.com/2hYXmwteFLemN5bW`, public, no key).
- **Variable:** excess ER-visit rate per 10,000, CalHeatScore level 4 (CHS-4, extreme heat), years 2008–2018.
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

### 4b. Statewide spatial CV (6,700 rows, 10 groups, all CHS levels)

| Model | R² | Spearman ρ | Top-10 recall | Top-20 recall |
|---|---|---|---|---|
| Poisson | 0.517 | 0.866 | 0.53 | 0.81 |
| Random forest | 0.630 | 0.900 | 0.61 | 0.82 |
| Gradient boosting | 0.669 | 0.887 | 0.64 | 0.82 |

### 4c. LA hold-out (train on non-LA California, test on LA)

Train n = 5,552, test n = 1,148.

| Model | Scope | R² | Spearman ρ |
|---|---|---|---|
| Poisson | all CHS levels | 0.753 | 0.891 |
| Poisson | **CHS-4 only (n=287)** | **0.266** | **0.674** |
| Random forest | all CHS | 0.604 | 0.909 |
| Random forest | CHS-4 only | −0.550 | 0.680 |
| Gradient boosting | all CHS | 0.646 | 0.902 |
| Gradient boosting | CHS-4 only | −0.280 | 0.674 |
| Baseline: predict mean | all CHS | −0.061 | — |
| Baseline: CES 4.0 percentile | LA | — | 0.237 |

> **Honest headline.** The pooled all-CHS numbers (ρ ≈ 0.89) are **inflated** because `chs_level` carries most of the signal — predicting that CHS-4 ZIPs have higher rates than CHS-1 ZIPs is easy. The fair measure of out-of-region skill on the quantity we care about is the **CHS-4-only LA hold-out: Poisson ρ = 0.674**. Tree models give negative R² on this slice (they overfit the non-LA distribution), so Poisson is the model to report. Even so, 0.674 rank correlation still clearly beats the CES baseline (0.237).

### Reproducibility

Bit-exact results require `n_jobs=1` and single-thread BLAS (`OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1` set before importing numpy); joblib parallelism caused sub-ULP drift. Seed = 42.

## 5. ZIP → tract downscale

Each ZIP's excess-ER count is split across its census tracts in proportion to (model-predicted rate × tract population), then rescaled so the tract sum equals the real observed ZIP total. Validated by holding out ZIPs in 47 groups and comparing tract-level MAE:

| Split method | MAE |
|---|---|
| Model-weighted | **4.309** |
| Population-only | 5.181 |

Model split beats a naive population split by **16.8%**. Output: `results/tract_risk_la.csv`.

## 6. 2030 outlook (Cal-Adapt)

- **Source:** Cal-Adapt `exheat_year_ens32avg` (average extreme-heat days/yr, 32-model LOCA ensemble; 98th-percentile 1961–1990 April–October threshold), RCP 4.5 and RCP 8.5, sampled at each LA ZIP centroid. 287 ZIPs (91123, 91522 skipped — no centroid).
- **Method:** `heat_factor = mean exheat days 2026–2035 ÷ mean exheat days 2008–2018` (same series, no splice). `projected_rate_2030 = observed_CHS4_rate × heat_factor`.

| Scenario | Heat-factor median (range) | Mean rate 2008–18 → 2030 | Change |
|---|---|---|---|
| RCP 4.5 | 1.40 (1.20–1.75) | 10.04 → 14.19 | +41% |
| RCP 8.5 | 1.56 (1.29–1.95) | 10.04 → 15.73 | +57% |

Highest-projected ZIP in both scenarios is **91767** (Pomona area): 19.7 → 28.8 (RCP 4.5) / 31.9 (RCP 8.5). Output: `results/projection_2030.json`, `data/processed/heat_factor_2030.csv`.

> **Caveat.** This is a proportional-scaling outlook, not a re-fit epidemiological model. It assumes the heat-to-ER relationship holds constant and that only exposure frequency changes. It does not model adaptation, population change, or healthcare-capacity change.

## 7. Cooling centers

- **Source:** LA County Regional Cooling Centers (ArcGIS, July 2022), 153 sites.
- **Siting:** exact integer linear program (PuLP/CBC) to maximize risk-weighted coverage. Exact ILP ≥ greedy on every budget tested (gap ≤ 3.9 percentage points).

## 8. Limitations

- ZIP-level only; no daily or individual records.
- Small LA sample (~287 ZIPs); data years differ across sources (target 2008–18, CES ~2021, ACS 2022).
- Out-of-fold / out-of-region predictions, not an operational tool.
- ZIP 90095 (UCLA) flagged for possible mis-attributed ER patients.
- `asthma_ed_per10k` is partly an ER-utilization proxy.
- 2030 outlook is a proportional scaling, not a refit model.

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
