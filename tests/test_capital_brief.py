from datetime import datetime

import pytest

from hkexradar.capital_brief import (
    attach_market,
    build_alerts,
    pre_deal_shares,
    render_brief,
    shares_for_market,
)
from hkexradar.marketdata import Quote


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


def test_pre_deal_shares_from_existing_or_post_ratio():
    assert pre_deal_shares(580_000_000, 20.0, 16.67) == pytest.approx(2_900_000_000)
    assert pre_deal_shares(3_550_000, None, 2.6) == pytest.approx(132_988_461.54)
    assert pre_deal_shares(3_550_000, None, None) is None
    assert pre_deal_shares(None, 20.0, None) is None


def test_shares_for_market_prefers_announced_then_larger_ndr():
    assert shares_for_market(announced=823_331_036, shares=164_666_206,
                             ratio_existing=None, ratio_post=16.7,
                             ndr_shares=800_000_000) == (823_331_036, "公告")

    assert shares_for_market(announced=None, shares=78_250_000,
                             ratio_existing=10.76, ratio_post=9.72,
                             ndr_shares=805_530_000) == (805_530_000, "NDR")

    assert shares_for_market(announced=None, shares=3_550_000,
                             ratio_existing=None, ratio_post=2.6,
                             ndr_shares=45_180_000)[1] == "推算"

    assert shares_for_market(announced=None, shares=1_368_000_000,
                             ratio_existing=None, ratio_post=None,
                             ndr_shares=1_824_000_000) == (1_824_000_000, "NDR")

    assert shares_for_market(announced=None, shares=None, ratio_existing=None,
                             ratio_post=None, ndr_shares=None) == (None, "")


def test_attach_market_computes_cap_and_scaled_amounts():
    row = _row(code="03708", net=14_232_000, derived_shares=727_230_483)
    quotes = {
        "03708": Quote(code="03708", name="世界數字經濟產業", currency="HKD",
                       prev_close=0.18, close=0.182, high=0.19, low=0.17,
                       shares_traded=5_000_000, turnover=900_000.0),
    }

    attach_market([row], quotes)

    assert row["close"] == 0.182
    assert row["market_cap"] == pytest.approx(132_355_948.0)
    assert row["net_to_cap"] == pytest.approx(10.75, abs=0.01)
    assert row["amount_to_turnover"] == pytest.approx(15.81, abs=0.01)


def test_attach_market_prefers_reported_outstanding_shares():
    row = _row(code="08659", net=11_960_000, shares_outstanding=823_331_036,
               derived_shares=821_358_980)
    quotes = {
        "08659": Quote(code="08659", name="易和國際控股", currency="HKD",
                       prev_close=0.087, close=0.09, high=0.091, low=0.087,
                       shares_traded=825_000, turnover=72_740.0),
    }

    attach_market([row], quotes)

    assert row["market_cap"] == pytest.approx(74_099_793.24)


def test_attach_market_leaves_missing_quotes_unscaled():
    row = _row(code="09999", net=1_000_000, derived_shares=10_000_000)

    attach_market([row], {})

    assert row["market_cap"] is None
    assert row["net_to_cap"] is None
    assert row["amount_to_turnover"] is None


def test_render_includes_market_columns_and_labels_proxy():
    row = _row(code="03708", ratio_existing=10.76, ratio_post=9.72,
               derived_shares=727_230_483, market_cap=132_355_948.0,
               net_to_cap=10.75, amount_to_turnover=15.81)
    alerts = build_alerts([row], {"dilution_p0_pct": 10})

    text = render_brief([row], alerts, {"date": "2026-10-30", "market_quotes": 17_102,
                                        "market_matched": 1},
                        datetime(2026, 10, 30, 23, 0))

    assert "市值(推算)" in text
    assert "募資/市值" in text
    assert "10.75%" in text
    assert "15.8x" in text
    assert "×收市價" in text
