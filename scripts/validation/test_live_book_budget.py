"""Offline guard verification for the deferred two-call live gate."""
import json,tempfile
from pathlib import Path
from unittest.mock import Mock,patch
from scripts.validation import live_book_gate as gate
from evidence_runs import new_run

with tempfile.TemporaryDirectory() as tmp, patch.object(gate,'OUT',Path(tmp)), \
 patch.object(gate,'validate_proposal'), patch.object(gate,'BOOKS',('draftkings','hardrockbet')), \
 patch.object(gate.oddspapi,'api_key',return_value='FAKE'), \
 patch.object(gate,'quota',side_effect=[{'used':10,'limit':250},{'used':12,'limit':250}]), \
 patch.object(gate.time,'sleep'), \
 patch.object(gate.safe_http,'get',return_value=Mock(status_code=404,json=lambda:{'code':'FIXTURE_NOT_FOUND'})) as fetch:
 gate.run()
 assert fetch.call_count==2
 ledger=json.loads((Path(tmp)/'ledger.json').read_text())
 assert ledger['reserved']==['draftkings','hardrockbet'] and ledger['cap']==5
 assert ledger['state']=='gate_failed_no_pregame_markets'
 try:gate.run()
 except RuntimeError:pass
 else:raise AssertionError('Duplicate attempt allowed')
 assert fetch.call_count==2
with tempfile.TemporaryDirectory() as tmp, patch.object(gate,'OUT',Path(tmp)), \
 patch.object(gate,'validate_proposal'), patch.object(gate,'BOOKS',('draftkings','hardrockbet')), \
 patch.object(gate.oddspapi,'api_key',return_value='FAKE'), \
 patch.object(gate,'quota',side_effect=[{'used':10,'limit':250},{'used':11,'limit':250}]), \
 patch.object(gate.time,'sleep'), \
 patch.object(gate.safe_http,'get',return_value=Mock(status_code=403)) as fetch:
 try:gate.run()
 except SystemExit:pass
 else:raise AssertionError('403 did not stop gate')
 assert fetch.call_count==1
 ledger=json.loads((Path(tmp)/'ledger.json').read_text())
 assert ledger['reserved']==['draftkings'] and ledger['state']=='stopped'
 assert ledger['quota_after_stop']['used']==11
out=new_run(gate.ROOT/'evidence/t15-20261004/budget')
checks=dict(cap_five_two_selected=True,reserve_before_call=True,empty_counts=True,duplicate_attempt_refused=True,authorization_error_stops_first_call=True,quota_checked_on_stop=True,real_calls=0)
(out/'checks.json').write_text(json.dumps(checks,indent=2));print(out)
