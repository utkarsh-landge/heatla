# Earth Engine exports

The three raster inputs (land-surface temperature, tree canopy, impervious
surface) are aggregated to census tracts in Google Earth Engine, because the
rasters are far too large to download and process locally.

## How to run

1. Sign in at <https://code.earthengine.google.com> (a free non-commercial
   account is enough).
2. Paste a script from this folder into the Code Editor and press **Run**.
3. Go to the **Tasks** tab and start the export. Each one takes a few minutes.
4. The CSV lands in your Google Drive. Download it and put it in `data/raw/`
   with the filename the script's `fileNamePrefix` uses:

   | script | output file |
   |---|---|
   | `export_lst_landsat.js` | `data/raw/gee_lst_landsat.csv` |
   | `export_lst_ecostress.js` | `data/raw/gee_lst_ecostress.csv` |
   | `export_canopy_impervious.js` | `data/raw/gee_canopy.csv`, `data/raw/gee_impervious.csv` |

5. Re-run the pipeline: `make real`.

`src/heatla/ingest.py::load_gee_tract_summaries` picks these up automatically.
Each file needs a `GEOID` column plus the value column; anything else is
ignored.

## Landsat vs ECOSTRESS

Landsat is the default. It is well documented, has a long archive, and 30 m
resolution, but it only sees ~10:30 local time, so it measures daytime surface
heat. Night-time heat is what kills - a home that never cools below 80F is
the actual risk - so `export_lst_ecostress.js` is provided as the upgrade
path. ECOSTRESS's ISS orbit drifts across the diurnal cycle and gives
night-time passes at ~70 m, at the cost of a sparser, less regular archive.

Run both and compare before switching `lst_source` in `config.yaml`.
