"""Part 2 follow-up: the LA-only comparison on the level-4-only target and without the
asthma and heart-attack ER-rate inputs.

Part 1 found that (a) UCLA's level-4 label totals all heat levels, so the excess on
level-4 days alone is label(4) - label(3), and (b) much of the level-4 skill rests on two
inputs drawn from the same ER records as the label. This repeats Part 2's controlled
base-versus-augmented comparison under both changes. Everything else is unchanged:
the same 287 ZIPs, the same five LA spatial folds, the same models, settings, seed,
preprocessing and metrics, all imported from run_feature_comparison.py.

Runs (4 variants x 2 configurations x 3 models x 5 folds = 120 fits)
  cumulative          published level-4 label, all inputs (reproduces the main run)
  level4_only         target = label(4) - label(3), all inputs
  cumulative_no_ed    published label, without asthma_ed_per10k, cardiovascular_ed_per10k
  level4_only_no_ed   both changes

Level-4-only values come from Member 1's table (results/member1/inputs/
model_table_ca_ces40_fixed_level_only.csv), Los Angeles rows at heat level 4.

Writes part2/results/followup/: metrics_all_287.csv, metrics_CES_matched_273.csv,
augmented_minus_base.csv, paired_delta_exploratory_intervals.csv, predictions_oof.csv,
run_manifest.json. The main run's outputs are not modified.

Run:  python part2/run_followup_experiments.py
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
from run_feature_comparison import SEED, build_model, delta_ci, metrics  # noqa: E402

OUT = ROOT / 'results/followup'
LEVEL_ONLY = ROOT.parent / 'results/member1/inputs/model_table_ca_ces40_fixed_level_only.csv'
ED = ['asthma_ed_per10k', 'cardiovascular_ed_per10k']
NAMES = ['poisson', 'random_forest', 'gradient_boosting']
VARIANTS = {'cumulative': ('cumulative', False), 'level4_only': ('level4_only', False),
            'cumulative_no_ed': ('cumulative', True), 'level4_only_no_ed': ('level4_only', True)}


def load():
    cfg = json.loads((ROOT / 'experiment_config.json').read_text())
    tables = {c: pd.read_csv(ROOT / f'data/la_{c}.csv', dtype={'zip': str}).sort_values('zip').reset_index(drop=True)
              for c in ['base', 'augmented']}
    pd.testing.assert_frame_equal(tables['base'], tables['augmented'][tables['base'].columns])
    lo = pd.read_csv(LEVEL_ONLY, dtype={'zip': str})
    lo = lo[(lo.county == 'Los Angeles') & (lo.chs_level == 4)].set_index('zip')
    base = tables['base']
    assert base.zip.isin(lo.index).all()
    np.testing.assert_allclose(lo.loc[base.zip, 'excess_er_rate_per_10k_cumulative'],
                               base[cfg['target']], rtol=0, atol=1e-9)
    targets = {'cumulative': base[cfg['target']].to_numpy(float),
               'level4_only': lo.loc[base.zip, 'excess_er_rate_per_10k'].to_numpy(float)}
    assert (targets['level4_only'] >= 0).all()
    return cfg, tables, targets


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
    cfg, tables, targets = load()
    base = tables['base']
    folds, zips = base.group.to_numpy(), base.zip.to_numpy()
    pop = base.population.to_numpy(float)
    mask = base.ces4_percentile.notna().to_numpy()
    preds = base[['zip', 'group', 'population', 'ces4_percentile']].copy()
    preds['y_cumulative'], preds['y_level4_only'] = targets['cumulative'], targets['level4_only']
    rows, matched, deltas, intervals, conv = [], [], [], {}, 0
    for variant, (target, drop_ed) in VARIANTS.items():
        y = targets[target]
        for config in ['base', 'augmented']:
            feats = [f for f in cfg[f'{config}_features'] if not (drop_ed and f in ED)]
            for name in NAMES:
                p, c = oof_predict(tables[config][feats], y, folds, pop, name)
                conv += c
                col = f'pred_{variant}_{name}_{config}'
                preds[col] = p
                rows.append({'variant': variant, 'target': target, 'ed_inputs': not drop_ed,
                             'config': config, 'n_features': len(feats), 'model': name, **metrics(y, p, zips)})
                matched.append({'variant': variant, 'config': config, 'model': name,
                                **metrics(y[mask], p[mask], zips[mask])})
                print(f'{variant:18s} {config:9s} {name:17s} rho={rows[-1]["spearman"]:.3f} r2={rows[-1]["r2"]:.3f}', flush=True)
        ces = metrics(y[mask], base.ces4_percentile.to_numpy(float)[mask], zips[mask])
        for k in ['r2', 'rmse', 'mae']:
            ces[k] = None
        matched.append({'variant': variant, 'config': 'reference', 'model': 'CES_percentile', **ces})
        mean_pred = np.array([y[folds != g].mean() for g in folds])
        mm = metrics(y, mean_pred, zips)
        for k in ['spearman', 'top10_recall', 'top20_recall', 'top10_k']:
            mm[k] = None
        rows.append({'variant': variant, 'target': target, 'ed_inputs': not drop_ed, 'config': 'reference',
                     'n_features': 0, 'model': 'training_fold_mean', **mm})
        for name in NAMES:
            b = preds[f'pred_{variant}_{name}_base'].to_numpy()
            a = preds[f'pred_{variant}_{name}_augmented'].to_numpy()
            bm, am = metrics(y, b, zips), metrics(y, a, zips)
            deltas.append({'variant': variant, 'model': name,
                           **{f'delta_{k}': am[k] - bm[k] for k in ['r2', 'rmse', 'mae', 'spearman', 'top10_recall', 'top20_recall']}})
            intervals[f'{variant}/{name}'] = delta_ci(y, b, a, folds)
    if conv:
        raise RuntimeError(f'{conv} convergence warnings')
    pd.DataFrame(rows).to_csv(OUT / 'metrics_all_287.csv', index=False)
    pd.DataFrame(matched).to_csv(OUT / 'metrics_CES_matched_273.csv', index=False)
    pd.DataFrame(deltas).to_csv(OUT / 'augmented_minus_base.csv', index=False)
    pd.DataFrame([{'variant_model': k, 'metric': m, 'lower': v[0], 'upper': v[1]}
                  for k, d in intervals.items() for m, v in d.items()]).to_csv(
        OUT / 'paired_delta_exploratory_intervals.csv', index=False)
    preds.to_csv(OUT / 'predictions_oof.csv', index=False)
    main_metrics = pd.read_csv(ROOT / 'results/feature_comparison/metrics_all_287.csv')
    repro = {}
    for r in rows:
        if r['variant'] == 'cumulative' and r['config'] != 'reference':
            ref = main_metrics[(main_metrics.config == r['config']) & (main_metrics.model == r['model'])].iloc[0]
            repro[f"{r['config']}/{r['model']}"] = abs(ref.spearman - r['spearman'])
    (OUT / 'run_manifest.json').write_text(json.dumps({
        'seed': SEED, 'n_model_fits': 120, 'variants': {k: {'target': t, 'ed_inputs_dropped': ED if d else []}
                                                         for k, (t, d) in VARIANTS.items()},
        'level4_only_source': 'results/member1/inputs/model_table_ca_ces40_fixed_level_only.csv',
        'folds': 'part2/data/la_base.csv group column (unchanged)',
        'cumulative_rerun_max_abs_spearman_diff_vs_main_run': max(repro.values()),
        'note': 'Poisson reproduces the main run exactly; random forest and gradient boosting can '
                'differ slightly across operating systems.'}, indent=2))
    print('max |rho - main run| for the cumulative rerun:', round(max(repro.values()), 4))


if __name__ == '__main__':
    main()
