from __future__ import annotations

import re

from .base import AnalyzerEvent, AnalyzerFact, AnalyzerResult, Evidence, quote_around

TAGS = {"停牌", "復牌", "短暫停牌"}
SOURCE_COMPANY = "公司公告"
SOURCE_EXCHANGE = "交易所通告"

_CONTINUING = ("繼續暫停買賣", "繼續暫停交易", "持續暫停交易", "維持停牌", "繼續停牌")
_RESUMPTION = ("恢復買賣", "恢復交易")
_SUSPENSION = ("暫停買賣", "停止買賣", "暫停交易", "停止交易")

_REASONS = (
    ("清盤", "清盤/臨時清盤人"),
    ("臨時清盤人", "清盤/臨時清盤人"),
    ("延遲刊發", "延遲刊發業績"),
    ("延遲發表", "延遲刊發業績"),
    ("延遲寄發", "延遲寄發文件"),
    ("證券及期貨事務監察委員會的指令", "監管機構指令"),
    ("收購及合併守則", "收購守則相關"),
    ("收購守則", "收購守則相關"),
    ("復牌指引", "復牌指引"),
    ("未能符合", "未能符合上市規則"),
)

_DATE = (
    r"(?:"
    r"(?:[零〇一二三四五六七八九]{4}\s*年|20\d{2}\s*年)\s*"
    r"[0-9零〇一二三四五六七八九十]{1,2}\s*月\s*"
    r"[0-9零〇一二三四五六七八九十]{1,3}\s*日"
    r"(?:\s*（[^）]{1,10}）)?"
    r"|（?\d{1,2}/\d{1,2}/\d{4}）?"
    r")"
)
_TIME = (
    r"(?:上午|下午|中午|早上)?\s*"
    r"[0-9零〇一二三四五六七八九十]{1,3}\s*(?:時|点|點)\s*"
    r"(?:[0-9零〇一二三四五六七八九十]{1,3}\s*分)?\s*(?:正)?"
)
_TIMING = re.compile(rf"({_DATE}\s*{_TIME}\s*起)")
_RESUMPTION_AFTER = re.compile(rf"{_TIMING.pattern}\s*(?:恢復|復牌)")
_SUSPENSION_AFTER = re.compile(rf"{_TIMING.pattern}[^。；]{{0,20}}(?:暫停|停止|停牌)")


def is_exchange_notice(title: str) -> bool:
    return (title or "").strip().startswith(SOURCE_EXCHANGE)


def classify_status(title: str, text: str) -> str:
    title = title or ""
    body = text or ""

    if is_exchange_notice(title):
        if "短暫停牌" in title:
            return "短暫停牌"
        if "復牌" in title:
            return "復牌"
        if "停牌" in title:
            return "停牌"

    if any(word in title for word in _CONTINUING):
        return "繼續停牌"
    if "短暫停牌" in title or "短暫停止買賣" in title:
        return "短暫停牌"
    if any(word in title for word in _RESUMPTION + ("復牌",)) and not any(
        word in title for word in ("進展", "進度", "指引", "計劃", "更新", "最新")
    ):
        return "復牌"
    if any(word in title for word in _SUSPENSION + ("停牌",)):
        return "停牌"

    if any(word in body for word in _CONTINUING):
        return "繼續停牌"
    if any(word in body for word in _RESUMPTION):
        return "復牌"
    if any(word in body for word in _SUSPENSION + ("短暫停牌",)):
        return "停牌"
    return "停牌"


def _sentence_around(text: str, index: int) -> str:
    start = max(text.rfind("。", 0, index), text.rfind("；", 0, index)) + 1
    end = text.find("。", index)
    end = len(text) if end < 0 else end + 1
    return text[start:end].strip()


def _shorten(sentence: str, needle: str, limit: int = 200) -> str:
    if len(sentence) <= limit:
        return sentence
    return quote_around(sentence, needle, limit)


