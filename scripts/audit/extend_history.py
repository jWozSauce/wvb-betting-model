"""T3 approved extension: one fixture request, free history, durable checkpoints.

Run from repository root. Resume uses existing raw caches and ledger; it never
reissues a reserved fixture request. Output stays beside protected originals.
"""
import datetime as dt,fcntl,hashlib,json,os,sys,time
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import oddspapi,safe_http
from scripts.backfill_odds import trail_rows,BOOKS
OUT=ROOT/'evidence/t3-20261001/extension-1'

def atomic_json(path,obj):
 temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(obj,indent=2));temp.replace(path)

def main():
 os.environ['WVB_ENABLE_REPAIRS']='1'
 OUT.mkdir(parents=True,exist_ok=True)
 with (OUT/'job.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  ledger_path=OUT/'ledger.json'
  ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else dict(task='T3',cap=1,reserved=0,state='starting',history_calls=0)
  def save():ledger['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat();atomic_json(ledger_path,ledger)
  key=oddspapi.api_key()
  def quota():
   blob=safe_http.get(f'{oddspapi.API}/account',params={'apiKey':key},timeout=30);blob.raise_for_status();blob=blob.json()
   def walk(x):
    if isinstance(x,dict):
     if 'request_count' in x and 'request_limit' in x:return {'used':int(x['request_count']),'limit':int(x['request_limit'])}
     for v in x.values():
      result=walk(v)
      if result:return result
    elif isinstance(x,list):
     for v in x:
      result=walk(v)
      if result:return result
   result=walk(blob)
   if not result:raise RuntimeError('Account quota unavailable')
   return result
  def fetch(endpoint,params,path,billable=False):
   if path.exists():return json.loads(path.read_text())
   if billable:
    if ledger['reserved']>=ledger['cap']:raise RuntimeError('Fixture budget reserved; no retry allowed')
    ledger['reserved']+=1;save()
   else:ledger['history_calls']+=1;save()
   response=safe_http.get(f'{oddspapi.API}/{endpoint}',params={'apiKey':key,**params},timeout=60)
   status=response.status_code
   # Cache metadata even on a stop status. Never retain an echoed key.
   blob={'endpoint':endpoint,'params':params,'status':status,'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat()}
   if status in (200,404):
    payload=response.json();encoded=json.dumps(payload)
    if key and key in encoded:raise RuntimeError('Credential echo refused')
    blob['payload']=payload
   atomic_json(path,blob)
   if status not in (200,404):raise RuntimeError(f'{endpoint}: HTTP {status}; stopped without retry')
   return blob
  original=ROOT/'data/processed/odds_hist_2026.parquet'
  source_hash=hashlib.sha256(original.read_bytes()).hexdigest()
  ledger.setdefault('source_sha256',source_hash)
  assert ledger['source_sha256']==source_hash,'Source changed during extension'
  rawdir=OUT/'raw';rawdir.mkdir(exist_ok=True)
  try:
   if 'quota_before' not in ledger:ledger['quota_before']=quota();save()
   if ledger['quota_before']['used']>=ledger['quota_before']['limit']:raise RuntimeError('No quota remains')
   fixture=fetch('fixtures',{'tournamentId':oddspapi.TOURNAMENT_NCAAW,'from':'2026-08-20T04:00:00Z','to':'2026-10-01T04:00:00Z','statusId':2},rawdir/'fixtures.json',True)
   if 'quota_after_enumeration' not in ledger:
    time.sleep(2.1);ledger['quota_after_enumeration']=quota();save()
   delta=ledger['quota_after_enumeration']['used']-ledger['quota_before']['used'];ledger['measured_delta']=delta;save()
   if delta!=1:raise RuntimeError('Unexpected quota delta; stop for review')
   if fixture['status']!=200 or not isinstance(fixture.get('payload'),list):raise RuntimeError('Fixture enumeration unavailable')
   fixtures=[f for f in fixture['payload'] if f['statusId']==2 and dt.date(2026,8,20)<=pd.Timestamp(f['startTime']).tz_convert('America/New_York').date()<dt.date(2026,10,1)]
   ids=[f['fixtureId'] for f in fixtures]
   if len(ids)!=len(set(ids)):raise RuntimeError('Duplicate fixture identity')
   original_df=pd.read_parquet(original);outpath=OUT/'odds_hist_2026.parquet'
   frame=pd.read_parquet(outpath) if outpath.exists() else original_df.copy()
   done=set(frame.fixture_id);todo=[f for f in fixtures if f['fixtureId'] not in done]
   ledger.update(state='history',enumerated=len(fixtures),initial_todo=len(todo));save()
   mktmap=oddspapi._markets_map();names=oddspapi._participants()
   for f in todo:
    fid=str(f['fixtureId'])
    if not fid.replace('_','').replace('-','').isalnum():raise RuntimeError('Unsafe fixture ID')
    path=rawdir/f'{fid}.json'
    if not path.exists():time.sleep(5.2)
    blob=fetch('historical-odds',{'fixtureId':fid,'bookmakers':BOOKS},path)
    if blob['status'] not in (200,404):raise RuntimeError('Cached stop response; manual review required')
    rows=trail_rows(f,blob['payload'],mktmap,names) if blob['status']==200 else []
    if not rows:
     rows=[dict(fixture_id=fid,start_time=f['startTime'],home_name=names.get(str(f['participant1Id'])),away_name=names.get(str(f['participant2Id'])),book='',market='',side='',point=None,open_dec=None,close_dec=None,close_at='',n_moves=0)]
    frame=pd.concat([frame,pd.DataFrame(rows)],ignore_index=True)
    temp=outpath.with_suffix('.tmp.parquet');frame.to_parquet(temp,index=False);temp.replace(outpath)
    ledger.update(completed_new_fixtures=len(set(frame.fixture_id)-set(original_df.fixture_id)),new_boarded_fixtures=len(set(frame[frame.book!=''].fixture_id)-set(original_df[original_df.book!=''].fixture_id)))
    save();print(json.dumps({k:ledger[k] for k in ['completed_new_fixtures','new_boarded_fixtures','history_calls']}),flush=True)
   if not outpath.exists():
    temp=outpath.with_suffix('.tmp.parquet');frame.to_parquet(temp,index=False);temp.replace(outpath)
   ledger['quota_final']=quota();ledger['state']='completed';save()
   assert hashlib.sha256(original.read_bytes()).hexdigest()==source_hash
  except Exception as error:
   ledger.update(state='stopped',error=safe_http.public_error(error),error_type=type(error).__name__);save();print(json.dumps(ledger),flush=True);raise SystemExit(1)
  print(json.dumps(ledger),flush=True)
if __name__=='__main__':main()
