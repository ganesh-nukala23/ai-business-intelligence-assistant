"""Shared test setup. Every test gets its OWN temporary database built from the
real data/sales.csv, so the real data/sales.db is never touched."""
import pytest
from fastapi.testclient import TestClient

from app import data_loader, database
from app.main import app


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    # Tests must never call the real LLM, even if a key exists in .env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test_sales.db"
    monkeypatch.setenv("DB_PATH", str(path))
    data_loader.load_csv_to_db()  # uses the real data/sales.csv
    return path


@pytest.fixture
def conn(db_path):
    connection = database.connect_readonly()
    yield connection
    connection.close()


@pytest.fixture
def client(db_path):
    with TestClient(app) as test_client:
        yield test_client
