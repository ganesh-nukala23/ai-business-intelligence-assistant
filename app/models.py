"""Request and response shapes for the API (Pydantic)."""
from typing import Any, Optional

from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    answer: str
    data: dict[str, Any]
    sql: str                      # the SQL (with its ? parameter values) that produced the numbers
    status: str                   # "success"
    interpreted_by: str           # "llm" or "fallback"
    ai_note: Optional[str] = None
