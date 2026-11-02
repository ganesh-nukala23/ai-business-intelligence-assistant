# Test documentation

Run: `python -m pytest -v`  (full output of the run made while building: `docs/test_results.txt`)

**Result of the last run: 79 passed.** (Linux, Python 3.13, FastAPI 0.162.0, pytest 9.1.1.)

## Isolation
`tests/conftest.py` builds a fresh temporary SQLite database from the real `data/sales.csv` for each test
(`DB_PATH` points to a temp folder). The real `data/sales.db` is never touched. The API key is removed from the
environment for every test so the real LLM is never called.

## What is covered
| File | Tests | Covers |
|---|---|---|
| `test_validation.py` | 27 | Load report counts (51/51/0/48/3); missing price kept as NULL and excluded; returned row excluded; zero-quantity flagged; date parsed as day-month-year; duplicates, bad dates, negative qty, oversize discount, missing CSV columns (temporary bad CSVs); SQL validator accepts safe queries and rejects 16 unsafe ones; read-only connection cannot write |
| `test_analytics.py` | 14 | Total revenue (also recomputed straight from the CSV); top product; top region; monthly figures, order and sum; April excludes the 2 bad rows; compare months (forward, backward, with years, decrease); bad month input; zero-base percentage; unknown operation |
| `test_api.py` | 38 | All five questions through `/api/ask`; wording variants; health, stats, home page; empty/blank/too-long/invalid-body; 8 unsupported questions (weather, forecast, lowest, average, DROP TABLE, single month, product filter, region filter); clarification; 503 without leaking paths; AI behaviour below |

## AI tests use simulated replies
These patch `requests.post` with fake responses: valid reply used; reply in a code fence; invalid months caught by the
database; unknown operation (`run_sql`) rejected and fallback used; 4 kinds of garbage output; network failure;
HTTP error status; LLM saying "unsupported"; LLM filters; secrets not leaked in responses; the request sent has the
key from the environment, the question only, and no sales figures.
**They prove our handling logic, not that the real Anthropic API accepts the request.**

## Expected values
Computed independently with Python's `csv` module (not the app): total 1,439,200 from 48 transactions; top product
Monitor 473,000; top region South 411,200; Jan 210,250 -> Feb 234,600 = +24,350 (+11.58%).

## Bug found by the tests
`monthly_revenue` first returned 7 months. `GROUP BY month` made SQLite use the view's own `month` column instead of
the alias, so excluded rows formed a separate NULL group. Fixed by grouping on the full `strftime(...)` expression.

## Not tested
Real LLM API call; Windows; browsers other than headless Chromium (UI was checked manually with a script: example
button, answer, tables, error box, blank input).
