# Schedule + board manual matching — T12

Accepted by the planner on October 4 and enabled by default.
Run `.venv/bin/streamlit run streamlit_app.py`; set
`WVB_ENABLE_MANUAL_BOARD=0` to hide the fourth source for rollback.

Choose a date, load the NCAA schedule and paste/parse a book board in either
order. Each board row offers a schedule fixture, the schedule team represented
by the book's first team, a venue override, and confirmation. Confident T7
matches are proposed, but pricing requires confirmation. Unknown orientation,
unrated teams, and duplicate confirmed fixtures cannot silently price. Exclude
unwanted rows explicitly. Matches, exclusions, venue overrides and pasted text
survive independent reloads and switching dates or sources.

`board_pricing.evaluate_game` is the shared cached evaluator for Paste, Live API
and the new source. All three use the existing card renderer and log/paper
buttons. A changed match or venue invalidates the displayed card immediately;
Price recomputes only the changed game. Schedule home/away/date/time and the
actual per-game venue mode reach the existing logging path. Reversed board
sides are remapped without changing the handicap attached to the picked team.

Validation on Streamlit 1.62.0 (all actual UI calls guarded from external I/O):

- `PYTHONPATH=. .venv/bin/python scripts/validation/test_manual_board.py`
  passes 18-market exact parity across three games with pre-T12 Paste and
  Live API, reversed moneylines/spreads/totals, confirmation/duplicate guards,
  state persistence, counts, default-on/explicit-zero rollback, and captured mock logging.
  Initial three games: 1,503 model evaluations; unchanged reprice: zero;
  single venue change: 501; single match correction: 501. Only explicit fetch
  buttons fetched the mocked slate. Evidence:
  `evidence/t12-20261004/run-20261004T195852.817138Z-uva9w_mg/`.
- `scripts/validation/test_integrated_defaults.py` passes source-3 startup,
  nine exact 16-market boards, and rollback. Evidence:
  `evidence/integration-20261001/run-20261004T195850.078390Z-x7u5u2sc/`.
- `scripts/validation/test_card_state.py` passes seven stale-card controls,
  bankroll $31.50→$63.00, and exact mocked logging context. Evidence:
  `evidence/t8-20261001/run-20261004T200039.179102Z-pvvtv4aj/`.

Real-slate replay:

- Free NCAA capture for September 30: 87 listings minus one duplicate = 86
  fixtures (9 rated + 77 unrated), 12 requests, 4.23 seconds cold / 0.0067 warm.
  Raw responses and slate are preserved in
  `evidence/t12-20261004/real-slate/run-20261004T195743.899221Z-szg1csja/`.
- `scripts/validation/replay_manual_real_slate.py` matches Vanderbilt @ LSU
  to contest 6625618, 7 PM Eastern, home court; four markets price through
  the new UI. Board counts: 1 matched, 0 excluded, 0 unmatched; 85 schedule
  fixtures have no board match. Text/card/provenance:
  `evidence/t12-20261004/real-replay/run-20261004T195937.247920Z-1evw6cqb/`.
- Limit: authentic cached DraftKings closing quotes were reconstructed as
  paste text, with American odds rounded to integers. This validates real
  fixture/quote integration, not today's BetOnline clipboard or live prices.
  Current ratings are used only for UI validation, not strategy backtesting.
  Existing parser is unchanged. No paid calls, real logging or grading occurred.

No new background jobs. Integration/push is authorized by the October 4
acceptance and the owner's standing authorization. See the worker log for the
verified deployment commit and final default-on evidence.
