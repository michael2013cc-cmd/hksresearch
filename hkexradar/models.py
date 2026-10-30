from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Grade = Literal["S", "A", "B", "C"]
Direction = Literal["positive", "negative", "neutral", "unclear"]
Hint = Literal["high", "medium", "low"]
TextStatus = Literal["ok", "unavailable", "skipped"]


class AnnouncementRaw(BaseModel):
    news_id: str
    stock_code: str
    stock_name: str
    published_at: datetime
    title: str
    category_label: str
    file_type: str
    file_info: str
    file_link: str


class Announcement(BaseModel):
    news_id: str
    primary_code: str
    alt_codes: list[str] = Field(default_factory=list)
    stock_name: str
    published_at: datetime
    title: str
    doc_group: str
    headline_tags: list[str] = Field(default_factory=list)
    category_label: str
    file_url: str
    file_bytes: int | None = None
    pdf_path: str | None = None
    text_head: str = ""
    text_status: TextStatus = "skipped"
    is_revision: bool = False
    revision_of: str | None = None


class Fact(BaseModel):
    key: str
    value: str
    quote: str


class AnnouncementInsight(BaseModel):
    news_id: str
    summary_zh: str
    facts: list[Fact] = Field(default_factory=list)
    surprise_hint: Hint = "medium"
    direction: Direction = "unclear"
    direction_reason: str = ""
    uncertainty: str = ""
    source: Literal["llm", "rule"] = "llm"


class ScoreBreakdown(BaseModel):
    category_prior: float
    scale: float
    surprise: float
    scarcity: float
    coverage: float
    spread: float


class ScoredAnnouncement(BaseModel):
    announcement: Announcement
    insight: AnnouncementInsight | None = None
    magnitude: float
    interest: float
    final_score: float
    grade: Grade
    breakdown: ScoreBreakdown
    triage_reason: str = ""
    flags: list[str] = Field(default_factory=list)


class CategoryStat(BaseModel):
    doc_group: str
    count: int


class Quality(BaseModel):
    collection_errors: list[str] = Field(default_factory=list)
    pdf_unavailable: int = 0
    revisions: int = 0
    llm_fallbacks: int = 0
    total_records: int = 0


class DailyReport(BaseModel):
    report_date: date
    generated_at: datetime
    window_from: str | None = None
    total: int
    candidate_count: int
    read_count: int
    grade_counts: dict[str, int] = Field(default_factory=dict)
    category_stats: list[CategoryStat] = Field(default_factory=list)
    top: list[ScoredAnnouncement] = Field(default_factory=list)
    ranked: list[ScoredAnnouncement] = Field(default_factory=list)
    overview: str = ""
    quality: Quality = Field(default_factory=Quality)
