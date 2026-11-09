# Unified feature comparison — Part 2

This document compares predictor definitions, sources and inclusion. It is not a new experiment and does not change the completed model outputs. The old LA model is a historical reference, not the control group in the new paired experiment.

Model A has 12 inputs in its all-level statewide form. At fixed category 4, its constant heat-level field is removed, leaving **11 base predictors**. The original LA model has **13 predictors**. The new augmented model has **15 predictors**, comprising the exact 11 base predictors plus four ACS 2018 indicators. Each current configuration retains the same 287 ZIPs.

## Table 1. Predictor inclusion across configurations

| Feature | Field | Base (11) | Original LA (13) | Augmented (15) |
|---|---|---|---|---|
| PM2.5 | pm25 | Yes | Yes | Yes |
| Ozone | ozone | Yes | Yes | Yes |
| Asthma ED rate | asthma_ed_per10k | Yes | Yes | Yes |
| Heart-attack ED rate | cardiovascular_ed_per10k | Yes | Yes | Yes |
| CES poverty | poverty_pct | Yes | — | Yes |
| CES age 65+ | elderly65_pct | Yes | — | Yes |
| Low educational attainment | edu_lt_hs_pct | Yes | — | Yes |
| Linguistic isolation | ling_isol_pct | Yes | — | Yes |
| Unemployment | unemployment_pct | Yes | — | Yes |
| Housing burden | housing_burden_pct | Yes | — | Yes |
| Population density | pop_density_per_sqmi | Yes | Yes | Yes |
| Median household income | median_hh_income | — | Yes | — |
| Original ACS poverty | pct_poverty | — | Yes | — |
| Original ACS age 65+ | pct_age_65plus | — | Yes | — |
| Renter households | pct_renters | — | Yes | Yes |
| No-vehicle households | pct_no_vehicle | — | Yes | Yes |
| Uninsured population | pct_uninsured | — | Yes | Yes |
| Construction-industry employment | pct_construction | — | Yes | Yes |
| ACS total population | total_pop | — | Yes | — |

## Table 2. Definitions, units and raw variables

Percentages are on the 0–100 scale. CES percentages are source indicator values aggregated using population weights; they are not reconstructed from raw ZIP numerator/denominator counts by this project. ACS housing indicators refer to occupied housing units, not all individual residents.

| Field | Definition / universe | Unit | Raw field / formula |
|---|---|---|---|
| pm25 | Mean fine particulate concentration | µg/m³ | PM2_5 |
| ozone | Mean daily maximum 8-hour ozone concentration | ppm | Ozone |
| asthma_ed_per10k | Age-adjusted asthma emergency-department visit rate | visits / 10,000 | Asthma |
| cardiovascular_ed_per10k | Age-adjusted heart-attack emergency-department visit rate; field name is broader than the measured outcome | visits / 10,000 | Cardiovas |
| poverty_pct | Population below twice the federal poverty threshold | % | Poverty |
| elderly65_pct | Population age 65 or older | % | Elderly65 |
| edu_lt_hs_pct | Population age 25+ without a high-school diploma | % | Educatn |
| ling_isol_pct | Households with limited English proficiency, as defined by the CES indicator | % households | Ling_Isol |
| unemployment_pct | Unemployed population age 16+ eligible for/in the labor force, per CES definition | % labor force | Unempl |
| housing_burden_pct | Households that are low income and spend more than half their income on housing; CES/HUD-defined measure | % households | HousBurd |
| pop_density_per_sqmi | Population divided by Gazetteer ZCTA land area; population numerator differs across old versus new configurations | persons / sq mi | derived |
| median_hh_income | Median income of households in the ACS income universe | 2022 dollars | B19013_001E |
| pct_poverty | Population below the federal poverty threshold / population with determined poverty status × 100 | % | 100 × B17001_002E / B17001_001E |
| pct_age_65plus | Male and female age-65+ counts / total population × 100 | % | 100 × sum(B01001_020E..025E,044E..049E) / B01001_001E |
| pct_renters | Renter-occupied housing units / occupied housing units × 100 | % occupied housing units | 100 × B25003_003E / B25003_001E |
| pct_no_vehicle | Owner- plus renter-occupied units with no vehicle / all occupied housing units × 100 | % occupied housing units | 100 × (B25044_003E + B25044_010E) / B25044_001E |
| pct_uninsured | Uninsured civilian noninstitutionalized population; subject-table percentage | % population | S2701_C05_001E (already a percentage) |
| pct_construction | Construction-industry employed residents / civilian employed population age 16+ × 100 | % employed population age 16+ | 100 × C24050_003E / C24050_001E |
| total_pop | Total population estimate | persons | B01003_001E |

## Table 3. Source and reference period by configuration

CES source periods are taken from the reviewed Part 1 audit at bf4c5bf and its cited CES 4.0 documentation; the 2021 publication date is not treated as the measurement year. Unknown years remain explicit rather than inferred. The original LA source pipeline selects LA-county tracts, while the new base uses the corrected statewide aggregation.

