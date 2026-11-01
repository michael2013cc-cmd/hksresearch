from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import partial

from .base import AnalyzerEvent, AnalyzerFact, AnalyzerResult, Evidence

_DATE = r"\d{4}年\d{1,2}月\d{1,2}日"
_EVENT_HEAD = re.compile(r"(\d+)\)\.\s*")
_TAIL = re.compile(r"^(?P<delta>-?[\d,]+)?\s*(?P<pct>[\d.]+)?\s*%\s*(?P<rest>.*)$")
_CURRENCY = re.compile(r"(HKD|RMB|GBP|USD|CNY)")
_BUYBACK_CANCEL = re.compile(r"購回股份[（(]擬註銷[）)]\s*數目\s*([\d,]+)")
_BUYBACK_TREASURY = re.compile(r"購回股份[（(]擬持作庫存股份[）)]\s*數目\s*([\d,]*)")
_BUYBACK_TOTAL = re.compile(
    r"合共購回股份總數\s*([\d,]+).*?合共付出的價格總額 \(元\)\s*(?:(HKD|RMB|GBP|USD|CNY))?\s*([\d,.]+)",
    re.S,
)


@dataclass
class Event:
    desc: str
    delta: int | None = None
    pct: float | None = None
    treasury: int | None = None
    currency: str | None = None
    price: float | None = None


@dataclass
class Buyback:
    shares: int
    amount: float | None = None
    currency: str | None = None


@dataclass
class Filing:
    news_id: str
    category: str = "其他"
    subtypes: list[str] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    buybacks: list[Buyback] = field(default_factory=list)
    pending: list[Event] = field(default_factory=list)
    buyback_cancel: int = 0
    buyback_treasury: int = 0
    start_shares: int | None = None
    end_shares: int | None = None
    treasury_sold: int | None = None


def _num(text: str | None) -> int | None:
    if not text:
        return None
    cleaned = text.replace(",", "").strip()
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _fnum(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text.replace(",", "").strip())
    except ValueError:
        return None


def _balance(text: str, label: str) -> int | None:
    match = re.search(label + r".{0,24}?(" + _DATE + r")\s*([\d,]+)", text, re.S)
    return _num(match.group(2)) if match else None


def _parse_tail(rest: str) -> tuple[int | None, str | None, float | None]:
    rest = rest.strip()
    if not rest:
        return None, None, None
    currency_match = _CURRENCY.search(rest)
    if currency_match:
        before = re.findall(r"\d[\d,]*", rest[:currency_match.start()])
        after = re.findall(r"\d[\d,]*(?:\.\d+)?", rest[currency_match.end():])
        return (
            _num(before[-1]) if before else None,
            currency_match.group(1),
            _fnum(after[0]) if after else None,
        )
    numbers = re.findall(r"\d[\d,]*(?:\.\d+)?", rest)
    return None, None, _fnum(numbers[0]) if numbers else None


_SECTION_A = re.compile(r"A\. 已發行(?:股份|單位)或庫存(?:股份|單位)變動")


def _class_blocks(text: str) -> list[str]:
    starts = [match.start() for match in _SECTION_A.finditer(text)]
    return [
        text[start:starts[index + 1] if index + 1 < len(starts) else len(text)]
        for index, start in enumerate(starts)
    ]


def _events_in(block: str) -> list[Event]:
    end = block.find("B. 贖回/購回")
    section = block[:end] if end > 0 else block
    heads = list(_EVENT_HEAD.finditer(section))
    events: list[Event] = []
    for index, head in enumerate(heads):
        stop = heads[index + 1].start() if index + 1 < len(heads) else len(section)
        chunk = section[head.end():stop]
        if "變動日期" not in chunk:
            continue
        desc, tail = chunk.split("變動日期", 1)
        tail = re.sub(r"^\s*" + _DATE + r"\s*", "", tail.strip())
        match = _TAIL.match(tail)
        if not match:
            continue
        treasury, currency, price = _parse_tail(match.group("rest"))
        events.append(
            Event(
                desc=re.sub(r"\s+", " ", desc).strip(),
                delta=_num(match.group("delta")),
                pct=_fnum(match.group("pct")),
                treasury=treasury,
                currency=currency,
                price=price,
            )
        )
    return events


