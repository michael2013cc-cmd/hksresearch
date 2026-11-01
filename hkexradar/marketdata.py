from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import httpx

MAIN_URL = "https://www.hkex.com.hk/eng/stat/smstat/dayquot/d{stamp}e.htm"
GEM_URL = "https://www.hkex.com.hk/eng/stat/smstat/dayquot/GEM/e_G{stamp}.htm"

_ROW = re.compile(
    r"^\s*[*#]?\s*(\d{1,5})\s+(\S.*?)\s{2,}(HKD|USD|RMB|CNY)\s+(.*)$"
)
_CURRENCY = re.compile(r"^(?:HKD|USD|RMB|CNY)$")
_NUMBER = re.compile(r"^-?(?:\d[\d,]*)(?:\.\d+)?$")
_HEADER = "PRV.CLO"
_END = "SALES RECORDS"
_MARKERS = ("TRADING SUSPENDED", "TRADING HALT")


@dataclass(frozen=True)
class Quote:
    code: str
    name: str
    currency: str
    prev_close: float | None
    close: float | None
    high: float | None
    low: float | None
    shares_traded: int | None
    turnover: float | None
    suspended: bool = False


def _clean_blocks(html_text: str) -> list[str]:
    blocks = re.findall(r"<pre>(.*?)</pre>", html_text, re.S | re.I)
    return [re.sub(r"<[^>]+>", "", html_lib.unescape(block)) for block in blocks]


def _number(token: str) -> float | None:
    token = token.strip()
    return float(token.replace(",", "")) if _NUMBER.match(token) else None


def _integer(token: str) -> int | None:
    value = _number(token)
    return int(value) if value is not None else None


def _tokens(lines: Sequence[str], index: int, rest: str) -> tuple[list[str], int]:
    tokens = rest.split()
    cursor = index + 1
    while len(tokens) < 8 and cursor < len(lines):
        line = lines[cursor].strip()
        if not line:
            cursor += 1
            continue
        if _ROW.match(lines[cursor]) or _END in line:
            break
        tokens.extend(line.split())
        cursor += 1
    return tokens[:8], cursor


def parse_quotations(html_text: str) -> dict[str, Quote]:
    lines = "\n".join(_clean_blocks(html_text)).replace("\r", "").split("\n")
    start = next((i for i, line in enumerate(lines) if _HEADER in line), None)
    if start is None:
        return {}

    quotes: dict[str, Quote] = {}
    index = start + 2
    while index < len(lines):
        line = lines[index]
        if _END in line:
            break
        match = _ROW.match(line)
        if not match:
            index += 1
            continue
        code, name, currency, rest = match.groups()
        quote_code = code.zfill(5)
        upper = rest.upper()
        if any(marker in upper for marker in _MARKERS):
            quotes[quote_code] = Quote(
                code=quote_code, name=name.strip(), currency=currency,
                prev_close=None, close=None, high=None, low=None,
                shares_traded=None, turnover=None, suspended=True,
            )
            index += 1
            continue

        tokens, index = _tokens(lines, index, rest)
        if len(tokens) != 8:
            continue
        prev_close, ask, high, shares, close, bid, low, turnover = tokens
        quotes[quote_code] = Quote(
            code=quote_code,
            name=name.strip(),
            currency=currency,
            prev_close=_number(prev_close),
            close=_number(close),
            high=_number(high),
            low=_number(low),
            shares_traded=_integer(shares),
            turnover=_number(turnover),
        )
    return quotes


def quotation_urls(day: date) -> tuple[str, str]:
    stamp = day.strftime("%y%m%d")
    return MAIN_URL.format(stamp=stamp), GEM_URL.format(stamp=stamp)


def _cache_path(cache_dir: Path, day: date) -> Path:
    return cache_dir / f"quotes-{day.isoformat()}.json"


def save_cache(cache_dir: Path, day: date, quotes: Mapping[str, Quote]) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, day)
    payload = {
        "date": day.isoformat(),
        "quotes": {code: asdict(quote) for code, quote in quotes.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    return path


def load_cache(cache_dir: Path, day: date) -> dict[str, Quote] | None:
    path = _cache_path(cache_dir, day)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    allowed = {field.name for field in fields(Quote)}
    return {
        code: Quote(**{key: value for key, value in row.items() if key in allowed})
        for code, row in payload.get("quotes", {}).items()
    }


def fetch_day(day: date, cache_dir: Path, *, client: httpx.Client | None = None,
              timeout: float = 60.0) -> dict[str, Quote]:
    cached = load_cache(cache_dir, day)
    if cached is not None:
        return cached

    owns_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": "Mozilla/5.0 (compatible; hkexradar/0.1)"},
        timeout=timeout,
        follow_redirects=True,
    )
    try:
        quotes: dict[str, Quote] = {}
        for url in quotation_urls(day):
            response = client.get(url)
            response.raise_for_status()
            quotes.update(parse_quotations(response.text))
    finally:
        if owns_client:
            client.close()
    save_cache(cache_dir, day, quotes)
    return quotes


def market_cap(quote: Quote, shares: int | float | None) -> float | None:
    if not shares or shares <= 0:
        return None
    price = quote.close if quote.close is not None else quote.prev_close
    return price * shares if price is not None else None


def average_turnover(history: Iterable[Mapping[str, Quote]], code: str,
                     days: int = 20) -> float | None:
    values: list[float] = []
    for day_quotes in reversed(list(history)):
        quote = day_quotes.get(code)
        if quote is None or quote.turnover is None:
            continue
        values.append(quote.turnover)
        if len(values) >= days:
            break
    return sum(values) / len(values) if values else None
