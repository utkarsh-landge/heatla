# CalEnviroScreen −999 fix: corrected LA and statewide tables

Shared preprocessing fix for all three members. It rebuilds the CalEnviroScreen-derived columns from the original tract files and saves corrected tables next to the originals. No original dataset, no model result and no member's code is changed.

## What was wrong

CalEnviroScreen 4.0 stores −999 where a census tract has no value for an indicator. Both aggregation scripts (`fetch_features_ces_geo.py` for LA, `fetch_statewide.py` for California) averaged those markers into the ZIP-level population-weighted means. One affected tract could push a ZIP's value far below zero: ZIP 90024's CalEnviroScreen percentile was stored as −193.5.

## The rule now applied

Implemented in `src/heatla/ces.py` and used by `scripts/build_corrected_ces_tables.py`:

1. −999 (and blank) means missing, for that indicator in that tract.
2. A tract contributes to a ZIP's mean for an indicator only if it has a value for that indicator and a positive population. A missing value is left out of the numerator and its population is left out of the denominator.
3. If no tract in a ZIP has a value for an indicator, the ZIP's value stays empty. Nothing is filled in.

## Corrected files — use these

| Use | Original (unchanged) | Corrected |
|---|---|---|
| LA modeling table | `data/processed/model_table.csv` | `data/corrected/model_table_corrected.csv` |
| LA CalEnviroScreen + geography features | `data/processed/features_ces_geo.csv` | `data/corrected/features_ces_geo_corrected.csv` |
| Statewide modeling table | `data/processed/model_table_ca.csv` | `data/corrected/model_table_ca_corrected.csv` |
| Statewide CalEnviroScreen features by ZIP | `data/processed/features_ces_ca.csv` | `data/corrected/features_ces_ca_corrected.csv` |

The corrected files have the same rows, row order, columns and column order as the originals, so they are drop-in replacements: change the path and nothing else. Only CalEnviroScreen-derived cells differ; every other cell is copied as the identical text. `data/corrected/` is tracked in git, so both members get the same data by pulling this branch.

To rebuild from the tract files (no network needed, a few seconds):

```bash
.venv/bin/python scripts/build_corrected_ces_tables.py
```

The script stops without writing anything if it cannot first reproduce the existing processed feature files from the tract files using the old, uncorrected rule. It can: all 2,023 LA cells and all 14,905 statewide cells match.

## What changed

| | LA table | Statewide table |
|---|---|---|
| Tract file | `ces40_la_tracts.csv`, 2,343 tracts | `ces40_ca_tracts.csv`, 8,035 tracts |
| Tracts with −999 in at least one field used | 49 | 592 |
| ZIPs with any CalEnviroScreen feature changed | 29 of 289 | 443 of 1,355 with CalEnviroScreen data |
| ZIPs with a modeling-table column changed | 26 of 289 | 438 of 1,686 |
| ZIPs that had a negative value | 12 | 429 |
| ZIP-feature values changed | 49 | 831 |
| of which now empty (no valid tract) | 5 | 129 |
| Negative CalEnviroScreen cells, original modeling table | 8 | 2,728 (682 ZIP-features × 4 heat-level rows) |
| Percentiles outside 0–100, original modeling table | 8 | 152 (38 ZIPs × 4 rows) |
| Negative cells or percentiles outside 0–100, corrected | 0 | 0 |

**Which features moved.**

| Feature | LA ZIPs changed | Statewide ZIPs changed |
|---|---|---|
| PM2.5, ozone | 0 | 0 |
| Asthma ED rate, cardiovascular ED rate | 0 | 0 |
| CalEnviroScreen percentile | 26 | 73 |
| Poverty (CES) | 22 | 50 |
| Age 65+ (CES) | 1 | 1 |
| Education | not in LA file | 73 |
| Linguistic isolation | not in LA file | 256 |
| Unemployment | not in LA file | 268 |
| Housing burden | not in LA file | 110 |

PM2.5 and ozone have no −999 values. The asthma and cardiovascular fields do (9 LA tracts, 11 statewide), but every one of those tracts has zero population, so they never entered a weighted mean and no ZIP value changes.

**Affected ZIP codes.**

- LA, modeling-table column changed (26): 90024, 90027, 90058, 90242, 90272, 90650, 90670, 90731, 90744, 90802, 90813, 90815, 90840, 91011, 91042, 91330, 91342, 91384, 91390, 91406, 91711, 91768, 93510, 93536, 93550, 93563.
- LA, only a feature-file column changed (3): 90503, 91326, 91367.
- LA, percentile now empty (3): 90840, 91330, 93563. Each has a single tract whose percentile is −999.
- Statewide: 443 ZIPs, led by Los Angeles (92), Orange (33), San Diego (30), Riverside (29) and San Bernardino (23) counties. The full list, and every original and corrected value, are in the files below.

