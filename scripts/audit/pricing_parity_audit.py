"""Compare historical diagnostic pricing against actual app defaults on same lines."""
import json
from pathlib import Path
import sys
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import kelly,paste_odds
from vbstats import model
out=ROOT/'evidence/t1-20261001/parity-1';out.mkdir(exist_ok=False)
bt=pd.read_parquet(ROOT/'evidence/t3-20261001/run-1/rebuilt_backtest.parquet')
results=pd.read_parquet(ROOT/'app_data/results_current.parquet');results['date']=pd.to_datetime(results.start_epoch,unit='s',utc=True).dt.tz_convert('America/New_York').dt.date
blob=json.loads((ROOT/'app_data/model_params.json').read_text());params=np.array(blob['params']);draws=np.random.default_rng(7).multivariate_normal(params,np.array(blob['cov']),size=500)
cache={};rows=[]
for row in bt.itertuples():
 away,home=row.matchup.split(' @ ');day=pd.Timestamp(row.date).date();hit=None
 for offset in (0,1,-1):
  dd=day+pd.Timedelta(days=offset).to_pytimedelta()
  candidates=results[(((results.home_seo==home)&(results.away_seo==away))|((results.home_seo==away)&(results.away_seo==home)))&(results.date==dd)]
  if len(candidates):hit=candidates.iloc[:1].copy();break
 assert hit is not None
 cid=int(hit.iloc[0].contest_id)
 if cid not in cache:
  x=hit.copy();x['is_neutral']=False
  X=model.features(x)
  point=model.set_score_probs(X,params)[0]
  posterior=np.stack([model.set_score_probs(X,d)[0] for d in draws])
  cache[cid]=(point,posterior)
 point,posterior=cache[cid]
 pp=paste_odds.price_market(point,row.market,row.side,row.point)
 q=float(np.percentile([paste_odds.price_market(dp,row.market,row.side,row.point) for dp in posterior],20))
 ep=kelly.blend_prob(pp,row.p_mkt,.3)-row.implied
 eq=kelly.blend_prob(q,row.p_mkt,.3)-row.implied
 rounded=kelly.blend_prob(round(q,4),row.p_mkt,.3)-row.implied
 rows.append(dict(fixture=row.fixture,matchup=row.matchup,market=row.market,side=row.side,point=row.point,backtest_p=row.p_model,app_home_point=pp,app_home_p20=q,backtest_pass=row.edge_blend>=.02,app_home_point_pass=ep>=.02,app_default_p20_pass=eq>=.02,manual_rounded_pass=rounded>=.02,backtest_edge=row.edge_blend,app_p20_edge=eq))
df=pd.DataFrame(rows);df.to_csv(out/'priced_comparison.csv',index=False)
summary=dict(markets=len(df),fixtures=df.fixture.nunique(),backtest_bets=int(df.backtest_pass.sum()),app_home_point_bets=int(df.app_home_point_pass.sum()),app_default_p20_bets=int(df.app_default_p20_pass.sum()),venue_gate_changes=int((df.backtest_pass!=df.app_home_point_pass).sum()),p20_gate_changes=int((df.app_home_point_pass!=df.app_default_p20_pass).sum()),rounding_gate_changes=int((df.app_default_p20_pass!=df.manual_rounded_pass).sum()),limitation='Same historical pregame ratings for all scenarios; live app actually uses current ratings, and API anchors may differ from DK. Orientation follows results, not original API labels; no claim of replaying unrecorded live state.')
(out/'summary.json').write_text(json.dumps(summary,indent=2));print(summary)
