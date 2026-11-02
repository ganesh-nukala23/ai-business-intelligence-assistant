"""Data loading rules and SQL safety."""
import pytest

from app import data_loader, database
from app.query_validator import UnsafeQueryError, validate_select_query


# ---------- data loading on the real dataset ----------
def test_load_report_counts(db_path):
    conn = database.connect_readonly()
    report = data_loader.build_data_report(conn)
    assert report["total_rows_received"] == 51
    assert report["rows_loaded"] == 51
    assert report["rows_rejected"] == 0
    assert report["rows_counted_in_revenue"] == 48
    assert report["rows_excluded_from_revenue"] == 3


def test_missing_unit_price_is_excluded_and_not_guessed(db_path):
    conn = database.connect_readonly()
    row = conn.execute("SELECT unit_price, data_issue FROM sales WHERE transaction_id='TXN0051'").fetchone()
    assert row["unit_price"] is None            # not turned into 0
    assert row["data_issue"] == "missing_unit_price"
    in_view = conn.execute("SELECT COUNT(*) FROM valid_sales WHERE transaction_id='TXN0051'").fetchone()[0]
    assert in_view == 0


def test_returned_transaction_is_excluded(db_path):
    conn = database.connect_readonly()
    assert conn.execute("SELECT status FROM sales WHERE transaction_id='TXN0033'").fetchone()[0] == "Returned"
    assert conn.execute("SELECT COUNT(*) FROM valid_sales WHERE transaction_id='TXN0033'").fetchone()[0] == 0


def test_zero_quantity_is_flagged_not_a_normal_sale(db_path):
    conn = database.connect_readonly()
    row = conn.execute("SELECT quantity, data_issue FROM sales WHERE transaction_id='TXN0034'").fetchone()
    assert row["quantity"] == 0
    assert row["data_issue"] == "zero_quantity"
    assert conn.execute("SELECT COUNT(*) FROM valid_sales WHERE transaction_id='TXN0034'").fetchone()[0] == 0


def test_dates_are_stored_as_iso_day_month_order(db_path):
    conn = database.connect_readonly()
    # CSV says 03-01-2026 (3 January), not March 1st
    assert conn.execute("SELECT order_date FROM sales WHERE transaction_id='TXN0001'").fetchone()[0] == "2026-01-03"


def test_loader_rejects_duplicates_and_bad_dates(tmp_path, monkeypatch):
    csv_file = tmp_path / "bad.csv"
    csv_file.write_text(
        "Transaction_Id,Order_date,Product,Category,Region,Sales_channel,Quantity,Unit_price,Discount_amount,Status\n"
        "T1,01-01-2026,A,X,North,Online,1,100,0,Completed\n"
        "T1,02-01-2026,A,X,North,Online,1,100,0,Completed\n"
        "T2,31-02-2026,A,X,North,Online,1,100,0,Completed\n"
        "T3,03-01-2026,A,X,North,Online,-2,100,0,Completed\n"
        "T4,03-01-2026,A,X,North,Online,2,100,500,Completed\n",
        encoding="utf-8")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "bad.db"))
    report = data_loader.load_csv_to_db(csv_file)
    assert report["total_rows_received"] == 5
    assert report["rows_rejected"] == 2
    reasons = [r["reason"] for r in report["rejected_details"]]
    assert "duplicate_transaction_id" in reasons
    assert any(r.startswith("invalid_order_date") for r in reasons)
    assert report["rows_counted_in_revenue"] == 1          # only T1; T3 and T4 are flagged
    assert report["rows_excluded_from_revenue"] == 2


def test_loader_raises_for_missing_columns(tmp_path, monkeypatch):
    csv_file = tmp_path / "nocols.csv"
    csv_file.write_text("a,b\n1,2\n", encoding="utf-8")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "x.db"))
    with pytest.raises(ValueError):
        data_loader.load_csv_to_db(csv_file)


# ---------- SQL safety ----------
def test_safe_select_is_accepted():
    sql = "SELECT SUM(revenue) AS total FROM valid_sales WHERE month = ?"
    assert validate_select_query(sql).startswith("SELECT")


def test_join_on_allowed_tables_is_accepted():
    validate_select_query("SELECT s.order_date FROM sales s LEFT JOIN valid_sales v ON v.transaction_id = s.transaction_id")


@pytest.mark.parametrize("bad_sql", [
    "DROP TABLE sales",
    "DELETE FROM sales",
    "UPDATE sales SET status = 'x'",
    "INSERT INTO sales VALUES (1)",
    "ALTER TABLE sales ADD COLUMN x TEXT",
    "CREATE TABLE evil (x TEXT)",
    "SELECT * FROM sales; DROP TABLE sales",          # two statements
    "SELECT * FROM sales -- hidden",                   # comment
    "SELECT * FROM sqlite_master",                     # table not allowed
    "SELECT * FROM rejected_rows",                     # table not allowed
    "SELECT * FROM sales, rejected_rows",              # comma join
    "SELECT 1",                                        # no table
    "WITH x AS (SELECT 1) SELECT * FROM sales",        # must start with SELECT
    "PRAGMA table_info(sales)",
    "ATTACH DATABASE 'x.db' AS x",
    "",
])
def test_unsafe_sql_is_rejected(bad_sql):
    with pytest.raises(UnsafeQueryError):
        validate_select_query(bad_sql)


def test_run_safe_query_blocks_before_execution(conn):
    with pytest.raises(UnsafeQueryError):
        database.run_safe_query(conn, "DELETE FROM sales")


def test_readonly_connection_cannot_write(conn):
    """Second safety layer: even raw SQL cannot change the database."""
    import sqlite3
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM sales")
