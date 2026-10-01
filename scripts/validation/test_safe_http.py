import os,sys,unittest,traceback
from pathlib import Path
from unittest.mock import patch
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[2]));import safe_http,oddspapi
class SafeErrors(unittest.TestCase):
 def run(self,result=None):
  with patch.dict(os.environ,{'WVB_ENABLE_REPAIRS':'1'}):return super().run(result)
 def test_http_status(self):
  for status in [401,403,429,500]:
   r=requests.Response();r.status_code=status;r.url='https://example.invalid/v4/odds-by-tournaments?apiKey=FAKE_SECRET'
   with patch('requests.get',return_value=r):
    with self.assertRaises(safe_http.SafeHTTPError) as caught:oddspapi.fetch_board(books=('draftkings',),key='FAKE_SECRET')
   self.assertNotIn('FAKE_SECRET',str(caught.exception));self.assertIn(str(status),str(caught.exception))
 def test_transport_traceback(self):
  for error in [requests.Timeout('FAKE_SECRET'),requests.ConnectionError('FAKE_SECRET')]:
   url='https://example.invalid/v4/fixtures?apiKey=FAKE_SECRET'
   with patch('requests.get',side_effect=error):
    try:safe_http.get(url)
    except safe_http.SafeHTTPError:
     self.assertNotIn('FAKE_SECRET',traceback.format_exc())
 def test_json_error(self):
  r=requests.Response();r.status_code=200;r._content=b'FAKE_SECRET'
  with patch('requests.get',return_value=r):
   with self.assertRaises(safe_http.SafeHTTPError) as e:safe_http.get('https://example.invalid/v4/account').json()
  self.assertNotIn('FAKE_SECRET',str(e.exception))
 def test_arbitrary_app_exception(self):self.assertNotIn('FAKE_SECRET',safe_http.public_error(ValueError('FAKE_SECRET')))
 def test_404_empty_board(self):
  r=requests.Response();r.status_code=404
  with patch('requests.get',return_value=r):self.assertEqual(oddspapi.fetch_board(books=('draftkings',),key='FAKE_SECRET'),([],1))
if __name__=='__main__':unittest.main()
