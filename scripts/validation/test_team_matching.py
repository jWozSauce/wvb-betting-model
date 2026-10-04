import os,sys,unittest,json
from pathlib import Path
from evidence_runs import new_run
from unittest.mock import patch
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));import paste_odds
class Matching(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  r=pd.read_parquet(ROOT/'app_data/elo_current.parquet');cls.seos=r.team.tolist();cls.full=dict(zip(r.team,r.name_full))
 def match(self,name):
  with patch.dict(os.environ,{'WVB_ENABLE_REPAIRS':'1'}):return paste_odds.match_team(name,self.seos,self.full)[0]
 def test_regressions(self):
  for name,expected in [('Utah','utah'),('UTA','texas-arlington'),('USC','southern-california'),('USC Upstate','usc-upstate'),('Miami University Ohio','miami-oh'),('LSU','lsu'),('LSU New Orleans','new-orleans')]:
   actual=self.match(name)
   self.assertEqual(actual,expected,name)
  self.assertEqual(self.match('Utah'),'utah');self.assertEqual(self.match('USC Upstate'),'usc-upstate')
 def test_ambiguous_identity_refused(self):
  with patch.dict(os.environ,{'WVB_ENABLE_REPAIRS':'1'}):
   self.assertIsNone(paste_odds.match_team('Shared University',['a','b'],{'a':'Shared University','b':'Shared University'})[0])
 def test_punctuation_school_identity(self):
  self.assertEqual(self.match('Missouri S&T'),'missouri-snt')
  self.assertEqual(self.match('Missouri St.'),'missouri-st')
 def test_unknown_campus_refused(self):
  for name in ['USC unknown campus','Utah nowhere','LSU Elsewhere','Miami unknown','XYZ','']:
   self.assertIsNone(self.match(name),name)
 def test_vendor_names(self):
  cases=json.loads((ROOT/'evidence/t7-20261001/vendor_names.json').read_text())
  for case in cases:self.assertEqual(self.match(case['name']),case['expected'],case['name'])
  self.assertIsNone(self.match('USC Unknown Campus Trojans'))
  self.assertEqual(self.match('USC Upstate Spartans'),'usc-upstate')
 def test_live_participant_regressions(self):
  cases=json.loads((ROOT/'scripts/validation/fixtures/live_unmatched_teams.json').read_text())
  for case in cases:self.assertEqual(self.match(case['name']),case['expected'],case['name'])
 def test_corpus(self):
  df=pd.read_csv(ROOT/'evidence/t1-20261001/matching-1/team_names.csv',keep_default_na=False)
  df['repaired']=df.input.map(self.match);df['repaired_verdict']=['unmatched' if pd.isna(x) else 'correct' if x==y else 'wrong' for x,y in zip(df.repaired,df.expected)]
  self.assertEqual((df.repaired_verdict=='wrong').sum(),0,df[df.repaired_verdict=='wrong'].to_string())
  out=new_run(ROOT/'evidence/t7-20261001');df.to_csv(out/'corpus.csv',index=False)
  summary=df.repaired_verdict.value_counts().to_dict();(out/'summary.json').write_text(json.dumps(summary,indent=2));print(summary)
if __name__=='__main__':unittest.main()
