"""Verify the captured Q12 catalog in a temporary app directory; no network."""
import json,tempfile
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from validate_t2_ui import ROOT,guards,new_app,check
import oddspapi
raw=ROOT/'evidence/q12-catalog-20261005/raw.json'
rows=json.loads(raw.read_text())['payload'];slugs={r['slug'] for r in rows}
assert len(rows)==len(slugs)==363
with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
 guards(stack)
 stack.enter_context(patch.object(oddspapi,'HERE',Path(tmp)))
 path=Path(tmp)/'app_data';path.mkdir();(path/'oddspapi_bookmakers.json').write_text(json.dumps(rows))
 books,complete=oddspapi.available_books();assert complete and set(books)==slugs
 fetch=stack.enter_context(patch('oddspapi.fetch_board',side_effect=AssertionError('Fetch not permitted')))
 app=new_app((ROOT/'streamlit_app.py').read_text())
 widget=app.multiselect(key='api_books')
 labels={f'{slug} (anchor only)' if slug in oddspapi.ANCHOR_ONLY_BOOKS else slug for slug in slugs}
 assert set(widget.options)==labels and widget.value==list(oddspapi.BOOKS)
 assert not any('Full bookmaker catalog is unavailable' in e.value for e in app.caption)
 widget.set_value(['pinnacle','draftkings']);check(app.run())
 assert app.multiselect(key='api_books').value==['pinnacle','draftkings']
 assert fetch.call_count==0
print('PASS actual cached catalog: 363 unique options, five defaults, selection change without fetch; real calls=0')
