# DATA_SOURCES.md

Every column in `data/processed/` is listed here with its real source, the exact
layer/table, the year, the unit, the retrieval date, and any transformation.
No value in `data/processed/` is invented, imputed, or interpolated. Where a real
value could not be obtained it is left blank and reported (see "Known gaps").
The models fill missing inputs with the training-fold median at fit time; the
stored files keep them blank.

Retrieval dates are given per entry. Sections 1–4 were retrieved on **2026-10-28**;
later sections state their own date.

---

## 1. Target — UCLA Heat Maps excess ER visits (`data/processed/target.csv`)

**Source.** UCLA Heat Maps, an ArcGIS Experience app:
<https://experience.arcgis.com/experience/4c158842b5c94857a06c3a85c7aa02de/page/Map>.
The app renders with JavaScript, but its configuration (ArcGIS item
`4c158842b5c94857a06c3a85c7aa02de`) references hosted FeatureServer layers on the
public org `services7.arcgis.com/2hYXmwteFLemN5bW`. No login or key is required.
The layers were queried directly over the ArcGIS REST API (no browser needed).

**Layer used (primary target):**
`.../arcgis/rest/services/zip_ER/FeatureServer/0`, filtered to
`cnty_nm = 'Los Angeles'`. Raw rows saved untouched to
`data/raw/ucla_excess_er_zip.csv` (4,624 LA rows) with the layer field
definitions in `data/raw/ucla_excess_er_zip.meta.json`.

**Structure of the layer.** Each ZIP appears in up to 16 rows — the cross of:
- `categry` = CalHeatScore (CHS) level **1–4**. The app labels this "Filter by
  CalHeatScore Category". Per the app text, CHS levels are temperature thresholds
  derived from historical heat–health relationships, categorized into four levels
  of risk (CHS 1 = mildest heat threshold … CHS 4 = most extreme heat).
  **The values are cumulative across levels** (inferred from the data, see
  `reports/member3_labels_website_siting.md` section 1): the level-k row covers
  every warm-season day at or below level k, so the level-4 row is the total over
  all heat levels and the level-k-only contribution is level k minus level k−1.
- `NumRate` = `"Rate"` or `"Number"`.
- `Years` = `"2008-2018"` (All Years) or `"2014-2018"` (Last Five Years).

**Target definition chosen (confirmed with project owner, 2026-10-28):**
CHS category **4** (most extreme heat), `Years = "2008-2018"`. This matches the
project's goal ("extra ER visits during *extreme* heat") and the table previously
copied from the app (e.g. ZIP 91767 rate = 19.7). The full CHS 1–4 cross is also
saved to `data/processed/target_all_chs.csv` for sensitivity analysis.
Because the values are cumulative, the level-4 row is a total over all heat levels,
not over extreme-heat days only. The extreme-heat-only quantity is level 4 minus
level 3; results for that target are in `results/member1/ces40_fixed_level_only/`.

**Columns in `target.csv`:**

| column | source field | unit | notes |
|---|---|---|---|
| `zip` | `zip` | — | LA County ZIP (289 rows) |
| `excess_er_rate_per_10k` | `excs_ER` where `NumRate='Rate'` | excess ER visits per 10,000 persons, **total over May–October 2008–2018** | layer label: "Rate (per 10,000)". Not a daily or yearly rate: UCLA's yearly layer (`time_trend_zip`) sums to this value over the 11 years, to within rounding (checked in two ZIPs) |
| `excess_er_number` | `excs_ER` where `NumRate='Number'` | excess ER visit count | — |
| `population` | `popultn` | persons | layer-provided ZIP population |
| `n_heat_days` | `n_ht_dy` | days | number of warm-season days at or below the row's CHS level. For CHS 4 it equals 2,024 in every ZIP, which is all warm-season days in 2008–2018 (184 days × 11 years); it is **not** a count of extreme-heat days |
| `chs_category` | `categry` | — | 4 |
| `years` | `Years` | — | 2008-2018 |
| `is_ucla_campus_90095` | derived | 0/1 | flags ZIP 90095 (see caveat) |

**The "three numbers" mystery (resolved).** A ZIP row copied from the app table
showed three values (e.g. 91767 → 19.7, 86.8, 95.2). Confirmed from the raw
layer: **19.7** is `excs_ER` (the rate); **86.8** is `lvl1_th` and **95.2** is
`lvl4_th` — that ZIP's own **CalHeatScore temperature thresholds** in °F for
levels 1 and 4 (2008–2018, ZIP 91767: 86.8 / 88.8 / 91.4 / 95.2). They are
ZIP-specific, not constant: there are 267 distinct level-4 thresholds across
California ZIPs (69.7–107.6 °F), and ZIP 90001's are 81.4 / 83.6 / 86.6 / 91.5.
They are **not** map legend breakpoints and **not** CalEnviroScreen values.
*(Corrected 2026-11-08; an earlier version of this note described them as legend
class breaks that were constant across ZIPs.)*