| Feature | Base: source; period | Original LA: source; period | Augmented: source; period |
|---|---|---|---|
| PM2.5 | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; 2015–2017 | CES 4.0; LA-county tracts → ZIP; original snapshot; 2015–2017 | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; 2015–2017 |
| Ozone | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; 2017–2019 | CES 4.0; LA-county tracts → ZIP; original snapshot; 2017–2019 | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; 2017–2019 |
| Asthma ED rate | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; 2015–2017 | CES 4.0; LA-county tracts → ZIP; original snapshot; 2015–2017 | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; 2015–2017 |
| Heart-attack ED rate | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; 2015–2017 | CES 4.0; LA-county tracts → ZIP; original snapshot; 2015–2017 | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; 2015–2017 |
| CES poverty | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; ACS 2015–2019 | — | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; ACS 2015–2019 |
| CES age 65+ | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; Unconfirmed — Part 1 source-year follow-up | — | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; Unconfirmed — Part 1 source-year follow-up |
| Low educational attainment | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; ACS 2015–2019 | — | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; ACS 2015–2019 |
| Linguistic isolation | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; ACS 2015–2019 | — | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; ACS 2015–2019 |
| Unemployment | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; ACS 2015–2019 | — | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; ACS 2015–2019 |
| Housing burden | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; HUD CHAS 2013–2017 | — | CES 4.0; statewide tracts → ZIP; Member 1 corrected table bf4c5bf; HUD CHAS 2013–2017 |
| Population density | UCLA layer population / Gazetteer 2023 land area; UCLA population reference year unconfirmed; land area: Gazetteer 2023 | ACS 2022 B01003 population / Gazetteer 2023 land area; Population: ACS 2018–2022; land area: Gazetteer 2023 | UCLA layer population / Gazetteer 2023 land area; UCLA population reference year unconfirmed; land area: Gazetteer 2023 |
| Median household income | — | ACS 2022 five-year; same-code ZCTA; 2018–2022 | — |
| Original ACS poverty | — | ACS 2022 five-year; same-code ZCTA; 2018–2022 | — |
| Original ACS age 65+ | — | ACS 2022 five-year; same-code ZCTA; 2018–2022 | — |
| Renter households | — | ACS 2022 five-year; same-code ZCTA; 2018–2022 | ACS 2018 five-year; same-code ZCTA; 2014–2018 |
| No-vehicle households | — | ACS 2022 five-year; same-code ZCTA; 2018–2022 | ACS 2018 five-year; same-code ZCTA; 2014–2018 |
| Uninsured population | — | ACS 2022 five-year; same-code ZCTA; 2018–2022 | ACS 2018 five-year; same-code ZCTA; 2014–2018 |
| Construction-industry employment | — | ACS 2022 five-year; same-code ZCTA; 2018–2022 | ACS 2018 five-year; same-code ZCTA; 2014–2018 |
| ACS total population | — | ACS 2022 five-year; same-code ZCTA; 2018–2022 | — |

## Important distinctions and preserved metadata

- **Poverty:** CES `poverty_pct` uses twice the federal poverty threshold; original ACS `pct_poverty` uses the poverty threshold itself. These are separate rows and are not interchangeable. Only the CES field is used in both new configurations.
- **Age:** CES `elderly65_pct` and original ACS `pct_age_65plus` describe a similar age group but have different sources/periods. The new pair uses the same CES values. CES demographic reference year remains unconfirmed.
- **Density:** original `pop_density_per_sqmi` uses ACS 2022 population, whereas new base/augmented use UCLA layer population. Both divide by Gazetteer 2023 land area. A shared field name does not make the old/new values or population vintage identical. The UCLA population reference year remains unconfirmed.
- **CES scope:** even identically named pollution/health indicators can differ between the original LA-only aggregation and the statewide base source. Actual value differences are recorded in results/original_vs_base_value_differences.csv. Within the current paired comparison, all common values are identical.
- **ACS additions:** source formulas are the same in principle, but original LA used ACS 2022 (2018–2022), and the augmented model uses ACS 2018 (2014–2018). Unavailable historical cells remain missing, never filled with 2022 values.
- **Construction:** the indicator measures residents employed in an industry, not their workplace locations or all outdoor occupations.
- **Population:** `total_pop` is excluded as a predictor in both new models. UCLA population is retained as `population` for Poisson fitting weights and possible rate-to-count conversion; the original table calls that metadata `ucla_population`.
- **Other non-predictors:** ZIP is a join key; coordinates and `group` define geography/folds; `chs_level=4` and `years` identify the fixed target slice. The CES percentile is a ranking reference, not an input. The UCLA rate/count fields are outcomes/metadata, never predictors.
- **Missingness:** complete inputs are available for 270/287 base ZIPs and 266/287 augmented ZIPs. No ZIP is excluded due to predictor missingness; imputation is fitted inside each training fold.
- **Time and geography:** historical ACS represents the later part of the 2008–2018 label period. Same-code matching is not a claim of harmonized geography. These are documented limitations; no additional boundary-based exclusion is imposed.

## Provenance and verification

Source inputs: Member 1 corrected CES 4.0 table at bf4c5bf; original 0980d9a snapshot; downloaded ACS 2018; the actual source feature lists. Definitions/formulas were checked against fetch_features_acs.py, fetch_features_ces_geo.py and fetch_statewide.py, the ACS metadata audit, and the reviewed Part 1 report. Supporting heat-health literature is listed separately in SUPPORTING_LITERATURE.md.

The machine-readable counterpart, results/unified_feature_comparison.csv, contains inclusion, source, period and missing counts for every configuration. This table retains the unconfirmed CES age and UCLA population years as open shared documentation items. It does not silently change any input values.
