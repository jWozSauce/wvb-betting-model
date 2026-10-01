"""Offline T1 boundary checks; no network or real Sheets writes."""
import sys,json,copy
from pathlib import Path
from unittest.mock import patch
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import oddspapi,bet_log,kelly
out=ROOT/'evidence/t1-20261001/transactions-1';out.mkdir(exist_ok=False)
# Controlled provider schema: line shop independently of the anchor book.
ref={'1':{'marketType':'moneyline','period':'result','outcomes':[{'outcomeId':1,'outcomeName':'1'},{'outcomeId':2,'outcomeName':'2'}]}}
def market(a,b):
 return {'1':{'outcomes':{str(i):{'players':{'0':{'active':True,'priceAmerican':v}}} for i,v in enumerate([a,b],1)}}}
f={'fixtureId':123,'statusId':0,'startTime':'2026-10-02T20:00:00Z','participant1Id':1,'participant2Id':2,'bookmakerOdds':{'pinnacle':{'markets':market(-120,110)},'draftkings':{'markets':market(105,-125)}}}
class Response:
 status_code=200
 def raise_for_status(self):pass
 def json(self):return [copy.deepcopy(f)]
with patch.object(oddspapi,'_markets_map',return_value=ref),patch.object(oddspapi,'_participants',return_value={'1':'home','2':'away'}),patch.object(oddspapi.requests,'get',return_value=Response()) as req,patch.object(oddspapi.time,'sleep'):
 games,n=oddspapi.fetch_board(books=('pinnacle','draftkings'),key='DUMMY')
 assert n==2 and req.call_count==2
 r={x['side']:x for x in games[0]['markets']}
 assert r['home']['odds']==105 and r['home']['book']=='draftkings'
 assert r['away']['odds']==110 and r['away']['book']=='pinnacle'
 assert r['home']['devig_book']=='pinnacle' and r['home']['mkt_prob']==round(kelly.vig_free_probs(-120,110)[0],4)
 f['statusId']=1
 assert oddspapi.fetch_board(books=('pinnacle',),key='DUMMY')[0]==[]
# Grade reversed rows, pushes, and missing-profit repair into a mock worksheet.
base={'home_team':'a','away_team':'h','game_date':'2026-10-01','point':'','odds':100,'stake':10,'status':'pending','profit':''}
rows=[{**base,'market':'ml','side':'away'},{**base,'market':'ml','side':'home','status':'lost'}, {**base,'market':'total','side':'over','point':4},{**base,'market':'ml','side':'home','status':'lost','profit':-10}]
class Sheet:
 def __init__(self):self.writes=[];self.appended=[]
 def get_all_records(self):return rows
 def batch_update(self,data,**kw):self.writes.append(data)
 def append_rows(self,data,**kw):self.appended.append(data)
ws=Sheet();res=pd.DataFrame([{'home_seo':'h','away_seo':'a','date':'2026-10-01','home_sets':3,'away_sets':1}])
with patch.object(bet_log,'_ws',return_value=ws):
 n,_=bet_log.grade_pending(res)
assert n==3 and len(ws.writes)==1
assert [x['values'][0][:2] for x in ws.writes[0]]==[['won',10.0],['lost',-10.0],['push',0.0]]
# Demonstrate dedupe does not remove duplicates within a single submitted batch.
rows=[]; duplicate={'game_date':'2026-10-01','matchup':'a @ h','bet':'h ML'}
with patch.object(bet_log,'_ws',return_value=ws):n=bet_log.log_bets([duplicate,duplicate],dedupe=True)
assert n==2
# Fake credential only: HTTPError embeds the query URL; no external request.
import requests
resp=requests.Response();resp.status_code=401;resp.url='https://example.invalid/odds?apiKey=DUMMY_CREDENTIAL'
try:resp.raise_for_status()
except requests.HTTPError as e:exposure='DUMMY_CREDENTIAL' in str(e)
assert exposure
hist=pd.read_parquet(ROOT/'data/processed/odds_hist_2026.parquet');real=hist[hist.book!=''];post=(pd.to_datetime(real.close_at,utc=True)>pd.to_datetime(real.start_time,utc=True)).sum()
result={'decoder':'PASS: best price independent from first complete anchor; live status excluded','grade_rows':3,'grade_batches':1,'half_written_profit_repaired':True,'within_batch_duplicates_appended':n,'fake_key_in_http_error':exposure,'historical_rows':len(hist),'boarded_rows':len(real),'swept_fixtures':int(hist.fixture_id.nunique()),'boarded_fixtures':int(real.fixture_id.nunique()),'post_scheduled_start_prices':int(post),'books':real.book.value_counts().to_dict()}
(out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
