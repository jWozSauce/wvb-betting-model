"""No-network cap, capture, schema, and duplicate-attempt checks."""
import json,tempfile
from pathlib import Path
from unittest.mock import Mock,patch
from scripts.audit import fetch_bookmaker_catalog as f
for status in (200,403):
 with tempfile.TemporaryDirectory() as tmp,patch.object(f,'OUT',Path(tmp)/'evidence'),patch.object(f,'TARGET',Path(tmp)/'catalog.json'),patch.object(f.oddspapi,'api_key',return_value='fake-secret'),patch.object(f,'quota',side_effect=[{'used':20,'limit':250},{'used':21,'limit':250}]),patch.object(f.safe_http,'get',return_value=Mock(status_code=status,json=lambda:[{'slug':b} for b in f.oddspapi.BOOKS])) as request:
  try:f.run()
  except SystemExit:assert status==403
  assert request.call_count==1 and request.call_args.kwargs['allow_redirects'] is False
  ledger=json.loads((f.OUT/'ledger.json').read_text());assert ledger['reserved']==ledger['cap']==1
  assert ledger['state']==('complete' if status==200 else 'stopped')
  assert f.TARGET.exists()==(status==200)
  try:f.run()
  except RuntimeError:pass
  else:raise AssertionError('Duplicate attempt accepted')
  assert request.call_count==1
print('PASS one-call reservation, HTTP failure stop, no redirect/retry, immutable duplicate refusal; real calls=0')

with tempfile.TemporaryDirectory() as tmp,patch.object(f,'OUT',Path(tmp)/'evidence'),patch.object(f,'TARGET',Path(tmp)/'catalog.json'),patch.object(f.oddspapi,'api_key',return_value='fake-secret'),patch.object(f,'quota',side_effect=[{'used':25,'limit':250},f.safe_http.SafeHTTPError('account: HTTP 429')]) as account,patch.object(f.safe_http,'get',return_value=Mock(status_code=200,json=lambda:[{'slug':b} for b in f.oddspapi.BOOKS])) as request:
 try:f.run()
 except SystemExit:pass
 else:raise AssertionError('Rate limit did not stop job')
 assert account.call_count==2 and request.call_count==1
 assert (f.OUT/'raw.json').exists() and not f.TARGET.exists()
 ledger=json.loads((f.OUT/'ledger.json').read_text());assert ledger['state']=='stopped' and ledger['reserved']==1
print('PASS after-account 429 preserves raw cache and stops without retry; real calls=0')
