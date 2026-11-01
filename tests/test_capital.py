from datetime import datetime

from hkexradar.analyzers.capital import CapitalActionsAnalyzer
from hkexradar.models import Announcement

PLACEMENT_2597 = (
    "董事會欣然宣佈，配售協議項下的所有條件均已達成，且交割已於2026年10 月30日進行。 "
    "合共3,550,000股配售股份（佔緊隨交割後經配發及發行配售股份擴大後的已發行股份總數"
    "（不包括庫存股份）的約2.60%）已根據配售協議所載條款及條件按配售價每股配售股份29.00港元"
    "成功配售予不少於六名承配人。 配售事項的所得款項總額及所得款項淨額（扣除佣金及估計開支後）"
    "分別約為 102.95百萬港元及102.32百萬港元。"
)

SUBSCRIPTION_3708 = (
    "本公司欣然宣佈，認購協議中列明的全部先決條件已獲達成，完成已於二零二六年十月三十日作實。 "
    "合共78,250,000股認購股份佔(i)於本公告日期，本公司現有已發行股本約10.76%；及(ii)本公司經"
    "配發及發行認購股份擴大後之已發行股本約9.72%，已成功按每股股份0.182港元的認購價發行予認購方。 "
    "認購事項的所得款項淨額約為14,232,000港元。"
)

RIGHTS_1536 = (
    "截至二零二六年十月十二日（星期一）下午四時正（即最後接納時限），已接獲合共七(7) 份有效接納，"
    "涉及根據暫定配額通知書暫定配發之合共1,295,957,159 股供股股份，佔供股項下提呈發售之供股股份總數約94.73 % 。 "
    "餘下72,042,841 股未獲認購供股股份，佔供股項下提呈發售之供股股份總數約 5.27%，將受補償安排規限。 "
    "72,042,841 股未獲認購供股股份已根據配售事項按每股配售股份0.10 港元（相等於認購價）之價格成功配售。 "
    "根據供股項下有效接納之結果及配售事項之結果，將予配發及發行1,368,000,000 股供股股份，"
    "佔供股項下可供認購之供股股份總數100%。 供股所得款項總額約為136.8百萬港元。"
    "經扣除供股所產生之相關開支後，所得款項淨額約為134.9百萬港元。"
)

TERMINATION_643 = (
    "董事會宣佈，鑒於市況，本公司與配售代理於二零二六年十月三十日（交易時段後）共同協定終止配售協議，"
    "自二零二六年十月三十日起生效。 由於概無根據配售協議配發及發行任何配售股份，"
    "終止對本公司已發行股本或股權架構並無影響。"
)

PLACEMENT_MAX_858 = (
    "本公司已有條件同意透過配售代理按竭力基準配售最多580,000,000 股配售股份予不少於六名承配人，"
    "價格為每股配售股份 0.052港元。 配售股份的最高數目佔：(i) 本公司於本公告日期的現有已發行股本20 % ；"
    "及(ii) 本公司經發行配售股份擴大的已發行股本約16.67%。 假設根據配售協議配售最高數目之配售股份，"
    "配售事項所得款項總額將約為30,200,000港元，而所得款項淨額（經扣除配售佣金及配售事項之其他開支後）"
    "將約為29,400,000 港元。"
)

SUBSCRIPTION_090 = (
    "本公司有條件同意配發及發行，而認購人有條件同意以每股認購股份0.834港元之認購價認購61,400,000股認購股份。 "
    "根據認購事項將予配發及發行之61,400,000股認購股份總數相當於(i)於本公告日期已發行股份總數約13.39%；"
    "及(ii)緊隨完成後經配發及發行認購股份擴大之已發行股份總數約11.81%。 "
    "認購事項所得款項總額約為51.21百萬港元，扣除相關開支後，認購事項所得款項淨額約為50.50百萬港元。"
)

SUBSCRIPTION_403 = (
    "本公司與認購人訂立認購協議，據此，本公司已有條件同意配發及發行，而認購人已有條件同意按認購價"
    "每股認購股份3.60港元認購合共17,000,000股認購股份。 認購股份相當於(i)於本公告日期本公司現有已發行股本約10.05%；"
    "及(ii)經發行認購股份擴大的本公司已發行股本約9.13%。 認購事項之所得款項總額及淨額將分別為61.2百萬港元"
    "及約61.00百萬港元。"
)


def _ann(title: str, tags: list[str], group: str = "公告及通告") -> Announcement:
    return Announcement(
        news_id="1",
        primary_code="02597",
        stock_name="測試公司",
        published_at=datetime(2026, 10, 30, 18, 0),
        title=title,
        doc_group=group,
        headline_tags=tags,
        category_label=group,
        file_url="https://example.test/1.pdf",
    )


def _facts(result) -> dict[str, str]:
    return {fact.key: fact.value for fact in result.events[0].facts}


def test_matches_placement_but_not_circular_or_product_purchase():
    analyzer = CapitalActionsAnalyzer()
    assert analyzer.matches(_ann("根據一般授權配售新H股之交割", ["配售"]))
    assert not analyzer.matches(_ann("建議授予一般授權", ["一般性授權"], group="通函"))
    assert not analyzer.matches(_ann("須予披露交易 認購理財產品", ["須予披露的交易"]))
    assert not analyzer.matches(_ann("翌日披露報表", ["股份購回"], group="翌日披露報表"))


