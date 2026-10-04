# Live API team matching — T14, October 4, 2026

Implementation complete, awaiting planner acceptance and cloud credential setup.
The new path defaults OFF (`WVB_ENABLE_LIVE_TEAM_MAP=0`). No deployment or real
repository mapping writes were performed. No paid API or real Sheets calls.

The Live API decoder now retains fixture and home/away participant IDs. The
pricing path consults owner-confirmed IDs before any name matching. A missing,
ambiguous, low-confidence or same-team match stays in a visible correction table,
with searchable `seoname — name_full` choices and an explicit confirmation for
both sides. Confirmation re-evaluates the cached board without another odds call.
Odds sides keep the vendor's orientation. All four sources use the existing
pricing/card/log path. No matcher heuristics changed.

Confirmations update only `app_data/oddspapi_team_map.json`. It starts empty;
no machine guesses are silently promoted into owner confirmations. The default
cloud adapter reads this fixed path on main and writes via GitHub Contents API
with its current blob SHA. Unrelated changes are merged; same-ID conflicts and
HTTP 409 stop for a refresh, without retries. A timed-out write is explicitly
reported as unknown and requires a read before retry. Response bodies, URLs with
credentials, and tokens are never shown. An explicit `WVB_MAPPING_STORAGE=local`
mode uses a file lock plus atomic replace; local changes need the ordinary Git
review/commit process. This local mode must not be used for durable cloud storage.

Cloud setup before enabling: owner configures `TEAM_MAP_GITHUB_TOKEN` in
Streamlit secrets, a fine-grained GitHub credential scoped to this repository with
Contents read/write. `APP_PASSWORD` must be set; the adapter exposes the credential
only after the existing password gate authenticates the session. No credential
was created or inspected here. Existing public/no-password sessions cannot write.
Each confirmed change creates a mapping-only commit to main and may trigger cloud
redeployment. This is the permanent storage path requested by T14; acceptance
should explicitly include this runtime behavior. No code or arbitrary path can be
written by the mapping UI.

The ratings workflow stages app_data broadly, but its build scripts do not write
this mapping JSON. It fetches/rebases before pushing; an upstream mapping commit
therefore survives the normal ratings update. No workflow change was needed.

Verification: `PYTHONPATH=. .venv/bin/python scripts/validation/test_live_team_map.py`
uses the actual Streamlit app. Purdue/Washington initially refuses pricing,
confirmation produces two markets, and a brand-new session produces the identical
card with no prompt. ID resolution survives a vendor spelling change. Duplicate
schools are refused. The local stale-writer check preserves another session's
change. Mocked GitHub checks cover fixed path, blob SHA, unrelated-map merge, and
409 without retry; real GitHub credentials/cloud runtime remain unverified.

The feature-off Live API card and enabled-feature paste card exactly equal the
pre-task app. T12's actual UI suite verifies existing live/paste parity, all manual
source gates and no real writes; integrated-defaults boot verifies the NCAA source.
The decoder test verifies ID propagation plus best-line/anchor separation.

The committed participant reference contains 2,573 entries across volleyball,
not only NCAA women. The cached NCAA tournament enumeration identifies 338
participant IDs (including the named Purdue/Washington case); 228 currently need
confirmation. Those refused names plus Purdue were added as static regressions.
Existing T7 corpus: 1,596 correct, zero wrong. These are refusal regressions, not
228 newly verified identity mappings; the owner supplies those via the UI.

Sources: [GitHub Contents API](https://docs.github.com/en/rest/repos/contents),
including the required blob SHA and repository Contents permission.

Evidence for the final matching implementation:
- `evidence/t14-20261004/run-20261004T204405.846421Z-0z1ye1zq/`
- `evidence/t7-20261001/run-20261004T204300.911082Z-faln2f7t/`
- `evidence/t12-20261004/run-20261004T204249.853013Z-325bniwb/`
- `evidence/integration-20261001/run-20261004T204327.346243Z-eutpu76g/`
