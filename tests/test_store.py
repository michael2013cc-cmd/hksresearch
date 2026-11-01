from datetime import datetime

from hkexradar.analyzers.base import AnalyzerEvent, AnalyzerFact, AnalyzerResult, Evidence
from hkexradar.models import Announcement
from hkexradar.store import EventStore


def _announcement(news_id="1", code="00700", day=30) -> Announcement:
    return Announcement(
        news_id=news_id,
        primary_code=code,
        stock_name="測試公司",
        published_at=datetime(2026, 10, day, 18, 0),
        title="翌日披露報表",
        doc_group="翌日披露報表",
        headline_tags=["股份購回"],
        category_label="翌日披露報表 - [股份購回]",
        file_url=f"https://example.test/{news_id}.pdf",
    )


def _result(value: str, key: str = "buyback.shares", news_id: str = "1",
            code: str = "00700") -> AnalyzerResult:
    fact = AnalyzerFact(key=key, value=value, evidence=Evidence(page=1, quote=f"{value} 股"))
    event = AnalyzerEvent(
        family="ndr",
        type="新增購回",
        code=code,
        news_id=news_id,
        summary="測試",
        facts=[fact],
    )
    return AnalyzerResult(analyzer="ndr", events=[event])


def test_store_writes_and_queries_event(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.add_result(_announcement(), _result("400000"))

    events = store.events_for_day("2026-10-30")
    assert len(events) == 1
    assert events[0]["code"] == "00700"
    assert events[0]["type"] == "新增購回"

    facts = store.facts_for_event(events[0]["event_id"])
    assert [(fact["key"], fact["value"]) for fact in facts] == [("buyback.shares", "400000")]
    assert facts[0]["quote"] == "400000 股"
    store.close()


def test_store_is_idempotent_for_same_news_id(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.add_result(_announcement(), _result("400000"))
    store.add_result(_announcement(), _result("400000"))

    assert store.count_events("2026-10-30") == 1
    event = store.events_for_day("2026-10-30")[0]
    assert len(store.facts_for_event(event["event_id"])) == 1
    assert store.count_documents() == 1
    store.close()


def test_store_replaces_event_when_type_changes(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.add_result(_announcement(), _result("400000"))
    changed = _result("400000").model_copy(deep=True)
    changed.events[0].type = "配售/認購"
    store.add_result(_announcement(), changed)

    events = store.events_for_day("2026-10-30")
    assert [event["type"] for event in events] == ["配售/認購"]
    assert store.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 1
    store.close()


def test_store_replaces_facts_when_result_changes(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.add_result(_announcement(), _result("400000"))
    store.add_result(_announcement(), _result("500000", key="buyback.treasury.shares"))

    event = store.events_for_day("2026-10-30")[0]
    facts = store.facts_for_event(event["event_id"])
    assert [(fact["key"], fact["value"]) for fact in facts] == [
        ("buyback.treasury.shares", "500000")
    ]
    store.close()


def test_store_filters_by_code_and_day(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.add_result(_announcement("1", "00700", 30), _result("400000", news_id="1"))
    store.add_result(_announcement("2", "09988", 30), _result("100000", news_id="2", code="09988"))
    store.add_result(_announcement("3", "00700", 29), _result("200000", news_id="3"))

    assert store.count_events("2026-10-30") == 2
    assert store.count_events("2026-10-30", code="00700") == 1
    assert store.count_events() == 3
    store.close()


def test_latest_fact_respects_cutoff_and_missing_keys(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.add_result(_announcement("1", "00700", 29),
                     _result("100000", key="shares.end", news_id="1"))
    store.add_result(_announcement("2", "00700", 30),
                     _result("200000", key="shares.end", news_id="2"))

    before = store.latest_fact("00700", "shares.end", on_or_before="2026-10-29")
    latest = store.latest_fact("00700", "shares.end")

    assert before is not None and before["value"] == "100000"
    assert latest is not None and latest["value"] == "200000"
    assert store.latest_fact("00700", "buyback.shares") is None
    assert store.latest_fact("09988", "shares.end") is None
    store.close()
