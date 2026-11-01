from datetime import datetime

from hkexradar.capital_brief import build_alerts, render_brief


def _row(**overrides) -> dict:
    row = {
        "time": "16:30",
        "code": "02597",
        "name": "訊眾通信",
        "type": "配售/認購完成",
        "shares": 3_550_000,
        "price": 29.0,
        "gross": 102_950_000,
        "net": 102_320_000,
        "ratio_existing": None,
        "ratio_post": 2.6,
        "acceptance": None,
        "undersubscribed": None,
        "summary": "配售/認購完成，發行 3,550,000 股",
        "page": 2,
        "quote": "合共3,550,000股配售股份",
        "text_status": "ok",
        "warning": "",
    }
    row.update(overrides)
    return row


def test_dilution_uses_pre_deal_ratio_for_alert():
    row = _row(code="03708", ratio_existing=10.76, ratio_post=9.72)
    alerts = build_alerts([row], {"dilution_p0_pct": 10, "dilution_p1_pct": 5,
                                  "rights_low_acceptance_pct": 90})
    assert [alert["level"] for alert in alerts] == ["P0"]
    assert alerts[0]["rule"] == "dilution"


def test_small_placement_stays_below_threshold():
    alerts = build_alerts([_row()], {"dilution_p0_pct": 10, "dilution_p1_pct": 5,
                                     "rights_low_acceptance_pct": 90})
    assert alerts == []


def test_low_rights_acceptance_is_p1():
    row = _row(type="供股結果", acceptance=85.0)
    alerts = build_alerts([row], {"dilution_p0_pct": 10, "dilution_p1_pct": 5,
                                  "rights_low_acceptance_pct": 90})
    assert [alert["level"] for alert in alerts] == ["P1"]
    assert alerts[0]["rule"] == "rights_acceptance"


def test_max_placement_message_says_maximum():
    row = _row(type="配售/認購（上限）", ratio_existing=20.0, ratio_post=16.67)
    alerts = build_alerts([row], {"dilution_p0_pct": 10, "dilution_p1_pct": 5,
                                  "rights_low_acceptance_pct": 90})
    assert alerts[0]["level"] == "P0"
    assert "最多發行" in alerts[0]["message"]


def test_termination_does_not_alert():
    alerts = build_alerts([_row(type="終止配售", shares=None, price=None, gross=None,
                                net=None, ratio_post=None)], {})
    assert alerts == []


def test_render_puts_p0_first_and_keeps_evidence():
    rows = [
        _row(code="03708", time="16:36", ratio_existing=10.76, ratio_post=9.72,
             name="世界數字經濟產業"),
        _row(code="01536", time="16:35", type="供股結果", acceptance=85.0,
             name="煜榮集團", shares=1_368_000_000, price=0.1, page=2,
             quote="將予配發及發行1,368,000,000 股供股股份"),
        _row(code="00643", time="20:22", type="終止配售", name="恆富控股",
             shares=None, price=None, gross=None, net=None, ratio_existing=None,
             ratio_post=None, page=None, quote="", summary="終止配售協議，未發行股份"),
    ]
    alerts = build_alerts(rows, {"dilution_p0_pct": 10, "dilution_p1_pct": 5,
                                 "rights_low_acceptance_pct": 90})
    text = render_brief(rows, alerts, {"date": "2026-10-30", "total": 2},
                        datetime(2026, 10, 30, 23, 0))
    assert text.index("03708") < text.index("01536")
    assert "P0" in text and "第 2 頁" in text
    assert "供股認購率" in text
    assert "終止配售協議，未發行股份" in text
