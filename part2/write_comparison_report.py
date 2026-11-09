"""Build an English report and explicit website handoff files from completed runs."""
from pathlib import Path
import json
import pandas as pd

R=Path(__file__).resolve().parent
O=R/'results/feature_comparison'
m=pd.read_csv(O/'metrics_all_287.csv');d=pd.read_csv(O/'augmented_minus_base.csv')
fold=pd.read_csv(O/'metrics_per_fold.csv');matched=pd.read_csv(O/'metrics_CES_matched_273.csv')
run=json.loads((O/'run_manifest.json').read_text());cfg=run['settings']
pred=pd.read_csv(O/'predictions_oof.csv',dtype={'zip':str})
manifest=json.loads((R/'input_manifest.json').read_text())
rationale=(R/'FEATURE_SELECTION_RATIONALE.md').read_text(encoding='utf-8')
setup=(R/'EXPERIMENTAL_SETUP_TABLE.md').read_text(encoding='utf-8')
captions=(R/'FIGURE_CAPTIONS.md').read_text(encoding='utf-8')
feature_table=pd.read_csv(R/'results/unified_feature_comparison.csv')
feature_membership=feature_table[['field','base_included','original_la_included','augmented_included']].copy()
for col in ['base_included','original_la_included','augmented_included']:
    feature_membership[col]=feature_membership[col].map({True:'Yes',False:'—'})
feature_membership=feature_membership.rename(columns={'field':'Feature field','base_included':'Base (11)',
                                                     'original_la_included':'Original LA (13)','augmented_included':'Augmented (15)'})

def table(df,cols):
    def fmt(x):
        if pd.isna(x):return '—'
        if isinstance(x,float):return f'{x:.3f}'
        return str(x)
    return '| '+' | '.join(cols)+' |\n|'+'|'.join(['---']*len(cols))+'|\n'+'\n'.join('| '+' | '.join(fmt(row[c]) for c in cols)+' |' for _,row in df.iterrows())

mae_folds=[]
for name in d.model:
    a=fold[(fold.model==name)&(fold.config=='augmented')].set_index('group')
    b=fold[(fold.model==name)&(fold.config=='base')].set_index('group')
    mae_folds.append({'model':name,'folds_with_lower_MAE':int((a.mae<b.mae).sum()),
                      'folds_with_higher_R2':int((a.r2>b.r2).sum())})
counts=pred.groupby('group').size()
ci=[]
for model,values in run['paired_delta_intervals'].items():
    for metric,bounds in values.items():
        ci.append({'model':model,'metric':metric,'lower':bounds[0],'upper':bounds[1]})
ci=pd.DataFrame(ci)
ci.to_csv(O/'paired_delta_exploratory_intervals.csv',index=False)
if (d.delta_r2>0).all() and (d.delta_mae<0).all():
    finding='All three algorithms improve pooled out-of-fold R² and MAE when the four ACS features are added.'
elif (d.delta_r2<=0).all() and (d.delta_mae>=0).all():
    finding='The added features do not improve pooled out-of-fold R² or MAE for any of the three algorithms in this experiment.'
else:
    finding='The effect of adding the four ACS features depends on the algorithm and metric; the evidence does not support a uniform improvement claim.'
pb=m[(m.config=='base')&(m.model=='poisson')].iloc[0]
pa=m[(m.config=='augmented')&(m.model=='poisson')].iloc[0]
detail=(f'For Poisson, pooled R² changes from {pb.r2:.3f} to {pa.r2:.3f}, Spearman from {pb.spearman:.3f} to {pa.spearman:.3f}, '
        f'and MAE from {pb.mae:.3f} to {pa.mae:.3f}. Its MAE improves in '
        f'{next(x["folds_with_lower_MAE"] for x in mae_folds if x["model"]=="poisson")} of five held-out groups. '
        f'Its top-10% recall changes from {pb.top10_recall:.3f} to {pa.top10_recall:.3f} '
        f'({round(pa.top10_recall*pa.top10_k)} of {int(pa.top10_k)} ZIPs after augmentation). '
        'Changes in top-k recovery can differ from overall error improvements; better fit should not be presented as uniformly better identification of the highest-burden ZIPs.')

