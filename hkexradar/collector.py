from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path

import httpx

from .models import AnnouncementRaw

BASE_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
FILE_HOST = "https://www1.hkexnews.hk"
_TIME_FORMATS = ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S")


def build_params(day: date, row_range: int = 1000) -> dict:
    day_text = day.strftime("%Y%m%d")
    return {
        "sortDir": 0,
        "sortByOptions": "DateTime",
        "category": 0,
        "market": "SEHK",
        "stockId": -1,
        "documentType": -1,
        "fromDate": day_text,
        "toDate": day_text,
        "title": "",
        "searchType": 0,
        "t1code": -2,
        "t2Gcode": -2,
        "t2code": -2,
        "rowRange": row_range,
        "lang": "ZH",
    }


def parse_datetime(value: str) -> datetime:
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognized DATE_TIME: {value!r}")


def parse_payload(payload: dict) -> list[AnnouncementRaw]:
    raw_rows = payload.get("result") or "[]"
    rows = json.loads(raw_rows) if isinstance(raw_rows, str) else raw_rows
    result: list[AnnouncementRaw] = []
    for row in rows:
        result.append(
            AnnouncementRaw(
                news_id=str(row["NEWS_ID"]),
                stock_code=row.get("STOCK_CODE", ""),
                stock_name=row.get("STOCK_NAME", ""),
                published_at=parse_datetime(row["DATE_TIME"]),
                title=(row.get("TITLE") or "").strip(),
                category_label=(row.get("LONG_TEXT") or row.get("SHORT_TEXT") or "").strip(),
                file_type=row.get("FILE_TYPE", ""),
                file_info=row.get("FILE_INFO", ""),
                file_link=row.get("FILE_LINK", ""),
            )
        )
    return result


def _request(params: dict, *, timeout: float, retries: int,
             client: httpx.Client | None) -> dict:
    owns_client = client is None
    client = client or httpx.Client(timeout=timeout)
    last_error: Exception | None = None
    try:
        for attempt in range(retries):
            try:
                response = client.get(BASE_URL, params=params)
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # noqa: BLE001 - network faults are retried
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(2 ** (2 * attempt))
        raise RuntimeError(f"fetch failed after {retries} attempts: {last_error}") from last_error
    finally:
        if owns_client:
            client.close()


def fetch_payload(day: date, *, timeout: float = 60, retries: int = 3,
                  client: httpx.Client | None = None) -> dict:
    return _request(build_params(day), timeout=timeout, retries=retries, client=client)


def _rows(payload: dict) -> list[dict]:
    raw_rows = payload.get("result") or "[]"
    return json.loads(raw_rows) if isinstance(raw_rows, str) else raw_rows


def merge_payloads(newest: dict, oldest: dict) -> dict:
    unique: dict[str, dict] = {}
    for row in _rows(oldest) + _rows(newest):
        unique[str(row["NEWS_ID"])] = row
    rows = sorted(
        unique.values(),
        key=lambda row: (parse_datetime(row["DATE_TIME"]), str(row["NEWS_ID"])),
    )
    merged = dict(newest)
    merged["result"] = json.dumps(rows, ensure_ascii=False)
    merged["recordCnt"] = len(rows)
    merged["loadedRecord"] = len(rows)
    merged["hasNextRow"] = False
    return merged


def fetch_day_payload(day: date, *, timeout: float = 60, retries: int = 3,
                      client: httpx.Client | None = None) -> dict:
    """Row range is capped at 1000, so a busy day needs both sort directions."""
    newest = fetch_payload(day, timeout=timeout, retries=retries, client=client)
    if newest.get("hasNextRow") not in (True, "true"):
        return newest
    params = build_params(day)
    params["sortDir"] = 1
    oldest = _request(params, timeout=timeout, retries=retries, client=client)
    return merge_payloads(newest, oldest)


def save_snapshot(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def next_snapshot_path(raw_dir: Path) -> Path:
    first = raw_dir / "announcements.json"
    if not first.exists():
        return first
    index = 2
    while (raw_dir / f"announcements.{index}.json").exists():
        index += 1
    return raw_dir / f"announcements.{index}.json"
