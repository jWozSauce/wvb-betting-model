# T16 — Bulk identity review and conservative learning

Accepted by the planner on 2026-10-05 and pushed to production main in
`551e963`, after rebasing on the ratings bot's `0c84c7b`. The separate
`5ec2a1f` switch commit enables `WVB_ENABLE_LEARNED_MATCHING=1` by default;
set it to `0` for rollback. The Team matching tab is included in this release.
Local AppTest and server health passed; hosted-cloud startup was not observed.
Cloud mapping-token setup remains owner-deferred, so durable cloud confirmations
remain unavailable until the owner configures that credential.

The review tab lists all 228 currently unresolved names in the cached NCAA
inventory of 338 participant IDs. Suggestions use exact school prefixes where
available, otherwise a similarity ranking; every suggestion is labelled unconfirmed.
The owner chooses a batch, corrects individual searchable school selections, and
explicitly confirms the batch. One T14 storage operation saves the ID→school pairs
atomically, with the existing GitHub blob-SHA/concurrent-change checks. Saved names
leave the review list; a fresh session can load the same permanent mapping.

The deployed T14 credential requirements remain: cloud writes require the owner's
repository Contents credential and authenticated APP_PASSWORD session. Explicit
local mode writes only a local file; it is not durable Streamlit cloud storage.
No credential setup, real confirmations or mapping writes were performed here.

Learning happens in memory from confirmed IDs and their cached provider names.
Confirmed IDs always win, even if the provider later changes the name. No candidate
rule ever writes the confirmation file or overrides its contents. Exact normalized
aliases and mascot suffix candidates are considered; a suffix needs confirmations
from two different schools. Campus/directional/academic words are never learned
as removable suffixes. Existing unambiguous school matches remain unchanged;
multiple candidate identities refuse instead of choosing a highest score.

Every candidate is checked against 1,596 known identity cases, 229 live-name
regressions (228 refusals plus Purdue), and the accumulated confirmed pairs. A
refusal regression may be released only by its explicit, unambiguous owner answer.
Any wrong match rejects the candidate. Missing/invalid validation data refuses name
inference while preserving exact confirmed IDs. Rules are regenerated for each new
mapping/roster combination and cached within the process; none ship as an unchecked
persistent artifact. This conservative policy can reject a useful generalization
until more names are confirmed; zero wrong matches on the finite corpus does not
prove correctness of every unseen name. New NCAA IDs outside the cached inventory
remain handled by T14's per-slate review until the inventory is deliberately updated.

Verification uses the actual Streamlit app with external IO blocked and a temporary
mapping file. Twenty explicit mock owner choices save in one call; current-session
rerun clears the removed selections; a new session reloads the same mappings.
Unresolved counts are **228→208** in that mocked scenario. All **1,845 validation
cases** (including those 20 answers) have zero wrong matches; all 1,596 known cases
retain exact identities. A synthetic two-school mascot generalizes to a third
school, while unknown-campus and ambiguous-school names refuse. A contradicted
known identity cannot train a rule, stale batch writes preserve the other session,
and missing validation data fails closed. T14's complete UI/persistence/ID-priority
and paste/source-parity suite also passes with learning explicitly enabled.

Evidence:
- `evidence/t16-20261004/run-20261005T012921.672383Z-d9og9mdh/`
- `evidence/t14-20261004/run-20261005T012905.658911Z-xrc5dt8x/`

The real confirmation map is still empty: production unresolved count remains 228,
and there is no measured real-owner reduction yet. The 20 saved pairs and learned
rules in evidence are mock inputs, not ground truth to import. Packaged reference
provenance: NCAA inventory from T14's cached tournament participant corpus;
validation cases from `evidence/t1-20261001/matching-1/team_names.csv` and
`scripts/validation/fixtures/live_unmatched_teams.json`. No API enumeration or
billable calls were required. No new recurring monitor or background job exists.
