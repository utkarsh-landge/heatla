# Part 2 ACS Variable and Reference Period Audit

The four added variables use the intended Census fields, and their current processed values agree with a recalculation from the received raw ACS responses. Their definitions can be documented now. Temporal alignment remains unresolved because the current inputs cover 2018–2022 and the health labels cover 2008–2018. Historical inputs have not yet been downloaded or substituted.

> **Superseded.** The paragraph above describes the state before the historical update. The models now use ACS 2014–2018 inputs for the four added variables; see [HISTORICAL_FEATURE_UPDATE.md](HISTORICAL_FEATURE_UPDATE.md).

## Verified variable definitions

| Feature | Recommended report label | Universe and formula | Interpretation limit |
|---|---|---|---|
| `pct_renters` | Renter-occupied housing units percent | Occupied housing units. `100 * B25003_003E / B25003_001E` | Counts housing units or households, rather than the share of individual residents renting. It does not directly measure air-conditioning access. |
| `pct_no_vehicle` | Occupied housing units with no vehicle available percent | Occupied housing units. `100 * (B25044_003E + B25044_010E) / B25044_001E` | Includes owner- and renter-occupied units. It does not directly measure driving ability, transit access, or center travel time. |
| `pct_uninsured` | Uninsured civilian noninstitutionalized population percent | `S2701_C05_001E` is already a percentage. No further multiplication by 100 is needed. | The universe is civilian noninstitutionalized people. This is a population percentage, not a household percentage. |
| `pct_construction` | Construction-industry employment percent | Civilian employed population age 16 and over. `100 * C24050_003E / C24050_001E` | Industry differs from occupation. This resident-based ZCTA input is an imperfect proxy for outdoor work and does not locate the jobs themselves. |

