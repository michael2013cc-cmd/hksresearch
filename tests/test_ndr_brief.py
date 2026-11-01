from datetime import datetime

from hkexradar.ndr_brief import build_alerts, render_brief

THRESHOLDS = {
    "dilution_p0_pct": 10.0,
    "dilution_p1_pct": 5.0,
    "pipeline_p1_pct": 5.0,
    "buyback_p1_pct": 1.0,
    "cancellation_p1_pct": 2.0,
}


def _row(**overrides):
    row = {
        "time": "18:00",
        "code": "00700",
        "name": "測試公司",
        "category": "新增購回",
        "start_shares": 1_000_000,
        "end_shares": 1_000_000,
        "issued_new": 0,
        "cancelled": 0,
        "pending_shares": 0,
        "buyback_shares": 0,
        "buyback_amounts": {},
        "issue_note": "",
        "note": "",
    }
    row.update(overrides)
    return row


def test_dilution_of_ten_percent_or_more_is_p0():
    alerts = build_alerts([_row(issued_new=120_000, category="配售/認購")], THRESHOLDS)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "P0"
    assert alerts[0]["rule"] == "dilution"
    assert "12.0%" in alerts[0]["message"]


def test_dilution_between_five_and_ten_percent_is_p1():
    alerts = build_alerts([_row(issued_new=60_000, category="供股")], THRESHOLDS)
    assert [(alert["level"], alert["rule"]) for alert in alerts] == [("P1", "dilution")]


def test_pipeline_and_buyback_are_p1():
    alerts = build_alerts(
        [
            _row(code="00001", pending_shares=60_000),
            _row(code="00002", buyback_shares=15_000),
        ],
        THRESHOLDS,
    )
    assert {(alert["code"], alert["rule"]) for alert in alerts} == {
        ("00001", "pipeline"),
        ("00002", "buyback"),
    }
    assert all(alert["level"] == "P1" for alert in alerts)


def test_plain_buyback_below_threshold_has_no_alert():
    assert build_alerts([_row(buyback_shares=5_000)], THRESHOLDS) == []


def test_domestic_to_h_conversion_is_not_dilution():
    alerts = build_alerts(
        [_row(issued_new=207_102_914, start_shares=762_000_000, category="內資股轉H股")],
        THRESHOLDS,
    )
    assert alerts == []


def test_alerts_are_sorted_p0_before_p1():
    alerts = build_alerts(
        [
            _row(code="00001", buyback_shares=15_000),
            _row(code="00002", issued_new=200_000),
        ],
        THRESHOLDS,
    )
    assert [alert["level"] for alert in alerts] == ["P0", "P1"]


def test_render_brief_contains_alerts_and_quality():
    rows = [_row(issued_new=120_000, category="配售/認購", issue_note="配售 120,000 股")]
    alerts = build_alerts(rows, THRESHOLDS)
    text = render_brief(rows, alerts, {"total": 1, "text_failures": []}, datetime(2026, 10, 30, 21, 0))
    assert "2026-10-30" in text
    assert "P0" in text
    assert "00700" in text
    assert "配售 120,000 股" in text