**Unit / magnitude check (resolved).** Press coverage quotes excess rates of
roughly 0.9–3.5 per 10,000 (e.g. West Adams ≈ 3.5). Those figures match a
**different, secondary layer**, `Daily_Excess_ER_ZIPCODE_with_county`
(`Z_ER_RN`, LA mean 2.35 per 10,000 **per day**) — the daily excess rate matching
the About-page definition (excess daily ER visit rate = daily rate on heat-event
days minus daily rate on non-heat days, per 10,000 persons per day). The copied
table values (2.5–19.7) are the **CHS-4 `zip_ER` rate**, a different slice (by CHS
severity, not a single daily rate). The secondary Daily layer is saved untouched
to `data/raw/ucla_daily_excess_er_zip.csv` for reference/sensitivity.

**Internal consistency check (passed).** The About-page relation
`number = rate × population ÷ 10,000` holds in the data: e.g. ZIP 90001,
rate 11.4 × pop 56,410 ÷ 10,000 = 64.3 vs reported number 64.4.

**Caveat — ZIP 90095 (UCLA campus/hospital).** Flagged by `is_ucla_campus_90095`.
Its residential population is ~1, so rates for it are unstable and ER patients may
be mis-attributed here. In the secondary Daily layer this ZIP is the extreme
outlier (`Z_ER_RN` max 77.4). Models will be run with and without it.

---

## 2. Pollution, health & some social — CalEnviroScreen 4.0 (`data/processed/features_ces_geo.csv`)

**Source.** CalEnviroScreen 4.0 (OEHHA/CalEPA), accessed via the UCLA-hosted copy
on the same ArcGIS org used for the target:
`.../arcgis/rest/services/calenviroscreen_test3/FeatureServer/0`, filtered to
`County = 'Los Angeles'`. CES 4.0 inputs describe roughly 2013–2019
(published 2021). Raw tract rows saved untouched to
`data/raw/ces40_la_tracts.csv` (2,343 LA census tracts).

**Transformation.** CES is census-tract level; each tract carries a `ZIP`.
Features are aggregated tract → ZIP as a **population-weighted mean** using the
layer's `TotPop19` as the weight. Percentile columns (CES percentile) are also
population-weighted; averaging percentiles is an approximation and is noted here
as such.

**Missing-value correction (−999).** CalEnviroScreen marks missing tract values
as −999. These are set to missing, field by field, before the population-weighted
aggregation, so a tract with no value for a field is left out of that field's mean.
The original pull did not do this; the corrected tables are in `data/corrected/`
(built by `scripts/build_corrected_ces_tables.py`). See `reports/member1_statewide.md`
section 1 and `reports/ces_sentinel_fix.md`.

| column | CES field | unit | notes |
|---|---|---|---|
| `pm25` | `PM2_5` | µg/m³ (annual mean PM2.5) | pop-weighted to ZIP |
| `ozone` | `Ozone` | ppm (summer daily max 8-hr) | pop-weighted to ZIP |
| `asthma_ed_per10k` | `Asthma` | age-adjusted ED visits per 10,000 | pop-weighted to ZIP |
| `cardiovascular_ed_per10k` | `Cardiovas` | age-adjusted ED visits per 10,000 | pop-weighted to ZIP |
| `poverty_pct_ces` | `Poverty` | % below 2× federal poverty level | pop-weighted to ZIP |
| `elderly65_pct_ces` | `Elderly65` | % population age 65+ | pop-weighted to ZIP |
| `edu_lt_hs_pct` | `Educatn` | % of population over 25 without a high-school education | pop-weighted to ZIP |
| `ling_isol_pct` | `Ling_Isol` | % of limited-English-speaking households | pop-weighted to ZIP |
| `unemployment_pct` | `Unempl` | % of population over 16 unemployed and in the labour force | pop-weighted to ZIP |
| `housing_burden_pct` | `HousBurd` | % of households that are low-income and pay more than 50% of income on housing | pop-weighted to ZIP |
| `ces4_percentile` | `CIscoreP` | CES 4.0 overall percentile (0–100) | pop-weighted; used as a rank-only baseline index on matched ZIPs (REPORT §4a, §4c) |
| `ces_pop19` | sum of `TotPop19` | persons | CES-covered population in the ZIP (reference) |

The four rows above `ces4_percentile` (education, linguistic isolation,
unemployment, housing burden) are used by the models through the statewide and
LA tables; definitions follow `reports/member1_statewide.md` section 3. In those
tables the poverty and age-65+ columns are named `poverty_pct` and `elderly65_pct`.

