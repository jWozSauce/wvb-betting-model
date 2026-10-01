"""Replay raw NCAA data through the unchanged legacy venue classifier."""
import datetime as dt
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from vbstats.venues import slate_venues
from vbstats.ncaa import NCAAClient
from schedule_pricing import point_price, game_time
from vbstats import model
import kelly

source=ROOT/'evidence/t2-20261001/full-slate-1'
slate=json.loads((source/'slate.json').read_text())
responses=[json.loads(p.read_text()) for p in sorted(source.glob('response-*.json'))]
schedules={r['variables']['division']:r['data']['contests'] for r in responses if r['meta']=='GetContests_web'}
games={r['variables']['id']:r['data']['contests'] for r in responses if r['meta']=='GetGamecenterGameById_web'}
hv=pd.read_parquet(ROOT/'app_data/home_venues.parquet')
hvmap=dict(zip(hv.team,hv.home_venue))
own=hv.sort_values('n',ascending=False).drop_duplicates('home_venue')
owners=dict(zip(own.home_venue,own.team))
# Start with one game per observed site label, then fill to ten.
selected=[]
for site in dict.fromkeys(r['site'] for r in slate['priced']):
    selected.append(next(r for r in slate['priced'] if r['site']==site))
for row in slate['priced']:
    if len(selected)>=10: break
    if row not in selected: selected.append(row)
selected=selected[:10]
pairs=[(r['ncaa_away'],r['ncaa_home']) for r in selected]
def contests(self,day,season,division=1):
    return schedules[division] if day==dt.date.fromisoformat(slate['date']) else []
def game(self,cid):
    rows=games[str(cid)]
    return rows[0] if rows else None
with patch.object(NCAAClient,'contests',contests),patch.object(NCAAClient,'game',game):
    old=slate_venues(pairs,hvmap,venue_owner=owners)
checks=[]
for row in selected:
    actual=old[(row['ncaa_away'],row['ncaa_home'])]
    expected_site=row['site'].replace('venue ?','?').replace(' — host shown as home','')
    assert expected_site==actual['site'], (row,actual)
    assert row['venue']==actual['venue']
    checks.append(dict(contest_id=row['contest_id'],away=row['ncaa_away'],home=row['ncaa_home'],
                       legacy=actual['site'],new=row['site'],venue=row['venue'],verdict='confirmed'))
pd.DataFrame(checks).to_csv(source/'venue_spot_check.csv',index=False)
ratings=pd.read_parquet(ROOT/'app_data/elo_current.parquet').set_index('team')
params=tuple(json.loads((ROOT/'app_data/model_params.json').read_text())['params'])
rows=[]
for row in slate['priced']:
    h,a=ratings.loc[row['home']],ratings.loc[row['away']]
    values=lambda r:tuple(float(r[k]) for k in ('serve_elo','receive_elo','conf_elo'))
    p=point_price(values(h),values(a),row['venue_mode'],params)
    mk={k:float(v[0]) for k,v in model.markets(p[None,:]).items()}
    shown=dict(time_et=game_time(row),away=row['away'],home=row['home'],site=row['site'],venue=row['venue'],mode=row['venue_mode'],
               away_ml=kelly.prob_to_american(1-mk['home_ml']),home_ml=kelly.prob_to_american(mk['home_ml']))
    for k,v in mk.items():
        shown[k+'_prob']=v
        shown[k+'_fair']=kelly.prob_to_american(v)
    rows.append(shown)
pd.DataFrame(rows).to_csv(source/'slate_table.csv',index=False)
print('10/10 legacy venue labels match; 126-game slate CSV saved')
