"""Independent numerical and provenance checks on saved OOF deliverables."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

R=Path(__file__).resolve().parent;O=R/'results/feature_comparison'
p=pd.read_csv(O/'predictions_oof.csv',dtype={'zip':str})
base=pd.read_csv(R/'data/la_base.csv',dtype={'zip':str}).sort_values('zip').reset_index(drop=True)
assert len(p)==287 and p.zip.is_unique
assert (p.zip==base.zip).all() and (p.group==base.group).all()
np.testing.assert_allclose(p.y_true,base.excess_er_rate_per_10k)
run=json.loads((O/'run_manifest.json').read_text())
for path,digest in run['input_sha256'].items():
    assert hashlib.sha256((R/path).read_bytes()).hexdigest()==digest
assert run['n_model_fits']==30 and not run['warnings']
checked=0
for filename,restricted in [('metrics_all_287.csv',False),('metrics_CES_matched_273.csv',True)]:
    m=pd.read_csv(O/filename)
    q=p[p.ces4_percentile.notna()] if restricted else p
    for row in m.itertuples():
        if row.model=='CES_percentile': pred=q.ces4_percentile.to_numpy()
        elif row.model=='training_fold_mean':pred=q.pred_training_fold_mean.to_numpy()
        else:pred=q[f'pred_{row.model}_{row.config}'].to_numpy()
        y=q.y_true.to_numpy();err=pred-y
        expected={'r2':1-np.dot(err,err)/np.dot(y-y.mean(),y-y.mean()),'rmse':np.sqrt(np.mean(err**2)),
                  'mae':np.mean(np.abs(err)),'spearman':spearmanr(y,pred).statistic}
        for metric,value in expected.items():
            if hasattr(row,metric) and pd.notna(getattr(row,metric)):
                np.testing.assert_allclose(value,getattr(row,metric),rtol=0,atol=1e-10);checked+=1
        for frac,metric in [(.1,'top10_recall'),(.2,'top20_recall')]:
            if pd.isna(getattr(row,metric)):continue
            k=max(1,round(frac*len(q)))
            rank=pd.DataFrame({'zip':q.zip.to_numpy(),'true':y,'pred':pred})
            true=set(rank.sort_values(['true','zip'],ascending=[False,True]).head(k).zip)
            guessed=set(rank.sort_values(['pred','zip'],ascending=[False,True]).head(k).zip)
            np.testing.assert_allclose(len(true&guessed)/k,getattr(row,metric),rtol=0,atol=1e-12);checked+=1
for group in p.group.unique():
    np.testing.assert_allclose(p.loc[p.group==group,'pred_training_fold_mean'],p.loc[p.group!=group,'y_true'].mean())
for config in ['base','augmented']:
    for model in ['poisson','random_forest','gradient_boosting']:
        np.testing.assert_allclose(p[f'error_{model}_{config}'],p[f'pred_{model}_{config}']-p.y_true)
result={'status':'passed','n_zip_rows':len(p),'n_prediction_columns':6,'metric_values_independently_checked':checked,
        'checks':['saved-input/script hashes','original ZIP/fold/target alignment','six model error identities',
                  'NumPy/scipy metric recomputation','independent pandas stable top-k ranking',
                  'training-only mean baseline','no recorded training warnings'],
        'note':'Training-time checks also verify imputation medians and scaling means against training rows only.'}
(O/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
