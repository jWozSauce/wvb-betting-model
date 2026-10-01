"""Readonly T7 exposure inventory; canonical log names cannot prove source spelling."""
import sys,json,os
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import bet_log,app_config
bad=pd.read_csv(ROOT/'evidence/t1-20261001/matching-1/team_names.csv');targets=set(bad[bad.verdict=='wrong'].actual.dropna())
bet_log.SCOPES=['https://www.googleapis.com/auth/spreadsheets.readonly'];ss=bet_log._client().open_by_key(app_config._sheet_id())
flags=[];counts={}
for name in [bet_log.WORKSHEET,bet_log.PAPER_WORKSHEET]:
 rows=ss.worksheet(name).get_all_records();n=0
 for i,row in enumerate(rows,2):
  if row.get('home_team') in targets or row.get('away_team') in targets:
   flags.append({'worksheet':name,'row':i,'date':row.get('game_date'),'matchup':row.get('matchup'),'bet':row.get('bet'),'status':row.get('status'),'reason':'Logged canonical team also appears as a wrong-matcher destination; original vendor labels absent, not proof of misidentification.'});n+=1
 counts[name]={'rows':len(rows),'potential_review_rows':n}
p=Path('/tmp/volleyball-t7-team-exposure-20261001.json');fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as f:json.dump(flags,f,indent=2)
summary={'counts':counts,'private_review_list':str(p),'confirmed_wrong_logged_rows':None,'limitation':'Original provider/paste team text is not stored, so canonical destination flags cannot establish misidentification. Owner review only; no changes.','writes':0}
(ROOT/'evidence/t7-20261001/log_exposure.json').open('x').write(json.dumps(summary,indent=2));print(json.dumps(counts))
