# Data

Nothing in this project is simulated unless the run says `mode=mock`. This
file lists where every real input comes from, which ones download
automatically, and what you have to fetch by hand.

## Quick start

```bash
make fetch     # everything that needs no credentials
make real      # run the pipeline against data/raw
```

`make fetch` currently retrieves tract geometry, CDC SVI, CalEnviroScreen 4.0,
both Census crosswalks, LA County's cooling-centre layer, and LA County tree
canopy. Three inputs it cannot get are listed under **Manual steps** below.

## Automatic sources

| File in `data/raw/` | Source | URL |
|---|---|---|
| `tl_2023_06_tract.zip` | TIGER/Line 2023 census tracts, California | <https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_06_tract.zip> |
| `svi_2022_CA.csv` | CDC/ATSDR Social Vulnerability Index 2022 | <https://svi.cdc.gov/Documents/Data/2022/csv/states/California.csv> |
| `ces40.csv` | CalEnviroScreen 4.0 results | <https://gis.data.ca.gov/api/download/v1/items/b6e0a01c423b489f8d98af641445da28/csv?layers=0> |
| `zcta_tract_rel.txt` | 2020 ZCTA ↔ tract relationship file | <https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_tract20_natl.txt> |
| `tract_2010_to_2020.txt` | 2020 ↔ 2010 tract relationship file | <https://www2.census.gov/geo/docs/maps-data/data/rel2020/tract/tab20_tract20_tract10_natl.txt> |
| `cooling_centers.geojson` | LA County Regional Cooling Centers (official layer, 153 sites) | ArcGIS: `services.arcgis.com/RmCCgQtiZLDCtblq/.../Cooling_Centers_-_Los_Angeles_County_Regional_(Official_-_Updated_July_2022)_(View)/FeatureServer/0` |
| `gee_canopy.csv` | LA County tree canopy by 2020 tract | ArcGIS: `services.arcgis.com/RmCCgQtiZLDCtblq/.../tree_canopy_by_tract/FeatureServer/0` |

Note on the canopy file: LA County publishes canopy per tract directly, so you
get that column without Earth Engine. If you run the Earth Engine canopy
export as well, it writes to the same filename and overwrites this one.

## Manual steps

### 1. ACS (needs a free API key)

The Census API stopped serving keyless requests. Get a key (instant, free) at
<https://api.census.gov/data/key_signup.html>, then:

```bash
export CENSUS_API_KEY=your_key_here
make real
```

`ingest.load_acs` pulls DP05 (age, race/ethnicity) and DP03 (poverty, median
income) for LA County tracts and caches the result at
`data/raw/acs_la_tracts.csv`.

**Without a key the pipeline still runs.** It falls back to the CDC SVI file,
which carries the same ACS counts for population, 65+, under-18, poverty and
race. Two columns are then unavailable and are reported as missing rather than
guessed: **% under 5** and **median household income**. Since the under-5
group is one of the vulnerable subgroups the analysis tracks, the key is worth
the two minutes.

### 2. Earth Engine rasters

Land-surface temperature and impervious surface come from rasters too large to
process locally. See `gee/README.md`: run the scripts in the Earth Engine Code
Editor, download the CSVs from Drive, and drop them in `data/raw/`:

- `gee_lst_landsat.csv` (or `gee_lst_ecostress.csv`)
- `gee_impervious.csv`
- `gee_canopy.csv` (optional; the LA County file above already covers it)

Each needs a `GEOID` column plus its value column.

### 3. Heat-related ER visits

CDPH / CalBRACE publish heat-related emergency-department visit rates by ZIP
code through the Climate Change and Health Vulnerability Indicators
(CCHVIz) portal: <https://skylab.cdph.ca.gov/CCHVIz/>. Export the
heat-related-illness ED visit table for Los Angeles County and save it as:

```
data/raw/heat_er_zip.csv
```

with at least a ZIP column and a rate column (the loader matches on any
column containing `zip`/`zcta` and any column containing `rate`).

These are **ZIP-level**, not tract-level. The pipeline apportions them to
tracts with the 2020 ZCTA↔tract relationship file, weighted by the population
each tract contributes to the ZIP. That is an estimate, not a measurement, and
every output that uses it says so.

## Mock mode

`data_mode: mock` in `config.yaml` (the default) builds a synthetic
LA-shaped county of 2,498 tracts and ~9.9M residents with realistic spatial
structure. It exists so Parts B and C are runnable before any download lands,
and so CI has something deterministic to test. Mock outputs are stamped
`mode=mock` in `reports/run_manifest.json` and in the dashboard header; they
are never presented as findings.