def parse_events(text: str) -> list[Event]:
    return [event for block in _class_blocks(text) for event in _events_in(block)]


def _classify_event(desc: str) -> str:
    if "股份被持作庫存" in desc:
        return "新增購回"
    if "購回股份" in desc and "註銷" in desc:
        return "註銷購回股份"
    if "以股代息" in desc:
        return "以股代息"
    if "資本重組" in desc or "股份合併" in desc:
        return "股份合併/資本重組"
    if "供股" in desc:
        return "供股"
    if "配售" in desc or "認購" in desc:
        return "配售/認購"
    if "股份計劃" in desc and ("獎勵" in desc or "期權" in desc):
        return "股份計劃發行"
    if "行使股份期權" in desc or "購股權" in desc:
        return "期權行使"
    if "轉換" in desc and "內資股" in desc:
        return "內資股轉H股"
    if "可換股票據" in desc or "可換股債券" in desc:
        return "可換股轉換"
    if "贖回" in desc:
        return "股份贖回"
    if "基金單位" in desc or "以單位" in desc:
        return "單位發行"
    if "見B部" in desc or "見 B 部" in desc or "Part B" in desc:
        return "新增購回"
    return "其他"


def parse_pending(text: str) -> list[Event]:
    rows: list[Event] = []
    for block in _class_blocks(text):
        start = block.find("B. 贖回/購回")
        if start < 0:
            continue
        section = block[start:]
        end = min(
            (pos for pos in (section.find("第二章節"), section.find("確認")) if pos > 0),
            default=len(section),
        )
        for match in re.finditer(
            r"變動日期\s*" + _DATE + r"\s*(.*?)(?=變動日期|$)", section[:end], re.S
        ):
            parsed = _TAIL.match(match.group(1).strip())
            if not parsed:
                continue
            treasury, currency, price = _parse_tail(parsed.group("rest"))
            rows.append(
                Event(
                    desc="待註銷購回",
                    delta=_num(parsed.group("delta")),
                    pct=_fnum(parsed.group("pct")),
                    treasury=treasury,
                    currency=currency,
                    price=price,
                )
            )
    return rows


def parse_filing(news_id: str, text: str) -> Filing:
    filing = Filing(news_id=news_id)
    filing.start_shares = _balance(text, "於下列日期開始時的結存")
    filing.end_shares = _balance(text, "於下列日期結束時的結存")
    filing.events = parse_events(text)
    filing.pending = parse_pending(text)

    for match in _BUYBACK_TOTAL.finditer(text):
        filing.buybacks.append(
            Buyback(
                shares=_num(match.group(1)) or 0,
                currency=match.group(2),
                amount=_fnum(match.group(3)),
            )
        )

    for match in _BUYBACK_CANCEL.finditer(text):
        filing.buyback_cancel += _num(match.group(1)) or 0
    for match in _BUYBACK_TREASURY.finditer(text):
        filing.buyback_treasury += _num(match.group(1)) or 0

    treasury = re.search(r"合共出售庫存股份總數\s*([\d,]+)", text)
    if treasury:
        filing.treasury_sold = _num(treasury.group(1))

    subtypes = {_classify_event(event.desc) for event in filing.events}
    if filing.buybacks or filing.pending:
        subtypes.add("新增購回")
    if filing.treasury_sold:
        subtypes.add("庫存股出售")
    subtypes.discard("其他")
    filing.subtypes = sorted(subtypes) or ["其他"]

    if len(filing.subtypes) == 1:
        filing.category = filing.subtypes[0]
    elif set(filing.subtypes) == {"新增購回", "註銷購回股份"}:
        filing.category = "購回並註銷"
    else:
        filing.category = "混合"
    return filing


