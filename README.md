# Women's College Volleyball Betting Model

Goal: a player-level betting model for NCAA Women's Volleyball, built up from a
team-level model. Roadmap:

1. **Data pipeline** (done): point-level play-by-play for D1 WVB, 2021-present.
2. **Team model**: serve-Elo / receive-Elo per team, then a Bayesian model
   (logistic regression or similar) on top to quantify matchup advantages.
3. **Player model**: extend to player level using pbp player attribution +
   boxscores.
4. **App**: Streamlit app hosted on Streamlit Community Cloud.

## Streamlit app

`streamlit_app.py` — structured like the NCAAF Python_Asshole_Algo app:
password gate (`APP_PASSWORD` secret), bankroll/Kelly/edge-cap/value-required
synced from the shared Constants Google Sheet (`Vball` row), manual odds
entry, Kelly staking with edge cap. Pick home/away teams, get the set-score
distribution and fair prices for moneyline, set spreads (±1.5/±2.5), and
total-sets markets; enter the book's odds to get a stake. Conservative mode
sizes off the 20th percentile of the model's posterior. Run locally with:

    ./.venv/bin/streamlit run streamlit_app.py

Tabs: **Price a match** (odds entry + Kelly), **Rankings** (searchable table;
`overall` = regression-weighted serve/receive blend with the conference
anchor), **Results** (season games + outcomes).

In-season updates are AUTOMATIC: `.github/workflows/update-ratings.yml` runs
nightly (3:30am ET) on GitHub Actions — downloads new final games (raw files
persist in the Actions cache), rebuilds the season tables and the full Elo
chain, commits `app_data/` + the season parquets, and pushes; Streamlit
Community Cloud then auto-redeploys. It can also be triggered on demand from
the repo's Actions tab ("Run workflow"). The processed parquets for past
seasons are committed to the repo so the workflow can replay the whole chain.
The same pipeline still runs locally when needed:

    ./.venv/bin/python scripts/backfill.py --season 2026 [--boxscores]
    ./.venv/bin/python scripts/build_points.py --season 2026
    ./.venv/bin/python scripts/build_elo.py --seasons 2021 2022 2023 2024 2025 2026
    git add app_data data/processed && git commit -m "ratings update" && git push

(after a local run like this, `git pull` first next time — the bot commits too)

`--boxscores` also fetches player boxscores (one extra request per game, and
it backfills them into already-downloaded game files) — the raw material for
the future player-level model. `app_data/` is committed so cloud deploys
have ratings + model params without the (gitignored) data/ tree.

## Data source

NCAA.com's GraphQL API (`sdataprod.ncaa.com`) with persisted queries. The
query hashes are embedded in ncaa.com page HTML (`drupalSettings.gqlShas`) and
rotate on site deploys; `vbstats/ncaa.py` ships known-good hashes and
re-scrapes them automatically on HTTP 400.

Key endpoints (all GET, `?meta=<op>&extensions={persistedQuery...}&variables={...}`):

| Operation | Purpose | Variables |
|---|---|---|
| `GetContests_web` | schedule/results for one date | `{sportCode:"WVB", division:1, seasonYear, contestDate:"MM/DD/YYYY"}` |
| `GetGamecenterGameById_web` | linescores, venue/location, championship flags | `{id, week:null, staticTestEnv:null}` |
| `NCAA_GetGamecenterPbpGenericById_web` | play-by-play | `{contestId, staticTestEnv:null}` |
| `NCAA_GetGamecenterBoxscoreVolleyballById_web` | player boxscore | `{contestId, staticTestEnv:null}` |

Coverage: pbp from the **2021 season onward** (2019/2020 return no pbp).
`seasonYear` is the calendar year the season starts (2026 = current season).
JSON must be serialized with compact separators — the API 500s on `+`-encoded
spaces.

## Pipeline

```bash
.venv/bin/python scripts/backfill.py --season 2024          # download raw JSON
.venv/bin/python scripts/build_points.py --season 2024      # build parquet tables
```

- `data/raw/<season>/contests/<date>.json` — daily schedules
- `data/raw/<season>/games/<id>.json` — `{game, pbp}` per match (resumable;
  reruns skip existing files)
- `data/processed/matches_<season>.parquet` — one row per match, with venue
  and a derived `is_neutral` flag
- `data/processed/points_<season>.parquet` — one row per rally: set, score,
  `winner_id`, `server_id`, raw play text

## Serve/receive reconstruction

The pbp feed doesn't label the server, but under rally scoring the point
winner serves next, so each set's serve sequence is determined by its first
server. That is resolved from a `Service ace` / `Service error` on the set's
first point, or serve-first alternation across sets 1-4. Later aces/errors act
as consistency checks (`serve_conflict` column — 0.00% conflicts observed).
~99% of points get a resolved server.

## Elo tuning

`scripts/tune_elo.py` tunes (k, carryover, conf_weight) by coordinate descent:
fit sigmoid(a + b*elo_edge) on 2021-2023, score log-loss on held-out
2024-2025. Best (saved to `data/processed/elo_tuning.json`, now the
`build_elo.py` defaults): **k=1.0, carryover=0.8, conf_weight=0.1** →
val log-loss 0.4604, accuracy 77.7%. The loss surface is flat near the
optimum (k anywhere in 0.75-1.5 is within 0.003), so these are robust.

## Venue / neutral-site handling

`GetGamecenterGameById_web` returns `location` (venue, city, state) for most
games and all championship games. `build_points.py` flags a match as neutral
when its venue differs from the home team's modal venue that season (or when
it's a championship game). Needs a full season of data to classify well —
small samples misidentify a team's modal venue. Games with null location fall
back to non-neutral; `isConferenceTournament`/`isChampionship` flags are kept
in the matches table.
