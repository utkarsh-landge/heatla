# Part 2 — LA base versus augmented feature comparison

Start with [the English report](PART2_MODEL_COMPARISON_REPORT.md).

## Included

- Frozen prepared inputs: 287 LA ZIPs, UCLA category-4 historical target, corrected common features and four ACS 2018 additions.
- Six model/configuration results, OOF predictions, independent validation, six PNG/PDF figures and full captions.
- Feature definitions, periods, supporting references, setup table and source provenance hashes.
- `data/zips.geojson`: plotting geometry copied unchanged from Member 3 commit 7f2c2c0 (`site/data/zips.geojson`). It is a plotting asset, not proof of harmonized source boundaries.
- Explicitly named ACS 2022 provisional data and metadata, retained for historical-replacement checks; not used in the main experiment.

## Reproduce from the repository root

Use Python 3.12. The virtual environment is local and must not be committed.

```powershell
python -m venv part2/.venv
./part2/.venv/Scripts/python.exe -m pip install -r part2/requirements-models.txt
./part2/.venv/Scripts/python.exe part2/validate_comparison_results.py
./part2/.venv/Scripts/python.exe part2/make_comparison_figures.py
./part2/.venv/Scripts/python.exe part2/write_comparison_report.py
```

On macOS or Linux:

```bash
python -m venv part2/.venv
part2/.venv/bin/python -m pip install -r part2/requirements-models.txt
part2/.venv/bin/python part2/validate_comparison_results.py
part2/.venv/bin/python part2/make_comparison_figures.py
part2/.venv/bin/python part2/write_comparison_report.py
```

The reported run was on Windows. Random forest and gradient boosting results differ by up to about 0.002 in pooled metrics between Windows and macOS; Poisson reproduces to 1e-11.

To refit all 30 fold models, run `part2/run_feature_comparison.py` with the same Python environment before the validation/plot/report commands. No Census key or sibling data directory is needed for these commands. Model settings and prepared-input hashes are unchanged from the completed run.

## Preparation versus reproduction

This delivery reproduces the model comparison from the included prepared inputs. It does not bundle the full original data package, statewide tables, team branch snapshots or national download caches. Full raw-to-prepared reconstruction and regeneration of the three-way historical feature dictionary require those original sources; the included table is a frozen audited deliverable. Source filenames/hashes are retained in input_manifest.json. `fetch_acs2018.py` is an optional refresh tool requiring a locally configured Census key; do not refresh inputs immediately before submission without rerunning and checking affected results.

## Remaining team checks

Confirm the population reference year and category-4 target interpretation. CES inputs have mixed periods; ACS additions cover 2014–2018, while the UCLA target covers 2008–2018. Source boundaries are not harmonized. Scott et al. claims are limited to the verified abstract. The website now loads these predictions through `scripts/build_site_results.py` (integration branch). Merge and synchronize with Parts 1 and 3 after review.

The upload package excludes local environments, caches, private review notes and team branch copies. Personal absolute paths in provenance metadata have been replaced with source filenames; numerical source hashes are preserved. Only the plotting geometry path was changed in the core reproduction scripts.
