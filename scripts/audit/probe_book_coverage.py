"""T15 free-only, resumable historical coverage probe. No billable endpoint exists here."""
import datetime as dt,fcntl,hashlib,json,os,sys,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import oddspapi,safe_http
OUT=ROOT/'evidence/t15-20261004/coverage-1'
BOOKS=['bet365','bet365-nj','betmgm','betrivers','bovada.lv','caesars','circasports','espnbet','fanatics','hardrockbet','lowvig.ag','pinnacle','pinnacle+5','pinnacle+30','betonline.ag','draftkings','fanduel']

def atomic(p,obj):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(obj,indent=2));t.replace(p)
def quota():
 def walk(x):
  if isinstance(x,dict):
   if 'request_count' in x and 'request_limit' in x:return {'used':int(x['request_count']),'limit':int(x['request_limit'])}
   for v in x.values():
    r=walk(v)
    if r:return r
  if isinstance(x,list):
   for v in x:
    r=walk(v)
    if r:return r
 q=walk(oddspapi.account())
 if q is None:raise RuntimeError('Quota fields unavailable')
 return q

def summarize(fixtures):
 rows=[];refs=oddspapi._markets_map()
 for f in fixtures:
  for bi in range(0,len(BOOKS),3):
   path=OUT/'raw'/f"{f['fixtureId']}-{bi//3}.json"
   if not path.exists():continue
   raw=json.loads(path.read_text());blob=raw.get('payload',{})
   for bk in BOOKS[bi:bi+3]:
    pre=set();live=set();allm=set();points=0;prem=0
    for mid,m in blob.get('bookmakers',{}).get(bk,{}).get('markets',{}).items():
     name=refs.get(str(mid),{}).get('marketName',str(mid))
     for o in (m.get('outcomes') or {}).values():
      for trail in (o.get('players') or {}).values():
       for t in trail:
        if not t.get('price'):continue
        points+=1;allm.add(name)
        if pd.Timestamp(t['createdAt']) < pd.Timestamp(f['startTime']):pre.add(name);prem+=1
        else:live.add(name)
    rows.append(dict(fixture_id=f['fixtureId'],start_time=f['startTime'],book=bk,status=raw['status'],trail_points=points,pregame_points=prem,pregame_markets=sorted(pre),post_start_markets=sorted(live),markets=sorted(allm)))
 atomic(OUT/'fixture-coverage.json',rows)
 books=[]
 for bk in BOOKS:
  r=[x for x in rows if x['book']==bk];pre=sorted({m for x in r for m in x['pregame_markets']});post=sorted({m for x in r for m in x['post_start_markets']})
  books.append(dict(book=bk,fixtures_checked=sum(x['status'] in (200,404) for x in r),blocked_statuses=sorted({x['status'] for x in r if x['status'] not in (200,404)}),fixtures_with_trails=sum(x['trail_points']>0 for x in r),pregame_fixtures=sum(x['pregame_points']>0 for x in r),pregame_markets=pre,post_start_markets=post))
 atomic(OUT/'summary.json',books)
 print(json.dumps(books,indent=2),flush=True)

def main():
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'raw').mkdir(exist_ok=True)
 with (OUT/'job.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  lp=OUT/'ledger.json';ledger=json.loads(lp.read_text()) if lp.exists() else dict(task='T15',billable_cap=0,requests=0,state='starting',candidates=BOOKS)
  def save():ledger['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat();atomic(lp,ledger)
  if ledger['state']=='stopped':raise SystemExit('Stopped checkpoint requires review; no automatic retry.')
  d=pd.read_parquet(ROOT/'evidence/t3-20261001/extension-1/odds_hist_2026.parquet')
  selected=d[d.book!=''].sort_values('start_time').drop_duplicates('fixture_id').tail(5)
  fixture_ids=set(selected.fixture_id)
  fixtures=[f for f in json.loads((ROOT/'evidence/t3-20261001/extension-1/raw/fixtures.json').read_text())['payload'] if f['fixtureId'] in fixture_ids]
  assert len(fixtures)==5 and all(f['statusId']==2 for f in fixtures)
  atomic(OUT/'fixtures.json',fixtures)
  try:
   if 'quota_before' not in ledger:ledger['quota_before']=quota();save()
   if ledger['quota_before']['used']>=ledger['quota_before']['limit']:raise RuntimeError('Quota exhausted; free history blocked by provider')
   key=oddspapi.api_key()
   for f in fixtures:
    for bi in range(0,len(BOOKS),3):
     path=OUT/'raw'/f"{f['fixtureId']}-{bi//3}.json"
     if path.exists():continue
     time.sleep(5.2)
     params={'fixtureId':f['fixtureId'],'bookmakers':','.join(BOOKS[bi:bi+3])}
     ledger['requests']+=1;ledger['state']='running';save()
     r=safe_http.get(f'{oddspapi.API}/historical-odds',params={'apiKey':key,**params},timeout=60)
     blob=dict(params=params,status=r.status_code,retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat())
     if r.status_code in (200,404):
      payload=r.json()
      if key in json.dumps(payload):raise RuntimeError('Credential echo refused')
      blob['payload']=payload
     atomic(path,blob)
     if r.status_code not in (200,404):raise RuntimeError(f'History HTTP {r.status_code}; stopped without retry')
     if ledger['requests']==1:
      ledger['quota_after_probe']=quota();save()
      if ledger['quota_after_probe']['used']!=ledger['quota_before']['used']:raise RuntimeError('Unexpected quota delta after free probe')
     print(f"Completed {ledger['requests']}/30 free history requests",flush=True)
   ledger['quota_after']=quota();ledger['state']='complete';save()
   if ledger['quota_after']['used']!=ledger['quota_before']['used']:raise RuntimeError('Quota changed during probe; attribution requires review')
   summarize(fixtures)
  except Exception as e:
   ledger['state']='stopped';ledger['error']=safe_http.public_error(e);ledger['error_type']=type(e).__name__;save();print(json.dumps(ledger),flush=True);raise SystemExit(1)
if __name__=='__main__':main()
