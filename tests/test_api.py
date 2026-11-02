"""API tests (FastAPI TestClient) and AI interpretation tests.

NOTE: the LLM tests use SIMULATED replies (monkeypatched requests.post). They test
our request building, validation and fallback logic - they do NOT prove the real
Anthropic API works. That needs a real key (see README)."""
import pytest
import requests

from app import ai_service


def ask(client, question):
    return client.post("/api/ask", json={"question": question})


# ---------- the five questions, end to end ----------
def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200 and response.json()["database"] == "ok"


def test_stats_endpoint(client):
    body = client.get("/api/stats").json()
    assert body["total_rows_received"] == 51 and body["rows_excluded_from_revenue"] == 3


def test_ask_total_revenue(client):
    response = ask(client, "What is the total revenue?")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "success"
    assert body["data"]["total_revenue"] == 1439200.0
    assert "1,439,200.00" in body["answer"]
    assert "SELECT" in body["sql"] and "valid_sales" in body["sql"]
    assert body["interpreted_by"] == "fallback"


def test_ask_top_product_with_different_wording(client):
    body = ask(client, "What is our best-performing product by revenue?").json()
    assert body["data"]["top_product"] == "Monitor"


def test_ask_monthly(client):
    body = ask(client, "What is the monthly revenue trend?").json()
    assert len(body["data"]["months"]) == 6


def test_ask_top_region_wording_variants(client):
    for question in ["Which region generated the highest sales?", "Which area made the most money?"]:
        assert ask(client, question).json()["data"]["top_region"] == "South"


def test_ask_compare_months(client):
    body = ask(client, "How did revenue change between January and February?").json()
    assert body["data"]["absolute_difference"] == 24350.0
    assert body["data"]["percentage_change"] == 11.58
    body = ask(client, "Compare March and April revenue").json()
    assert body["data"]["later_month"] == "2026-04"


# ---------- errors ----------
@pytest.mark.parametrize("question", ["", "   "])
def test_empty_question_is_400(client, question):
    response = ask(client, question)
    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_too_long_question_is_400(client):
    assert ask(client, "revenue " * 200).status_code == 400


@pytest.mark.parametrize("payload", [{}, {"question": 123}, {"wrong": "x"}])
def test_invalid_body_is_422(client, payload):
    response = client.post("/api/ask", json=payload)
    assert response.status_code == 422
    assert response.json()["status"] == "error"


@pytest.mark.parametrize("question", [
    "What is the weather today?",
    "Forecast next year's revenue",
    "Which product had the lowest revenue?",
    "What is the average order value?",
    "DROP TABLE sales",
    "What was the revenue in March?",
    "What is the total revenue for Monitor?",     # product filter not supported
    "Show revenue for the North region",           # region filter not supported
])
def test_unsupported_questions_are_rejected_not_guessed(client, question):
    response = ask(client, question)
    assert response.status_code == 400
    assert response.json()["status"] == "unsupported"


def test_compare_without_months_asks_for_clarification(client):
    response = ask(client, "How did revenue change between two months?")
    assert response.status_code == 400
    assert response.json()["status"] == "needs_clarification"


def test_compare_month_without_data(client):
    response = ask(client, "Compare July and January revenue")
    assert response.status_code == 400
    assert "no data for July" in response.json()["message"]


