# OddsPapi coverage and Bovada — T15, October 4, 2026

## Current status — planner stage-1 ruling received October 4

**T15 stage 2 in progress; blocked on catalog/probe artifacts and live-call approval.**
The planner reports a completed five-fixture × 18-candidate free probe:
DraftKings 5/5 (ML/spread), Hard Rock 5/5 (ML), others absent on that sample.
These are planner-reported results, not worker-verified pregame trails: raw
responses, times and quota evidence have not yet been placed in this checkout.
Q12 requests those artifacts plus the full valid bookmaker catalog. No second
coverage sweep was started; the earlier worker access-error stop remains preserved.

The updated review path now defaults to **DraftKings, Hard Rock**, in that anchor
order. Old Pinnacle/FanDuel/BetOnline defaults are removed from the enabled review
path, with explicit legacy rollback when `WVB_ENABLE_BOOK_SELECTION=0` (still the
default until acceptance). One fresh fetch costs 2 requests: 60/month at one/day,
120 at two/day, 180 at three/day (30-day assumptions). Non-default selections still
show their own cost. Choosing a sharp Pinnacle variant places it before the default
books for anchoring, without changing the best-line calculation.

`oddspapi.available_books()` reads the provider-schema array at
`app_data/oddspapi_bookmakers.json` without a billable catalog call. This artifact
is missing: the UI explicitly labels a limited fallback of known default/legacy
books. It does not claim the full catalog is available. Once the supplied catalog
is installed, every valid slug becomes selectable, including non-default books
for manual retesting. A catalog entry is not a claim of NCAA coverage. BetOnline
and Bovada website odds remain usable through T12's paste/bookmarklet flow.

Offline gate passes at
`evidence/t15-20261004/offline/run-20261004T205643.616145Z-2f155run/checks.json`:
2-request default, Hard Rock best-price merge, DK anchor, optional Pinnacle anchor,
full supplied-catalog parsing (temporary representative fixture only), missing and
invalid catalog handling, cache-by-selection, stale-board invalidation and no calls
on selection change/empty selection. T14's confirmation/persistence suite also
passes after this amendment. No real external calls occurred this turn.

The real two-book gate is prepared as `scripts/validation/live_book_gate.py`; it
requires recorded owner approval then `--owner-approved-two-calls`, caps reservations
at two, caches each raw response, refuses rerunning an attempted ledger, and records
account counts. Offline ledger guards also pass (two-call cap, empty responses counted, duplicate
attempt refused, first-call 403 stops, quota checked on stop), in
`evidence/t15-20261004/budget/run-20261004T205853.059216Z-4epebqdi/`.
It has not been run against the provider. Once
captured, the live prices still need comparison against each book's raw quotes to
complete the unchanged best-line/anchor acceptance gate. Q11 spending remains open;
its earlier five-call proposal is reduced to two for the new default.

## Earlier worker probe and preparation (superseded where noted)

**Stopped at a gate.** The free historical coverage probe stopped at HTTP 403
on its fifth request. It did not retry or continue past that authorization error.
The required five-fixture coverage sweep and real new-default live fetch are not
complete. No production changes or billable calls occurred.

`evidence/t15-20261004/coverage-1/` contains the checkpoint ledger, five selected
fixtures, credential-free request metadata, cached raw responses, per-fixture
coverage and partial summary. Account usage was **10/250 before and 10/250 after**,
including the rejected request: measured billable delta zero. An initial sandbox
network failure occurred before any historical request and is retained in the
ledger; the network-enabled attempt made five requests, at least 5.2 seconds apart.
No probe remains running. Do not start another history sweep while resuming this.

The five latest known-boarded fixtures in the cached September 30 enumeration are
Michigan State–Penn State, Oklahoma–Florida, Colorado–Arizona, Utah–Baylor
(September 27), and LSU–Vanderbilt (September 30). No billable enumeration was
needed. The current 361-slug catalog was not in the workspace; `/bookmakers` is
billable, so it was not fetched under the free-stage authorization. The probe uses
the 17 exact candidate slugs in the plan. The public provider guide also verifies
`bookmaker.eu` as an additional plausible candidate for the resumed sweep.

