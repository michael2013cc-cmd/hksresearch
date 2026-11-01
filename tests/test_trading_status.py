from datetime import datetime

from hkexradar.analyzers.trading_status import TradingStatusAnalyzer
from hkexradar.htmltext import html_to_text
from hkexradar.models import Announcement

SHORT_SUSPENSION = (
    "短暫停牌 按應力控股有限公司（「本公司」）要求，本公司股份將於二零二六年十月三十日"
    "上午九時正起在香港聯合交易所有限公司短暫停牌，以待根據公司收購及合併守則發佈公告，"
    "該公告將構成本公司內幕消息。"
)
RESUMPTION = (
    "聯合公告 (5)恢復買賣 本公司已向聯交所申請股份恢復買賣，股份將於二零二六年十月三十日"
    "上午九時正起恢復買賣。"
)
CONTINUING = (
    "復牌進展的季度更新及繼續暫停買賣 本公司接獲聯交所的函件，當中載列復牌指引。"
    "股份已自二零二六年二月三日上午九時正起暫停買賣。股份買賣將繼續暫停，直至另行通知為止。"
)
WINDING_UP = (
    "由法院作出清盤；委任臨時清盤人；及暫停買賣 該公司於2026年10月30日在公司(清盤案)"
    "2026年第170號被高等法院根據公司清盤條例頒令清盤。該公司之股份自2026年10月30日"
    "下午3時40分起於聯交所暫停買賣，並將繼續暫停買賣，直至另行通知為止。"
)


def _ann(title: str, tags: list[str], *, code: str = "02663", name: str = "應力控股",
         news_id: str = "1") -> Announcement:
    return Announcement(
        news_id=news_id,
        primary_code=code,
        stock_name=name,
        published_at=datetime(2026, 10, 30, 8, 45),
        title=title,
        doc_group="公告及通告",
        headline_tags=tags,
        category_label="公告及通告",
        file_url=f"https://example.test/{news_id}.pdf",
    )


def _facts(result) -> dict[str, str]:
    return {fact.key: fact.value for fact in result.events[0].facts}


def test_html_to_text_strips_scripts_and_tags():
    text = html_to_text(
        "<html><script>bad()</script><body><b>交易所通告 - 短暫停牌</b> "
        "股份將於上午九時正起短暫停止買賣。</body></html>"
    )
    assert "bad()" not in text
    assert "交易所通告 - 短暫停牌" in text
    assert "上午九時正起短暫停止買賣" in text


def test_matches_trading_status_tags_only():
    analyzer = TradingStatusAnalyzer()
    assert analyzer.matches(_ann("短暫停牌", ["短暫停牌"]))
    assert not analyzer.matches(_ann("股份購回", ["股份購回"]))


def test_exchange_notice_is_short_suspension():
    analyzer = TradingStatusAnalyzer()
    text = "應力控股有限公司的股份（證券代號：02663）將於今天（30/10/2026）上午九時正起短暫停止買賣。"
    result = analyzer.analyze(
        _ann("交易所通告 - 短暫停牌", ["短暫停牌"], news_id="2"),
        text,
        pages=[(1, text)],
    )
    event = result.events[0]
    facts = _facts(result)
    assert event.type == "短暫停牌"
    assert facts["status.source"] == "交易所通告"
    assert "上午九時正" in facts["status.timing"]
    assert event.facts[0].evidence.page == 1


def test_company_short_suspension_extracts_reason_and_timing():
    result = TradingStatusAnalyzer().analyze(
        _ann("短暫停牌", ["短暫停牌"]), SHORT_SUSPENSION, pages=[(1, SHORT_SUSPENSION)]
    )
    event = result.events[0]
    facts = _facts(result)
    assert event.type == "短暫停牌"
    assert event.direction == "negative"
    assert facts["status.source"] == "公司公告"
    assert facts["status.reason"] == "收購守則相關"
    assert "上午九時正" in facts["status.timing"]


def test_actual_resumption_is_resumption():
    result = TradingStatusAnalyzer().analyze(
        _ann("聯合公告 (5)恢復買賣", ["復牌"], code="03774", name="亮晴控股"),
        RESUMPTION,
    )
    event = result.events[0]
    assert event.type == "復牌"
    assert event.direction == "positive"


def test_resumption_progress_is_continuing_suspension():
    result = TradingStatusAnalyzer().analyze(
        _ann("復牌進展的季度更新及繼續暫停買賣", ["停牌"], code="00036", name="遠東控股國際"),
        CONTINUING,
    )
    event = result.events[0]
    facts = _facts(result)
    assert event.type == "繼續停牌"
    assert event.type != "復牌"
    assert facts["status.reason"] == "復牌指引"


def test_winding_up_suspension_extracts_reason():
    result = TradingStatusAnalyzer().analyze(
        _ann("由法院作出清盤；委任臨時清盤人；及暫停買賣", ["停牌"], code="02608", name="陽光１００中國"),
        WINDING_UP,
    )
    event = result.events[0]
    facts = _facts(result)
    assert event.type == "停牌"
    assert facts["status.reason"] == "清盤/臨時清盤人"
    assert "下午3時40分" in facts["status.timing"]


def test_textless_exchange_notice_uses_title_and_warns():
    result = TradingStatusAnalyzer().analyze(
        _ann("交易所通告 - 停牌", ["停牌"], code="02608", name="陽光１００中國"), ""
    )
    event = result.events[0]
    assert event.type == "停牌"
    assert event.confidence == 0.6
    assert result.warnings
    assert event.facts[0].evidence.quote == "交易所通告 - 停牌"


RESUMPTION_WITH_HISTORY = (
    "恢復股份買賣 應本公司之要求，股份已自二零二六年十月二十三日下午一時正起"
    "於聯交所短暫停止買賣，以待刊發本聯合公告。本公司已向聯交所申請自二零二六年"
    "十一月二日上午九時正起恢復股份於聯交所買賣。"
)


def test_resumption_timing_prefers_resumption_date():
    result = TradingStatusAnalyzer().analyze(
        _ann("聯合公告 (5)恢復買賣", ["復牌"], code="03774", name="亮晴控股"),
        RESUMPTION_WITH_HISTORY,
    )
    facts = _facts(result)
    assert facts["status.timing"] == "二零二六年十一月二日上午九時正起"


def test_resumption_has_no_reason_from_unrelated_liquidation():
    text = "聯合公告 (3)恢復買賣 董事會已獲清盤人（作為賣方代理人行事）通知，訂立購股協議。"
    result = TradingStatusAnalyzer().analyze(
        _ann("聯合公告 (5)恢復買賣", ["復牌"], code="06666", name="恒大物業"), text
    )
    assert "status.reason" not in _facts(result)


def test_suspension_timing_has_no_title_prefix():
    result = TradingStatusAnalyzer().analyze(
        _ann("短暫停牌", ["短暫停牌"]), SHORT_SUSPENSION, pages=[(1, SHORT_SUSPENSION)]
    )
    assert _facts(result)["status.timing"] == "二零二六年十月三十日上午九時正起"


def test_spaced_date_still_extracts_timing():
    text = (
        "繼續暫停買賣 按本公司之要求，本公司股份於聯交所的買賣已自 2026 年 3 月 17 日"
        "（星期二）上午九時正起暫停買賣，及將維持停牌直至另行通知。"
    )
    result = TradingStatusAnalyzer().analyze(
        _ann("復牌進度更新及繼續暫停買賣", ["停牌"], code="06883", name="穎通控股"), text
    )
    assert _facts(result)["status.timing"] == "2026 年 3 月 17 日（星期二）上午九時正起"
