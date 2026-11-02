# Interview guide

## 60-second explanation
"It's a FastAPI app over a SQLite database loaded from the supplied CSV. The user types a question; `ai_service.py`
decides which of five analytics operations it means - using an LLM if a key is set, otherwise keyword rules. Then
`analytics.py` runs a fixed SQL query on a view called `valid_sales`, which is where revenue is defined, and builds the
answer from the rows. The AI never produces numbers. Every query is checked by a validator and runs on a read-only
connection."

## Walk through the code
1. `data_loader.py` - reads CSV, `check_numbers()` flags problems, inserts rows, `build_data_report()` summarises.
2. `database.py` - `SCHEMA_SQL` (tables + `valid_sales` view), `connect_readonly()`, `run_safe_query()`.
3. `analytics.py` - five functions, `INTENT_HANDLERS` dict maps operation name -> function, `compare_months()`.
4. `ai_service.py` - `interpret_question()` -> `call_llm()` + `validate_ai_output()` or `interpret_with_rules()`.
5. `main.py` - `/api/ask` flow: validate -> interpret -> run -> respond.

## Likely questions
- **Why is revenue 1,439,200 and not the sum of every row?** Returned (TXN0033), zero-quantity (TXN0034) and missing-price (TXN0051) rows are excluded; 48 of 51 rows count.
- **Why not treat the missing price as 0?** That would invent data; with a NULL price the revenue is unknown, so the row is excluded and listed in the report.
- **How do you stop the LLM inventing numbers?** It only returns an operation name; SQL computes everything; the answer text is built in Python.
- **What if the LLM returns garbage or the API is down?** `validate_ai_output` raises, `interpret_question` falls back to rules, and the response says `interpreted_by: fallback` with a note. Tested.
- **Is the fallback an LLM?** No - keyword matching in `interpret_with_rules`.
- **How is SQL injection prevented?** User text never goes into SQL; only `?` parameters (months). SQL is fixed templates; validator + read-only connection as extra layers.
- **What does the validator check?** Single SELECT, no comments, no forbidden words, only `sales`/`valid_sales`.
- **Why a view?** One definition of revenue shared by all five queries, so totals agree (tests check products, regions and months each sum to the total).
- **How is percentage change defined?** (later - earlier) / earlier x 100, earlier = earlier in time; None if earlier is 0.
- **Why `def` not `async def` endpoints?** SQLite and `requests` block; FastAPI runs `def` endpoints in a thread pool.
- **Bug you hit?** Monthly query returned 7 months: `GROUP BY month` bound to the view's column, not my alias (see `test_documentation.md`).
- **What would you improve?** Verify live LLM, filters via parameterised templates, chart, follow-ups, CI.

## Modifications an interviewer might ask for - where to change
- Add a new operation (e.g. top category): write a function in `analytics.py`, add it to `INTENT_HANDLERS`, add keywords in `ai_service.py` (and the intent name in `SYSTEM_PROMPT` list is automatic).
- Change revenue (e.g. ignore discount): edit the `revenue` expression in the `valid_sales` view in `database.py`, rerun `python -m app.data_loader`.
- Include Returned sales: change the view's `WHERE` clause.
- Return top 3 products: change `top_by_group` to slice `rows[:3]`.
- Change the model: set `ANTHROPIC_MODEL` in `.env`.
