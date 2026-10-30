from hkexradar.ndr import filing_numbers, parse_events, parse_filing


def _wrap(event_text: str, end_balance: str = "2026年10月30日 1,000,000 0 1,000,000") -> str:
    return (
        "A. 已發行股份或庫存股份變動事件"
        "於下列日期開始時的結存(註1) 2026年9月30日 1,000,000 0 1,000,000 "
        f"{event_text} "
        "於下列日期結束時的結存 (註5及6) " + end_balance
    )


def test_cancellation_event_is_parsed_and_classified():
    text = _wrap(
        "1). 購回股份 (股份購回並註銷) 於2026年10月13日購回之股份已於2026年10月30日註銷"
        "變動日期 2026年10月30日 -100,000 0.1 % HKD 10 "
        "B. 贖回/購回股份 (擬註銷但截至期終結存日期尚未註銷) 備註："
    )
    filing = parse_filing("1", text)
    assert filing.category == "註銷購回股份"
    assert filing.events[0].delta == -100_000
    assert filing.events[0].pct == 0.1
    assert filing.events[0].currency == "HKD"
    assert filing.events[0].price == 10
    assert filing_numbers(filing) == (-100_000, 100_000, 0)


def test_treasury_buyback_keeps_treasury_shares_and_foreign_currency():
    text = _wrap(
        "1). 購回股份 (股份被持作庫存股份) 員工持股計劃或股權激勵"
        "變動日期 2026年10月22日 -471,000 0.14 % 471,000 RMB 58.38 "
        "B. 贖回/購回股份 (擬註銷但截至期終結存日期尚未註銷) 備註："
    )
    event = parse_events(text)[0]
    assert event.delta == -471_000
    assert event.treasury == 471_000
    assert event.currency == "RMB"
    assert event.price == 58.38
    assert parse_filing("1", text).category == "新增購回"


def test_buyback_totals_tolerate_blank_treasury_field():
    text = _wrap(
        "1). 其他 (請註明) 見B部 變動日期 2026年10月30日 % "
        "B. 贖回/購回股份 (擬註銷但截至期終結存日期尚未註銷) 備註："
        "合共購回股份總數 400,000 合共付出的價格總額 (元) HKD 270,390 "
        "購回股份（擬註銷）數目 400,000 購回股份（擬持作庫存股份） 數目 "
        "B. 在本交易所作主要上市的發行人的其他資料"
    )
    filing = parse_filing("1", text)
    assert filing.category == "新增購回"
    assert [(b.shares, b.currency, b.amount) for b in filing.buybacks] == [(400_000, "HKD", 270_390)]
    assert filing.buyback_cancel == 400_000
    assert filing.buyback_treasury == 0


def test_second_share_class_does_not_leak_into_pending_rows():
    text = (
        _wrap(
            "1). 其他 (請註明) 轉換207股內資股為H股 變動日期 2026年10月30日 200 27.2 % 0 "
            "B. 贖回/購回股份 (擬註銷但截至期終結存日期尚未註銷) 備註："
        )
        + " 2. 股份分類普通股股份類別 其他類別 (請註明) 於香港聯交所上市否 "
        + "A. 已發行股份或庫存股份變動事件"
        + "於下列日期開始時的結存(註1) 2026年9月30日 800,000 0 800,000 "
        + "1). 其他 (請註明) 轉換207股內資股為H股 變動日期 2026年10月30日 -200 27.2 % 0 "
        + "於下列日期結束時的結存 (註5及6) 2026年10月30日 799,800 0 799,800"
    )
    filing = parse_filing("1", text)
    assert [event.delta for event in filing.events] == [200, -200]
    assert filing.pending == []
    assert filing.category == "內資股轉H股"


def test_placement_reference_to_part_b_is_a_buyback():
    text = _wrap(
        "1). 其他 (請註明) 參見Part B 變動日期 2026年10月30日 % "
        "B. 贖回/購回股份 (擬註銷但截至期終結存日期尚未註銷) "
        "1). 已購回以作註銷但尚未註銷之股份 變動日期 2026年10月30日 100,000 0.0082 % HKD 19.782 "
        "確認"
    )
    filing = parse_filing("1", text)
    assert filing.category == "新增購回"
    assert [(p.delta, p.currency, p.price) for p in filing.pending] == [(100_000, "HKD", 19.782)]


def test_rights_issue_delta_is_new_issuance():
    text = _wrap(
        "1). 供股 - 涉及新股於2026年10月30日配發及發行532,227,024股供股股份"
        "變動日期 2026年10月30日 532,227,024 150 % HKD 0.14 "
        "B. 贖回/購回股份 (擬註銷但截至期終結存日期尚未註銷) 備註："
    )
    filing = parse_filing("1", text)
    assert filing.category == "供股"
    issued, cancelled, new = filing_numbers(filing)
    assert (issued, cancelled, new) == (532_227_024, 0, 532_227_024)
