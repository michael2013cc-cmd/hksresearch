from __future__ import annotations

from datetime import date
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

Direction = Literal["positive", "negative", "neutral", "unclear"]


class Evidence(BaseModel):
    page: int | None = None
    quote: str


class AnalyzerFact(BaseModel):
    key: str
    value: str
    unit: str | None = None
    currency: str | None = None
    evidence: Evidence
    confidence: float = 1.0


class AnalyzerEvent(BaseModel):
    family: str
    type: str
    code: str
    news_id: str
    effective_date: date | None = None
    direction: Direction = "unclear"
    materiality: float = 0.0
    confidence: float = 1.0
    summary: str = ""
    facts: list[AnalyzerFact] = Field(default_factory=list)
    links: list[tuple[str, str]] = Field(default_factory=list)


class AnalyzerResult(BaseModel):
    analyzer: str
    events: list[AnalyzerEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def quote_around(text: str, needle: str, width: int = 140) -> str:
    index = text.find(needle)
    if index < 0:
        return text[:width].strip()
    start = max(0, index - 30)
    return text[start:index + width].strip()


def make_fact(key: str, value: int | float | None, text: str, needle: str,
              *, unit: str | None = None, currency: str | None = None,
              pages: list[tuple[int, str]] | None = None) -> AnalyzerFact | None:
    if value is None or value == 0:
        return None
    shown = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    quote = quote_around(text, needle)
    page = None
    if pages:
        page = next((number for number, content in pages if quote in content), None)
        if page is None:
            page = next((number for number, content in pages if needle in content), None)
    return AnalyzerFact(
        key=key,
        value=shown,
        unit=unit,
        currency=currency,
        evidence=Evidence(page=page, quote=quote),
    )


@runtime_checkable
class Analyzer(Protocol):
    family: str

    def matches(self, ann: Any) -> bool: ...

    def analyze(self, ann: Any, text: str, ctx: Any = None) -> AnalyzerResult: ...
