"""Analytics on the real dataset. Expected numbers were computed separately
from the CSV with plain Python (not with the app code)."""
import csv

import pytest

from app import analytics
from app.database import get_csv_path


def independent_total_revenue():
    """Re-calculate total revenue straight from the CSV, without SQLite."""
    total = 0
    for row in csv.DictReader(open(get_csv_path(), newline="", encoding="utf-8")):
        if row["Status"] != "Completed" or row["Unit_price"] == "" or int(row["Quantity"]) == 0:
            continue
        total += int(row["Quantity"]) * float(row["Unit_price"]) - float(row["Discount_amount"])
    return total


def test_total_revenue(conn):
    result = analytics.total_revenue(conn)
    assert result["data"]["total_revenue"] == 1439200.0
    assert result["data"]["total_revenue"] == independent_total_revenue()
    assert result["data"]["included_transactions"] == 48
    assert result["data"]["excluded_transactions"] == 3
    assert result["data"]["gross_sales"] - result["data"]["total_discounts"] == 1439200.0


def test_top_product(conn):
    result = analytics.top_product(conn)
    assert result["data"]["top_product"] == "Monitor"
    assert result["data"]["top_revenue"] == 473000.0
    # product figures must add up to the total (same revenue definition everywhere)
    assert sum(p["total_revenue"] for p in result["data"]["all_products"]) == 1439200.0


def test_top_region(conn):
    result = analytics.top_region(conn)
    assert result["data"]["top_region"] == "South"
    assert result["data"]["top_revenue"] == 411200.0
    assert sum(r["total_revenue"] for r in result["data"]["all_regions"]) == 1439200.0


def test_monthly_revenue_is_chronological_and_adds_up(conn):
    months = analytics.monthly_revenue(conn)["data"]["months"]
    assert [m["month"] for m in months] == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    assert [m["total_revenue"] for m in months] == [210250.0, 234600.0, 223900.0, 240700.0, 318500.0, 211250.0]
    assert sum(m["total_revenue"] for m in months) == 1439200.0
    assert months[0]["change_pct"] is None  # first month has nothing to compare with


def test_april_excludes_returned_and_zero_quantity_rows(conn):
    april = [m for m in analytics.monthly_revenue(conn)["data"]["months"] if m["month"] == "2026-04"][0]
    assert april["transactions"] == 8  # 10 April rows - TXN0033 (returned) - TXN0034 (zero qty)


def test_compare_months(conn):
    data = analytics.compare_months(conn, "January", "February")["data"]
    assert data["earlier_month_revenue"] == 210250.0
    assert data["later_month_revenue"] == 234600.0
    assert data["absolute_difference"] == 24350.0
    assert data["percentage_change"] == 11.58


def test_compare_months_is_chronological_even_if_asked_backwards(conn):
    data = analytics.compare_months(conn, "February", "January")["data"]
    assert data["earlier_month"] == "2026-01"
    assert data["absolute_difference"] == 24350.0


def test_compare_months_with_year_and_decrease(conn):
    data = analytics.compare_months(conn, "2026-05", "jun 2026")["data"]
    assert data["absolute_difference"] == -107250.0
    assert data["percentage_change"] == -33.67


@pytest.mark.parametrize("month_a, month_b", [
    ("July", "January"),      # no data for July
    ("January", "January"),   # same month twice
    ("Smarch", "January"),    # not a month
    (None, "January"),        # missing month
])
def test_compare_months_bad_input_raises_clear_error(conn, month_a, month_b):
    with pytest.raises(analytics.AnalyticsError):
        analytics.compare_months(conn, month_a, month_b)


def test_percent_change_zero_base_is_safe():
    assert analytics.percent_change(0, 500) is None
    assert analytics.percent_change(200, 100) == -50.0


def test_unknown_intent_is_rejected(conn):
    with pytest.raises(analytics.AnalyticsError):
        analytics.run_intent(conn, "drop_everything")