| File in `results/ces_sentinel_fix/` | Contents |
|---|---|
| `SUMMARY.md` | Generated summary: all checks, counts by field, every changed LA value, statewide ZIP list |
| `affected_zips_la.csv`, `affected_zips_ca.csv` | One row per affected ZIP: which features changed, whether it had a negative value, tract counts |
| `feature_changes_la.csv`, `feature_changes_ca.csv` | One row per changed ZIP-feature: original, corrected, difference, tracts in ZIP, tracts missing that field |
| `sentinel_counts_by_tract_field.csv` | −999 counts per tract field |
| `verification.json` | Every check below, plus SHA-256 of the original and corrected files |

## Verification

| Check | LA | Statewide |
|---|---|---|
| Old rule reproduces the existing feature file | 2,023 of 2,023 cells | 14,905 of 14,905 cells |
| No −999 left in corrected files | Pass | Pass |
| No negative CalEnviroScreen value left | Pass | Pass |
| All percentiles within 0–100 | Pass | Pass |
| Empty kept where a ZIP has no valid tract | Pass | Pass |
| Same rows and order as the original | Pass | Pass |
| Non-CalEnviroScreen columns identical to the original | Pass | Pass |
| Unaffected CalEnviroScreen cells identical to the original | Pass | Pass |
| Original files unchanged by the run (SHA-256 before and after) | Pass | Pass |

The statewide corrected table is also identical, value for value and with the same empty cells, to the corrected table Member 1's rerun already used (`results/member1/inputs/model_table_ca_ces40_fixed.csv` on branch `member1/statewide-models`).

## What each member needs to do

Nothing below has been done; these are the coordination points.

**Member 1 (statewide models).** No rerun needed. The "CES 4.0 corrected" results on `member1/statewide-models` were produced from a table identical to `data/corrected/model_table_ca_corrected.csv`. Optional tidy-up: point `build_member1_ces_tables.py` at `heatla.ces` so there is one implementation.

**Member 2 (LA models).**

- The four CalEnviroScreen inputs in the current LA model (PM2.5, ozone, asthma, cardiovascular) are **unchanged**, so existing LA model metrics are not affected by this fix.
- The LA-only CES baseline **is** affected: 26 ZIPs had a wrong percentile, 8 of them negative. Computed read-only on the 287 modelled ZIPs, the baseline Spearman moves from 0.524 (276 ZIPs) to 0.566 (273 ZIPs); top-10% recall from 0.14 to 0.15. Recompute it from the corrected table.
- For the planned "Model A base features" configuration in LA, the CalEnviroScreen poverty, age, education, linguistic isolation, unemployment and housing-burden values **are** affected. Take them from `data/corrected/features_ces_ca_corrected.csv` (all ten inputs, all California ZIPs) or `features_ces_geo_corrected.csv` (poverty and age only, LA tracts only).
- The two LA sources differ slightly by construction: the LA file aggregates only tracts whose county is Los Angeles, while the statewide file aggregates every tract assigned to a ZIP. Pick one source per feature and say which.

**Member 3 (website and siting).**

- `site/data/zips.geojson` shows `ces4_percentile` in each ZIP's popup; 26 LA ZIPs show a wrong value, including negatives.
- `src/heatla/siting.py` reports coverage by CalEnviroScreen quartile (`equity_ces_quartile`) from the same column, so those equity numbers are computed with 8 ZIPs ranked at the very bottom because of negative values, and 18 more with a distorted value. The size of the effect on the quartile figures has not been measured.
- Site selection itself does not use the percentile and is not affected.

**Shared scripts — not changed here.** `fetch_features_ces_geo.py` and `fetch_statewide.py` still contain the old averaging. If either is rerun it will rewrite the uncorrected files. The lasting fix is to make both call `heatla.ces.aggregate_tracts`, which changes the "original" datasets and every result built on them, so it should be agreed by the team first. Other files still built on uncorrected inputs: `results/metrics_ca.json`, `results/predictions_la_holdout.csv`, `results/tract_risk_la.csv`, `results/downscale_validation.json`, and the statewide numbers in `REPORT.md` and on the website.

## Limits of this fix

- **Source of the −999 convention.** OEHHA's 3.0 shapefile metadata sets missing values to −999, and in our 4.0 tract files −999 is the only negative value in any field used. OEHHA's 4.0 data-dictionary PDF, which covers zeros and missing values, has not been read to confirm the wording for 4.0.
- **Zeros are left alone.** A tract value of 0 is treated as a real zero. If OEHHA also uses 0 for "not available" in some fields, that is not handled.
- **Missing values still have to be handled at modeling time.** The corrected tables have more empty cells than the originals (5 more ZIP-features in LA, 129 statewide). The models median-impute these inside each training fold, as they already did for ZIPs with no CalEnviroScreen data.
- **Tract-to-ZIP assignment is unchanged.** Each tract still belongs to the single ZIP CalEnviroScreen lists for it.
