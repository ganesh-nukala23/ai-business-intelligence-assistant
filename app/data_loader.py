"""Loads data/sales.csv into SQLite, checking every row.

Run it with:   python -m app.data_loader

Policy (documented in README):
- Rows are never silently dropped.
- A row that cannot be stored at all (missing/duplicate id, unreadable date)
  goes to the `rejected_rows` table with a reason.
- A row that can be stored but should not count as revenue is stored with a
  `data_issue` text (e.g. missing_unit_price, zero_quantity).
- Returned (non-Completed) rows are stored with their status and are excluded
  from revenue by the `valid_sales` view.
"""
import csv
from datetime import datetime

from app.database import connect_readwrite, create_schema, get_csv_path, get_db_path

REQUIRED_COLUMNS = [
    "Transaction_Id", "Order_date", "Product", "Category", "Region",
    "Sales_channel", "Quantity", "Unit_price", "Discount_amount", "Status",
]
DATE_FORMAT = "%d-%m-%Y"  # the CSV uses day-month-year, e.g. 03-01-2026 = 3 Jan 2026


def parse_date(text):
    """'03-01-2026' -> '2026-01-03'. Returns None if the date is not valid."""
    try:
        return datetime.strptime(text.strip(), DATE_FORMAT).date().isoformat()
    except ValueError:
        return None


def parse_number(text):
    """Returns (number, problem). problem is None, 'missing' or 'invalid'."""
    text = text.strip()
    if text == "":
        return None, "missing"
    try:
        return float(text), None
    except ValueError:
        return None, "invalid"


def check_numbers(raw_row):
    """Validate quantity, unit price and discount.

    Returns (quantity, unit_price, discount, issues) where `issues` is a list
    of problem names. A bad number is stored as None (NULL) in the database.
    """
    issues = []

    quantity, problem = parse_number(raw_row["Quantity"])
    if problem is None and (quantity < 0 or quantity != int(quantity)):
        problem = "invalid"
    if problem:
        issues.append(problem + "_quantity")
        quantity = None
    else:
        quantity = int(quantity)
        if quantity == 0:
            issues.append("zero_quantity")  # edge case: flagged, not a normal sale

    unit_price, problem = parse_number(raw_row["Unit_price"])
    if problem is None and unit_price < 0:
        problem = "invalid"
    if problem:
        issues.append(problem + "_unit_price")  # we never guess a missing price
        unit_price = None

    discount, problem = parse_number(raw_row["Discount_amount"])
    if problem is None and discount < 0:
        problem = "invalid"
    if problem:
        issues.append(problem + "_discount")
        discount = None

    if quantity and unit_price is not None and discount is not None:
        if discount > quantity * unit_price:
            issues.append("discount_exceeds_total")

    return quantity, unit_price, discount, issues


def load_csv_to_db(csv_path=None):
    """Read the CSV, validate each row, write to SQLite. Returns the data report."""
    csv_path = csv_path or get_csv_path()
    conn = connect_readwrite()
    create_schema(conn)

    seen_ids = set()
    with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        missing_columns = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing_columns:
            conn.close()
            raise ValueError("CSV is missing columns: " + ", ".join(missing_columns))

        for line_number, raw_row in enumerate(reader, start=2):  # line 1 is the header
            # DictReader gives None for cells missing at the end of a short line
            raw_row = {key: (value or "") for key, value in raw_row.items() if key}
            transaction_id = raw_row["Transaction_Id"].strip()
            order_date = parse_date(raw_row["Order_date"])

            # --- rows that cannot be stored at all ---
            reject_reason = None
            if transaction_id == "":
                reject_reason = "missing_transaction_id"
            elif transaction_id in seen_ids:
                reject_reason = "duplicate_transaction_id"
            elif order_date is None:
                reject_reason = "invalid_order_date (" + raw_row["Order_date"] + ")"
            if reject_reason:
                conn.execute(
                    "INSERT INTO rejected_rows (csv_line_number, transaction_id, reason) VALUES (?, ?, ?)",
                    (line_number, transaction_id, reject_reason),
                )
                continue
            seen_ids.add(transaction_id)

            # --- rows that are stored, but may be flagged ---
            quantity, unit_price, discount, issues = check_numbers(raw_row)
            product = raw_row["Product"].strip()
            region = raw_row["Region"].strip()
            if product == "":
                issues.append("missing_product")
            if region == "":
                issues.append("missing_region")

            conn.execute(
                """INSERT INTO sales (transaction_id, order_date, product, category, region,
                       sales_channel, quantity, unit_price, discount_amount, status, data_issue)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    transaction_id, order_date, product or None,
                    raw_row["Category"].strip() or None, region or None,
                    raw_row["Sales_channel"].strip() or None,
                    quantity, unit_price, discount,
                    raw_row["Status"].strip().capitalize(),
                    "; ".join(issues) if issues else None,
                ),
            )
    conn.commit()
    report = build_data_report(conn)
    conn.close()
    return report


def excluded_reason(status, data_issue):
    """Plain-English reason why a stored row is not counted as revenue."""
    reasons = []
    if status != "Completed":
        reasons.append("status is " + status)
    if data_issue:
        reasons.append(data_issue)
    return "; ".join(reasons)


def build_data_report(conn):
    """Summary of what was loaded, rejected and excluded from revenue.

    These queries are fixed text written by the developer (no user input),
    so they run directly on the connection.
    """
    rejected = conn.execute(
        "SELECT csv_line_number, transaction_id, reason FROM rejected_rows ORDER BY csv_line_number"
    ).fetchall()
    stored = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    included = conn.execute("SELECT COUNT(*) FROM valid_sales").fetchone()[0]
    excluded_rows = conn.execute(
        """SELECT transaction_id, status, data_issue FROM sales
           WHERE NOT (status = 'Completed' AND data_issue IS NULL)
           ORDER BY transaction_id"""
    ).fetchall()
    date_range = conn.execute("SELECT MIN(order_date), MAX(order_date) FROM sales").fetchone()

    excluded = [
        {"transaction_id": row[0], "reason": excluded_reason(row[1], row[2])}
        for row in excluded_rows
    ]
    return {
        "total_rows_received": stored + len(rejected),
        "rows_loaded": stored,
        "rows_rejected": len(rejected),
        "rejected_details": [
            {"csv_line": r[0], "transaction_id": r[1], "reason": r[2]} for r in rejected
        ],
        "rows_counted_in_revenue": included,
        "rows_excluded_from_revenue": len(excluded),
        "excluded_details": excluded,
        "date_range": {"first_order": date_range[0], "last_order": date_range[1]},
        "revenue_definition": "Quantity x Unit_price - Discount_amount, for Completed rows with no data issue",
    }


if __name__ == "__main__":
    print("Loading", get_csv_path(), "->", get_db_path())
    result = load_csv_to_db()
    print("Total rows received      :", result["total_rows_received"])
    print("Rows loaded into SQLite  :", result["rows_loaded"])
    print("Rows rejected            :", result["rows_rejected"])
    for item in result["rejected_details"]:
        print("   rejected line", item["csv_line"], item["transaction_id"], "-", item["reason"])
    print("Rows counted in revenue  :", result["rows_counted_in_revenue"])
    print("Rows excluded (stored)   :", result["rows_excluded_from_revenue"])
    for item in result["excluded_details"]:
        print("   excluded", item["transaction_id"], "-", item["reason"])
