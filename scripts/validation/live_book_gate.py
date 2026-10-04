"""T15 live gate. Run ONLY after written owner authorization for two billable calls.

Fixed defaults, fixed cap, no retry/resume of ambiguous reservations. Stores raw
responses before parsing; decodes from those caches without further API requests.
"""
import datetime as dt,fcntl,json,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import oddspapi,safe_http
from scripts.audit.probe_book_coverage import quota,atomic
OUT=ROOT/'evidence/t15-20261004/live-gate-1'
BOOKS=('draftkings','hardrockbet')

def run():
 OUT.mkdir(parents=True,exist_ok=True)
 with (OUT/'job.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  lp=OUT/'ledger.json'
  if lp.exists():raise RuntimeError('Gate already attempted; inspect its ledger. No automatic retry.')
  ledger=dict(task='T15 live gate',cap=2,reserved=[],state='starting')
  def save():ledger['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat();atomic(lp,ledger)
  save()
  try:
   ledger['quota_before']=quota();save()
   if ledger['quota_before']['limit']-ledger['quota_before']['used']<2:
    raise RuntimeError('Insufficient quota for the two-call gate')
   key=oddspapi.api_key();cache={}
   for book in BOOKS:
    if ledger['reserved']:time.sleep(1.2)
    ledger['reserved'].append(book);save() # reserve before the potentially charged request
    r=safe_http.get(f'{oddspapi.API}/odds-by-tournaments',params={
        'apiKey':key,'tournamentIds':oddspapi.TOURNAMENT_NCAAW,
        'bookmaker':book,'oddsFormat':'american'},timeout=60)
    data={'book':book,'status':r.status_code,'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    if r.status_code in (200,404):
     data['payload']=r.json()
     if key in json.dumps(data['payload']):raise RuntimeError('Credential echo refused')
    atomic(OUT/f'{book}.json',data);cache[book]=data
    if r.status_code not in (200,404):
     raise safe_http.SafeHTTPError(f'odds-by-tournaments: HTTP {r.status_code}')
   ledger['quota_after']=quota();save()
   if ledger['quota_after']['used']-ledger['quota_before']['used']!=2:
    raise RuntimeError('Unexpected quota delta; review before any further call')
   class Cached:
    def __init__(self,book):self.data=cache[book];self.status_code=self.data['status']
    def raise_for_status(self):pass
    def json(self):return self.data['payload']
   with patch.object(oddspapi.safe_http,'get',side_effect=lambda url,**kw:Cached(kw['params']['bookmaker'])):
    games,_=oddspapi.fetch_board(books=BOOKS,key='cache-replay-only')
   atomic(OUT/'decoded-board.json',games)
   # Provider-backed Hard Rock pregame markets, even if another book beats its price.
   hardrock=[]
   for f in cache['hardrockbet'].get('payload',[]) if cache['hardrockbet']['status']==200 else []:
    if f.get('statusId')!=0:continue
    bo=f.get('bookmakerOdds',{}).get('hardrockbet',{})
    if not bo.get('suspended') and oddspapi._decode_book(bo.get('markets'),oddspapi._markets_map()):
     hardrock.append(f['fixtureId'])
   result=dict(games=len(games),hardrock_pregame_fixtures=hardrock,
       displayed_hardrock_best_lines=sum(r['book']=='hardrockbet' for g in games for r in g['markets']),
       anchor_books=sorted({r['devig_book'] for g in games for r in g['markets']}))
   atomic(OUT/'summary.json',result)
   ledger['state']='live_data_captured' if hardrock else 'gate_failed_no_hardrock_pregame_markets'
   save();print(json.dumps(result))
  except Exception as e:
   ledger['state']='stopped';ledger['error']=safe_http.public_error(e);ledger['error_type']=type(e).__name__
   try:ledger['quota_after_stop']=quota()
   except Exception:ledger['quota_after_stop']='unavailable'
   save();raise SystemExit('Live gate stopped; inspect credential-safe ledger.') from None
if __name__=='__main__':
 if sys.argv[1:]!=['--owner-approved-two-calls']:
  raise SystemExit('Requires recorded owner approval; then pass --owner-approved-two-calls.')
 run()
