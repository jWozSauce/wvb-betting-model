"""Allocate a fresh evidence directory without replacing prior validation runs."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile


def new_run(parent):
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    result = Path(tempfile.mkdtemp(prefix=f'run-{stamp}-', dir=parent))
    print(f'Evidence: {result}', flush=True)
    return result
