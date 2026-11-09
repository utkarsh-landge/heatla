# Part 2 historical feature update — 2026-11-08

The base inputs now use Member 1's corrected CES 4.0 table (bf4c5bf). The augmented input now adds four ACS 2018 five-year estimates, representing 2014–2018, instead of ACS 2022 (2018–2022). Both retain the original 287 ZIPs, five spatial folds and unchanged UCLA category-4 labels. No prediction models were trained during this update.

## Sources and formulas

Official endpoints: [detailed tables](https://api.census.gov/data/2018/acs/acs5), [subject tables](https://api.census.gov/data/2018/acs/acs5/subject). Raw responses, each covering 33,120 ZCTAs, are saved under sources/acs2018_values. Previously checked 2018 metadata confirms these field definitions.

| Feature | Formula | Universe |
|---|---|---|
| Renters | 100 × B25003_003E / B25003_001E | Occupied housing units |
| No vehicle | 100 × (B25044_003E + B25044_010E) / B25044_001E | Occupied housing units |
| Uninsured | S2701_C05_001E, already a percentage | Civilian noninstitutionalized population |
| Construction | 100 × C24050_003E / C24050_001E | Civilian employed population age 16+; industry proxy, not all outdoor workers |

Negative suppression codes are missing, not zero. Zero numerators are valid; zero denominators are missing. Missing either no-vehicle numerator preserves a missing result.

## Matching and remaining limitations

285 target codes exist in the historical data. 90639 and 90840 are absent; their values remain missing. Feature missing counts are 12 renters, 12 no-vehicle, 9 uninsured and 9 construction. All 287 sample rows remain; no newer values are substituted and no imputation has been applied to the stored inputs. Future model imputation must be fitted separately inside each training fold.

The [official 2010/2020 ZCTA relationship file](https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta510_zcta520_natl.txt) was checked. 181 target codes have at least 95% mutual land overlap. The remaining 106, including the two unmatched codes, are flagged in results/acs2018_geography_audit.csv. The 95% threshold is a descriptive diagnostic chosen for this audit, not a professor requirement or an exclusion rule.

The retained historical values are same-code community proxies. Land overlap is not population overlap; no area-weighted conversion of these percentages is claimed. The relationship file does not independently establish the vintage of UCLA's published geometry. Exact geographic harmonization remains unperformed and should be stated in the report.

Likewise, 2014–2018 does not represent the complete 2008–2018 label period. The cumulative interpretation of the UCLA target remains unresolved; no L4−L3 substitution has been made. This update improves the temporal relevance of the added variables without claiming to resolve every temporal or spatial mismatch.

## Files and verification

- Current inputs: data/la_base.csv, data/la_augmented.csv, data/la_augmented_acs2018.csv.
- Historical feature table: data/features_acs2018.csv.
- Earlier input: data/la_augmented_acs2022_provisional.csv; its previous configuration/manifest is under versions/acs2022_provisional.
- Validation: results/historical_update_validation.json; all common fields, labels and fold IDs are unchanged, values are within 0–100 or missing, and historical columns reproduce the downloaded formulas.
- Source file hashes and paths: input_manifest.json.
- No secrets are saved in these files. The supplied key was used only in the temporary request process.
