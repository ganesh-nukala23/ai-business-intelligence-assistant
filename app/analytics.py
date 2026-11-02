"""The five analytics operations. All numbers come from SQL on the `valid_sales` view.

Revenue = Quantity x Unit_price - Discount_amount  (defined once, in the view).
Each function returns: {"answer": text, "data": dict, "queries": [ {sql, params} ]}
"""
from app.database import run_safe_query

MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
# short forms people type (sept is common too)
MONTH_ALIASES = {name[:3]: number for number, name in enumerate(MONTH_NAMES, start=1)}
MONTH_ALIASES["sept"] = 9
for _number, _name in enumerate(MONTH_NAMES, start=1):
    MONTH_ALIASES[_name] = _number


class AnalyticsError(Exception):
    """A problem with the question itself (e.g. unknown month). Shown to the user."""


def money(value):
    return f"{value:,.2f}"


def run(conn, queries, sql, params=()):
    """Run one safe query and remember it so the API can show it."""
    queries.append({"sql": " ".join(sql.split()), "params": list(params)})
    return run_safe_query(conn, sql, params)


def month_label(year_month):
    """'2026-01' -> 'January 2026'"""
    year, month = year_month.split("-")
    return MONTH_NAMES[int(month) - 1].capitalize() + " " + year


# ---------------------------------------------------------------------------
# Month handling (used by compare_months)
# ---------------------------------------------------------------------------
def data_month_range(conn, queries):
    row = run(conn, queries, "SELECT MIN(strftime('%Y-%m', order_date)) AS first_month, "
                             "MAX(strftime('%Y-%m', order_date)) AS last_month FROM sales")[0]
    return row["first_month"], row["last_month"]


def normalize_month(conn, queries, text):
    """Turn 'January', 'jan 2026', '2026-01' into '2026-01'. Raises AnalyticsError if unclear."""
    cleaned = str(text).strip().lower()
    year = None

    parts = cleaned.replace("-", " ").replace("/", " ").replace(",", " ").split()
    month_number = None
    for part in parts:
        if part in MONTH_ALIASES:
            month_number = MONTH_ALIASES[part]
        elif part.isdigit() and len(part) == 4:
            year = int(part)
        elif part.isdigit() and 1 <= int(part) <= 12 and month_number is None:
            month_number = int(part)
        else:
            raise AnalyticsError(f"I could not understand the month '{text}'.")
    if month_number is None:
        raise AnalyticsError(f"I could not understand the month '{text}'.")

    first_month, last_month = data_month_range(conn, queries)
    if year is None:
        # No year given: use the year in the data that has this month
        rows = run(conn, queries,
                   "SELECT DISTINCT substr(order_date, 1, 4) AS year FROM sales "
                   "WHERE substr(order_date, 6, 2) = ?", [f"{month_number:02d}"])
        if len(rows) > 1:
            raise AnalyticsError(f"{MONTH_NAMES[month_number-1].capitalize()} exists in several years. Please include the year.")
        if len(rows) == 0:
            raise AnalyticsError(f"There is no data for {MONTH_NAMES[month_number-1].capitalize()}. "
                                 f"The data covers {month_label(first_month)} to {month_label(last_month)}.")
        year = int(rows[0]["year"])

    year_month = f"{year:04d}-{month_number:02d}"
    exists = run(conn, queries, "SELECT COUNT(*) AS n FROM sales WHERE strftime('%Y-%m', order_date) = ?",
                 [year_month])[0]["n"]
    if exists == 0:
        raise AnalyticsError(f"There is no data for {month_label(year_month)}. "
                             f"The data covers {month_label(first_month)} to {month_label(last_month)}.")
    return year_month


# ---------------------------------------------------------------------------
# A. Total revenue
# ---------------------------------------------------------------------------
def total_revenue(conn, **_ignored):
    queries = []
    row = run(conn, queries, """
        SELECT COUNT(*) AS included_transactions,
               COALESCE(ROUND(SUM(quantity * unit_price), 2), 0) AS gross_sales,
               COALESCE(ROUND(SUM(discount_amount), 2), 0)       AS total_discounts,
               COALESCE(ROUND(SUM(revenue), 2), 0)               AS total_revenue
        FROM valid_sales""")[0]
    all_rows = run(conn, queries, "SELECT COUNT(*) AS n FROM sales")[0]["n"]
    excluded = all_rows - row["included_transactions"]
    data = {**row, "total_transactions_in_database": all_rows, "excluded_transactions": excluded}
    answer = (f"Total revenue is {money(row['total_revenue'])} from {row['included_transactions']} "
              f"completed transactions (gross sales {money(row['gross_sales'])} minus discounts "
              f"{money(row['total_discounts'])}). {excluded} transaction(s) were excluded "
              f"(returned or invalid data).")
    return {"answer": answer, "data": data, "queries": queries}


