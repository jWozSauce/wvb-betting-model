"""Q10-approved revised free-only sweep; preserve the first access-error attempt.

Five known fixtures x 22 candidates. No billable endpoints. No retries after a
non-200/404, ambiguous in-flight request, authorization or rate-limit response.
"""
import datetime as dt,fcntl,hashlib,json,sys,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import oddspapi,safe_http
from scripts.audit.probe_book_coverage import atomic,quota
OUT=ROOT/'evidence/t15-20261004/coverage-2'
PRIOR=ROOT/'evidence/t15-20261004/coverage-1'
GROUPS=[['bet365','bet365-nj','betmgm'],['betrivers','bovada.lv','caesars'],
 ['circasports','espnbet','fanatics'],['hardrockbet','lowvig.ag','pinnacle'],
 ['betonline.ag','draftkings','fanduel'],['bookmaker.eu'],
 ['1xbet','bwin','unibet'],['sbobet','bcgame','cloudbet']]
BOOKS=[b for g in GROUPS for b in g]

def path_for(f,group):
 digest=hashlib.sha256(','.join(group).encode()).hexdigest()[:12]
 return OUT/'raw'/f"{f['fixtureId']}-{digest}.json"

def summarize(fixtures):
 rows=[];refs=oddspapi._markets_map()
 for f in fixtures:
  for group in GROUPS:
   path=path_for(f,group)
   if not path.exists():continue
   raw=json.loads(path.read_text())
   for bk in group:
    pre=set();post=set();points=0;prem=0;usable=set();earliest=None;latest=None
    markets=raw.get('payload',{}).get('bookmakers',{}).get(bk,{}).get('markets',{})
    for mid,m in markets.items():
     ref=refs.get(str(mid),{});name=ref.get('marketName') or str(mid)
     for o in (m.get('outcomes') or {}).values():
      for player,trail in (o.get('players') or {}).items():
       for t in trail:
        if not t.get('price'):continue
        stamp=pd.Timestamp(t['createdAt']);assert stamp.tzinfo is not None
        earliest=stamp if earliest is None else min(earliest,stamp)
        latest=stamp if latest is None else max(latest,stamp);points+=1
        if stamp < pd.Timestamp(f['startTime']):
         pre.add(name);prem+=1
         if str(player)=='0' and not ref.get('playerProp') and ref.get('period')=='result' and ref.get('marketType') in ('moneyline','spreads','totals'):
          h=float(ref.get('handicap') or 0)
          if ref['marketType']=='moneyline' or h!=int(h):usable.add(name)
        else:post.add(name)
    rows.append(dict(fixture_id=f['fixtureId'],start_time=f['startTime'],book=bk,
       status=raw['status'],trail_points=points,pregame_points=prem,
       pregame_markets=sorted(pre),post_start_markets=sorted(post),supported_pregame_markets=sorted(usable),
       earliest=str(earliest) if earliest is not None else None,latest=str(latest) if latest is not None else None))
 atomic(OUT/'fixture-coverage.json',rows)
 summary=[]
 for book in BOOKS:
  r=[x for x in rows if x['book']==book]
  summary.append(dict(book=book,fixtures_checked=sum(x['status'] in (200,404) for x in r),
   blocked_statuses=sorted({x['status'] for x in r if x['status'] not in (200,404)}),
   fixtures_with_trails=sum(x['trail_points']>0 for x in r),pregame_fixtures=sum(x['pregame_points']>0 for x in r),
   pregame_markets=sorted({m for x in r for m in x['pregame_markets']}),
   post_start_markets=sorted({m for x in r for m in x['post_start_markets']}),
   supported_pregame_markets=sorted({m for x in r for m in x['supported_pregame_markets']})))
 atomic(OUT/'summary.json',summary)
 return summary

def main():
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'raw').mkdir(exist_ok=True)
 with (OUT/'job.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  lp=OUT/'ledger.json'
  ledger=json.loads(lp.read_text()) if lp.exists() else dict(task='T15 Q10 revised',billable_cap=0,
    requests=0,reused=0,state='starting',groups=GROUPS,access_unverified=['pinnacle+5','pinnacle+30'])
  def save():ledger['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat();atomic(lp,ledger)
  if ledger['state']=='stopped' or ledger.get('inflight'):
   raise SystemExit('Stopped/in-flight checkpoint requires review; no automatic retry.')
  fixtures=json.loads((PRIOR/'fixtures.json').read_text());assert len(fixtures)==5 and all(f['statusId']==2 for f in fixtures)
  atomic(OUT/'fixtures.json',fixtures)
  try:
   if 'quota_before' not in ledger:ledger['quota_before']=quota();save()
   if ledger['quota_before']['used']>=ledger['quota_before']['limit']:raise RuntimeError('Quota exhausted')
   key=oddspapi.api_key()
   for f in fixtures:
    for group in GROUPS:
     path=path_for(f,group);params={'fixtureId':f['fixtureId'],'bookmakers':','.join(group)}
     if path.exists():continue
     cached=None
     for old in (PRIOR/'raw').glob('*.json'):
      d=json.loads(old.read_text())
      if d['params']==params and d['status'] in (200,404):cached=(old,d);break
     if cached:
      old,d=cached;d={**d,'reused_from':str(old.relative_to(ROOT))};atomic(path,d)
      ledger['reused']+=1;save();continue
     time.sleep(5.2)
     ledger['requests']+=1;ledger['inflight']=params;ledger['state']='running';save()
     r=safe_http.get(f'{oddspapi.API}/historical-odds',params={'apiKey':key,**params},timeout=60)
     blob=dict(params=params,status=r.status_code,retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat())
     if r.status_code in (200,404):
      payload=r.json()
      if key in json.dumps(payload):raise RuntimeError('Credential echo refused')
      blob['payload']=payload
     atomic(path,blob);ledger.pop('inflight',None);save()
     if r.status_code not in (200,404):raise safe_http.SafeHTTPError(f'historical-odds: HTTP {r.status_code}')
     if ledger['requests']==1:
      ledger['quota_after_probe']=quota();save()
      if ledger['quota_after_probe']['used']!=ledger['quota_before']['used']:raise RuntimeError('Quota changed after free probe')
     print(json.dumps(dict(requests=ledger['requests'],reused=ledger['reused'],total=40)),flush=True)
   ledger['quota_after']=quota();save()
   if ledger['quota_after']['used']!=ledger['quota_before']['used']:raise RuntimeError('Quota changed during free sweep; attribution requires review')
   summarize(fixtures);ledger['state']='complete';save();print(json.dumps(ledger),flush=True)
  except Exception as e:
   ledger['state']='stopped';ledger['error']=safe_http.public_error(e);ledger['error_type']=type(e).__name__
   try:ledger['quota_after_stop']=quota()
   except Exception:ledger['quota_after_stop']='unavailable'
   save();summarize(fixtures);print(json.dumps(ledger),flush=True);raise SystemExit(1)
if __name__=='__main__':main()
