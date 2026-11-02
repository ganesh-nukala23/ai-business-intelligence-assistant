# Requirements checklist (assessment vs implementation)

| Requirement | Where | Verification |
|---|---|---|
| Load CSV into database | `data_loader.py`, `database.py` | Loader run: 51 loaded; tests in `test_validation.py` |
| Handle missing/invalid records | `data_loader.check_numbers`, `rejected_rows` | Real edge cases + temp bad-CSV tests pass |
| Explain storage and querying | README, `architecture.md` | Documented |
| API accepting a question, structured answer | `main.py` `/api/ask` | curl on a live server + TestClient tests |
| Handle invalid requests/errors | `main.py` | 400/422/503 tests pass |
| >= 4 of 5 analytics (all 5 done) | `analytics.py` | Values match independent CSV calculation |
| Show supporting figures | `data` and `sql` in response, UI tables | Seen in UI screenshot/script |
| LLM / AI interpretation | `ai_service.py` | **Logic tested with simulated replies; real API not tested** |
| Validate generated SQL, no destructive ops | `query_validator.py`, read-only connection | 16 unsafe queries rejected; write attempt fails |
| Explain how wrong answers are prevented | README "AI integration" | Documented; unsupported tests pass |
| Simple UI | `templates/`, `static/` | Driven in headless Chromium |
| >= 5 tests incl. invalid + edge case | `tests/` | 79 passed |
| README, architecture, AI report, limitations | `README.md`, `docs/` | Present |
| Git repository | `.gitignore` provided; init commands below | Not pushed; no remote created |
| No hardcoded key | `.env.example`, `os.getenv` | Key read from environment only |

Git: `git init`, `git add .`, `git commit -m "Initial commit"`, then add your own remote.
