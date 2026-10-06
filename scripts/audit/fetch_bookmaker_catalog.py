"""Q12 one-time approved catalog capture. One reservation; never retry/resume."""
import argparse,datetime as dt,fcntl,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import oddspapi,safe_http
from scripts.audit.probe_book_coverage import atomic,quota
OUT=ROOT/'evidence/q12-catalog-20261005'
TARGET=ROOT/'app_data/oddspapi_bookmakers.json'

def run():
 OUT.mkdir(parents=True,exist_ok=True)
 with (OUT/'job.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  lp=OUT/'ledger.json'
  if lp.exists() or TARGET.exists():raise RuntimeError('Catalog/attempt already exists; no new request permitted.')
  ledger=dict(task='Q12 catalog',cap=1,reserved=0,state='starting')
  def save():ledger['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat();atomic(lp,ledger)
  save()
  try:
   ledger['quota_before']=quota();save()
   if ledger['quota_before']['used']>=ledger['quota_before']['limit']:raise RuntimeError('No available quota')
   key=oddspapi.api_key()
   if ledger['reserved']>=ledger['cap']:raise RuntimeError('Cap exhausted')
   ledger['reserved']+=1;ledger['state']='reserved';save()
   r=safe_http.get(f'{oddspapi.API}/bookmakers',params={'apiKey':key},timeout=60,allow_redirects=False)
   ledger['status']=r.status_code;save()
   if r.status_code!=200:raise safe_http.SafeHTTPError(f'bookmakers: HTTP {r.status_code}')
   payload=r.json()
   if key in json.dumps(payload):raise RuntimeError('Credential echo refused')
   atomic(OUT/'raw.json',dict(retrieved_at=ledger['updated_at'],status=r.status_code,payload=payload))
   ledger['quota_after']=quota();save()
   if ledger['quota_after']['used']-ledger['quota_before']['used']!=1:raise RuntimeError('Unexpected quota delta; capture retained, no retry')
   if not isinstance(payload,list) or not payload or any(not isinstance(row,dict) or not isinstance(row.get('slug'),str) or not row['slug'].strip() for row in payload):raise RuntimeError('Invalid catalog schema')
   slugs=[row['slug'] for row in payload]
   if len(set(slugs))!=len(slugs) or not set(oddspapi.BOOKS)<=set(slugs):raise RuntimeError('Duplicate slugs or missing default books')
   # Exclusive install; do not overwrite another participant's catalog.
   with TARGET.open('x') as out:json.dump(payload,out,indent=2);out.write('\n')
   ledger.update(state='complete',catalog_books=len(slugs));save()
   print(json.dumps(ledger))
  except Exception as e:
   ledger.update(state='stopped',error=safe_http.public_error(e),error_type=type(e).__name__)
   # Stop immediately on any failure; accounting recovery needs a ruling.
   save();raise SystemExit('Catalog capture stopped; inspect safe ledger, do not retry.') from None
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--owner-approved-one-call',action='store_true');p.add_argument('--key-file',type=Path)
 a=p.parse_args()
 if not a.owner_approved_one_call:raise SystemExit('Recorded one-call owner approval required')
 if a.key_file:oddspapi.LOCAL_KEY=a.key_file
 run()
