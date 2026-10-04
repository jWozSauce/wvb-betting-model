"""T15 live gate. Run ONLY after written owner authorization for up to five billable calls.

Evidence-based defaults, fixed cap, no retry/resume of ambiguous reservations. Stores raw
responses before parsing; decodes from those caches without further API requests.
"""
import datetime as dt,fcntl,json,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import oddspapi,safe_http
from scripts.audit.probe_book_coverage import quota,atomic
OUT=ROOT/'evidence/t15-20261004/live-gate-1'
BOOKS=oddspapi.BOOKS

def validate_proposal():
 coverage=ROOT/'evidence/t15-20261004/coverage-2'
 ledger=json.loads((coverage/'ledger.json').read_text())
 summary=json.loads((coverage/'summary.json').read_text())
 eligible={r['book'] for r in summary if r['supported_pregame_markets']}
 if ledger['state']!='complete' or not set(BOOKS)<=eligible or not 1<=len(BOOKS)<=5:
  raise RuntimeError('Default proposal lacks completed pregame evidence or exceeds approved cap')


def verify_prices(games,cache):
 quotes={}
 for book in BOOKS:
  blob=cache[book]
  for f in blob.get('payload',[]) if blob['status']==200 else []:
   bo=f.get('bookmakerOdds',{}).get(book,{})
   if f.get('statusId')==0 and not bo.get('suspended'):
    quotes.setdefault(str(f['fixtureId']),{})[book]=oddspapi._decode_book(bo.get('markets'),oddspapi._markets_map())
 checked=0
 for g in games:
  books=quotes[g['fixture_id']]
  for row in g['markets']:
   key=(row['market'],row['side'],row['point'])
   candidates=[(b,r) for b in BOOKS if b not in oddspapi.ANCHOR_ONLY_BOOKS
       for r in books.get(b,[]) if (r['market'],r['side'],r['point'])==key]
   def decimal(r):return 1+r['odds']/100 if r['odds']>0 else 1+100/abs(r['odds'])
   best=max(candidates,key=lambda pair:decimal(pair[1]))
   assert (row['book'],row['odds'])==(best[0],best[1]['odds'])
   def pair(r):
    point=r['point']
    if r['market']=='spread' and r['side']=='away':point=-point
    return r['market'],point
   anchor=None
   for b in BOOKS:
    two={r['side']:r['odds'] for r in books.get(b,[]) if pair(r)==pair(row)}
    if len(two)==2:
     anchor=b
     other=next(odds for side,odds in two.items() if side!=row['side'])
     import kelly
     expected=round(kelly.vig_free_probs(two[row['side']],other)[0],4)
     assert row['mkt_prob']==expected
     break
   assert row['devig_book']==(anchor or '')
   checked+=1
 return checked

def run():
 validate_proposal()
 OUT.mkdir(parents=True,exist_ok=True)
 with (OUT/'job.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  lp=OUT/'ledger.json'
  if lp.exists():raise RuntimeError('Gate already attempted; inspect its ledger. No automatic retry.')
  ledger=dict(task='T15 live gate',cap=5,books=list(BOOKS),reserved=[],state='starting')
  def save():ledger['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat();atomic(lp,ledger)
  save()
  try:
   ledger['quota_before']=quota();save()
   if ledger['quota_before']['limit']-ledger['quota_before']['used']<len(BOOKS):
    raise RuntimeError('Insufficient quota for the approved gate')
   key=oddspapi.api_key();cache={}
   for book in BOOKS:
    if ledger['reserved']:time.sleep(1.2)
    if len(ledger['reserved'])>=ledger['cap']:raise RuntimeError('Approved cap exhausted')
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
   if ledger['quota_after']['used']-ledger['quota_before']['used']!=len(BOOKS):
    raise RuntimeError('Unexpected quota delta; review before any further call')
   class Cached:
    def __init__(self,book):self.data=cache[book];self.status_code=self.data['status']
    def raise_for_status(self):pass
    def json(self):return self.data['payload']
   with patch.object(oddspapi.safe_http,'get',side_effect=lambda url,**kw:Cached(kw['params']['bookmaker'])):
    games,_=oddspapi.fetch_board(books=BOOKS,key='cache-replay-only')
   atomic(OUT/'decoded-board.json',games)
   checked=verify_prices(games,cache)
   result=dict(games=len(games),markets_checked=checked,selected_books=list(BOOKS),
       actionable_books=sorted({r['book'] for g in games for r in g['markets']}),
       anchor_books=sorted({r['devig_book'] for g in games for r in g['markets']}),
       billable_delta=ledger['quota_after']['used']-ledger['quota_before']['used'])
   atomic(OUT/'summary.json',result)
   ledger['state']='capture_complete_awaiting_acceptance' if checked else 'gate_failed_no_pregame_markets'
   save();print(json.dumps(result))
  except Exception as e:
   ledger['state']='stopped';ledger['error']=safe_http.public_error(e);ledger['error_type']=type(e).__name__
   try:ledger['quota_after_stop']=quota()
   except Exception:ledger['quota_after_stop']='unavailable'
   save();raise SystemExit('Live gate stopped; inspect credential-safe ledger.') from None
if __name__=='__main__':
 if sys.argv[1:]!=['--owner-approved-up-to-five-calls']:
  raise SystemExit('Requires recorded owner approval; then pass --owner-approved-up-to-five-calls.')
 run()
