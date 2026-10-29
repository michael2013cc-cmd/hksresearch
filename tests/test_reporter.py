from datetime import date, datetime
from pathlib import Path

from hkexradar.models import (
    Announcement,
    AnnouncementInsight,
    CategoryStat,
    DailyReport,
    Fact,
    Quality,
    ScoredAnnouncement,
    ScoreBreakdown,
)
from hkexradar.reporter import build_overview, render_markdown, write_report


def _scored(rank_id: str = "1", grade: str = "A", score_value: float = 70.0) -> ScoredAnnouncement:
    ann = Announcement(
        news_id=rank_id,
        primary_code="01234",
        stock_name="示例控股",
        published_at=datetime(2026, 9, 8, 17, 30),
        title="私有化建議",
        doc_group="公告及通告",
        headline_tags=["私有化"],
        category_label="公告及通告 - [私有化]",
        file_url="https://example.com/a.pdf",
        file_bytes=120_000,
    )
    return ScoredAnnouncement(
        announcement=ann,
        insight=AnnouncementInsight(
            news_id=rank_id,
            summary_zh="要約人擬溢價 32% 私有化。",
            facts=[Fact(key="對價", value="12.5 港元/股", quote="每股現金12.5港元")],
            direction="positive",
        ),
        magnitude=78.0,
        interest=88.0,
        final_score=score_value,
        grade=grade,
        breakdown=ScoreBreakdown(
            category_prior=0.95, scale=0.7, surprise=1.0,
            scarcity=0.9, coverage=0.6, spread=0.9,
        ),
    )


def _report() -> DailyReport:
    return DailyReport(
        report_date=date(2026, 9, 8),
        generated_at=datetime(2026, 9, 8, 23, 30),
        total=590,
        candidate_count=120,
        read_count=60,
        grade_counts={"S": 1, "A": 2, "B": 10, "C": 107},
        category_stats=[CategoryStat(doc_group="公告及通告", count=198)],
        top=[_scored()],
        ranked=[_scored()],
        quality=Quality(collection_errors=[], pdf_unavailable=7, revisions=3, total_records=590),
    )


def test_overview_mentions_counts():
    text = build_overview(_report())
    assert "590" in text
    assert "120" in text
    assert "公告及通告" in text


def test_markdown_contains_required_sections():
    md = render_markdown(_report())
    assert "# 港交所公告日報 · 2026-09-08" in md
    assert "## 今日概覽" in md
    assert "## Top 20" in md
    assert "## 分類統計" in md
    assert "## 數據質量" in md
    assert "示例控股" in md
    assert "01234.HK" in md
    assert "12.5 港元/股" in md


def test_markdown_shows_data_quality_numbers():
    md = render_markdown(_report())
    assert "PDF 抽取失敗：7 條" in md
    assert "疑似修訂版：3 條" in md


def test_markdown_shows_publish_time_and_timeline():
    md = render_markdown(_report())
    assert "**發布時間**：2026-09-08 17:30" in md
    assert "## 全部候選（按發布時間）" in md
    assert "| 17:30 | 01234.HK | 示例控股 | 私有化建議 | A |" in md


def test_write_report_creates_md_and_json(tmp_path: Path):
    md_path, json_path = write_report(_report(), tmp_path)
    assert md_path.name == "2026-09-08-hkex-daily.md"
    assert json_path.name == "2026-09-08-hkex-daily.json"
    assert md_path.exists() and json_path.exists()
    assert "590" in md_path.read_text(encoding="utf-8")
    assert '"total": 590' in json_path.read_text(encoding="utf-8")
