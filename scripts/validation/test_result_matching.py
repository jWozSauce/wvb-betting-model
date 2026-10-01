import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import bet_log
class Matching(unittest.TestCase):
 def run(self,result=None):
  with patch.dict(os.environ,{'WVB_ENABLE_REPAIRS':'1'}):return super().run(result)
 def rows(self):
  return pd.DataFrame([dict(contest_id=1,date='2026-09-30',home_seo='a',away_seo='b'),dict(contest_id=2,date='2026-10-01',home_seo='b',away_seo='a')])
 def test_exact_reversed_beats_neighbor(self):
  row,flip=bet_log._find_result(self.rows(),'a','b','2026-10-01');self.assertEqual(row.contest_id,2);self.assertTrue(flip)
 def test_tied_neighbors_refused(self):
  df=self.rows();df.loc[1,'date']='2026-10-02';self.assertIsNone(bet_log._find_result(df,'a','b','2026-10-01')[0])
 def test_same_day_doubleheader_refused(self):
  df=self.rows();df['date']='2026-10-01';self.assertIsNone(bet_log._find_result(df,'a','b','2026-10-01')[0])
 def test_no_match_or_bad_date(self):
  self.assertIsNone(bet_log._find_result(self.rows(),'a','b','2026-10-05')[0]);self.assertIsNone(bet_log._find_result(self.rows(),'a','b','bad')[0])
 def test_current_exact_reversed(self):
  df=pd.read_parquet('app_data/results_current.parquet');df['date']=pd.to_datetime(df.start_epoch,unit='s',utc=True).dt.tz_convert('America/New_York').dt.date
  wrong=ambiguous=0
  for r in df.itertuples():
   hit,_=bet_log._find_result(df,r.away_seo,r.home_seo,r.date)
   if hit is None:ambiguous+=1
   elif hit.contest_id!=r.contest_id:wrong+=1
  self.assertEqual(wrong,0);print('Current results: wrong',wrong,'refused',ambiguous)
 def test_default_off(self):
  with patch.dict(os.environ,{'WVB_ENABLE_REPAIRS':'0'}):self.assertEqual(bet_log._find_result(self.rows(),'a','b','2026-10-01')[0].contest_id,1)
if __name__=='__main__':unittest.main()
