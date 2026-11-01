from datetime import datetime

from hkexradar.trading_status_brief import build_alerts, dedupe_rows, render_brief


def _row(**overrides):
    row = {
        "time": "08:45",
        "code": "02663",
        "name": "應力控股",
        "status": "短暫停牌",
        "effective_date": "2026-10-30",
        "timing": "上午九時正起",
        "reason": "收購守則相關",
        "note": "本公司股份將於上午九時正起短暫停牌，以待根據公司收購及合併守則發佈公告。",
        "source": "公司公告",
        "page": 1,
        "quote": "本公司股份將於上午九時正起短暫停牌。",
        "text_status": "ok",
    }
    row.update(overrides)
    return row


def test_dedupe_prefers_company_over_exchange_for_same_status():
    exchange = _row(source="交易所通告", note="交易所通告，" * 20, page=None)
    company = _row(source="公司公告")
    kept, dropped = dedupe_rows([exchange, company])
    assert len(kept) == 1
    assert kept[0]["source"] == "公司公告"
    assert dropped == [exchange]


def test_dedupe_merges_continuing_into_suspension():
    exchange = _row(status="停牌", source="交易所通告", timing="下午三時四十分起")
    company = _row(
        status="繼續停牌",
        source="公司公告",
        reason="清盤/臨時清盤人",
        note="該公司之股份自2026年10月30日下午3時40分起暫停買賣，並將繼續暫停買賣。",
    )
    kept, dropped = dedupe_rows([exchange, company])
    assert [row["status"] for row in kept] == ["繼續停牌"]
    assert len(dropped) == 1


def test_dedupe_fills_missing_timing_from_exchange_notice():
    exchange = _row(
        code="06666", name="恒大物業",
        source="交易所通告",
        status="復牌",
        timing="（30/10/2026）上午九時正起",
        reason="",
        page=None,
        note="交易所通告 - 復牌",
        quote="恒大物業集團有限公司的股份將於今天（30/10/2026）上午九時正起恢復買賣。",
    )
    company = _row(
        code="06666", name="恒大物業", status="復牌", source="公司公告",
        timing="", reason="", note="聯合公告 (5)恢復買賣",
    )
    kept, _ = dedupe_rows([exchange, company])
    assert kept[0]["source"] == "公司公告"
    assert kept[0]["timing"] == "（30/10/2026）上午九時正起"
    assert company["timing"] == ""


def test_dedupe_keeps_suspension_and_resumption_as_separate_events():
    suspended = _row()
    resumed = _row(status="復牌", time="15:00", source="公司公告")
    kept, dropped = dedupe_rows([suspended, resumed])
    assert {row["status"] for row in kept} == {"短暫停牌", "復牌"}
    assert dropped == []


def test_build_alerts_marks_every_event_p0():
    alerts = build_alerts([_row(), _row(code="02608", name="陽光１００中國", status="停牌")])
    assert [alert["level"] for alert in alerts] == ["P0", "P0"]
    assert all(alert["rule"] == "trading_status" for alert in alerts)


def test_render_brief_contains_p0_status_and_quality():
    rows = [_row()]
    alerts = build_alerts(rows)
    text = render_brief(
        rows,
        alerts,
        {
            "date": "2026-10-30",
            "total": 15,
            "unique": 1,
            "duplicates": 14,
            "text_failures": [],
            "title_only": 0,
            "source_counts": {"公司公告": 1},
            "status_counts": {"短暫停牌": 1},
        },
        datetime(2026, 10, 30, 23, 0),
    )
    assert "停復牌事件簡報" in text
    assert "P0" in text
    assert "02663" in text
    assert "短暫停牌" in text
    assert "上午九時正起" in text
    assert "交易所通告" in text
    assert "去重" in text