def test_missing_database_returns_503_without_details(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import database
    monkeypatch.setenv("DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setattr("app.main.data_loader.load_csv_to_db", lambda: None)  # skip auto-build
    with TestClient(app) as test_client:
        response = test_client.post("/api/ask", json={"question": "total revenue"})
    assert response.status_code == 503
    assert "Traceback" not in response.text and str(tmp_path) not in response.text


def test_home_page_served(client):
    response = client.get("/")
    assert response.status_code == 200 and "Ask Question" in response.text


# ---------- AI interpretation (SIMULATED LLM replies) ----------
class FakeResponse:
    def __init__(self, text, status=200):
        self._text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("bad status")

    def json(self):
        return {"content": [{"type": "text", "text": self._text}]}


def use_fake_llm(monkeypatch, text, status=200):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setattr(ai_service.requests, "post", lambda *a, **k: FakeResponse(text, status))


def test_llm_reply_is_used_when_valid(client, monkeypatch):
    use_fake_llm(monkeypatch, '{"intent": "top_region", "month_a": null, "month_b": null, "filters": []}')
    body = ask(client, "Where did we make the most dough?").json()   # fallback could not understand this
    assert body["interpreted_by"] == "llm"
    assert body["data"]["top_region"] == "South"   # number still comes from SQL


def test_llm_reply_inside_code_fence_is_accepted(client, monkeypatch):
    use_fake_llm(monkeypatch, '```json\n{"intent": "total_revenue", "month_a": null, "month_b": null}\n```')
    assert ask(client, "gimme the big number").json()["data"]["total_revenue"] == 1439200.0


def test_llm_months_are_validated_by_database(client, monkeypatch):
    use_fake_llm(monkeypatch, '{"intent": "compare_months", "month_a": "Smarch", "month_b": "January"}')
    response = ask(client, "compare stuff")
    assert response.status_code == 400 and response.json()["status"] == "needs_clarification"


def test_llm_cannot_choose_unknown_operation(client, monkeypatch):
    use_fake_llm(monkeypatch, '{"intent": "run_sql", "sql": "DROP TABLE sales"}')
    body = ask(client, "What is the total revenue?").json()
    assert body["interpreted_by"] == "fallback"     # invalid AI output -> fallback
    assert "InvalidAIOutput" in body["ai_note"]
    assert body["data"]["total_revenue"] == 1439200.0


@pytest.mark.parametrize("text", ["I think you want revenue", "{not json}", "[1,2]", '{"intent": 5}'])
def test_garbage_llm_output_falls_back(client, monkeypatch, text):
    use_fake_llm(monkeypatch, text)
    body = ask(client, "Which product generated the highest revenue?").json()
    assert body["interpreted_by"] == "fallback"
    assert body["data"]["top_product"] == "Monitor"


def test_llm_api_failure_falls_back(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    def boom(*args, **kwargs):
        raise requests.ConnectionError("network down, key=test-key-not-real")
    monkeypatch.setattr(ai_service.requests, "post", boom)

    response = ask(client, "What is the total revenue?")
    body = response.json()
    assert response.status_code == 200
    assert body["interpreted_by"] == "fallback"
    assert "AIServiceError" in body["ai_note"]
    assert "test-key-not-real" not in response.text      # secrets never leak


def test_llm_http_error_status_falls_back(client, monkeypatch):
    use_fake_llm(monkeypatch, "", status=529)
    assert ask(client, "total revenue").json()["interpreted_by"] == "fallback"


def test_llm_saying_unsupported_is_respected(client, monkeypatch):
    use_fake_llm(monkeypatch, '{"intent": "unsupported", "month_a": null, "month_b": null, "filters": []}')
    assert ask(client, "What is the total revenue?").json()["status"] == "unsupported"


def test_llm_filters_make_question_unsupported(client, monkeypatch):
    use_fake_llm(monkeypatch, '{"intent": "total_revenue", "month_a": null, "month_b": null, "filters": ["Monitor"]}')
    assert ask(client, "total revenue of the thing").json()["status"] == "unsupported"


def test_request_sent_to_llm_has_no_data_and_uses_env_key(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, body=json)
        return FakeResponse('{"intent": "total_revenue", "month_a": null, "month_b": null}')
    monkeypatch.setenv("ANTHROPIC_API_KEY", "abc123")
    monkeypatch.setattr(ai_service.requests, "post", fake_post)
    ai_service.call_llm("What is the total revenue?")
    assert captured["headers"]["x-api-key"] == "abc123"
    assert "<question>What is the total revenue?</question>" == captured["body"]["messages"][0]["content"]
    assert "1439200" not in str(captured["body"])        # no sales figures go to the LLM