---

## 3. Geography — US Census Gazetteer 2023, ZCTA (`data/processed/features_ces_geo.csv`)

**Source.** 2023 Census Gazetteer, national ZCTA file:
<https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_zcta_national.zip>.
No key required. Raw file saved untouched to
`data/raw/2023_Gaz_zcta_national.txt`.

**ZIP → ZCTA handling.** Each target ZIP is matched to the ZCTA with the same
5-digit code (`GEOID`). ZIPs with no identical ZCTA are left with blank geography
and reported (see "Known gaps"); they are not reassigned to a neighboring ZCTA.

| column | Gazetteer field | unit |
|---|---|---|
| `lat` | `INTPTLAT` | decimal degrees (ZCTA centroid) |
| `lon` | `INTPTLONG` | decimal degrees (ZCTA centroid) |
| `aland_sqmi` | `ALAND_SQMI` | square miles (land area) |

---

## 4. Census ACS 2022 5-year (ZCTA) (`data/processed/features_acs.csv`)

**Status.** This ACS 2022 pull was the original source. For the four features the
reported models add (`pct_renters`, `pct_no_vehicle`, `pct_uninsured`,
`pct_construction`) it is superseded: those now use ACS 2018 5-year estimates
(2014–2018), fetched by `part2/fetch_acs2018.py` with the same formulas. See
`part2/ACS_VARIABLE_AND_YEAR_AUDIT.md` and `part2/HISTORICAL_FEATURE_UPDATE.md`.

