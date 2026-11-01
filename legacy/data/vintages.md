# Dataset vintages

Every source in this project was published for a different year, on a
different spatial unit, by a different agency. Combining them is unavoidable —
nobody publishes a single consistent snapshot of heat, trees, pavement,
demographics and health for LA County — but the mismatches should be stated
rather than hidden in a join.

## The table

| Source | Vintage / period | Spatial unit | Used for | Why it is acceptable to combine |
|---|---|---|---|---|
| TIGER/Line census tracts | 2023 release, 2020 boundaries | 2020 tract polygon | geometry, join key, centroids, candidate sites | Boundaries are fixed for the decade, so the 2023 release is the 2020 geography. This is the spine everything else is pulled onto. |
| ACS 5-year profiles (DP03, DP05) | 2019–2023 (or 2020–2024 when released) | 2020 tract | population, age, race/ethnicity, poverty, income | A 5-year ACS estimate is an average over its window, not a point measurement. Tract demographics move slowly; the 5-year window is the price of having tract-level estimates at all. |
| CDC/ATSDR SVI | 2022 (built on ACS 2018–2022) | 2020 tract | comparison index, and the demographic fallback when no Census API key is set | Overlaps the ACS window. Using SVI as a demographic fallback means those columns are two years older than the ACS path; `provenance.json` records which path was used. |
| CalEnviroScreen 4.0 | 2021 (indicators from ~2015–2019) | **2010 tract** | pollution, health, socioeconomic indicators | The oldest input, and on the wrong boundaries. Crosswalked 2010→2020 with the Census relationship file, area-weighted. Where a 2020 tract is built from several 2010 tracts, its CES value is a weighted average — a reasonable approximation for percentile-scaled indicators, and wrong for anything requiring an exact count. CalEnviroScreen 5.0 (2026, 2020 tracts) is downloaded alongside and avoids the crosswalk entirely; the project keeps 4.0 as primary because that is what the proposal specified, and 5.0 is a one-line switch. |
| Landsat 8/9 C2 L2, band ST_B10 | June–September, 2021–2025, per-pixel maximum | 30 m raster → tract mean | exposure term of the HVI; Part A heat gap | A multi-year summer maximum is deliberately not a single-year value: one anomalous summer should not decide which tracts count as hot. The 2021–2025 window overlaps the ACS and SVI windows. |
| ECOSTRESS L2T_LSTE (optional) | June–September, 2021–2025 | ~70 m raster → tract mean | alternative exposure term | Same window, finer resolution, and includes night-time passes. Off by default pending advisor sign-off. |
| NLCD impervious surface | 2021 | 30 m raster → tract mean | Part A pavement gap; Part B control | Built environment changes slowly at tract scale; a 2021 layer is a fair description of 2021–2025 conditions. |
| USFS / NLCD tree canopy | 2021 | 30 m raster → tract mean | adaptive-capacity term of the HVI | Same reasoning. Mature canopy changes over decades. |
| LA County tree canopy by tract | 2016 imagery, published per 2020 tract | 2020 tract | canopy, when the Earth Engine export has not been run | Older than the NLCD layer. Prefer the Earth Engine export when available; this is the no-credentials fallback. |
| LA County Regional Cooling Centers | official layer, updated July 2022; 153 sites | point | Part A status quo; Part C starting coverage | Cooling centres are seasonal and the list is re-published each summer. The analysis is therefore about *a* plausible current network, not a guaranteed-live one. The seasonal "augmented" layer is empty out of season, which is why the regional layer is primary. |
| CDPH / CalBRACE heat-related ER visits | most recent published year | **ZIP code (ZCTA)** | HVI validation; alternative outcome in Part B | The only health outcome available, and the only input on a non-tract unit. See below. |

## The two mismatches that actually matter

**1. CalEnviroScreen is on 2010 tracts.** LA County's tracts were redrawn for
2020: some split, some merged, a few changed shape. A string match between a
2010 ID and a 2020 ID is wrong in exactly the places where population changed
most, which is to say the places this project cares about. The pipeline uses
the Census 2020↔2010 relationship file and area-weights the overlap. Where a
2020 tract draws from several 2010 tracts, its CES value is a weighted mean.

**2. ER visits are on ZIP codes, not tracts.** ZIP codes are mail-delivery
routes; they do not nest inside tracts or counties and were never designed as
statistical units. The pipeline pushes ZIP rates down to tracts weighted by
the population each tract contributes to the ZCTA. Two consequences that are
repeated wherever these numbers appear:

- every tract inside one ZIP receives the same rate, so within-ZIP variation
  is invented out of nothing, and
- the HVI-vs-ER correlation is therefore attenuated and partly mechanical. It
  is reported as corroboration, not as a test of the index.

## Temporal ordering

The chain runs: CalEnviroScreen indicators (~2015–2019) → ACS/SVI demographics
(2018–2023) → rasters (2021) → surface temperature (2021–2025) → cooling
centres (2022–2023). Roughly a decade end to end. For a cross-sectional
question — *which places are vulnerable, and where should the next centres
go* — that is tolerable, because the quantities involved (tract income,
canopy, pavement, who lives where) are slow-moving. It would not be tolerable
for anything claiming to measure change over time, and this project makes no
such claim.
