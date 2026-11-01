from __future__ import annotations

import re
from functools import partial

from .base import AnalyzerEvent, AnalyzerFact, AnalyzerResult, make_fact

_TAGS = {
    "配售",
    "供股",
    "根據一般性授權發行股份",
    "根據特定授權發行股份",
    "發行可轉換證券",
    "更改證券條款或隨附於證券的權利",
    "資本重組",
    "股份合併",
    "交換證券或取代原證券",
}

_TITLE_HINTS = ("配售新", "供股", "可換股債券", "可轉換債券", "股份合併", "資本重組")
_TITLE_EXCLUDES = ("認購理財產品", "認購基金", "股份計劃", "股權激勵")

_ISSUANCE_TYPES = {"配售/認購", "配售/認購（上限）", "配售/認購完成", "供股", "供股結果", "可換股債券"}
_QUIET_TYPES = {"終止配售", "進展/延遲"}


def _match(pattern: str, text: str):
    return re.search(pattern, text)


def _deal_text(text: str, sentences: int = 2) -> str:
    positions = [text.find(word) for word in ("配售股份", "認購股份", "供股股份")]
    positions = [pos for pos in positions if pos >= 0]
    if not positions:
        return text
    anchor = min(positions)
    begin = text.rfind("。", 0, anchor)
    begin = 0 if begin < 0 else begin + 1
    end = anchor
    for _ in range(sentences):
        stop = text.find("。", end)
        if stop < 0:
            return text[begin:]
        end = stop + 1
    return text[begin:end]


def _number(raw: str | None) -> float | None:
    if not raw:
        return None
    return float(raw.replace(",", ""))


def _money(raw: str | None, scale: str | None) -> float | None:
    value = _number(raw)
    if value is None:
        return None
    return value * {"百萬": 1e6, "億": 1e8, "千": 1e3}.get(scale or "", 1)


def _event_type(title: str, tags: list[str]) -> str:
    if "終止" in title and any(word in title for word in ("配售", "供股", "認購")):
        return "終止配售"
    if "供股" in title and "結果" in title:
        return "供股結果"
    if "換股價" in title and "調整" in title:
        return "調整換股價"
    if any(word in title for word in ("延遲", "延長", "澄清", "補充", "最新進展", "最新資料")):
        return "進展/延遲"
    if "可換股" in title or "可轉換" in title:
        return "可換股債券"
    if "股份合併" in title or "資本重組" in title:
        return "股份合併/資本重組"
    if "供股" in title or "供股" in tags:
        return "供股"
    if "完成" in title or "交割" in title:
        return "配售/認購完成"
    return "配售/認購"


