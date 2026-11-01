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


@runtime_checkable
class Analyzer(Protocol):
    family: str

    def matches(self, ann: Any) -> bool: ...

    def analyze(self, ann: Any, text: str, ctx: Any = None) -> AnalyzerResult: ...
