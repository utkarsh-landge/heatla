"""Part 2 population-year check: 2010 Census population instead of UCLA's 2020 population.

The label covers 2008-2018, but the population field in UCLA's layer is from the 2020
Census. It enters the models twice: as population density (a model input) and as the
Poisson sample weight. This repeats Part 2's base-versus-augmented comparison with
2010 Census ZCTA population (POP10, Census 2010 Gazetteer ZCTA file). Everything else is
unchanged: the same 287 ZIPs, the same five LA spatial folds, the same models, settings,
seed, preprocessing and metrics, all imported from run_feature_comparison.py.

Runs (3 variants x 2 configurations x 3 models x 5 folds = 90 fits)
  as_published   UCLA 2020 population for density and weight (reproduces the main run)
  density2010    pop_density_per_sqmi = POP10 / land area; weight unchanged
  both2010       same density, and the Poisson weight = POP10

Land area is aland_sqmi from the statewide table (2023 Gazetteer), the same area used for
the published density. A ZIP with no POP10 gets a missing density (median-imputed inside
each training fold) and keeps its UCLA weight; a ZIP with POP10 = 0 gets density 0 and
keeps its UCLA weight.

Needs data/raw/Gaz_zcta_national.txt
(https://www2.census.gov/geo/docs/maps-data/data/gazetteer/Gaz_zcta_national.zip).

Writes part2/results/population_year_check/: metrics_all_287.csv, predictions_oof.csv,
run_manifest.json. The main run's inputs and outputs are not modified.

Run:  python part2/run_population_year_check.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from run_feature_comparison import SEED, build_model, metrics  # noqa: E402

OUT = ROOT / 'results/population_year_check'
GAZ = ROOT.parent / 'data/raw/Gaz_zcta_national.txt'
STATEWIDE = ROOT.parent / 'results/member1/inputs/model_table_ca_ces40_fixed.csv'
NAMES = ['poisson', 'random_forest', 'gradient_boosting']
VARIANTS = ['as_published', 'density2010', 'both2010']


def load():
    cfg = json.loads((ROOT / 'experiment_config.json').read_text())
    tables = {c: pd.read_csv(ROOT / f'data/la_{c}.csv', dtype={'zip': str}).sort_values('zip').reset_index(drop=True)
              for c in ['base', 'augmented']}
    pd.testing.assert_frame_equal(tables['base'], tables['augmented'][tables['base'].columns])
    base = tables['base']
    gaz = pd.read_csv(GAZ, sep='\t', dtype={'GEOID': str})
    gaz.columns = gaz.columns.str.strip()
    pop10 = base.zip.map(gaz.set_index('GEOID')['POP10'].astype(float)).to_numpy()
    st = pd.read_csv(STATEWIDE, dtype={'zip': str}).drop_duplicates('zip').set_index('zip')
    aland = st.loc[base.zip, 'aland_sqmi'].to_numpy(float)
    # the published density is UCLA population / this land area
    np.testing.assert_allclose(base.pop_density_per_sqmi, (base.population / aland).round(2), rtol=0, atol=0.011)
    return cfg, tables, pop10, aland


def oof_predict(X, y, folds, pop, name):
    pred = np.full(len(y), np.nan)
    n_conv = 0
    for fold in np.unique(folds):
        tr, te = folds != fold, folds == fold
        model = build_model(name)
        kwargs = {'model__sample_weight': pop[tr]} if name == 'poisson' else {}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            model.fit(X.loc[tr], y[tr], **kwargs)
        n_conv += sum('Convergence' in w.category.__name__ for w in caught)
        pred[te] = model.predict(X.loc[te])
    assert np.isfinite(pred).all()
    return pred, n_conv


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cfg, tables, pop10, aland = load()
    base = tables['base']
    folds, zips = base.group.to_numpy(), base.zip.to_numpy()
    y = base[cfg['target']].to_numpy(float)
    pop20 = base.population.to_numpy(float)
    dens10 = np.round(pop10 / aland, 2)                       # NaN where POP10 is missing
    use10 = np.isfinite(pop10) & (pop10 > 0)
    weights = {'as_published': pop20, 'density2010': pop20, 'both2010': np.where(use10, pop10, pop20)}
    preds = base[['zip', 'group', 'population']].copy()
    preds['pop10'], preds['y_true'] = pop10, y
    rows, conv = [], 0
    for variant in VARIANTS:
        for config in ['base', 'augmented']:
            X = tables[config][cfg[f'{config}_features']].copy()
            if variant != 'as_published':
                X['pop_density_per_sqmi'] = dens10
            for name in NAMES:
                p, c = oof_predict(X, y, folds, weights[variant], name)
                conv += c
                preds[f'pred_{variant}_{name}_{config}'] = p
                rows.append({'variant': variant, 'config': config, 'model': name, **metrics(y, p, zips)})
                print(f'{variant:13s} {config:9s} {name:17s} rho={rows[-1]["spearman"]:.3f} r2={rows[-1]["r2"]:.3f}', flush=True)
    if conv:
        raise RuntimeError(f'{conv} convergence warnings')
    m = pd.DataFrame(rows)
    m.to_csv(OUT / 'metrics_all_287.csv', index=False)
    preds.to_csv(OUT / 'predictions_oof.csv', index=False)
    main_metrics = pd.read_csv(ROOT / 'results/feature_comparison/metrics_all_287.csv')
    repro = {}
    for r in rows:
        if r['variant'] == 'as_published':
            ref = main_metrics[(main_metrics.config == r['config']) & (main_metrics.model == r['model'])].iloc[0]
            repro[f"{r['config']}/{r['model']}"] = abs(ref.spearman - r['spearman'])
    (OUT / 'run_manifest.json').write_text(json.dumps({
        'seed': SEED, 'n_model_fits': 90,
        'variants': {'as_published': 'UCLA 2020 population for density and Poisson weight',
                     'density2010': 'density = POP10 / aland_sqmi; Poisson weight = UCLA 2020 population',
                     'both2010': 'density = POP10 / aland_sqmi; Poisson weight = POP10'},
        'pop10_source': 'Census 2010 Gazetteer ZCTA file (Gaz_zcta_national.txt)',
        'land_area_source': 'aland_sqmi in results/member1/inputs/model_table_ca_ces40_fixed.csv (2023 Gazetteer)',
        'zips': int(len(base)), 'pop10_missing': zips[~np.isfinite(pop10)].tolist(),
        'pop10_zero': zips[pop10 == 0].tolist(),
        'missing_pop10_rule': 'density missing (median-imputed in each training fold); UCLA weight kept',
        'zero_pop10_rule': 'density 0; UCLA weight kept',
        'folds': 'part2/data/la_base.csv group column (unchanged)',
        'as_published_rerun_max_abs_spearman_diff_vs_main_run': max(repro.values()),
        'note': 'Poisson reproduces the main run exactly; random forest and gradient boosting can '
                'differ slightly across operating systems.'}, indent=2))
    print('max |rho - main run| for the as-published rerun:', round(max(repro.values()), 4))


if __name__ == '__main__':
    main()
