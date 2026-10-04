# OddsPapi coverage and Bovada — T15, October 4, 2026

## Current status — Q10 revised sweep completed; final default proposed

The revised free sweep is complete: **22 candidates × 5 fixtures = 110 checks**,
36 new historical calls plus four compatible cached responses. Account usage
**15/250 → 15/250**, billable delta zero. Evidence:
`evidence/t15-20261004/coverage-2/` (raw responses, fixtures, timestamp bounds,
summary, ledger and independent datetime-versus-pandas timing check).

| Book | Any trails | Pregame fixtures | Supported pregame markets | Proposed role |
|---|---:|---:|---|---|
| DraftKings | 5/5 | 5/5 | Winner, set handicap | Bet prices and anchor |
| 1xBet | 3/5 | 3/5 | Winner, set handicap, total sets | Anchor only |
| bwin | 2/5 | 2/5 | Winner, set handicap, total sets | Anchor only |
| SBOBET | 2/5 | 1/5 | Winner | Anchor only |
| Hard Rock | 2/5 | 1/5 | Winner | Bet prices and anchor |
| Other 17 candidates | 0/5 each | 0/5 each | None returned | Excluded from default |

The 17 are bet365, bet365-nj, betmgm, betrivers, bovada.lv, caesars,
circasports, espnbet, fanatics, lowvig.ag, pinnacle, betonline.ag, fanduel,
bookmaker.eu, unibet, bcgame and cloudbet. Pinnacle +5/+30 were deliberately
omitted under Q10 and remain access-unverified, not classified as absent.
No-trail results apply to this five-fixture sample, not all NCAA volleyball.
Pregame means strictly before the provider's scheduled startTime; exact-start
and later timestamps count as post-start. Separate set-winner trails are reported
but are not supported by the current full-match pricer.

Final proposal, in anchor order: **SBOBET, DraftKings, Hard Rock, 1xBet, bwin**.
SBOBET supplies the sharp ML anchor where available; DK/Hard Rock remain bettable
sources; 1xBet/bwin add complementary pregame market coverage as fallback anchors.
All five meet the recorded pregame-evidence criterion. The international books
cannot win best-price selection, create a bet row, or be fetched alone from the
UI; they only inform the devig anchor for a line a bettable book quotes. Labels
make that distinction visible. Non-default Pinnacle variants retain sharp-first
priority if explicitly selected for a test. No subscription/access claim is made.

Five books cost 5 per uncached fetch: 150/month at one daily fetch, 300 at two.
The multiselect and per-selection cost display are therefore retained; owner can
reduce to the two bettable books (60/month at one/day). More coverage is not a
claim of better predictive accuracy. The full catalog remains missing (Q12);
known-books fallback is explicitly labelled, and no billable catalog fetch ran.

The new default remains behind default-off `WVB_ENABLE_BOOK_SELECTION` pending
acceptance. The owner approved ONE live test capped at five calls in Q11 after
this proposal. The gate uses persisted reservations, raw caches, before/after
quota and an independent selection/anchor check; no retry. Its live result is
recorded below after execution. This supersedes the earlier hardcoded two-book
proposal and its deferred two-call script described in the historical notes.


## Live gate — capture complete; acceptance gate incomplete

The Q11-approved fetch ran once on October 4 at approximately 17:28 EDT.
All **5/5** reservations were used; account quota **15/250 → 20/250**.
No retry, additional live fetch, catalog call, or AI call ran.

| Selected book | Response | Result |
|---|---|---|
| SBOBET | 200, empty array | Live anchor cannot be verified |
| DraftKings | 200, 3 fixtures | 1 fixture with 4 supported active outcome rows |
| Hard Rock | 404 | Live merge cannot be verified |
| 1xBet | 200, 2 fixtures | 6 supported outcome-active rows; bookmakerIsActive=false |
| bwin | 200, 3 fixtures | 18 supported active rows across 2 unsuspended fixtures; third suspended |

The default returns Kentucky at Florida with four rows, DraftKings best price
and anchor throughout. Independent best-price and devig checks pass on all four.
International-only markets do not become bet rows. The real bwin ML/spread prices
were merged internally; DK wins anchor priority. An **offline sensitivity check**
on the exact caches with bwin first produces the same four actionable DK rows,
now anchored to bwin, with ML probabilities independently checked. This proves
real bwin-schema merging, but is not a second live/default acceptance test.

1xBet's active outcome flags conflict with bookmakerIsActive=false. The existing
parser uses outcome activity plus suspension, not this book-level flag. Those
quotes did not win any default anchor or bet row. Their suitability as a fallback
is **cannot verify** until that flag's meaning is resolved; no schema guess was
implemented. This limitation is separate from historical pregame coverage.

Evidence: `evidence/t15-20261004/live-gate-1/` includes per-book raw captures,
ledger, decoded board, summary and `offline-assessment.json`. The original ledger's
`complete` means capture/replay finished, **not T15 acceptance**; the separate
assessment explicitly records `stopped_at_acceptance_gate`. The script now uses
`capture_complete_awaiting_acceptance` to remove that ambiguity on future approved
uses. Duplicate invocation remains refused; all existing captures are preserved.

The exact gate cannot be declared passed because Hard Rock and SBOBET produced
no usable board. Q13 asks the planner to assess these results and the activity flag,
with no further paid execution authorized. Q12's catalog portion remains open;
the new independently audited sweep supersedes its missing historical-probe
artifact dependency. No acceptance, production merge, enablement or push occurred.

Offline checks: final five-book selection/role UI, legacy rollback, cache and
invalidation checks, selection/anchor verifier, and budget/error-stop guards pass.
Timing counts independently agree for all 110 historical fixture/book checks.

## Prior status — planner stage-1 ruling received October 4

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
