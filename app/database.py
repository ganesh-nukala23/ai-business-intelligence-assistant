"""Database helpers: file paths, schema, connections and safe query execution."""
import os
import sqlite3
from pathlib import Path

from app.query_validator import validate_select_query

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_db_path():
    """SQLite file location. Can be changed with the DB_PATH environment variable."""
    return Path(os.getenv("DB_PATH", str(PROJECT_ROOT / "data" / "sales.db")))


def get_csv_path():
    """Source CSV location. Can be changed with the CSV_PATH environment variable."""
    return Path(os.getenv("CSV_PATH", str(PROJECT_ROOT / "data" / "sales.csv")))


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
# sales            : every row we could load from the CSV (nothing silently dropped)
# rejected_rows    : rows we could NOT load at all (e.g. duplicate id, bad date)
# valid_sales (view): the ONE place where "revenue" is defined. Every analytics
#                     query reads from this view, so all answers use the same rule.
SCHEMA_SQL = """
DROP VIEW  IF EXISTS valid_sales;
DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS rejected_rows;

CREATE TABLE sales (
    transaction_id  TEXT PRIMARY KEY,
    order_date      TEXT NOT NULL,              -- stored as ISO text YYYY-MM-DD
    product         TEXT,
    category        TEXT,
    region          TEXT,
    sales_channel   TEXT,
    quantity        INTEGER CHECK (quantity IS NULL OR quantity >= 0),
    unit_price      REAL    CHECK (unit_price IS NULL OR unit_price >= 0),
    discount_amount REAL    CHECK (discount_amount IS NULL OR discount_amount >= 0),
    status          TEXT NOT NULL,
    data_issue      TEXT                        -- NULL = row passed all checks
);

CREATE TABLE rejected_rows (
    csv_line_number INTEGER,
    transaction_id  TEXT,
    reason          TEXT NOT NULL
);

-- Revenue = quantity * unit_price - discount_amount
-- Only Completed rows with no data_issue count as revenue.
CREATE VIEW valid_sales AS
SELECT
    transaction_id,
    order_date,
    strftime('%Y-%m', order_date) AS month,
    product,
    region,
    quantity,
    unit_price,
    discount_amount,
    quantity * unit_price - discount_amount AS revenue
FROM sales
WHERE status = 'Completed' AND data_issue IS NULL;
"""


def create_schema(conn):
    """(Re)create all tables and the view. Existing data is dropped."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------
class DatabaseNotReadyError(Exception):
    """Raised when the database file does not exist yet."""


def connect_readwrite():
    """Normal connection. Only the data loader uses this."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(db_path))


def connect_readonly():
    """Read-only connection. The API uses this, so a query cannot change data
    even if the SQL validator were bypassed."""
    db_path = get_db_path()
    if not db_path.exists():
        raise DatabaseNotReadyError("Database not found. Run: python -m app.data_loader")
    # as_uri() builds a correct file: URL on both Windows and Linux/Mac
    conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row  # lets us read columns by name
    return conn


# ---------------------------------------------------------------------------
# Safe query execution
# ---------------------------------------------------------------------------
def run_safe_query(conn, sql, params=()):
    """Validate the SQL, then run it with parameters. Returns a list of dicts.

    Values from users must ALWAYS go in `params` (the ? placeholders),
    never be pasted into the SQL string.
    """
    safe_sql = validate_select_query(sql)
    cursor = conn.execute(safe_sql, tuple(params))
    return [dict(row) for row in cursor.fetchall()]
