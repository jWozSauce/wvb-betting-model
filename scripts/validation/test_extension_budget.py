"""Offline checks for the T3 reservation cap and cached-enumeration resume."""
import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.audit import extend_history as job
class Budget(unittest.TestCase):
 def test_reserved_request_never_reissued(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(job,'OUT',Path(tmp)),patch('oddspapi.api_key',return_value='DUMMY'),patch('safe_http.get') as request,patch.dict(os.environ,{}):
   job.atomic_json(Path(tmp)/'ledger.json',{'cap':1,'reserved':1,'state':'stopped','quota_before':{'used':5,'limit':250},'history_calls':0})
   with self.assertRaises(SystemExit):job.main()
   request.assert_not_called();self.assertEqual(json.loads((Path(tmp)/'ledger.json').read_text())['reserved'],1)
 def test_cached_fixture_enumeration_not_billed_again(self):
  class Account:
   def raise_for_status(self):pass
   def json(self):return {'request_count':6,'request_limit':250}
  with tempfile.TemporaryDirectory() as tmp,patch.object(job,'OUT',Path(tmp)),patch('oddspapi.api_key',return_value='DUMMY'),patch('safe_http.get',return_value=Account()) as request,patch.dict(os.environ,{}):
   p=Path(tmp);(p/'raw').mkdir();job.atomic_json(p/'raw/fixtures.json',{'status':200,'payload':[]})
   job.atomic_json(p/'ledger.json',{'cap':1,'reserved':1,'state':'history','history_calls':0,'quota_before':{'used':5,'limit':250},'quota_after_enumeration':{'used':6,'limit':250}})
   job.main();self.assertEqual(request.call_count,1);self.assertTrue(request.call_args.args[0].endswith('/account'))
   self.assertEqual(json.loads((p/'ledger.json').read_text())['reserved'],1)
if __name__=='__main__':unittest.main()
