from datetime import date

import pytest

from hkexradar.marketdata import (
    Quote,
    average_turnover,
    fetch_day,
    load_cache,
    market_cap,
    parse_quotations,
    quotation_urls,
    save_cache,
)

HTML = """<html><body>
<pre><font size='1'>CODE  NAME OF STOCK    CUR PRV.CLO./    ASK/    HIGH/      SHARES TRADED/
                            CLOSING      BID     LOW        TURNOVER ($)

     1 CKH HOLDINGS     HKD   65.45    66.20    66.20            8,117,147
                              66.20    66.15    64.65          534,037,708
*  700 TENCENT          HKD  377.60   383.80   387.60           22,269,954

                             387.60   387.40   376.00       8,540,915,574
    33 INTL GENIUS      HKD TRADING SUSPENDED
#   90 PUXING ENERGY    HKD    0.825    0.86      -                      -
                               0.825    0.80      -                      -
   858 EXTRAWELL PHAR   HKD    0.050    0.052    0.052            8,690,000
</font></pre>
<pre><font size='1'>                               0.051    0.051    0.049              404,710
   900 AEON CREDIT      HKD    5.00     5.01     5.05              100,000
                               5.02     5.02     4.98              500,000
                            SALES RECORDS FOR ALL STOCKS
   999 BOGUS            HKD    1.00     1.00     1.00                  100
                               1.00     1.00     1.00                  100
</font></pre></body></html>"""


def test_parse_quotations_normalizes_codes_and_reads_two_line_rows():
    quotes = parse_quotations(HTML)

    assert set(quotes) == {"00001", "00700", "00033", "00090", "00858", "00900"}
    ckh = quotes["00001"]
    assert ckh.name == "CKH HOLDINGS"
    assert ckh.currency == "HKD"
    assert ckh.prev_close == 65.45
    assert ckh.close == 66.20
    assert ckh.high == 66.20
    assert ckh.low == 64.65
    assert ckh.shares_traded == 8_117_147
    assert ckh.turnover == 534_037_708.0
    assert ckh.suspended is False


def test_parse_quotations_handles_markers_blank_lines_and_pre_blocks():
    quotes = parse_quotations(HTML)

    tencent = quotes["00700"]
    assert tencent.close == 387.60
    assert tencent.turnover == 8_540_915_574.0
    extra = quotes["00858"]
    assert extra.prev_close == 0.05
    assert extra.close == 0.051
    assert extra.turnover == 404_710.0


def test_parse_quotations_handles_suspended_and_dash_fields():
    quotes = parse_quotations(HTML)

    assert quotes["00033"].suspended is True
    assert quotes["00033"].close is None
    assert quotes["00033"].turnover is None
    puxing = quotes["00090"]
    assert puxing.suspended is False
    assert puxing.close == 0.825
    assert puxing.shares_traded is None
    assert puxing.turnover is None


def test_parse_quotations_stops_at_sales_records():
    quotes = parse_quotations(HTML)

    assert "00999" not in quotes


def test_quotation_urls_cover_main_board_and_gem():
    main, gem = quotation_urls(date(2026, 10, 30))

    assert main == "https://www.hkex.com.hk/eng/stat/smstat/dayquot/d261030e.htm"
    assert gem == "https://www.hkex.com.hk/eng/stat/smstat/dayquot/GEM/e_G261030.htm"


def test_market_cap_uses_close_and_falls_back_to_prev_close():
    quote = Quote(code="00001", name="CKH HOLDINGS", currency="HKD",
                  prev_close=65.45, close=66.20, high=66.20, low=64.65,
                  shares_traded=8_117_147, turnover=534_037_708.0)
    halted = Quote(code="00033", name="INTL GENIUS", currency="HKD",
                   prev_close=1.0, close=None, high=None, low=None,
                   shares_traded=None, turnover=None, suspended=True)

    assert market_cap(quote, 2_000_000_000) == pytest.approx(132_400_000_000)
    assert market_cap(halted, 100_000_000) == pytest.approx(100_000_000)
    assert market_cap(quote, None) is None
    assert market_cap(quote, 0) is None


def test_average_turnover_skips_missing_days():
    def day(turnover):
        return {"00001": Quote(code="00001", name="CKH", currency="HKD",
                               prev_close=1.0, close=1.0, high=1.0, low=1.0,
                               shares_traded=None, turnover=turnover)}

    history = [day(100.0), day(None), day(300.0), day(500.0)]

    assert average_turnover(history, "00001", days=2) == pytest.approx(400.0)
    assert average_turnover(history, "00001", days=3) == pytest.approx(300.0)
    assert average_turnover(history, "00700") is None


def test_cache_round_trip(tmp_path):
    quotes = parse_quotations(HTML)
    path = save_cache(tmp_path, date(2026, 10, 30), quotes)

    assert path.exists()
    loaded = load_cache(tmp_path, date(2026, 10, 30))
    assert loaded is not None
    assert loaded["00858"] == quotes["00858"]
    assert load_cache(tmp_path, date(2026, 10, 31)) is None


GEM_HTML = """<html><body>
<pre><font size='1'> CODE  NAME OF STOCK    CUR PRV.CLO./    ASK/    HIGH/      SHARES TRADED/
                            CLOSING      BID     LOW        TURNOVER ($)

  8403 DEFENG SOLIFE    HKD    3.71     4.10     4.00              243,600
                               4.00     4.00     3.60              911,868
</font></pre></body></html>"""


class _Response:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _Client:
    def __init__(self):
        self.urls: list[str] = []

    def get(self, url: str) -> _Response:
        self.urls.append(url)
        return _Response(GEM_HTML if "/GEM/" in url else HTML)


def test_fetch_day_merges_boards_and_uses_cache(tmp_path):
    client = _Client()

    quotes = fetch_day(date(2026, 10, 30), tmp_path, client=client)
    assert client.urls == list(quotation_urls(date(2026, 10, 30)))
    assert {"00001", "08403"} <= set(quotes)
    assert quotes["08403"].close == 4.0
    assert load_cache(tmp_path, date(2026, 10, 30)) is not None

    again = fetch_day(date(2026, 10, 30), tmp_path, client=client)
    assert len(client.urls) == 2
    assert again["08403"] == quotes["08403"]
