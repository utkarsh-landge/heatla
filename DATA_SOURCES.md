# DATA_SOURCES.md

Every column in `data/processed/` is listed here with its real source, the exact
layer/table, the year, the unit, the retrieval date, and any transformation.
No value in `data/processed/` is invented, imputed, or interpolated. Where a real
value could not be obtained it is left blank and reported (see "Known gaps").

Retrieval date for all entries below: **2026-10-28**.

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
- `NumRate` = `"Rate"` or `"Number"`.
- `Years` = `"2008-2018"` (All Years) or `"2014-2018"` (Last Five Years).

**Target definition chosen (confirmed with project owner, 2026-10-28):**
CHS category **4** (most extreme heat), `Years = "2008-2018"`. This matches the
project's goal ("extra ER visits during *extreme* heat") and the table previously
copied from the app (e.g. ZIP 91767 rate = 19.7). The full CHS 1–4 cross is also
saved to `data/processed/target_all_chs.csv` for sensitivity analysis.

**Columns in `target.csv`:**

| column | source field | unit | notes |
|---|---|---|---|
| `zip` | `zip` | — | LA County ZIP (289 rows) |
| `excess_er_rate_per_10k` | `excs_ER` where `NumRate='Rate'` | excess ER visits per 10,000 persons | layer label: "Rate (per 10,000)" |
| `excess_er_number` | `excs_ER` where `NumRate='Number'` | excess ER visit count | — |
| `population` | `popultn` | persons | layer-provided ZIP population |
| `n_heat_days` | `n_ht_dy` | days | heat days at CHS-4 threshold over 2008–2018 (constant across ZIPs = 2024) |
| `chs_category` | `categry` | — | 4 |
| `years` | `Years` | — | 2008-2018 |
| `is_ucla_campus_90095` | derived | 0/1 | flags ZIP 90095 (see caveat) |

**The "three numbers" mystery (resolved).** A ZIP row copied from the app table
showed three values (e.g. 91767 → 19.7, 86.8, 95.2). Confirmed from the raw
layer: **19.7** is `excs_ER` (the rate); **86.8** is `lvl1_th` and **95.2** is
`lvl4_th` — the choropleth **legend class-break thresholds**, which are constant
across all ZIPs within a year range (2008–2018: 86.8 / 88.8 / 91.4 / 95.2). They
are map legend breakpoints, **not** per-ZIP measurements and **not**
CalEnviroScreen values.

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
`County = 'Los Angeles'`. CES 4.0 reflects data vintages centered ~2015–2019
(published 2021). Raw tract rows saved untouched to
`data/raw/ces40_la_tracts.csv` (2,343 LA census tracts).

**Transformation.** CES is census-tract level; each tract carries a `ZIP`.
Features are aggregated tract → ZIP as a **population-weighted mean** using the
layer's `TotPop19` as the weight. Percentile columns (CES percentile) are also
population-weighted; averaging percentiles is an approximation and is noted here
as such.

| column | CES field | unit | notes |
|---|---|---|---|
| `pm25` | `PM2_5` | µg/m³ (annual mean PM2.5) | pop-weighted to ZIP |
| `ozone` | `Ozone` | ppm (summer daily max 8-hr) | pop-weighted to ZIP |
| `asthma_ed_per10k` | `Asthma` | age-adjusted ED visits per 10,000 | pop-weighted to ZIP |
| `cardiovascular_ed_per10k` | `Cardiovas` | age-adjusted ED visits per 10,000 | pop-weighted to ZIP |
| `poverty_pct_ces` | `Poverty` | % below 2× federal poverty level | pop-weighted to ZIP |
| `elderly65_pct_ces` | `Elderly65` | % population age 65+ | pop-weighted to ZIP |
| `ces4_percentile` | `CIscoreP` | CES 4.0 overall percentile (0–100) | pop-weighted; used as a **baseline index** in Step 4 |
| `ces_pop19` | sum of `TotPop19` | persons | CES-covered population in the ZIP (reference) |

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

## 5. Final modeling table (`data/processed/model_table.csv`)

One row per target ZIP (289), joining the target (section 1) with CES/geography
(sections 2–3) and ACS (section 4). 17 features total. **Complete-case rows (all
features present): 269 of 289**; the 20 incomplete rows are the institutional /
tiny-population ZIPs listed under "Known gaps". For social/demographic variables the
ACS versions are used; the CES `poverty_pct_ces` / `elderly65_pct_ces` columns remain
available in `features_ces_geo.csv` as a cross-check but are not duplicated here.

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
- **ACS features:** all pending, blocked on the Census API key (section 4).
