"""T6 read-only owner-log exposure review; private row output stays outside Git."""
import json,sys,os
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import bet_log,app_config
bet_log.SCOPES=['https://www.googleapis.com/auth/spreadsheets.readonly']
ss=bet_log._client().open_by_key(app_config._sheet_id())
results=pd.read_parquet(ROOT/'app_data/results_current.parquet');results['date']=pd.to_datetime(results.start_epoch,unit='s',utc=True).dt.tz_convert('America/New_York').dt.date
changed=[];counts={}
def grade(row,result,flip):
 if result is None:return {'status':'unresolved','profit':None,'contest_id':None}
 hs,aw=(result.away_sets,result.home_sets) if flip else (result.home_sets,result.away_sets)
 won,push=bet_log._settle(row['market'],row['side'].lower(),row['point'],int(hs),int(aw))
 odds=float(row['odds']);stake=float(row['stake'] or 0)
 return {'status':'push' if push else 'won' if won else 'lost','profit':round(0 if push else stake*(odds/100 if odds>0 else 100/-odds) if won else -stake,2),'contest_id':int(result.contest_id)}
for name in [bet_log.WORKSHEET,bet_log.PAPER_WORKSHEET]:
 rows=ss.worksheet(name).get_all_records();counts[name]={'rows':len(rows),'lookup_changes':0,'grade_changes':0,'unusable':0}
 for i,row in enumerate(rows,2):
  try:
   old=grade(row,*bet_log._find_result_legacy(results,row['home_team'],row['away_team'],str(row['game_date'])))
   new=grade(row,*bet_log._find_result_safe(results,row['home_team'],row['away_team'],str(row['game_date'])))
  except (ValueError,TypeError,KeyError):counts[name]['unusable']+=1;continue
  if old!=new:
   counts[name]['lookup_changes']+=1
   grade_change=(old['status'],old['profit'])!=(new['status'],new['profit']);counts[name]['grade_changes']+=int(grade_change)
   changed.append({'worksheet':name,'sheet_row':i,'game_date':row['game_date'],'matchup':row['matchup'],'bet':row['bet'],'stored_status':row.get('status'),'stored_profit':row.get('profit'),'old':old,'proposed':new,'grade_changes':grade_change})
p=Path('/tmp/volleyball-t6-grading-exposure-20261001.json');fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:json.dump(changed,f,indent=2)
out=ROOT/'evidence/t6-20261001';out.mkdir(exist_ok=False)
(out/'exposure_summary.json').write_text(json.dumps({'worksheets':counts,'private_row_report':str(p),'writes':0},indent=2));print(json.dumps(counts))
