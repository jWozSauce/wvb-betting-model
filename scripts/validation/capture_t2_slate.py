"""Free NCAA first-load timing and raw-response capture. No paid services."""
import argparse
import datetime as dt
import json
from pathlib import Path
from evidence_runs import new_run
import sys
import time
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from schedule_pricing import fetch_slate, schedule_response, game_response
from vbstats.ncaa import NCAAClient

parser = argparse.ArgumentParser()
parser.add_argument('--date', default='2026-10-02')
parser.add_argument('--output', required=True)
args = parser.parse_args()
out = new_run(args.output)
# Exclusive lock prevents duplicate network validation jobs.
lock = ROOT/'evidence/t2-20261001/capture.lock'
with lock.open('x') as f:
    f.write(str(out))
try:
    original = NCAAClient._gql
    requests = []
    def capture(self, meta, variables):
        start = time.perf_counter()
        requested_at = dt.datetime.now(dt.timezone.utc).isoformat()
        data = original(self, meta, variables)
        record = dict(meta=meta, variables=variables, requested_at=requested_at,
                      seconds=time.perf_counter()-start, data=data)
        # Save returned payload before the caller parses it into rows.
        with (out/f'response-{len(requests):03}.json').open('x') as f:
            json.dump(record, f)
        requests.append(record)
        return data
    ratings = pd.read_parquet(ROOT/'app_data/elo_current.parquet')
    venues = pd.read_parquet(ROOT/'app_data/home_venues.parquet')
    progress = []
    def show(value, message):
        progress.append(dict(fraction=value, message=message))
        if len(progress) % 20 == 0:
            print(message, flush=True)
    schedule_response.clear()
    game_response.clear()
    start = time.perf_counter()
    with patch.object(NCAAClient, '_gql', capture):
        slate = fetch_slate(dt.date.fromisoformat(args.date), ratings, venues, show)
    cold = time.perf_counter()-start
    start = time.perf_counter()
    with patch.object(NCAAClient, '_gql', side_effect=AssertionError('Warm load fetched network')):
        warm = fetch_slate(dt.date.fromisoformat(args.date), ratings, venues)
    warm_seconds = time.perf_counter()-start
    assert len(slate['priced'])+len(slate['unpriced']) == slate['fetched']
    result = dict(date=args.date, first_load_seconds=cold, warm_load_seconds=warm_seconds,
                  requests=len(requests), rated=len(slate['priced']), unpriced=len(slate['unpriced']),
                  fetched=slate['fetched'], raw_count=slate['raw_count'], duplicates=slate['duplicates'],
                  progress=progress)
    (out/'slate.json').write_text(json.dumps(slate, indent=2))
    (out/'timing.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='progress'}, indent=2))
finally:
    lock.unlink()