report=f'''# Part 2 — LA feature comparison

## Research question and result

Do four additional historical ACS community indicators improve estimation of UCLA's published category-4 excess ER label, beyond the common statewide feature set, within Los Angeles County?

{finding} Ranking and high-burden recovery are evaluated separately below. These are spatial generalization results for a historical model-derived label, not forecasts of future daily ER visits or estimates of the causal benefit of cooling centers.

{detail}

## Data and controlled comparison

- Target: unchanged UCLA category-4 estimated excess ER visits per 10,000 residents, labelled 2008–2018. Its cumulative interpretation is pending confirmation; no L4−L3 replacement is used in this main run. The level-4-only (L4−L3) target and a run without the asthma and cardiovascular inputs are in [FOLLOWUP_EXPERIMENTS.md](FOLLOWUP_EXPERIMENTS.md).
- Sample: all 287 original LA ZIPs. The same ZIPs and original five geographic groups are used in both configurations. Fold sizes: {', '.join(f'{g}: {n}' for g,n in counts.items())}.
- Base: 11 features from Member 1's corrected CES 4.0 statewide table, with heat level omitted because it is constant. Features: {', '.join(cfg['base_features'])}.
- Augmented: the same base values plus renters, no-vehicle households, uninsured population and construction-industry employment percentages from ACS 2018 five-year estimates (2014–2018).
- Total population and median household income are not predictors. Population remains the sample weight for Poisson fitting.
- {manifest['n_complete_base']} ZIPs have complete base inputs and {manifest['n_complete_augmented']} have complete augmented inputs. Missingness does not change the evaluation sample.

{setup}

## Unified feature comparison

{table(feature_membership,list(feature_membership.columns))}

The complete row-by-row definitions, units, raw fields, data sources and reference periods are supplied in [Unified Feature Comparison](FEATURE_COMPARISON_TABLE.md) and results/unified_feature_comparison.csv. The original LA model is shown for provenance; the controlled experiment compares only the new base and augmented configurations.

Identical field names do not guarantee identical source values. In particular, the original LA density uses ACS 2022 population, while the new base/augmented density uses UCLA population. CES poverty uses twice the federal poverty threshold; the old ACS poverty feature uses the threshold itself. The new pair preserves identical values and sources for all 11 common predictors. The CES age-field reference year and UCLA population reference year remain explicitly unconfirmed shared items.

{rationale}

## Method

The fixed algorithms and hyperparameters match the audited project: PoissonRegressor(alpha=1, max_iter=5000), RandomForestRegressor(n_estimators=500, min_samples_leaf=2, n_jobs=1), and default GradientBoostingRegressor. Random seeds are 42. No hyperparameters were selected using the held-out folds.

For each of five folds, training uses the other four geographic groups. Median imputation is fitted only on training rows; standardization is also fitted only on training rows for Poisson. Only Poisson uses training population weights. Evaluation weights each ZIP equally. Each model/configuration therefore produces one genuinely held-out prediction for every ZIP. There are 30 fitted fold models.

Top-k recall uses k = round(fraction × sample size): 29 for top 10% and 57 for top 20% on the full sample. Both true and predicted rankings break score ties by ascending ZIP. This deterministic convention can differ from the old project's unspecified NumPy tie order; close recall differences should not be overstated.

## Results on all 287 ZIPs

{table(m,['config','model','r2','rmse','mae','spearman','top10_recall','top20_recall'])}

The mean reference predicts the mean label of the training folds, never the full sample mean. Ranking scores are omitted because this is not an intended ZIP-risk ranking method.

## Added-feature change (augmented minus base)

{table(d,['model','delta_r2','delta_rmse','delta_mae','delta_spearman','delta_top10_recall','delta_top20_recall'])}

Positive R², Spearman and recall changes indicate improvement; negative RMSE and MAE changes indicate improvement. A top-10% recall change of 1/29 (about 0.0345) is one ZIP, so seemingly visible percentage changes may represent few ZIPs.

{table(pd.DataFrame(mae_folds),['model','folds_with_lower_MAE','folds_with_higher_R2'])}

Fold results are available in metrics_per_fold.csv. Pooled OOF R² is not the arithmetic mean of fold R². The five group sizes differ substantially, including a 12-ZIP fold, which limits precise interpretation of regional differences.

## CES ranking reference: matched sample only

{table(matched,['config','model','n','r2','spearman','top10_recall','top20_recall'])}

This table restricts every predictor to the identical 273 ZIPs with a corrected CES percentile. CES is a ranking index, so it has no R², RMSE or MAE against the ER-rate target. Do not compare its correlation to a model score from all 287 ZIPs as if those were matched.

## Exploratory paired uncertainty

{table(ci,['model','metric','lower','upper'])}

These 95% percentile intervals summarize augmented-minus-base differences from 1,000 paired resamples of the five geographic blocks, with OOF predictions held fixed. Only five blocks are available; models are not refitted in these resamples and upstream UCLA estimation uncertainty is not represented. The intervals are exploratory and are not a definitive significance or equivalence test.

{captions}

## Interpretation and limits

This controlled feature-set comparison asks whether the four indicators jointly improve held-out prediction. It does not estimate each indicator's causal effect or prove that cooling centers change those indicators. Correlated indicators may substitute for one another. A joint benefit does not imply that every added feature is individually useful.

ACS 2018 represents 2014–2018, not the entire target period. Historical matching is by unchanged ZIP code: 285 codes match and two (90639, 90840) have no 2010 ZCTA record. Other suppressed/undefined cells are also missing and handled only within training folds. No 2022 values or zero placeholders are substituted.

A possible supplementary experiment would use UCLA's official 2014–2018 label version for a matched-period comparison; this has not been performed and would require the team to adopt the same alternative target and rerun the affected experiments.

The official 2010/2020 ZCTA comparison documents boundary differences. It does not establish a known mismatch for every project feature, and does not independently verify UCLA's geometry vintage. Land overlap is not population equivalence. No geographic harmonization is claimed, no ZIPs are excluded by the exploratory overlap flag, and a high-overlap subset experiment is not part of this primary analysis.

The CES inputs have mixed reference periods and their tract-to-ZIP aggregation is approximate. Asthma and cardiovascular indicators are retained in both configurations; a no-health-indicator ablation is not conducted here. Source overlap with the UCLA label is a limitation to assess, not automatic proof of data leakage. The selected supporting literature motivates the added feature categories; Scott et al. remains verified at abstract level only.

These results are not directly attributable to training geography when compared with Part 1: Part 1 uses a different geographic evaluation design. They also should not be compared uncritically to the old 13-feature LA model, which used different input definitions and sources.

## Reproducibility and handoff

Run run_feature_comparison.py, make_comparison_figures.py and write_comparison_report.py with the Part 2 virtual environment. requirements-models.txt pins the principal packages; results/feature_comparison/environment_freeze.txt records all installed versions. run_manifest.json records input/script hashes, settings, preprocessing checks, runtime versions and warnings.

Website handoff: website_exports/predictions_oof_base.csv and predictions_oof_augmented.csv use the original ZIP/group/y_true/pred_* column convention, with corresponding errors. website_exports/metadata.json identifies each configuration. These are new handoff files, not updates to the repository's old predictions or live website. Member 3 must explicitly choose and import the final configuration.
'''
(R/'PART2_MODEL_COMPARISON_REPORT.md').write_text(report,encoding='utf-8')
export=O/'website_exports';export.mkdir(exist_ok=True)
for config in ['base','augmented']:
    cols=['zip','group','y_true']+[f'{prefix}_{name}_{config}' for prefix in ['pred','error'] for name in ['poisson','random_forest','gradient_boosting']]
    data=pred[cols].rename(columns={c:c.removesuffix(f'_{config}') for c in cols if c.endswith(f'_{config}')})
    data.to_csv(export/f'predictions_oof_{config}.csv',index=False)
(export/'metadata.json').write_text(json.dumps({'versions':{
    c:{'file':f'predictions_oof_{c}.csv','features':cfg[f'{c}_features']} for c in ['base','augmented']},
    'target':cfg['target_interpretation'],'period':'2008-2018','ACS_period':'2014-2018',
    'evaluation':'LA-only original 5 spatial folds, OOF, 287 ZIPs','error':'prediction minus UCLA label',
    'run_manifest':'../run_manifest.json'},indent=2),encoding='utf-8')
print('Wrote English report and two explicit website handoff files.')
