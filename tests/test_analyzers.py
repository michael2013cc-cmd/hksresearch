from datetime import datetime

from hkexradar.analyzers.base import AnalyzerEvent, AnalyzerFact, AnalyzerResult, Evidence
from hkexradar.analyzers.ndr import NdrAnalyzer
from hkexradar.models import Announcement


def _announcement(news_id: str = "1", doc_group: str = "翌日披露報表") -> Announcement:
    return Announcement(
        news_id=news_id,
        primary_code="00700",
        stock_name="測試公司",
        published_at=datetime(2026, 10, 30, 18, 0),
        title="翌日披露報表",
        doc_group=doc_group,
        headline_tags=["股份購回"],
        category_label="翌日披露報表 - [股份購回]",
        file_url="https://example.test/1.pdf",
    )


def _wrap(event_text: str) -> str:
    return (
        "A. 已發行股份或庫存股份變動事件 "
        "於下列日期開始時的結存(註1) 2026年9月30日 1,000,000 0 1,000,000 "
        f"{event_text} "
        "於下列日期結束時的結存 (註5及6) 2026年10月30日 900,000 0 900,000"
    )


def test_evidence_requires_a_quote():
    fact = AnalyzerFact(key="shares", value="100", evidence=Evidence(page=1, quote="100 股"))
    assert fact.evidence.quote == "100 股"
    assert fact.evidence.page == 1


def test_analyzer_result_keeps_events_and_warnings():
    event = AnalyzerEvent(
        family="ndr",
        type="新增購回",
        code="00700",
        news_id="1",
        summary="測試",
    )
    result = AnalyzerResult(analyzer="ndr", events=[event], warnings=["pdf missing"])
    assert result.events[0].type == "新增購回"
    assert result.warnings == ["pdf missing"]


def test_ndr_analyzer_matches_only_next_day_disclosure_returns():
    analyzer = NdrAnalyzer()
    assert analyzer.matches(_announcement()) is True
    assert analyzer.matches(_announcement(doc_group="公告及通告")) is False


def test_ndr_analyzer_builds_buyback_event_with_evidence():
    text = _wrap(
        "1). 購回股份 (股份購回並註銷) 於2026年10月13日購回之股份已於2026年10月30日註銷 "
        "變動日期 2026年10月30日 -100,000 0.1 % HKD 10 "
        "B. 贖回/購回股份 (擬註銷但截至期終結存日期尚未註銷) 備註："
        "合共購回股份總數 400,000 合共付出的價格總額 (元) HKD 270,390 "
        "購回股份（擬註銷）數目 400,000 購回股份（擬持作庫存股份） 數目 "
    )
    result = NdrAnalyzer().analyze(_announcement(), text)

    assert len(result.events) == 1
    event = result.events[0]
    assert event.family == "ndr"
    assert event.type == "購回並註銷"
    assert event.code == "00700"
    assert event.news_id == "1"

    facts = {fact.key: fact for fact in event.facts}
    assert facts["buyback.shares"].value == "400000"
    assert facts["buyback.amount.HKD"].value == "270390"
    assert facts["buyback.cancel.shares"].value == "400000"
    assert facts["cancelled.shares"].value == "100000"
    assert facts["shares.start"].value == "1000000"
    assert facts["shares.end"].value == "900000"
    for fact in event.facts:
        assert fact.evidence.quote
        assert fact.evidence.quote in text


def test_ndr_analyzer_attaches_page_numbers():
    text = _wrap(
        "1). 購回股份 (股份購回並註銷) 於2026年10月13日購回之股份已於2026年10月30日註銷 "
        "變動日期 2026年10月30日 -100,000 0.1 % HKD 10 "
        "B. 贖回/購回股份 (擬註銷但截至期終結存日期尚未註銷) 備註："
    )
    result = NdrAnalyzer().analyze(_announcement(), text, pages=[(1, "封面"), (2, text)])
    assert result.events[0].facts
    assert all(fact.evidence.page == 2 for fact in result.events[0].facts)


def test_ndr_analyzer_records_pending_and_new_issuance():
    text = _wrap(
        "1). 供股 - 涉及新股於2026年10月30日配發及發行532,227,024股供股股份 "
        "變動日期 2026年10月30日 532,227,024 150 % HKD 0.14 "
        "B. 贖回/購回股份 (擬註銷但截至期終結存日期尚未註銷) "
        "1). 已購回以作註銷但尚未註銷之股份 變動日期 2026年10月30日 100,000 0.0082 % HKD 19.782 "
        "確認"
    )
    result = NdrAnalyzer().analyze(_announcement(), text)

    facts = {fact.key: fact for fact in result.events[0].facts}
    assert facts["issued.new"].value == "532227024"
    assert facts["pending.shares"].value == "100000"
    assert result.events[0].type == "混合"