Only Michigan State–Penn State was attempted before the stop:

| Candidates | Response | Evidence |
|---|---:|---|
| bet365, bet365-nj, betmgm | 404 | No trails returned for this one fixture |
| betrivers, bovada.lv, caesars | 404 | No trails returned for this one fixture |
| circasports, espnbet, fanatics | 404 | No trails returned for this one fixture |
| hardrockbet, lowvig.ag, pinnacle | 200 | Hard Rock Winner trails only, all after scheduled start |
| pinnacle+5, pinnacle+30, betonline.ag | 403 | Access refused; no coverage conclusion for any member |
| draftkings, fanduel | Not attempted | Stopped before this batch |

Post-start is a timing classification, not proof of a provider's live-status flag.
A one-fixture absence is not evidence that a book never covers NCAA women.
A batch 403 does not identify which member caused the refusal. Existing cached
history contains pregame DraftKings quotes only (89 fixtures in the extension), but it
cannot substitute for the requested new sweep.

Independent preparation completed: `WVB_ENABLE_BOOK_SELECTION=1` enables a
book multiselect with the existing Pinnacle, DraftKings, FanDuel and BetOnline set.
The switch defaults **0**; the deployed four-book behavior stays intact until
acceptance. The planner amendment arrived during handoff and supersedes the earlier
unconditional Bovada addition: Bovada is now absent from BOOKS and from selectable
options until real historical coverage is found. Earlier mock Bovada decoder work
is retained as a test, not coverage evidence. No new book is promoted on incomplete
or post-start-only evidence. BetOnline website odds remain available through the
T12 paste/bookmarklet manual-match flow regardless of current API availability.
Selections are always ordered sharp-first; each cache key includes the selected
books. Changing selection invalidates the prior card/saved board, without a fetch.
Empty selection disables fetching. Mocked Bovada best prices merge while Pinnacle
remains the devig anchor. No real Bovada board has been verified.

Quota math, assuming a 30-day month: four books × one uncached fetch/day = 120;
five books = 150. At two/day, five books = 300, above the 250 allowance (and the
plan's ~180 soft ceiling). The actual owner's frequency is unknown, so the
multiselect is provided rather than silently fixing a larger set. Three selected
books at two/day = 180. Cache hits cost zero; each uncached book consumes one
request even if empty. The current unexpanded set costs **4 billable requests** per fresh fetch.
Q11 proposed a ceiling of five for an eventual evidenced expansion; written owner
spending approval is still needed before any billable gate. Any later evidence-based expansion needs a revised cap before that gate.

Sources: [request accounting](https://oddspapi.io/us/docs/requests-and-quota),
[historical schema, maximum three books, and 5-second cooldown](https://oddspapi.io/us/docs/get-historical-odds),
[BookMaker.eu slug](https://oddspapi.io/sportsbooks/bookmaker-eu).

Offline evidence: `evidence/t15-20261004/offline/run-20261004T204859.365387Z-0mys_8k4/checks.json`.
The final test enables T14 and T15 together, verifies book-set caching, selected-book
order and stale-board clearing. T14 recheck and existing T12 source regression also
pass in `evidence/t14-20261004/run-20261004T204716.891119Z-nos2sttk/` and
`evidence/t12-20261004/run-20261004T204735.831219Z-8qlbskfr/`. An initial test-harness
timeout was traced to patching Python's shared `time.sleep` while AppTest booted;
the harness no longer patches that clock, and the completed suite passes.

October 4 amendment correction: the first report draft incorrectly attributed
FanDuel/BetOnline quotes to the saved historical table. Inspection shows DraftKings
only (77 fixtures in the original, 89 in the extension). This has been corrected
above. A one-time live 404 cannot establish that a provider has never carried a
book; the incomplete historical sweep remains the test of that claim.

Amended final offline gate passes at
`evidence/t15-20261004/offline/run-20261004T205226.652906Z-nn6kacsi/checks.json`:
Bovada is excluded from UI choices/defaults; explicit synthetic decoder input
still proves the prepared best-line/anchor merge. Joint T14/T15 UI, cache,
invalidation and empty-selection checks remain green.