The official field labels support the selected numerators and denominators. B25003 and B25044 use occupied housing units. C24050 specifies civilian employed people age 16 and over. S2701 explicitly identifies the uninsured percentage and its population universe. [Census B25003](https://api.census.gov/data/2022/acs/acs5/groups/B25003.html), [B25003 universe](https://data.census.gov/table?q=B25003&y=2022), [Census B25044](https://api.census.gov/data/2022/acs/acs5/groups/B25044.html), [B25044 universe and calculation](https://www.ahrq.gov/sites/default/files/wysiwyg/data/clh/CLH-Data-Sources-Documentation-2025.pdf), [Census S2701](https://api.census.gov/data/2022/acs/acs5/subject/groups/S2701.html), [Census C24050](https://api.census.gov/data/2022/acs/acs5/groups/C24050.html)

The construction variable should be described as construction-industry employment. Treating it as an outdoor-exposure proxy is a research hypothesis requiring supporting literature. The table establishes its measurement definition, not a heat-health causal effect.

## Reference periods

| Input or outcome | Period represented | Audit conclusion |
|---|---|---|
| UCLA target used by this project | 2008–2018 | Fixed historical health-label period in the received target tables |
| Current ACS 2022 five-year features | 2018–2022 | A five-year pooled estimate; most years follow the health-label period |
| Candidate ACS 2018 five-year features | 2014–2018 | Entirely within the health-label period, but represents only its later portion |
| Raw ACS download timestamp | 2026-11-07 | Retrieval date only; it does not change the estimate period |

Census identifies the releases as 2018–2022 and 2014–2018 five-year estimates. The release year is the last year of the estimate period. [Census 2022 comparison guidance](https://www.census.gov/programs-surveys/acs/guidance/comparing-acs-data/2022.html), [Census 2018 release information](https://www.census.gov/programs-surveys/acs/news/data-releases/2018/release.html)

## Local calculation verification

The audit recalculated all four features from `acs5_2022_zcta_la.json` and compared them with `features_acs.csv`. The comparison included missing values and the original three-decimal rounding for calculated ratios.

| Feature | Processed ZIP rows checked | Formula mismatches | Missing among 287 modeled ZIPs |
|---|---|---|---|
| `pct_renters` | 289 | 0 | 10 |
| `pct_no_vehicle` | 289 | 0 | 10 |
| `pct_uninsured` | 289 | 0 | 4 |
| `pct_construction` | 289 | 0 | 5 |

The current no-vehicle formula uses `or 0` when parsing its two numerator terms. This could substitute zero for a missing component in a future dataset. No missing-component case with a positive denominator occurred in this received snapshot. Historical extraction should preserve the percentage as missing if either required numerator is missing. A zero count remains a valid observation.

## Historical data recommendation

Use ACS 2018 five-year estimates as a concrete candidate for the four added features. This is a recommendation for the historical comparison, subject to data retrieval and geography checks. The same eight required fields exist in both the official 2018 and 2022 metadata, and the relevant labels have matching meanings. The downloaded metadata and the 16 field checks are stored under `sources/census_metadata` and `results/acs_official_field_labels.csv`. [2018 B25003](https://api.census.gov/data/2018/acs/acs5/groups/B25003.html), [2018 B25044](https://api.census.gov/data/2018/acs/acs5/groups/B25044.html), [2018 C24050](https://api.census.gov/data/2018/acs/acs5/groups/C24050.html), [2018 S2701](https://api.census.gov/data/2018/acs/acs5/subject/groups/S2701.html)

Replacing the endpoint year alone is insufficient for a completed historical dataset. Census documents 2010 Census ZCTA geography for the 2018 release and 2020 Census ZCTA geography for the 2022 release. Check matching codes, unmatched ZIPs, and relevant boundary changes before joining the historical values. ZCTAs approximate postal ZIP areas, and some ZIPs have no corresponding ZCTA. [2018 geography](https://www.census.gov/programs-surveys/acs/geography-acs/geography-boundaries-by-year/2018.html), [2022 geography](https://www.census.gov/programs-surveys/acs/geography-acs/geography-boundaries-by-year/2022.html), [Census ZCTA explanation](https://www.census.gov/programs-surveys/geography/guidance/geo-areas/zctas.html)

The 2014–2018 window is not an exact representation of all eleven years from 2008 through 2018. Document this limitation and the reason for selecting it. A matched 2014–2018 health-label experiment would change the agreed target and should be a separate team decision. Avoid creating a period-wide demographic value by casually averaging overlapping five-year estimates.

## Next implementation steps

1. Confirm the shared corrected CES baseline and its reference periods with Member 1.
2. Retrieve the historical ACS candidate and validate its raw fields and geographic coverage.
3. Use identical corrected base-feature values and ZIP folds in both Part 2 configurations. Add only the four ACS variables to the augmented configuration.
4. Fit missing-value imputation within training folds. Do not drop different ZIP sets for the two configurations.
5. Record current-period and historical-period experiments separately if both are run.

## Original access attempt (superseded)

The initial sample-access attempt failed before a valid key was available. On 2026-11-08, the official detailed and subject tables were successfully downloaded with a key supplied at runtime. Four historical features were calculated and substituted. The key was not saved to project files. See HISTORICAL_FEATURE_UPDATE.md for the current status. [Census API key notice](https://www.census.gov/library/video/2026/adrm/requesting-a-census-data-api-key.html)

- Completed official definition checks for four variables and both metadata vintages.
- Completed recalculation of current processed values from raw responses.
- Completed reference-period and geography-vintage checks.
- Historical numeric retrieval and same-code replacement are complete. Official geographic overlap diagnostics are complete; exact boundary harmonization is not performed.
- The four selected empirical references and feature rationales are now in SUPPORTING_LITERATURE.md and FEATURE_SELECTION_RATIONALE.md. Scott et al. full-text verification remains pending.
- The CES -999 aggregation issue remains separate from these ACS formula checks.

The audit script below (`part2/audit_acs_variables.py`) is not included in the repository. With that script, the local checks were run from the workspace root as follows.

```powershell
python ./part2/audit_acs_variables.py --data-package ../heatla_data_0980d9a
```

Add `--fetch-metadata` to refresh the official metadata over the network.
