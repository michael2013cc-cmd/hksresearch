from datetime import date, datetime

from hkexradar.models import (
    Announcement,
    AnnouncementInsight,
    DailyReport,
    Fact,
    ScoredAnnouncement,
    ScoreBreakdown,
)


def _ann() -> Announcement:
    return Announcement(
        news_id="12325368",
        primary_code="01407",
        alt_codes=["80700"],
        stock_name="交運燃氣",
        published_at=datetime(2026, 9, 8, 22, 59),
        title="控股股東質押股份解除公告",
        doc_group="公告及通告",
        headline_tags=["內幕消息"],
        category_label="公告及通告 - [內幕消息]",
        file_url="https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0908/2026090801276_c.pdf",
        file_bytes=134144,
    )


def test_announcement_roundtrip():
    ann = _ann()
    again = Announcement.model_validate_json(ann.model_dump_json())
    assert again == ann
    assert again.alt_codes == ["80700"]


def test_scored_announcement_roundtrip():
    scored = ScoredAnnouncement(
        announcement=_ann(),
        insight=AnnouncementInsight(
            news_id="12325368",
            summary_zh="控股股東解除股份質押。",
            facts=[Fact(key="質押股數", value="1.2 億股", quote="合共 1.2 億股")],
        ),
        magnitude=62.0,
        interest=55.0,
        final_score=59.2,
        grade="B",
        breakdown=ScoreBreakdown(
            category_prior=0.95,
            scale=0.7,
            surprise=0.6,
            scarcity=0.5,
            coverage=0.6,
            spread=0.7,
        ),
    )
    assert ScoredAnnouncement.model_validate_json(scored.model_dump_json()) == scored


def test_daily_report_defaults():
    report = DailyReport(
        report_date=date(2026, 9, 8),
        generated_at=datetime(2026, 9, 8, 23, 30),
        total=590,
        candidate_count=120,
        read_count=60,
    )
    assert report.top == []
    assert report.grade_counts == {}
    assert report.quality.total_records == 0