def test_placement_completion_extracts_core_numbers():
    analyzer = CapitalActionsAnalyzer()
    result = analyzer.analyze(
        _ann("根據一般授權配售新H股之交割", ["配售"]), PLACEMENT_2597
    )
    event = result.events[0]
    facts = _facts(result)
    assert event.type == "配售/認購完成"
    assert event.direction == "negative"
    assert float(facts["issue.shares"]) == 3_550_000
    assert float(facts["issue.price"]) == 29.0
    assert float(facts["proceeds.gross"]) == 102_950_000
    assert float(facts["proceeds.net"]) == 102_320_000
    assert float(facts["ratio.post"]) == 2.6
    assert all(fact.evidence.quote for fact in event.facts)


def test_subscription_completion_extracts_existing_and_post_ratios():
    result = CapitalActionsAnalyzer().analyze(
        _ann("完成根據一般授權認購新股份", ["根據一般性授權發行股份"]), SUBSCRIPTION_3708
    )
    facts = _facts(result)
    assert float(facts["issue.shares"]) == 78_250_000
    assert float(facts["issue.price"]) == 0.182
    assert float(facts["proceeds.net"]) == 14_232_000
    assert float(facts["ratio.existing"]) == 10.76
    assert float(facts["ratio.post"]) == 9.72


def test_rights_result_extracts_acceptance_and_shortfall():
    result = CapitalActionsAnalyzer().analyze(
        _ann("供股之結果", ["供股", "配發結果"]), RIGHTS_1536
    )
    event = result.events[0]
    facts = _facts(result)
    assert event.type == "供股結果"
    assert float(facts["issue.shares"]) == 1_368_000_000
    assert float(facts["issue.price"]) == 0.1
    assert float(facts["rights.acceptance_pct"]) == 94.73
    assert float(facts["rights.undersubscribed.shares"]) == 72_042_841
    assert float(facts["proceeds.gross"]) == 136_800_000
    assert float(facts["proceeds.net"]) == 134_900_000


def test_termination_creates_event_without_numeric_facts():
    result = CapitalActionsAnalyzer().analyze(
        _ann("終止根據一般授權配售新股份", ["配售"]), TERMINATION_643
    )
    event = result.events[0]
    assert event.type == "終止配售"
    assert event.direction == "neutral"
    assert event.facts == []
    assert "終止" in event.summary


def test_placement_of_maximum_shares_uses_cap_and_ratios():
    result = CapitalActionsAnalyzer().analyze(
        _ann("根據一般授權配售新股份", ["配售"]), PLACEMENT_MAX_858
    )
    facts = _facts(result)
    assert result.events[0].type == "配售/認購（上限）"
    assert float(facts["issue.shares"]) == 580_000_000
    assert float(facts["ratio.existing"]) == 20.0
    assert float(facts["ratio.post"]) == 16.67
    assert float(facts["proceeds.net"]) == 29_400_000


def test_subscription_of_exact_shares_and_total_issued_ratio():
    result = CapitalActionsAnalyzer().analyze(
        _ann("有關根據特別授權認購新股份的關連交易", ["根據特定授權發行股份"]), SUBSCRIPTION_090
    )
    facts = _facts(result)
    assert float(facts["issue.shares"]) == 61_400_000
    assert float(facts["ratio.existing"]) == 13.39
    assert float(facts["ratio.post"]) == 11.81
    assert float(facts["proceeds.net"]) == 50_500_000
    existing = next(f for f in result.events[0].facts if f.key == "ratio.existing")
    assert "13.39" in existing.evidence.quote


def test_combined_proceeds_with_future_tense():
    result = CapitalActionsAnalyzer().analyze(
        _ann("根據一般授權認購新股份", ["根據一般性授權發行股份"]), SUBSCRIPTION_403
    )
    facts = _facts(result)
    assert float(facts["proceeds.gross"]) == 61_200_000
    assert float(facts["proceeds.net"]) == 61_000_000


def test_delay_notice_is_progress_without_warning():
    result = CapitalActionsAnalyzer().analyze(
        _ann("進一步延遲寄發通函", ["供股", "延遲發送通函或其他文件"]), "公司仍在編製通函。"
    )
    event = result.events[0]
    assert event.type == "進展/延遲"
    assert event.facts == []
    assert result.warnings == []


def test_unparsed_placement_keeps_warning_for_manual_review():
    result = CapitalActionsAnalyzer().analyze(
        _ann("根據一般授權配售新股份", ["配售"]), "公司宣布配售事項，詳情請參閱公告。"
    )
    assert result.events[0].type == "配售/認購"
    assert result.warnings


def test_fact_evidence_carries_page_number():
    pages = [(1, "封面"), (2, PLACEMENT_2597)]
    result = CapitalActionsAnalyzer().analyze(
        _ann("配售新H股之交割", ["配售"]), PLACEMENT_2597, pages=pages
    )
    assert {fact.evidence.page for fact in result.events[0].facts} == {2}
