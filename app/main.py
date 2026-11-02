"""FastAPI application: serves the web page and the JSON API."""
import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()  # reads the .env file (API key etc.) if it exists

from app import analytics, database, data_loader  # noqa: E402
from app.ai_service import interpret_question  # noqa: E402
from app.models import AskRequest, AskResponse  # noqa: E402
from app.query_validator import UnsafeQueryError  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bi_assistant")

APP_DIR = Path(__file__).resolve().parent
MAX_QUESTION_LENGTH = 500


@asynccontextmanager
async def lifespan(app):
    # Build the database from the CSV on first start
    if not database.get_db_path().exists():
        logger.info("Database not found, loading CSV...")
        data_loader.load_csv_to_db()
    yield


app = FastAPI(title="Mini AI Business Intelligence Assistant", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


def error_response(status_code, status, message, question=None, **extra):
    body = {"status": status, "message": message, "question": question}
    body.update(extra)
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(RequestValidationError)
async def bad_request_body(request: Request, exc: RequestValidationError):
    return error_response(422, "error", 'Invalid request. Send JSON like {"question": "What is the total revenue?"}')


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(APP_DIR / "templates" / "index.html")


@app.get("/api/health")
def health():
    try:
        conn = database.connect_readonly()
        conn.execute("SELECT 1 FROM sales LIMIT 1")
        conn.close()
        return {"status": "ok", "database": "ok"}
    except (database.DatabaseNotReadyError, sqlite3.Error):
        return error_response(503, "error", "Database is not available.")


@app.get("/api/stats")
def stats():
    """Data loading report: rows received, loaded, rejected and excluded."""
    try:
        conn = database.connect_readonly()
        try:
            return data_loader.build_data_report(conn)
        finally:
            conn.close()
    except (database.DatabaseNotReadyError, sqlite3.Error):
        logger.exception("stats failed")
        return error_response(503, "error", "Database is not available.")


def get_known_names(conn):
    """Product and region names in the data (used to detect unsupported filters)."""
    queries = []
    names = []
    for column in ("product", "region"):
        rows = analytics.run(conn, queries, f"SELECT DISTINCT {column} AS name FROM sales")
        names += [r["name"] for r in rows if r["name"]]
    return names


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest):
    # (plain `def`, so FastAPI runs it in a worker thread - fine for blocking SQLite/HTTP calls)
    question = request.question.strip()
    if not question:
        return error_response(400, "error", "Question cannot be empty.", question=request.question)
    if len(question) > MAX_QUESTION_LENGTH:
        return error_response(400, "error", f"Question is too long (max {MAX_QUESTION_LENGTH} characters).")

    try:
        conn = database.connect_readonly()
    except database.DatabaseNotReadyError:
        return error_response(503, "error", "Database is not available.", question=question)

    try:
        interpretation = interpret_question(question, get_known_names(conn))
        if interpretation["intent"] == "unsupported":
            return error_response(
                400, "unsupported", interpretation["reason"] or "Unsupported question.",
                question=question, supported_operations=analytics.SUPPORTED_INTENTS,
                interpreted_by=interpretation["source"], ai_note=interpretation["ai_note"])

        result = analytics.run_intent(conn, interpretation["intent"],
                                      interpretation["month_a"], interpretation["month_b"])
    except analytics.AnalyticsError as error:
        return error_response(400, "needs_clarification", str(error), question=question,
                              interpreted_by=interpretation["source"], ai_note=interpretation["ai_note"])
    except (sqlite3.Error, UnsafeQueryError):
        logger.exception("Database/query error")  # details go to the server log only
        return error_response(500, "error", "A database error occurred.", question=question)
    finally:
        conn.close()

    sql_text = "\n\n".join(
        q["sql"] + ("   -- params: " + str(q["params"]) if q["params"] else "") for q in result["queries"])
    return AskResponse(
        question=question, answer=result["answer"], data=result["data"], sql=sql_text,
        status="success", interpreted_by=interpretation["source"], ai_note=interpretation["ai_note"])
