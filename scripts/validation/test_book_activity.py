"""Q14: explicit false excludes both bets and anchors; all requests replay offline."""
import copy,json,sys
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import oddspapi
from evidence_runs import new_run
ref={'231':{'marketType':'moneyline','period':'result','outcomes':[{'outcomeId':1,'outcomeName':'1'},{'outcomeId':2,'outcomeName':'2'}]}}
def markets(a,b):return {'231':{'outcomes':{str(i):{'players':{'0':{'active':True,'priceAmerican':v}}} for i,v in enumerate([a,b],1)}}}
f={'fixtureId':'123','statusId':0,'startTime':'2026-10-05T23:00:00Z','participant1Id':1,'participant2Id':2,'bookmakerOdds':{'sbobet':{'markets':markets(-130,105)},'draftkings':{'markets':markets(110,-130)},'hardrockbet':{'markets':markets(120,115)}}}
with patch.object(oddspapi,'_markets_map',return_value=ref),patch.object(oddspapi,'_participants',return_value={'1':'Nebraska','2':'Kansas'}),patch.object(oddspapi.time,'sleep'):
 for state in (None,True,False):
  current=copy.deepcopy(f)
  if state is not None:
   for b in ('sbobet','hardrockbet'):current['bookmakerOdds'][b]['bookmakerIsActive']=state
  with patch.object(oddspapi.safe_http,'get',return_value=Mock(status_code=200,json=lambda:[current])):
   games,_=oddspapi.fetch_board(books=('sbobet','draftkings','hardrockbet'),key='offline')
  assert all(r['book']==('draftkings' if state is False else 'hardrockbet') for r in games[0]['markets'])
  assert all(r['devig_book']==('draftkings' if state is False else 'sbobet') for r in games[0]['markets'])
 # Excluding the only bettable book must not turn anchor-only rows into bets.
 current['bookmakerOdds']['draftkings']['bookmakerIsActive']=False
 with patch.object(oddspapi.safe_http,'get',return_value=Mock(status_code=200,json=lambda:[current])):
  assert oddspapi.fetch_board(books=('sbobet','draftkings','hardrockbet'),key='offline')[0]==[]
cache={b:json.loads((ROOT/f'evidence/t15-20261004/live-gate-1/{b}.json').read_text()) for b in oddspapi.BOOKS}
class Cached:
 def __init__(self,b):self.d=cache[b];self.status_code=self.d['status']
 def json(self):return self.d['payload']
 def raise_for_status(self):assert self.status_code==200
with patch.object(oddspapi.safe_http,'get',side_effect=lambda url,**kw:Cached(kw['params']['bookmaker'])),patch.object(oddspapi.time,'sleep'):
 games,_=oddspapi.fetch_board(books=oddspapi.BOOKS,key='offline')
 assert games==json.loads((ROOT/'evidence/t15-20261004/live-gate-1/decoded-board.json').read_text())
 # Make the inactive real book first; DK must still anchor all retained markets.
 priority=('1xbet',)+tuple(b for b in oddspapi.BOOKS if b!='1xbet')
 assert all(r['devig_book']=='draftkings' for g in oddspapi.fetch_board(books=priority,key='offline')[0] for r in g['markets'])
out=new_run(ROOT/'evidence/q14-20261004')
(out/'checks.json').write_text(json.dumps(dict(explicit_false_excluded_from_bets_and_anchors=True,missing_and_true_unchanged=True,inactive_real_1xbet_ignored=True,preserved_capture_same_card=True,real_calls=0),indent=2))
print('PASS Q14 activity filter')
