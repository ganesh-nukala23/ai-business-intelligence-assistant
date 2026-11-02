# Mini AI Business Intelligence Assistant

Ask questions about sales data in plain English and get answers calculated from a real SQLite database.
Built for the "AI-Assisted Development Challenge for GET selection".

**Key idea:** the AI only *understands the question* (picks one of 5 fixed operations). All numbers come from
SQL queries on SQLite. The AI never sees or invents sales figures.

## Features
- Loads the supplied `data/sales.csv` (51 rows, unchanged) into SQLite with row-by-row validation and a loading report
- 5 questions supported: total revenue, top product, monthly trend, top region, compare two months
- LLM interpretation (Anthropic API) **or** a rule-based fallback when there is no key / the API fails
- Safe SQL: fixed templates + validator + read-only connection
- Simple web page + JSON API + 79 automated tests

## Technology
Python, FastAPI, Uvicorn, SQLite (`sqlite3`), plain HTML/CSS/JavaScript, `requests` (LLM call), pytest + FastAPI TestClient.
(Pandas is not used: the standard `csv` module makes row-by-row validation easier to read and explain.)

## Project structure
```
app/
  main.py            FastAPI app: routes, error handling
  database.py        paths, schema (tables + valid_sales view), connections, run_safe_query()
  data_loader.py     CSV -> SQLite with validation, loading report
  analytics.py       the 5 operations (SQL) + month handling
  ai_service.py      LLM call, output validation, rule-based fallback
  query_validator.py SQL safety checks
  models.py          request/response models
  templates/index.html, static/style.css, static/script.js   the web page
tests/               test_validation.py, test_analytics.py, test_api.py, conftest.py
data/sales.csv       original dataset (unchanged)
docs/                architecture, tests, development report, checklist, interview guide
```

## Setup on Windows (step by step)
Required: **Python 3.10 or newer** from python.org (tick "Add Python to PATH" in the installer). Check with `python --version`.

Open **Command Prompt** in the extracted folder (the one containing `requirements.txt`):
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.data_loader
uvicorn app.main:app --reload
```
Then open **http://127.0.0.1:8000** in your browser. (PowerShell: if activation is blocked, run
`Set-ExecutionPolicy -Scope Process Bypass` first, or use Command Prompt.)

Mac/Linux: same, but `source venv/bin/activate` and `cp .env.example .env`.

`python -m app.data_loader` creates `data/sales.db` and prints the loading report. If you skip it, the app builds
the database automatically on first start.

## Environment variables (all optional)
| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables LLM interpretation. Put it in `.env`. Without it the fallback is used. |
| `ANTHROPIC_MODEL` | Model name (default `claude-sonnet-5-5`; change it if your account uses another). |
| `DB_PATH`, `CSV_PATH` | Override file locations. |

Never put the key in source code. `.env` is git-ignored.

## Run the tests
```
python -m pytest -v
```
Tests use a temporary database built from the real CSV; they never touch `data/sales.db` and never call the real LLM.

## API
- `POST /api/ask` body `{"question": "..."}` -> `question, answer, data, sql, status, interpreted_by, ai_note`
- `GET /api/health`, `GET /api/stats` (data loading report), interactive docs at `/docs`

| Situation | HTTP | `status` |
|---|---|---|
| Answered | 200 | success |
| Empty / too long question | 400 | error |
| Wrong JSON body | 422 | error |
| Unsupported question | 400 | unsupported |
| Needs clarification (e.g. unknown month) | 400 | needs_clarification |
| Database missing / error | 503 / 500 | error (no stack trace shown) |

## Supported questions (examples)
1. What is the total revenue? / How much revenue did we generate?
2. Which product generated the highest revenue?
3. What is the monthly revenue trend? / Show monthly revenue
4. Which region generated the highest sales? / Which area made the most money?
5. Compare January and February revenue / How did revenue change between March and April?

Month names without a year use the year found in the data (2026). Not supported (returns a clear "unsupported"
message): forecasts, profit, averages, lowest/worst, customers, category/channel analysis, revenue of one month
alone, and filters such as "revenue for Monitor" or "for the North region".

## Revenue and data validation rules
**Revenue = Quantity x Unit_price - Discount_amount**, defined once in the `valid_sales` SQL view and used by every query.

Only rows with status `Completed` and no data issue count. Nothing is silently dropped:

| Case in the real dataset | Handling |
|---|---|
| TXN0033 status `Returned` | stored, excluded from revenue |
| TXN0034 quantity `0` | stored, flagged `zero_quantity`, excluded (it would add 0 anyway) |
| TXN0051 blank unit price | stored with NULL price (not 0, not guessed), flagged `missing_unit_price`, excluded |

Other rules: missing/duplicate transaction id or unreadable date -> row goes to `rejected_rows` with the reason;
negative or non-numeric quantity/price/discount, discount larger than the sale, missing product or region ->
stored but flagged and excluded. Dates in the CSV are day-month-year (`03-01-2026` = 3 Jan) and stored as ISO text.
Actual result on the supplied file: **51 received, 51 loaded, 0 rejected, 48 counted, 3 excluded.**
Currency is not stated in the dataset, so numbers are shown without a currency symbol.

## AI integration
1. If `ANTHROPIC_API_KEY` is set, the question is sent to the Anthropic Messages API with instructions to reply
   with JSON `{intent, month_a, month_b, filters}`. The reply is validated: it must be JSON, the intent must be one
   of the 5 names (or `unsupported`), months must be text, and any filter makes the question unsupported.
2. If there is no key, the call fails, or the reply is invalid, a **rule-based keyword fallback** (plain Python,
   *not* an LLM) is used. The response says which one was used (`interpreted_by`, `ai_note`).
3. Either way the backend runs SQL and writes the answer text itself. The LLM sees only the question text.

Preventing wrong answers: fixed list of operations, validated AI output, unsupported/ambiguous questions rejected
instead of guessed, months checked against the database, a question naming one product/region is refused.

## SQL safety
No LLM-written SQL is executed. Layers: (1) fixed SQL templates; (2) `query_validator.py` checks every query
(single SELECT, no comments, no INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/ATTACH/PRAGMA, only tables `sales` and
`valid_sales`); (3) user-derived values go in `?` parameters; (4) the API opens SQLite in read-only mode.

## Limitations
- **The real LLM call was not tested live** (no API key was available while building). Request building,
  validation and fallback are tested with simulated replies. Try it yourself with your key.
- Keyword fallback is simple; unusual phrasing may be reported as unsupported. The word "may" is read as a month.
- One question = one operation; no follow-up/conversation memory; no filters by product/region.
- Only one year of data; no authentication, deployment or caching (out of scope).
- Developed and tested on Linux with Python 3.13; not run on Windows by the builder.