# ---------------------------------------------------------------------------
# B / D. Top product and top region share the same logic
# ---------------------------------------------------------------------------
def top_by_group(conn, column, label):
    queries = []
    # `column` is chosen by our own code ('product' or 'region'), never by the user.
    rows = run(conn, queries, f"""
        SELECT {column} AS {label}, COUNT(*) AS transactions, SUM(quantity) AS units_sold,
               ROUND(SUM(revenue), 2) AS total_revenue
        FROM valid_sales
        GROUP BY {column}
        ORDER BY total_revenue DESC, {column} ASC""")
    if not rows:
        raise AnalyticsError("There are no valid sales to analyse.")
    best = rows[0]
    tied = [r[label] for r in rows if r["total_revenue"] == best["total_revenue"]]
    if len(tied) > 1:
        answer = (f"{' and '.join(tied)} are tied for highest revenue at "
                  f"{money(best['total_revenue'])} each.")
    else:
        answer = f"{best[label]} generated the highest revenue: {money(best['total_revenue'])} from {best['transactions']} transactions."
    data = {f"top_{label}": best[label], "top_revenue": best["total_revenue"], f"all_{label}s": rows}
    return {"answer": answer, "data": data, "queries": queries}


def top_product(conn, **_ignored):
    return top_by_group(conn, "product", "product")


def top_region(conn, **_ignored):
    return top_by_group(conn, "region", "region")


# ---------------------------------------------------------------------------
# C. Monthly trend
# ---------------------------------------------------------------------------
def monthly_revenue(conn, **_ignored):
    queries = []
    # LEFT JOIN so a month whose rows were all excluded still shows up (with 0 revenue).
    # We group by the full expression, NOT the alias `month`: valid_sales also has a
    # column called month, and SQLite would pick that column and split the groups.
    rows = run(conn, queries, """
        SELECT strftime('%Y-%m', s.order_date) AS month,
               COUNT(v.transaction_id) AS transactions,
               COALESCE(ROUND(SUM(v.revenue), 2), 0) AS total_revenue
        FROM sales s
        LEFT JOIN valid_sales v ON v.transaction_id = s.transaction_id
        GROUP BY strftime('%Y-%m', s.order_date)
        ORDER BY strftime('%Y-%m', s.order_date) ASC""")
    previous = None
    for row in rows:  # month-over-month change, computed in Python
        if previous is None:
            row["change_vs_previous"] = None
            row["change_pct"] = None
        else:
            row["change_vs_previous"] = round(row["total_revenue"] - previous, 2)
            row["change_pct"] = percent_change(previous, row["total_revenue"])
        previous = row["total_revenue"]
        row["month_name"] = month_label(row["month"])
    best = max(rows, key=lambda r: r["total_revenue"])
    worst = min(rows, key=lambda r: r["total_revenue"])
    parts = [f"{r['month_name']}: {money(r['total_revenue'])}" for r in rows]
    answer = ("Monthly revenue - " + "; ".join(parts) +
              f". Highest month: {best['month_name']}; lowest month: {worst['month_name']}.")
    return {"answer": answer, "data": {"months": rows}, "queries": queries}


# ---------------------------------------------------------------------------
# E. Compare two months
# ---------------------------------------------------------------------------
def percent_change(old_value, new_value):
    """(new - old) / old * 100. Returns None when old is 0 (cannot divide by zero)."""
    if old_value == 0:
        return None
    return round((new_value - old_value) / old_value * 100, 2)


def compare_months(conn, month_a=None, month_b=None, **_ignored):
    queries = []
    if not month_a or not month_b:
        raise AnalyticsError("Please name two months to compare, for example: "
                             "'Compare January and February revenue'.")
    first = normalize_month(conn, queries, month_a)
    second = normalize_month(conn, queries, month_b)
    if first == second:
        raise AnalyticsError("Please give two different months to compare.")
    earlier, later = sorted([first, second])  # change is always earlier -> later

    def revenue_for(year_month):
        return run(conn, queries, """
            SELECT COUNT(*) AS transactions, COALESCE(ROUND(SUM(revenue), 2), 0) AS total_revenue
            FROM valid_sales WHERE month = ?""", [year_month])[0]

    old = revenue_for(earlier)
    new = revenue_for(later)
    difference = round(new["total_revenue"] - old["total_revenue"], 2)
    pct = percent_change(old["total_revenue"], new["total_revenue"])

    data = {
        "earlier_month": earlier, "earlier_month_revenue": old["total_revenue"],
        "later_month": later, "later_month_revenue": new["total_revenue"],
        "absolute_difference": difference, "percentage_change": pct,
        "formula": "percentage_change = (later - earlier) / earlier x 100",
    }
    direction = "increased" if difference > 0 else "decreased" if difference < 0 else "did not change"
    pct_text = f"{abs(pct)}%" if pct is not None else "undefined (earlier month revenue is 0)"
    answer = (f"Revenue {direction} from {money(old['total_revenue'])} in {month_label(earlier)} to "
              f"{money(new['total_revenue'])} in {month_label(later)}: a difference of "
              f"{money(difference)} ({pct_text}).")
    return {"answer": answer, "data": data, "queries": queries}


# The only operations the app can run. The AI must pick one of these names.
INTENT_HANDLERS = {
    "total_revenue": total_revenue,
    "top_product": top_product,
    "monthly_revenue": monthly_revenue,
    "top_region": top_region,
    "compare_months": compare_months,
}
SUPPORTED_INTENTS = list(INTENT_HANDLERS.keys())


def run_intent(conn, intent, month_a=None, month_b=None):
    if intent not in INTENT_HANDLERS:
        raise AnalyticsError("Unsupported operation: " + str(intent))
    return INTENT_HANDLERS[intent](conn, month_a=month_a, month_b=month_b)