class CapitalActionsAnalyzer:
    family = "capital"

    def matches(self, ann) -> bool:
        if ann.doc_group != "公告及通告":
            return False
        title = ann.title or ""
        if any(word in title for word in _TITLE_EXCLUDES):
            return False
        tags = list(ann.headline_tags or [])
        return bool(set(tags) & _TAGS) or any(word in title for word in _TITLE_HINTS)

    def analyze(self, ann, text: str, ctx=None,
                pages: list[tuple[int, str]] | None = None) -> AnalyzerResult:
        kind = _event_type(ann.title or "", list(ann.headline_tags or []))
        if kind == "配售/認購" and "配售最多" in text:
            kind = "配售/認購（上限）"
        make = partial(make_fact, pages=pages)
        facts: list[AnalyzerFact] = []

        shares, shares_needle = self._shares(text, kind)
        price, price_needle = self._price(text)
        gross, gross_needle = self._gross(text)
        net, net_needle = self._net(text)
        existing = _match(r"(?:現有已發行股本|已發行股份總數)的?\s*約?\s*([\d.]+)\s*%", _deal_text(text))
        post = _match(r"擴大[後之的]?[^。%]{0,60}?約?\s*([\d.]+)\s*%", _deal_text(text))
        acceptance = _match(r"佔供股項下提呈發售之供股股份總數約\s*([\d.]+)\s*%", text)
        undersubscribed = _match(r"餘下\s*([\d,]+)\s*股未獲認購", text)
        outstanding = _match(r"已發行股份總數(?:為|約為)?\s*([\d,]+)\s*股", text)
        ratio_existing = _number(existing.group(1)) if existing else None
        ratio_post = _number(post.group(1)) if post else None
        acceptance_value = _number(acceptance.group(1)) if acceptance else None

        candidates = [
            make("issue.shares", shares, text, shares_needle or "", unit="shares"),
            make("issue.price", price, text, price_needle or "", unit="per share", currency="HKD"),
            make("proceeds.gross", gross, text, gross_needle or "", currency="HKD"),
            make("proceeds.net", net, text, net_needle or "", currency="HKD"),
            make("ratio.existing", ratio_existing, text, existing.group(0) if existing else "", unit="%"),
            make("ratio.post", ratio_post, text, post.group(0) if post else "", unit="%"),
            make("shares.outstanding", _number(outstanding.group(1)) if outstanding else None,
                 text, outstanding.group(0) if outstanding else "", unit="shares"),
            make("rights.acceptance_pct", acceptance_value,
                 text, acceptance.group(0) if acceptance else "", unit="%"),
            make("rights.undersubscribed.shares",
                 _number(undersubscribed.group(1)) if undersubscribed else None,
                 text, undersubscribed.group(0) if undersubscribed else "", unit="shares"),
        ]
        facts.extend(item for item in candidates if item is not None)

        if kind == "終止配售":
            direction = "neutral"
            summary = "終止配售協議，未發行股份"
            materiality = 10.0
        else:
            direction = "negative" if kind in _ISSUANCE_TYPES else "neutral"
            materiality = min(100.0, (ratio_post or ratio_existing or 0.0) * 5)
            summary = self._summary(kind, shares, price, net, ratio_post, acceptance_value)

        warnings = []
        if not facts and kind not in _QUIET_TYPES:
            warnings.append("未抽取到數字，需人工復核原文")

        event = AnalyzerEvent(
            family=self.family,
            type=kind,
            code=ann.primary_code,
            news_id=ann.news_id,
            direction=direction,
            materiality=materiality,
            summary=summary,
            facts=facts,
        )
        return AnalyzerResult(analyzer=self.family, events=[event], warnings=warnings)

    def _shares(self, text: str, kind: str) -> tuple[float | None, str | None]:
        patterns = []
        if kind == "供股結果":
            patterns.append(r"將予配發及發行\s*([\d,]+)\s*股供股股份")
        patterns.extend([
            r"合共(?:為)?\s*([\d,]+)\s*股(?:配售|認購)股份",
            r"配售最多\s*([\d,]+)\s*股配售股份",
            r"(?:配售|認購)\s*([\d,]+)\s*股(?:配售|認購)股份",
        ])
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return _number(match.group(1)), match.group(0)
        return None, None

    def _price(self, text: str) -> tuple[float | None, str | None]:
        match = re.search(
            r"(?:配售價|認購價|發行價)?\s*每股(?:配售|認購)?股份\s*([\d.]+)\s*港元", text
        )
        if match:
            return float(match.group(1)), match.group(0)
        match = re.search(r"([\d.]+)\s*港元的(?:認購價|配售價|發行價)", text)
        if match:
            return float(match.group(1)), match.group(0)
        return None, None

    def _gross(self, text: str) -> tuple[float | None, str | None]:
        match = re.search(
            r"所得款項總額及(?:所得款項)?淨額[^。]{0,60}?分別(?:約為|將為|為)\s*([\d,.]+)\s*(百萬|億|千)?\s*港元"
            r"\s*及\s*約?\s*([\d,.]+)\s*(百萬|億|千)?\s*港元",
            text,
        )
        if match:
            return _money(match.group(1), match.group(2)), "所得款項總額及所得款項淨額"
        match = re.search(
            r"所得款項總額[^。]{0,40}?約為\s*([\d,.]+)\s*(百萬|億|千)?\s*港元", text
        )
        if match:
            return _money(match.group(1), match.group(2)), match.group(0)
        return None, None

    def _net(self, text: str) -> tuple[float | None, str | None]:
        match = re.search(
            r"所得款項總額及(?:所得款項)?淨額[^。]{0,60}?分別(?:約為|將為|為)\s*([\d,.]+)\s*(百萬|億|千)?\s*港元"
            r"\s*及\s*約?\s*([\d,.]+)\s*(百萬|億|千)?\s*港元",
            text,
        )
        if match:
            return _money(match.group(3), match.group(4)), "所得款項總額及所得款項淨額"
        match = re.search(
            r"所得款項淨額[^。]{0,40}?約為\s*([\d,.]+)\s*(百萬|億|千)?\s*港元", text
        )
        if match:
            return _money(match.group(1), match.group(2)), match.group(0)
        return None, None

    @staticmethod
    def _summary(kind: str, shares: float | None, price: float | None,
                 net: float | None, ratio_post: float | None,
                 acceptance: float | None) -> str:
        parts = [kind]
        if shares:
            prefix = "最多發行" if kind.endswith("（上限）") else "發行"
            parts.append(f"{prefix} {int(shares):,} 股")
        if price:
            parts.append(f"每股 {price:g} 港元")
        if net:
            parts.append(f"淨籌 {int(net):,} 港元")
        if ratio_post:
            parts.append(f"佔擴大後股本 {ratio_post:g}%")
        if acceptance:
            parts.append(f"認購率 {acceptance:g}%")
        return "，".join(parts)
