"""SQL safety checks.

The app does NOT let the LLM write SQL (it only picks one of 5 fixed
operations), but every query still passes through this validator before it
is executed. This is "defence in depth": if someone later adds text-to-SQL,
the safety check is already in place.

Rules (a query is rejected if ANY rule fails):
1. Must be a single statement (no second statement after a ';').
2. No SQL comments (-- or /* */), they can hide things.
3. Must start with SELECT.
4. Must not contain forbidden words (INSERT, UPDATE, DELETE, DROP, ...).
5. Every table after FROM / JOIN must be in the allowed list.
"""
import re

# The only tables/views a query may read from.
ALLOWED_TABLES = {"sales", "valid_sales"}

# Words that must never appear anywhere in a query.
# We check whole words only, so a column like "updated_at" would not match "update".
FORBIDDEN_WORDS = [
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "truncate", "attach", "detach", "pragma", "vacuum", "reindex",
    "load_extension", "begin", "commit", "rollback", "grant", "revoke",
]


class UnsafeQueryError(Exception):
    """Raised when a query fails a safety rule."""


def validate_select_query(sql):
    """Return the cleaned query if it is safe, otherwise raise UnsafeQueryError."""
    if not isinstance(sql, str) or not sql.strip():
        raise UnsafeQueryError("Query is empty.")

    query = sql.strip()

    # Rule 2: no comments
    if "--" in query or "/*" in query or "*/" in query:
        raise UnsafeQueryError("SQL comments are not allowed.")

    # Rule 1: single statement. One trailing ';' is fine, anything after is not.
    if query.endswith(";"):
        query = query[:-1].rstrip()
    if ";" in query:
        raise UnsafeQueryError("Only one SQL statement is allowed.")

    lowered = query.lower()

    # Rule 3: must start with SELECT
    if not re.match(r"^select\b", lowered):
        raise UnsafeQueryError("Only SELECT queries are allowed.")

    # Rule 4: forbidden words (whole words only)
    for word in FORBIDDEN_WORDS:
        if re.search(r"\b" + word + r"\b", lowered):
            raise UnsafeQueryError("Forbidden keyword in query: " + word.upper())

    # Rule 5: only approved tables. Comma joins ("FROM a, b") are blocked
    # because they would hide a second table from the check below.
    if re.search(r"\bfrom\s+[\w\.]+(\s+(as\s+)?\w+)?\s*,", lowered):
        raise UnsafeQueryError("Comma joins are not allowed. Use JOIN.")
    table_names = re.findall(r"\b(?:from|join)\s+([\w\.\"`\[\]]+)", lowered)
    if not table_names:
        raise UnsafeQueryError("Query must read from an approved table.")
    for name in table_names:
        if name not in ALLOWED_TABLES:
            raise UnsafeQueryError("Table not allowed: " + name)

    return query
