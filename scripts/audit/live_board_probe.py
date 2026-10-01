"""T1-only live compatibility probe: hard cap ONE billable request, no retries."""
import datetime as dt,json
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlsplit
import requests
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import oddspapi
out=ROOT/'evidence/t1-20261001/live-probe-1';out.mkdir(exist_ok=False)
ledger={'task':'T1','authorized_cap':4,'probe_cap':1,'reserved_billable_requests':0,'state':'started','created_at':dt.datetime.now(dt.timezone.utc).isoformat()}
def save():
 p=out/'ledger.tmp';p.write_text(json.dumps(ledger,indent=2));p.replace(out/'ledger.json')
def quota(blob):
 result=[]
 def walk(x):
  if isinstance(x,dict):
   keep={k:v for k,v in x.items() if k in ('request_count','requests_used','request_limit') and isinstance(v,(str,int,float))}
   if keep:result.append(keep)
   for v in x.values():walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(blob);return result
save()
original=requests.sessions.Session.request
seq=0
def safe_request(self,method,url,**kwargs):
 global seq
 endpoint=urlsplit(url).path
 if endpoint not in ('/v4/account','/v4/odds-by-tournaments'):
  raise RuntimeError('Unexpected endpoint refused')
 if endpoint=='/v4/odds-by-tournaments':
  if ledger['reserved_billable_requests']>=ledger['probe_cap']:raise RuntimeError('Billable probe cap reached')
  ledger['reserved_billable_requests']+=1;save()
 response=original(self,method,url,**kwargs)
 if endpoint=='/v4/odds-by-tournaments':
  ledger['billable_http_status']=response.status_code;save()
 if response.status_code in (401,403,429):raise RuntimeError(f'Provider status {response.status_code}; stopped')
 # Do not call raise_for_status, whose exception contains the credential URL.
 if response.status_code not in (200,404):raise RuntimeError(f'Provider status {response.status_code}; stopped')
 if endpoint.endswith('odds-by-tournaments'):
  with (out/'raw_board.json').open('x') as f:json.dump({'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':response.status_code,'payload':response.json()},f)
 return response
try:
 with patch.object(requests.sessions.Session,'request',safe_request):
  ledger['quota_before']=quota(oddspapi.account());save()
  games,n=oddspapi.fetch_board(books=('draftkings',))
  (out/'decoded_board.json').write_text(json.dumps(games,indent=2))
  ledger['quota_after']=quota(oddspapi.account())
  ledger.update(state='completed',games=len(games),reported_requests=n)
except Exception as exc:
 ledger.update(state='failed',error_type=type(exc).__name__)
finally:
 save()
print(json.dumps(ledger,indent=2))
