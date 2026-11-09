"""Matched LA spatial OOF comparison: corrected CES base versus base + ACS 2018.

No feature selection or hyperparameter tuning on the held-out ZIPs. No changes to
the repository, original predictions, website or siting outputs.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name]='1'
import datetime as dt
import hashlib
import importlib.metadata
import json
import platform
import time
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/feature_comparison'
SEED=42

def build_model(name):
    # Identical settings and preprocessing to the audited project's make_models().
    steps=[('impute',SimpleImputer(strategy='median'))]
    if name=='poisson':
        steps += [('scale',StandardScaler()),('model',PoissonRegressor(alpha=1.0,max_iter=5000))]
    elif name=='random_forest':
        steps += [('model',RandomForestRegressor(n_estimators=500,min_samples_leaf=2,n_jobs=1,random_state=SEED))]
    else:
        steps += [('model',GradientBoostingRegressor(random_state=SEED))]
    return Pipeline(steps)

def rank_recall(y,p,zips,frac):
    k=max(1,round(len(y)*frac))
    a=np.lexsort((np.asarray(zips),-np.asarray(y)))[:k]
    b=np.lexsort((np.asarray(zips),-np.asarray(p)))[:k]
    return len(set(a)&set(b))/k

def metrics(y,p,zips):
    y,p=np.asarray(y,float),np.asarray(p,float)
    return {'n':len(y),'r2':float(r2_score(y,p)),
            'rmse':float(np.sqrt(mean_squared_error(y,p))),
            'mae':float(mean_absolute_error(y,p)),
            'spearman':float(pd.Series(y).rank().corr(pd.Series(p).rank())),
            'top10_recall':rank_recall(y,p,zips,.1),
            'top20_recall':rank_recall(y,p,zips,.2),
            'top10_k':max(1,round(.1*len(y)))}

def delta_ci(y,b,a,groups,n_boot=1000):
    """Paired resampling of the five geographic blocks, with predictions held fixed.

    Exploratory intervals only: five clusters, no repeated model training and no
    characterization of upstream UCLA label estimation uncertainty.
    """
    rng=np.random.default_rng(SEED)
    folds=np.unique(groups)
    indices={g:np.flatnonzero(groups==g) for g in folds}
    draws={k:[] for k in ['r2','mae','spearman']}
    for _ in range(n_boot):
        ix=np.concatenate([indices[g] for g in rng.choice(folds,len(folds),replace=True)])
        yy,bb,aa=y[ix],b[ix],a[ix]
        draws['r2'].append(r2_score(yy,aa)-r2_score(yy,bb))
        draws['mae'].append(mean_absolute_error(yy,aa)-mean_absolute_error(yy,bb))
        draws['spearman'].append(pd.Series(yy).rank().corr(pd.Series(aa).rank())-
                                  pd.Series(yy).rank().corr(pd.Series(bb).rank()))
    return {k:np.nanpercentile(v,[2.5,97.5]).tolist() for k,v in draws.items()}

def main():
    started=time.perf_counter()
    OUT.mkdir(parents=True,exist_ok=True)
    cfg=json.loads((ROOT/'experiment_config.json').read_text())
    assert cfg['acs_vintage']=='2018'
    tables={c:pd.read_csv(ROOT/f'data/la_{c}.csv',dtype={'zip':str}).sort_values('zip').reset_index(drop=True)
            for c in ['base','augmented']}
    base,aug=tables['base'],tables['augmented']
    pd.testing.assert_frame_equal(base,aug[base.columns])
    assert len(base)==287 and not base.zip.duplicated().any() and base.group.nunique()==5
    assert cfg['augmented_features']==cfg['base_features']+cfg['extra_features']
    folds=base.group.to_numpy(); y=base[cfg['target']].to_numpy(float); zips=base.zip.to_numpy()
    pop=base.population.to_numpy(float)
    assert np.isfinite(y).all() and (y>=0).all() and np.isfinite(pop).all() and (pop>0).all()
    names=['poisson','random_forest','gradient_boosting']
    predictions=base[['zip','group','county','chs_level',cfg['target'],'population','lat','lon','ces4_percentile']].copy()
    predictions=predictions.rename(columns={cfg['target']:'y_true'})
    metric_rows=[]; fold_rows=[]; prep_rows=[]; warning_rows=[]
    for config,df in tables.items():
        features=cfg[f'{config}_features']
        X=df[features]
        assert not X.lt(0).any().any()
        for name in names:
            pred=np.full(len(df),np.nan); assigned=np.zeros(len(df),int)
            for fold in np.unique(folds):
                tr,te=folds!=fold,folds==fold
                assert X.loc[tr].notna().any(axis=0).all(), 'All-missing feature in training fold'
                model=build_model(name)
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always')
                    kwargs={'model__sample_weight':pop[tr]} if name=='poisson' else {}
                    model.fit(X.loc[tr],y[tr],**kwargs)
                    pred[te]=model.predict(X.loc[te])
                for warning in caught:
                    warning_rows.append({'config':config,'model':name,'fold':int(fold),
                                         'category':warning.category.__name__,'message':str(warning.message)})
                    if issubclass(warning.category,ConvergenceWarning):
                        raise RuntimeError('Unresolved convergence warning; see training configuration')
                assigned[te]+=1
                np.testing.assert_allclose(model.named_steps['impute'].statistics_,X.loc[tr].median(),rtol=0,atol=1e-10)
                for feature,value in zip(features,model.named_steps['impute'].statistics_):
                    prep_rows.append({'config':config,'model':name,'group':int(fold),'feature':feature,'training_median':float(value),
                                      'n_missing_train':int(X.loc[tr,feature].isna().sum()),'n_missing_test':int(X.loc[te,feature].isna().sum())})
                if name=='poisson':
                    transformed=model.named_steps['impute'].transform(X.loc[tr])
                    np.testing.assert_allclose(model.named_steps['scale'].mean_,transformed.mean(axis=0),rtol=1e-10,atol=1e-10)
                fold_rows.append({'config':config,'model':name,'group':int(fold),'n_train':int(tr.sum()),**metrics(y[te],pred[te],zips[te])})
                print(f'{config} / {name} / fold {fold}: {tr.sum()} train, {te.sum()} test',flush=True)
            assert (assigned==1).all() and np.isfinite(pred).all()
            predictions[f'pred_{name}_{config}']=pred
            predictions[f'error_{name}_{config}']=pred-y
            metric_rows.append({'config':config,'model':name,**metrics(y,pred,zips)})
    mean_pred=np.full(len(y),np.nan)
    for g in np.unique(folds): mean_pred[folds==g]=y[folds!=g].mean()
    predictions['pred_training_fold_mean']=mean_pred
    mean_metrics=metrics(y,mean_pred,zips)
    for k in ['spearman','top10_recall','top20_recall','top10_k']: mean_metrics[k]=None
    metric_rows.append({'config':'reference','model':'training_fold_mean',**mean_metrics})
    pd.DataFrame(metric_rows).to_csv(OUT/'metrics_all_287.csv',index=False)
    pd.DataFrame(fold_rows).to_csv(OUT/'metrics_per_fold.csv',index=False)
    pd.DataFrame(prep_rows).to_csv(OUT/'preprocessing_audit.csv',index=False)
    predictions.to_csv(OUT/'predictions_oof.csv',index=False)
    delta_rows=[]; intervals={}
    for name in names:
        b=predictions[f'pred_{name}_base'].to_numpy();a=predictions[f'pred_{name}_augmented'].to_numpy()
        bm,am=metrics(y,b,zips),metrics(y,a,zips)
        delta_rows.append({'model':name,**{f'delta_{k}':am[k]-bm[k] for k in ['r2','rmse','mae','spearman','top10_recall','top20_recall']}})
        intervals[name]=delta_ci(y,b,a,folds)
    pd.DataFrame(delta_rows).to_csv(OUT/'augmented_minus_base.csv',index=False)
    mask=base.ces4_percentile.notna().to_numpy();matched=[]
    for config in tables:
        for name in names:
            matched.append({'config':config,'model':name,**metrics(y[mask],predictions.loc[mask,f'pred_{name}_{config}'],zips[mask])})
    ces=metrics(y[mask],base.loc[mask,'ces4_percentile'],zips[mask])
    for k in ['r2','rmse','mae']: ces[k]=None
    matched.append({'config':'reference','model':'CES_percentile',**ces})
    pd.DataFrame(matched).to_csv(OUT/'metrics_CES_matched_273.csv',index=False)
    provenance={'run_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'python':platform.python_version(),
                'packages':{p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','scikit-learn','matplotlib']},
                'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                [ROOT/'data/la_base.csv',ROOT/'data/la_augmented.csv',ROOT/'experiment_config.json',Path(__file__)]},
                'settings':cfg,'n_model_fits':30,'evaluations':'LA-only 5-fold spatial OOF; not whole-LA holdout',
                'tie_rule':'descending score, ascending ZIP, identical rule for labels and predictions',
                'metrics_weighting':'Equal ZIP weights; population weights in Poisson fitting only',
                'mean_baseline':'Training-fold mean, with no ranking claim',
                'paired_delta_intervals':intervals,'interval_method':'1000 paired bootstrap draws of 5 geographic blocks, fixed OOF predictions',
                'interval_limitations':'Exploratory: only five geographic blocks; no refitting or upstream label uncertainty. Not a definitive significance test.',
                'warnings':warning_rows,'elapsed_seconds':time.perf_counter()-started}
    (OUT/'run_manifest.json').write_text(json.dumps(provenance,indent=2,allow_nan=False),encoding='utf-8')
    print(pd.DataFrame(metric_rows).to_string(index=False),flush=True)
    print(pd.DataFrame(delta_rows).to_string(index=False),flush=True)

if __name__=='__main__': main()