**Source.** Census Data API, ACS 2022 5-year estimates, ZCTA geography. A free API
key is required (<https://api.census.gov/data/key_signup.html>); it is read from
env var `CENSUS_API_KEY` only and never written to a file or committed. Target ZIPs
are matched to the same-code ZCTA. Raw API rows saved untouched to
`data/raw/acs5_2022_zcta_la.json`.

| column | ACS variable(s) | unit | notes |
|---|---|---|---|
| `total_pop` | `B01003_001E` | persons | — |
| `median_hh_income` | `B19013_001E` | 2022 dollars | suppressed (blank) in tiny-pop ZIPs |
| `pct_poverty` | `B17001_002E` / `B17001_001E` | % below poverty | — |
| `pct_age_65plus` | sum `B01001_020..025E,044..049E` / `B01001_001E` | % | age 65+ both sexes |
| `pct_renters` | `B25003_003E` / `B25003_001E` | % renter-occupied | — |
| `pct_no_vehicle` | (`B25044_003E`+`B25044_010E`) / `B25044_001E` | % households no vehicle | — |
| `pct_uninsured` | `S2701_C05_001E` (subject table) | % uninsured | civilian noninstitutionalized |
| `pct_construction` | `C24050_003E` / `C24050_001E` | % civ. employed in construction | proxy for outdoor workers |
| `pop_density_per_sqmi` | `total_pop` / Gazetteer `aland_sqmi` | persons / sq mi | — |

**Suppressed values.** ACS sentinel codes (≤ −666666) are treated as missing and
left blank, never substituted.

**Omitted on purpose.** "% living alone age 65+" is not included: no single ACS
variable maps to it unambiguously, and guessing a column's meaning is forbidden by
the project's hard rules. It can be added later once the exact table is confirmed.

**Validation.** UCLA layer population vs ACS `total_pop` agree to a median ~3%
relative difference (ZIPs with pop > 500), confirming the ZIP↔ZCTA join is correct.

---

## 5. California-wide training table (`data/processed/model_table_ca.csv`)

For the honest LA-holdout test and the ZIP→tract downscale, the same target and
CES feature pulls were extended from LA County to **all of California**, one row per
ZIP × CalHeatScore level.

**Target.** Same UCLA `zip_ER` FeatureServer layer as section 1, queried statewide
(all counties, all four CHS levels, `Years = "2008-2018"`). Raw rows saved untouched
to `data/raw/ca_excess_er_zip.csv`. Retrieval date 2026-10-31.

**Features.** CalEnviroScreen 4.0 statewide (`calenviroscreen_test3`, all counties,
`data/raw/ces40_ca_tracts.csv`), aggregated tract → ZIP by `TotPop19` population
weight exactly as in section 2, plus population density and the ZCTA centroid. No
ACS key was required for the statewide table; it uses CES-sourced social columns.
Script: `scripts/fetch_statewide.py`. Every column traces to the sources already
documented above — nothing new is invented.

---

## 6. Cal-Adapt projected extreme-heat days (`data/processed/heat_days_la.csv`, `heat_factor_2030.csv`)

**Source.** Cal-Adapt API (UC Berkeley Geospatial Innovation Facility),
<https://api.cal-adapt.org>. Series `exheat_year_ens32avg_rcp45` and
`exheat_year_ens32avg_rcp85` = **average number of extreme-heat days per year across
32 LOCA-downscaled climate models** (Scripps/Pierce et al. 2014), on a 1/16°
(~6 km) grid, one value per year 2006–2100. Retrieval date 2026-11-02. No key.

**Definition (Cal-Adapt API docs, "Climate Indicators").** An *extreme-heat day* is
a day whose daily maximum temperature exceeds the **98th percentile of observed
1961–1990 April–October** maximum temperature at that grid cell. This is Cal-Adapt's
own published definition, not one we chose.

**Query.** For each LA ZIP, the grid cell under the ZCTA centroid (lat/lon from the
2023 Gazetteer, section 3) was queried via `/series/{slug}/events/?g=POINT(lon lat)`.
Raw JSON responses saved untouched to `data/raw/caladapt_exheat/<scenario>/<zip>.json`.
287 ZIPs retrieved; **2 skipped** (`91123`, `91522` — no centroid, section "Known
gaps"); never filled in.

**Derived `heat_factor` (`heat_factor_2030.csv`; written by `scripts/run_projection_2030.py`, not committed).**
`heat_factor(zip) = mean exheat days 2026–2035 ÷ mean exheat days 2008–2018`, using
the **same** ens32avg series for numerator and denominator (no historical/projection
splice; 2008–2018 matches the UCLA observation window). 2026–2035 is a 10-year window
centred on 2030. The projection in `results/projection_2030.json` is
`observed CHS-4 excess-ER rate × heat_factor`.

**Assumptions (stated, not hidden).** Per-heat-day vulnerability is held constant —
only the count of extreme-heat days changes, not the ER response per heat day.
Demographic/health features are today's (CES/ACS) and are **not** projected forward;
doing so would be fabrication. The factor is a multiplicative climate signal, not a
fitted per-ZIP time series (no per-ZIP yearly ER series exists to fit). Script:
`scripts/fetch_climate_caladapt.py`, `scripts/run_projection_2030.py`.

---

## 7. Modeling tables

### Original LA table (`data/processed/model_table.csv`, legacy)

This is the original LA table (ACS 2022), used by the original 13-input LA model.
The reported models no longer use it. One row per target ZIP (289), joining the
target (section 1) with CES/geography (sections 2–3) and ACS (section 4). 17
features total. **Complete-case rows (all features present): 269 of 289**; the 20 incomplete rows are the institutional /
tiny-population ZIPs listed under "Known gaps". For social/demographic variables the
ACS versions are used; the CES `poverty_pct_ces` / `elderly65_pct_ces` columns remain
available in `features_ces_geo.csv` as a cross-check but are not duplicated here.

### Tables used by the reported models

- `data/corrected/model_table_ca_corrected.csv`: statewide ZIP × heat level table
  with the −999 correction. It is identical to
  `results/member1/inputs/model_table_ca_ces40_fixed.csv`.
- `part2/data/la_base.csv`: 287 LA ZIPs at level 4, 11 inputs (corrected
  CalEnviroScreen fields plus population density).
- `part2/data/la_augmented.csv`: the same 287 ZIPs, 15 inputs (the 11 above plus
  the four ACS features, ACS 2014–2018).

---

## Known gaps (real missing data, not filled)

- **ZIPs with no matching ZCTA (2):** `91123`, `91522`. Both are special-use /
  non-residential ZIPs (Pasadena PO/institutional; Warner Bros. studio, pop ≈ 26).
  Geography left blank.
- **ZIPs with no CalEnviroScreen tracts (13):** `90014, 90073, 90089, 90095,
  90263, 90639, 90822, 91123, 91210, 91522, 91608, 91759, 93553`. Most are
  institutional or non-residential (90073 VA hospital pop ≈ 8; 90089 USC;
  90095 UCLA pop ≈ 1; 90263 Pepperdine; 90822 VA Long Beach pop ≈ 6; 91608
  Universal Studios pop ≈ 34; 91210 Glendale Galleria; 91522 Warner Bros.);
  90014 (Downtown LA), 91759 (Mt Baldy), and 93553 (Pearblossom) are small or
  rural. CES-derived features left blank for these ZIPs.
- **ACS features:** retrieved (section 4). Suppressed ACS values remain blank.
- **Missing model inputs:** 17 of the 287 modelled LA ZIPs have at least one of the
  11 LA base inputs missing, and 21 have at least one of the 15 augmented inputs
  missing. Statewide, 394 of 1,675 ZIPs have at least one input missing.
