# HEATLA

> **This README describes the original tract-level pipeline, which is now archived under `legacy/`.**
> The commands, layout and outputs below (`make`, `tests/`, `dashboard/`, `reports/methods_and_results.md`)
> exist only there. For the current project — ZIP-level prediction of UCLA Heat Maps excess ER visits,
> the website in `site/`, and cooling-center siting — see `REPORT.md` and `DATA_SOURCES.md`.

Heat vulnerability and cooling-centre siting for Los Angeles County.

Two questions, answered at the level of the 2020 census tract (2,498 tracts,
~9.9M residents):

1. **Which tracts are most vulnerable to extreme heat?**
2. **Where should a limited number of new public cooling centres go, so they
   reach the most vulnerable people?**

CSCI 461 (AI for Sustainable Development) · UN SDGs 3, 11, 13.

**Live dashboard: <https://heatla.vercel.app>**

The project has three parts:

- **Part A — status quo.** Who do the 153 existing cooling centres actually
  serve? A close-vs-far distribution comparison with effect sizes, not
  eyeballed histograms.
- **Part B — HVI + association study.** Build a tract-level Heat Vulnerability
  Index, validate it against heat-related ER visits and the CDC SVI, then ask
  which *social* factors go with vulnerability once the physical heat of a
  place is held fixed. This is an association analysis, not a deployed
  predictor — see below.
- **Part C — optimisation.** Choose K new sites with a maximum-coverage
  facility-location model: greedy and exact ILP, two objectives, five
  baselines, fairness by demographic subgroup, and sensitivity to budget and
  service radius.

Outputs: `reports/methods_and_results.md` (the write-up, with every figure and
table embedded), `reports/figures/`, `reports/tables/`, and an interactive
dashboard in `dashboard/`.

---

## Quick start

```bash
make setup     # python 3.12 venv + pinned dependencies
make mock      # full pipeline on synthetic data, ~45 s, no credentials needed
make test      # 25 unit tests
open reports/methods_and_results.md
```

`make mock` builds a synthetic LA-shaped county so the whole pipeline runs
before any download lands. Every mock output is stamped `mode=mock` in
`reports/run_manifest.json` and flagged in the dashboard header.

### Running against real data

```bash
make fetch     # downloads every public source that needs no credentials
make real      # same pipeline, real inputs
```

`make fetch` currently retrieves tract geometry, CDC SVI, CalEnviroScreen,
both Census crosswalks, LA County's 153-site cooling-centre layer, and LA
County tree canopy. Three inputs need a manual step:

| Input | What to do |
|---|---|
| ACS DP03/DP05 | get a free key at <https://api.census.gov/data/key_signup.html>, then `export CENSUS_API_KEY=…` |
| Land-surface temperature, impervious surface | run the scripts in `gee/` in the Earth Engine Code Editor, drop the CSVs in `data/raw/` |
| Heat-related ER visits by ZIP | export from the CDPH CCHVIz portal to `data/raw/heat_er_zip.csv` |

Full instructions and URLs: `data/README.md`. Without the ACS key the pipeline
falls back to CDC SVI for demographics, which covers everything except **%
under 5** and **median household income** — those are reported as missing
rather than guessed.

### The dashboard

```bash
make dashboard      # build to dashboard/dist
cd dashboard && npm run dev   # serve it locally at :5173
```

Five views: an interactive tract map with layer toggles and a service-radius
slider; an optimiser view where you pick method, objective, radius and K and
see the chosen sites, the metrics and the fairness-by-subgroup table against
every baseline; an interactive budget-vs-coverage curve with the marginal
benefit read off; the association-study results (SHAP, spatial-CV table, HVI
validation); and a plain-language methods and data-vintages page.

No Python runs in the browser — the pipeline exports static JSON/GeoJSON to
`dashboard/public/data/` and the page reads that.

### Deploying

Already deployed at <https://heatla.vercel.app>. To redeploy after a new run:

```bash
make mock          # or make real — regenerates dashboard/public/data
cd dashboard
npx vercel --prod  # vercel.json is committed, so no settings to configure
```

Or point the Vercel Git integration at this repo with **root directory**
`dashboard`. The build command is `node build.mjs` and the output directory is
`dist`; both are already in `vercel.json`, so no dashboard settings need
changing in the UI.

---

## Layout

```
heatla/
  config.yaml              run settings: data mode, radius, K grid, LST source
  data/
    raw/                   cached downloads (git-ignored)
    processed/             tract master table, HVI, Part C solutions
    README.md              every source URL and manual step
    vintages.md            every dataset's year, unit, and why mixing them is OK
  gee/                     Earth Engine export scripts (LST, canopy, impervious)
  src/heatla/
    config.py              seeds, paths, radii, K grid, lst_source toggle
    ingest.py              loaders, GEOID normalisation, 2010->2020 and ZIP->tract crosswalks
    build_table.py         one row per tract + provenance
    partA_statusquo.py     close-vs-far comparison, unmet need, quartile gaps
    partB_hvi.py           HVI construction and validation
    partB_association.py   spatial CV, SHAP, PDP/ALE
    partC_optimize.py      greedy + ILP, objectives, baselines, fairness, sensitivity
    figures.py             every figure
    export_dashboard.py    static JSON/GeoJSON for the dashboard
    fetch_real.py          download the credential-free sources
    run_all.py             the whole pipeline
  dashboard/               static site (index.html + app.js + styles.css + data)
  reports/                 methods_and_results.md, figures/, tables/
  tests/                   25 unit tests
```

---

## Notes on three choices

**The HVI is percentile-based.** A tract's score is the mean percentile rank
of four inputs — peak summer surface temperature, % 65+, % below poverty, %
without canopy. Percentiles rather than z-scores, because the inputs have
incompatible units and one very hot tract would otherwise stretch the index.

**Part B is an association study, not a predictor.** Training a model to
predict HVI from features correlated with HVI's own inputs just relearns the
formula. Instead, physical heat variables enter as *controls* and social
variables are the ones of interest; the ranking among them is the deliverable,
read off SHAP and ALE curves. Cross-validation folds are spatial k-means
clusters, because neighbouring tracts are near-copies — on this data a random
split inflates random-forest R² from 0.24 to 0.70.

**Part C separates what is optimised from what is measured.** Each
method × objective pair produces a site set; every site set is then scored on
every metric, including coverage by demographic subgroup. Greedy carries the
(1 − 1/e) submodular guarantee and lands within 0.1% of the ILP optimum here,
which is why the dashboard can sweep budgets interactively.

Seed is 461 throughout. Versions are pinned in `requirements.txt`. CI runs the
tests plus a full pipeline smoke run on the synthetic county.