def filing_numbers(filing: Filing) -> tuple[int, int, int]:
    """Return (issued share delta, cancellation shares, new issuance shares)."""
    issued = 0
    cancelled = 0
    issued_new = 0
    for event in filing.events:
        if event.delta is None:
            continue
        issued += event.delta
        if event.delta < 0 and "註銷" in event.desc:
            cancelled += -event.delta
        elif event.delta > 0 and "購回" not in event.desc:
            issued_new += event.delta
    return issued, cancelled, issued_new


def _quote(text: str, needle: str, width: int = 140) -> str:
    index = text.find(needle)
    if index < 0:
        return text[:width].strip()
    start = max(0, index - 30)
    return text[start:index + width].strip()


def _fact(key: str, value: int | float | None, text: str, needle: str,
          *, unit: str | None = None, currency: str | None = None,
          pages: list[tuple[int, str]] | None = None) -> "AnalyzerFact | None":
    if value is None or value == 0:
        return None
    shown = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    quote = _quote(text, needle)
    page = None
    if pages:
        page = next((number for number, content in pages if quote in content), None)
        if page is None:
            page = next((number for number, content in pages if needle in content), None)
    return AnalyzerFact(
        key=key,
        value=shown,
        unit=unit,
        currency=currency,
        evidence=Evidence(page=page, quote=quote),
    )


class NdrAnalyzer:
    family = "ndr"

    def matches(self, ann) -> bool:
        return ann.doc_group == "翌日披露報表"

    def analyze(self, ann, text: str, ctx=None,
                pages: list[tuple[int, str]] | None = None) -> AnalyzerResult:
        filing = parse_filing(ann.news_id, text)
        facts: list[AnalyzerFact] = []
        make = partial(_fact, pages=pages)

        buyback_shares = sum(item.shares for item in filing.buybacks)
        candidates = [
            make("buyback.shares", buyback_shares, text, "合共購回股份總數", unit="shares"),
            make("buyback.cancel.shares", filing.buyback_cancel, text, "購回股份（擬註銷）", unit="shares"),
            make("buyback.treasury.shares", filing.buyback_treasury, text, "購回股份（擬持作庫存股份）", unit="shares"),
            make("pending.shares", sum(row.delta or 0 for row in filing.pending), text, "B. 贖回/購回", unit="shares"),
            make("shares.start", filing.start_shares, text, "於下列日期開始時的結存", unit="shares"),
            make("shares.end", filing.end_shares, text, "於下列日期結束時的結存", unit="shares"),
            make("treasury.sold", filing.treasury_sold, text, "合共出售庫存股份總數", unit="shares"),
        ]
        facts.extend(item for item in candidates if item is not None)

        amounts: dict[str, float] = {}
        for item in filing.buybacks:
            if item.amount is None:
                continue
            amounts[item.currency or "UNKNOWN"] = amounts.get(item.currency or "UNKNOWN", 0) + item.amount
        for currency, amount in amounts.items():
            fact = make(
                f"buyback.amount.{currency}", amount, text, "合共付出的價格總額",
                currency=None if currency == "UNKNOWN" else currency,
            )
            if fact is not None:
                facts.append(fact)

        issued, cancelled, issued_new = filing_numbers(filing)
        for key, value, needle in (
            ("issued.delta", issued, "變動日期"),
            ("issued.new", issued_new, "變動日期"),
            ("cancelled.shares", cancelled, "變動日期"),
        ):
            fact = make(key, value, text, needle, unit="shares")
            if fact is not None:
                facts.append(fact)

        summary = f"{filing.category}；事件 {len(filing.events)} 項"
        if filing.buybacks:
            summary += f"，購回 {buyback_shares:,} 股"
        if filing.pending:
            summary += f"，待註銷 {sum(row.delta or 0 for row in filing.pending):,} 股"

        event = AnalyzerEvent(
            family=self.family,
            type=filing.category,
            code=ann.primary_code,
            news_id=ann.news_id,
            summary=summary,
            facts=facts,
        )
        return AnalyzerResult(analyzer=self.family, events=[event])
