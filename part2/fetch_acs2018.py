"""Fetch the four historical ACS features. Never replace outputs with HTML/error responses."""
import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import pandas as pd

ROOT=Path(__file__).resolve().parent
DEST=ROOT/'sources/acs2018_values'
FIELDS={
 'detail':['NAME','B25003_001E','B25003_003E','B25044_001E','B25044_003E','B25044_010E','C24050_001E','C24050_003E'],
 'subject':['NAME','S2701_C05_001E']}

def api_key():
    key=os.environ.get('CENSUS_API_KEY')
    if not key and os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as env:
                key=winreg.QueryValueEx(env,'CENSUS_API_KEY')[0]
        except OSError:
            pass
    return key

def fetch(name):
    endpoint='https://api.census.gov/data/2018/acs/acs5'+('/subject' if name=='subject' else '')
    params={'get':','.join(FIELDS[name]),'for':'zip code tabulation area:*'}
    key=api_key()
    if key: params['key']=key
    try:
        req=urllib.request.Request(endpoint+'?'+urllib.parse.urlencode(params),headers={'User-Agent':'HEATLA academic feature audit'})
        with urllib.request.urlopen(req,timeout=15) as response:
            content=response.read().decode('utf-8')
            response_path=urllib.parse.urlsplit(response.geturl()).path
        try: data=json.loads(content)
        except json.JSONDecodeError: data=None
        if not isinstance(data,list) or len(data)<2:
            return name,None,{'status':'non_data_response','mentions_key_requirement':'key' in content.lower(),
                              'response_path':response_path,
                              'mentions_activation':'activat' in content.lower(),
                              'mentions_invalid_key':'invalid' in content.lower() and 'key' in content.lower(),
                              'endpoint':endpoint}
        frame=pd.DataFrame(data[1:],columns=data[0])
        if any(c not in frame for c in FIELDS[name]+['zip code tabulation area']):
            return name,None,{'status':'unexpected_schema','endpoint':endpoint}
        (DEST/f'{name}_raw.json').write_text(json.dumps(data),encoding='utf-8')
        return name,frame,{'status':'retrieved','rows':len(frame),'endpoint':endpoint}
    except Exception as exc:
        # Never log a request URL or exception message: it may contain a key.
        return name,None,{'status':'request_failed','error_type':type(exc).__name__,'http_status':getattr(exc,'code',None),'endpoint':endpoint}

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    status={'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'api_key_available':bool(api_key()),'reference_period':'2014-2018','checks':{}}
    frames={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for name,frame,result in pool.map(fetch,FIELDS):
            status['checks'][name]=result
            if frame is not None: frames[name]=frame
    if len(frames)==2:
        a=frames['detail'].merge(frames['subject'],on='zip code tabulation area',validate='one_to_one',suffixes=('','_subject'))
        for field in FIELDS['detail'][1:]+FIELDS['subject'][1:]:
            a[field]=pd.to_numeric(a[field],errors='coerce').where(lambda s:s>=0)
        a['zip']=a['zip code tabulation area'].str.zfill(5)
        def percentage(numerator,denominator):
            return (100*numerator/denominator.where(denominator>0)).where(lambda s:s.between(0,100))
        a['pct_renters']=percentage(a.B25003_003E,a.B25003_001E)
        a['pct_no_vehicle']=percentage(a.B25044_003E+a.B25044_010E,a.B25044_001E)
        a['pct_uninsured']=a.S2701_C05_001E.where(a.S2701_C05_001E.between(0,100))
        a['pct_construction']=percentage(a.C24050_003E,a.C24050_001E)
        wanted=pd.read_csv(ROOT/'data/fold_assignments.csv',dtype={'zip':str})[['zip']]
        columns=['zip','pct_renters','pct_no_vehicle','pct_uninsured','pct_construction']
        joined=wanted.merge(a[columns],on='zip',how='left',validate='one_to_one',indicator=True)
        status['same_code_matches']=int(joined['_merge'].eq('both').sum())
        status['unmatched_codes']=joined.loc[joined['_merge'].eq('left_only'),'zip'].tolist()
        status['missing_by_feature']=joined[columns[1:]].isna().sum().to_dict()
        joined[columns].to_csv(ROOT/'data/features_acs2018.csv',index=False)
        status['status']='values_downloaded_geographic_alignment_review_pending'
        status['geographic_note']='2018 uses 2010 ZCTAs; same code does not establish equal boundaries with 2020 ZCTAs.'
    else:
        status['status']='blocked_on_official_data_access_no_historical_replacement_performed'
    (DEST/'status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    print(json.dumps(status,indent=2))

if __name__=='__main__': main()
