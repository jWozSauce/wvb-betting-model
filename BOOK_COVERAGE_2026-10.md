# OddsPapi coverage and Bovada — T15, October 4, 2026

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
history separately contains pregame DraftKings/FanDuel/BetOnline quotes, but it
cannot substitute for the requested new sweep.

Independent preparation completed: `WVB_ENABLE_BOOK_SELECTION=1` enables a
book multiselect with Pinnacle, DraftKings, FanDuel, BetOnline and Bovada by default.
The switch defaults **0**; the deployed four-book behavior stays intact until
acceptance. Bovada is included because the owner requested it regardless of probe
coverage. No further book was promoted on incomplete or post-start-only evidence.
Selections are always ordered sharp-first; each cache key includes the selected
books. Changing selection invalidates the prior card/saved board, without a fetch.
Empty selection disables fetching. Mocked Bovada best prices merge while Pinnacle
remains the devig anchor. No real Bovada board has been verified.

Quota math, assuming a 30-day month: four books × one uncached fetch/day = 120;
five books = 150. At two/day, five books = 300, above the 250 allowance (and the
plan's ~180 soft ceiling). The actual owner's frequency is unknown, so the
multiselect is provided rather than silently fixing a larger set. Three selected
books at two/day = 180. Cache hits cost zero; each uncached book consumes one
request even if empty. The required real gate at the prepared default has a
maximum cost of **5 billable requests**; written owner spending approval is still
needed. Any later evidence-based expansion needs a revised cap before that gate.

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
