"""T5 metric parity, position denominators, unknowns and actual UI labels."""
import os,sys,json
from pathlib import Path
from evidence_runs import new_run
from contextlib import ExitStack
from unittest.mock import patch
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from vbstats import player_metrics
from validate_t2_ui import guards,new_app,element,check,select_match,board
r=pd.read_parquet(ROOT/'app_data/rapm.parquet');idx=player_metrics.annotation_index(r)
with ExitStack() as stack:
 guards(stack);stack.enter_context(patch.dict(os.environ,{'WVB_ENABLE_REPAIRS':'1'}))
 at=new_app((ROOT/'streamlit_app.py').read_text());rank=next(x.value for x in at.dataframe if 'impact_per_set' in x.value.columns)
 selected=[('nebraska','Harper Murray'),('pittsburgh','Olivia Babcock'),('nebraska','Bergen Reilly'),('nebraska','Teraya Sigler'),('pittsburgh','Ayanna Watson')]
 evidence=[]
 for team,name in selected:
  row=rank[(rank.team==team)&(rank.player==name)]
  if row.empty:raise AssertionError((team,name))
  actual=row.iloc[0].impact_per_set;label=player_metrics.annotate(team,name,idx)
  assert f'{actual:+.2f} pts/set' in label
  eligible=r[(r.team==team)&(r.position==row.iloc[0].position)&(r.sets_started_cur>=1)]
  assert f'of {len(eligible)} {row.iloc[0].position}' in label
  evidence.append(dict(team=team,player=name,rank_tab_impact=float(actual),annotation=label))
 select_match(at,'nebraska','kansas','Home court');element(at.radio,'Pricing model').set_value('Hybrid (Elo + lineup adjust)');check(at.run())
 lineup=element(at.multiselect,'nebraska lineup (remove injured/absent)');assert any('Harper Murray' in x and 'pts/set' in x for x in lineup.options)
 before=board(at).copy();ids=list(lineup.value);check(at.run());assert list(element(at.multiselect,lineup.label).value)==ids;pd.testing.assert_frame_equal(before,board(at))
 assert player_metrics.annotate('nebraska','Unknown Player',idx)=='Unknown Player (unrated)'
 # Controlled ties and a zero-start teammate: tied rank 1 of 2, not 3.
 tiny=pd.DataFrame([dict(team='a',player=n,position='OH',serve=.1,recv=.1,sets_started_cur=starts) for n,starts in [('One',1),('Two',2),('Zero',0)]])
 tie=player_metrics.annotation_index(tiny);assert '#1 of 2 OH' in player_metrics.annotate('a','One',tie);assert '(unrated)' in player_metrics.annotate('a','Zero',tie)
 out=new_run(ROOT/'evidence/t5-20261001');(out/'annotations.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence))
