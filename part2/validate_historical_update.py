"""Cross-check the final paired inputs, year replacement and documented missingness."""
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd

R=Path(__file__).resolve().parent
base=pd.read_csv(R/'data/la_base.csv',dtype={'zip':str}).set_index('zip').sort_index()
new=pd.read_csv(R/'data/la_augmented.csv',dtype={'zip':str}).set_index('zip').sort_index()
old=pd.read_csv(R/'data/la_augmented_acs2022_provisional.csv',dtype={'zip':str}).set_index('zip').sort_index()
historical=pd.read_csv(R/'data/features_acs2018.csv',dtype={'zip':str}).set_index('zip').sort_index()
cfg=json.loads((R/'experiment_config.json').read_text())
assert cfg['acs_vintage']=='2018'
pd.testing.assert_frame_equal(base,new[base.columns])
pd.testing.assert_frame_equal(base,old[base.columns])
stats={}
for c in cfg['extra_features']:
    np.testing.assert_allclose(new[c],historical.loc[new.index,c],equal_nan=True)
    assert new[c].dropna().between(0,100).all()
    stats[c]={'missing_2018':int(new[c].isna().sum()),'missing_2022':int(old[c].isna().sum()),
              'mean_2018':float(new[c].mean()),'mean_2022':float(old[c].mean()),
              'missing_zip_codes':new.index[new[c].isna()].tolist()}
geo=json.loads((R/'results/acs2018_geography_summary.json').read_text())
report={'status':'historical_same_code_features_prepared_not_geographically_harmonized',
        'n_zips':len(new),'n_base_features':len(cfg['base_features']),'n_augmented_features':len(cfg['augmented_features']),
        'n_folds':int(new.group.nunique()),'labels_and_base_values_unchanged':True,
        'acs_reference_period':'2014-2018','feature_summary':stats,
        'geography_review':{'same_code_pairs':geo['same_code_pair_in_official_relationship_file'],
                            'mutual_land_overlap_at_least_95pct':geo['mutual_land_overlap_at_least_95pct'],
                            'review_flags_not_row_exclusions':len(geo['flagged_zips'])},
        'input_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'data/la_base.csv',R/'data/la_augmented.csv',R/'data/features_acs2018.csv']},
        'missing_value_policy':'No 2022 fallback, no zero filling; future median imputation inside training folds only.',
        'training_status':'No prediction models trained in this data replacement step.'}
(R/'results/historical_update_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ['feature_summary','input_hashes']},indent=2))