def _anchors(status: str) -> tuple[str, ...]:
    if status == "復牌":
        return _RESUMPTION + ("恢復股份", "復牌", "恢復")
    return _CONTINUING + ("短暫停牌", "暫停買賣", "短暫停止買賣", "停止買賣", "暫停交易", "停牌")


def _matches_status(sentence: str, status: str) -> bool:
    if status == "復牌":
        return bool(re.search(r"起\s*(?:恢復|復牌)", sentence))
    return bool(re.search(r"起[^。；]{0,20}(?:暫停|停止|停牌)", sentence))


def status_sentence(title: str, text: str, status: str = "") -> str:
    body = text or ""
    fallback: tuple[str, str] | None = None
    for needle in _anchors(status):
        start = 0
        while True:
            index = body.find(needle, start)
            if index < 0:
                break
            sentence = _sentence_around(body, index)
            if sentence and fallback is None:
                fallback = (sentence, needle)
            if sentence and _matches_status(sentence, status):
                return _shorten(sentence, needle)
            start = index + len(needle)
    if fallback:
        return _shorten(*fallback)
    return title


def extract_timing(text: str, status: str = "") -> str:
    body = text or ""
    pattern = _RESUMPTION_AFTER if status == "復牌" else _SUSPENSION_AFTER
    match = pattern.search(body)
    if match:
        return match.group(1).strip()
    match = _TIMING.search(body)
    return match.group(1).strip() if match else ""


def extract_reason(text: str) -> str:
    for needle, label in _REASONS:
        if needle in (text or ""):
            return label
    return ""


def _page_for(pages: list[tuple[int, str]] | None, needle: str) -> int | None:
    if not pages or not needle:
        return None
    return next((number for number, content in pages if needle in content), None)


class TradingStatusAnalyzer:
    family = "trading_status"

    def matches(self, ann) -> bool:
        if ann.doc_group != "公告及通告":
            return False
        return bool(set(ann.headline_tags or []) & TAGS) or is_exchange_notice(ann.title or "")

    def analyze(self, ann, text: str, ctx=None,
                pages: list[tuple[int, str]] | None = None) -> AnalyzerResult:
        title = ann.title or ""
        body = text or ""
        has_text = bool(body.strip())
        status = classify_status(title, body)
        source = SOURCE_EXCHANGE if is_exchange_notice(title) else SOURCE_COMPANY
        note = status_sentence(title, body, status) if has_text else title
        timing = extract_timing(body, status)
        reason = "" if status == "復牌" else extract_reason(body)
        page = _page_for(pages, note) or _page_for(pages, title)
        if page is None and pages:
            page = 1

        facts: list[AnalyzerFact] = [
            AnalyzerFact(key="status", value=status, evidence=Evidence(page=page, quote=note)),
            AnalyzerFact(key="status.source", value=source, evidence=Evidence(page=page, quote=title)),
            AnalyzerFact(key="status.note", value=note, evidence=Evidence(page=page, quote=note)),
        ]
        if timing:
            facts.append(AnalyzerFact(
                key="status.timing", value=timing, evidence=Evidence(page=page, quote=timing)
            ))
        if reason:
            facts.append(AnalyzerFact(
                key="status.reason", value=reason, evidence=Evidence(page=page, quote=note)
            ))

        direction = "positive" if status == "復牌" else "negative"
        summary = f"{ann.stock_name}（{ann.primary_code}）{status}"
        if reason:
            summary += f"：{reason}"
        warnings = [] if has_text else ["未读取正文，仅依据标题与标签判断"]

        event = AnalyzerEvent(
            family=self.family,
            type=status,
            code=ann.primary_code,
            news_id=ann.news_id,
            effective_date=ann.published_at.date(),
            direction=direction,
            materiality=100.0,
            confidence=1.0 if has_text else 0.6,
            summary=summary,
            facts=facts,
        )
        return AnalyzerResult(analyzer=self.family, events=[event], warnings=warnings)
