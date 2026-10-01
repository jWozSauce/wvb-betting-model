# Authorized repair handoff — October 1, 2026

**Implementation complete, awaiting planner acceptance.** Branch:
`codex/review-repairs`. No push, merge, deployment or real Sheets write.
Review with `WVB_ENABLE_REPAIRS=1`; the repair behavior and annotations default
off. The separate schedule feature still requires `WVB_ENABLE_NCAA_SCHEDULE=1`.
The owner's D1 replacement-player decision remains open; lineup math is unchanged.

| Task | Change | Validation | Commit |
|---|---|---|---|
| T6 | Search both result orientations together; nearest calendar date wins; tied fixtures are refused | Six tests; 2,287 reversed queries: zero wrong matches, 14 ambiguous refusals. 43 real bet rows + 159 paper rows reviewed read-only: zero lookup or grade changes | `c9c9b71` |
| T7 | Exact known identities before whole-name aliases; preserve campus and ampersand distinctions; reject unknown/ambiguous names | All 1,596 corpus cases correct, versus 26 wrong and three unmatched before. Five tests cover Utah/UTA, USC/Upstate, Miami, LSU/New Orleans, Missouri S&T/St., ambiguous and unknown names | `4e0c7c0` |
| T8 | Invalidate cards when inputs change; retain and log the exact pricing snapshot | Seven control edits invalidate the card; $500→$1,000 bankroll changes $31.50→$63 after reevaluation. A nonempty mocked paper record matches the snapshot | `1ce6412` |
| T9 | Provider errors expose allowlisted endpoint/status only; suppress credential-bearing exception chains and arbitrary UI error details | Five unit checks for status, network, JSON and 404; actual API UI exercised with fake credential exception | `c5fb92c` |
| Small T4 defects | Explain last-match defaults vs season reference; refuse player pricing when either roster is unavailable | Spring Hill–Kansas in Player and Hybrid modes shows an actionable message without crashing | `3922cef` |
| T5 | Shared rank metric powers absence labels and lineup options; rank within same team/position among teammates with ≥1 set started | Five actual Player ranks comparisons, ties/zero-start/unknown checks; underlying selection IDs and prices unchanged | `599c35b` |

Additional integration checks compare the pre-repair application at `c7fd873`
with this branch: 18 manual boards (three models × three venue modes × switch
off/on), each with 16 market rows, match exactly. Two Best bets card comparisons
also match on all pricing/staking columns. Annotation text is intentionally
excluded from the enabled comparison. These checks use mocks for all external
calls and logs; they do not certify current provider nonempty-board compatibility.
Evidence: `evidence/repairs-20261001/parity.json`.

## T6 owner-record review

The review used a read-only OAuth scope, bypassing the schema-migrating `_ws`
helper. No affected rows were found among the 202 currently logged rows.
The private affected-row list is empty at
`/tmp/volleyball-t6-grading-exposure-20261001.json`; the aggregate result is
committed at `evidence/t6-20261001/exposure_summary.json`. No real record needs
a correction based on this check. This is exposure under the available local
results snapshot, not proof about all prior grading runs or deleted records.

## T7 matching tradeoff

Unrecognized names no longer receive fuzzy guesses. The known corpus loses no
coverage, but a new vendor spelling may now require an explicit reviewed alias.
No arbitrary prefix can turn a new campus into a different school's priced bet.
The finite corpus cannot certify every future book spelling. Whole normalized
names define the alias boundary; mascot suffixes outside the known identity
are refused rather than silently stripped.

## T8 snapshot behavior

Changing bankroll, conservative basis, blend, minimum edge, venue, Kelly fraction
or cap removes the card and its logging controls until the user evaluates again.
Source text, ratings, model draws and availability are also part of the snapshot.
Reevaluation resets selections in the card editor. This avoids a paid automatic
refetch when only settings change. The next deliberate fetch uses the existing
API cache behavior. Logs use the stored snapshot, not live sidebar variables.

The first logging test produced zero records because the fixture was excluded
by the existing absence filter. That run did not validate record contents.
`evidence/t8-20261001/run-2/` is the decisive test: the filter is deliberately
stubbed, one record is captured, and every context field matches exactly.

## T5 annotation examples

The metric is rally **points per set**, not ML percentage points or a causal
injury effect. It uses the exact shared Player ranks rounding of serve and
receive contributions. Tied impacts share rank; the denominator counts eligible
teammates with the same literal position label.

| Player | Display |
|---|---|
| Harper Murray | +1.43 pts/set, #1 of 5 OH |
| Olivia Babcock | +1.78 pts/set, #1 of 6 OH |
| Bergen Reilly | +1.36 pts/set, #1 of 2 S |
| Teraya Sigler | +0.78 pts/set, #2 of 5 OH |
| Ayanna Watson | +0.44 pts/set, #4 of 6 OH |

Deterministic absence warnings, lineup options and slate absence text use these
annotations. Free-text news/AI prose is not rewritten. Missing or ambiguous
player identity and ineligible current-season players display `(unrated)`.
No replacement-level semantics or price effect was added.

## Credential handling and owner action

The planner reported that a real OddsPapi key appeared in a chat error URL on
September 26. This worker did not reproduce or print that key. The repair prevents
credential-bearing HTTP errors from reaching these app/collector surfaces when
enabled; it cannot undo earlier exposure. The planner recommends owner rotation
of the key. Rotation has not been performed and requires updating the owner's
local/cloud configuration. This report contains no credential values.

## Reproduction and boundaries

Unit checks: `scripts/validation/test_result_matching.py`,
`test_team_matching.py`, `test_safe_http.py`. UI checks: `test_card_state.py`,
`test_player_guards.py`, `test_player_annotations.py`, `test_repair_parity.py`.
UI output directories are exclusive; preserve prior evidence when rerunning.
Owner basketball reference files are untouched. Review switches remain off
until acceptance; accepting one repair does not authorize an unreviewed bundle
for production. T3's external-data extension is separately logged in PLANS.md
and its budget ledger.
