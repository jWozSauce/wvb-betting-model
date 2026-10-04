"""Offline assessment of T15's one approved capture. Never contacts a provider."""
import json, sys
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import oddspapi
from scripts.validation.live_book_gate import verify_prices
OUT = ROOT / 'evidence/t15-20261004/live-gate-1'
cache = {b: json.loads((OUT / f'{b}.json').read_text()) for b in oddspapi.BOOKS}
class Cached:
    def __init__(self, book):
        self.data = cache[book]
        self.status_code = self.data['status']
    def raise_for_status(self):
        assert self.status_code == 200
    def json(self):
        return self.data['payload']
def replay(books):
    with patch.object(oddspapi.safe_http, 'get', side_effect=lambda url, **kw: Cached(kw['params']['bookmaker'])), patch.object(oddspapi.time, 'sleep'):
        return oddspapi.fetch_board(books=books, key='offline-cache-only')[0]
games = replay(oddspapi.BOOKS)
assert games == json.loads((OUT / 'decoded-board.json').read_text())
assert verify_prices(games, cache) == 4
inventory = []
for b, blob in cache.items():
    for f in blob['payload'] if blob['status'] == 200 else []:
        bo = f['bookmakerOdds'][b]
        rows = oddspapi._decode_book(bo.get('markets'), oddspapi._markets_map())
        inventory.append(dict(book=b, fixture_id=f['fixtureId'], start_time=f['startTime'], status_id=f['statusId'], bookmaker_is_active=bo.get('bookmakerIsActive'), suspended=bo.get('suspended'), supported_active_outcomes=len(rows), decoded_rows=rows))
# Sensitivity check on the same captured prices, not a second live/default gate:
# promoting bwin to first anchor proves its real returned quotes merge by fixture/line.
books = ('bwin',) + tuple(b for b in oddspapi.BOOKS if b != 'bwin')
alternate = replay(books)
assert len(alternate) == 1 and len(alternate[0]['markets']) == 4
assert all(r['book'] == 'draftkings' and r['devig_book'] == 'bwin' for r in alternate[0]['markets'])
import kelly
raw_bwin = {r['side']: r['odds'] for r in inventory[-1]['decoded_rows'] if r['market'] == 'ml'}
for row in alternate[0]['markets']:
    if row['market'] == 'ml':
        other = 'away' if row['side'] == 'home' else 'home'
        assert row['mkt_prob'] == round(kelly.vig_free_probs(raw_bwin[row['side']], raw_bwin[other])[0], 4)
result = dict(state='stopped_at_acceptance_gate', capture_complete=True, default_replay_identical=True, default_markets_verified=4, live_requests=5, quota_before=15, quota_after=20, additional_requests=0, fixture_inventory=inventory, bwin_first_diagnostic=alternate, remaining=['Hard Rock returned HTTP 404; its live merge cannot be verified.', 'SBOBET returned an empty array; its live anchor cannot be verified.', '1xBet returned outcome-active prices with bookmakerIsActive=false; semantics need review before relying on that fallback.', 'Full bookmaker catalog is absent (Q12).'], caveat='Original ledger complete denotes capture/replay completion, not T15 acceptance. Altered anchor priority is offline diagnostic evidence only.')
path = OUT / 'offline-assessment.json'
with path.open('x') as out:
    json.dump(result, out, indent=2)
print(json.dumps({k: v for k, v in result.items() if k not in ('fixture_inventory', 'bwin_first_diagnostic')}, indent=2))
