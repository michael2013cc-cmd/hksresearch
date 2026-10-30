import json
from datetime import date, datetime
from pathlib import Path

import httpx

from hkexradar.collector import (
    build_params,
    fetch_day_payload,
    fetch_payload,
    parse_datetime,
    parse_payload,
    save_snapshot,
)

ROW = {
    "FILE_INFO": "131KB",
    "NEWS_ID": "12325368",
    "SHORT_TEXT": "公告及通告 - [內幕消息]<br/>",
    "TOTAL_COUNT": "590",
    "DOD_WEB_PATH": "",
    "STOCK_NAME": "交運燃氣",
    "TITLE": "控股股東質押股份解除公告",
    "FILE_TYPE": "PDF",
    "DATE_TIME": "08/09/2026 22:59",
    "LONG_TEXT": "公告及通告 - [內幕消息]",
    "STOCK_CODE": "01407",
    "FILE_LINK": "/listedco/listconews/sehk/2026/0908/2026090801276_c.pdf",
}


def _payload(rows):
    return {"result": json.dumps(rows, ensure_ascii=False), "recordCnt": len(rows), "hasNextRow": False}


def test_build_params_uses_single_day_range():
    p = build_params(date(2026, 9, 8), row_range=1000)
    assert p["fromDate"] == "20260908"
    assert p["toDate"] == "20260908"
    assert p["rowRange"] == 1000
    assert p["lang"] == "ZH"
    assert p["searchType"] == 0


def test_parse_datetime_accepts_minutes_and_seconds():
    assert parse_datetime("08/09/2026 22:59") == datetime(2026, 9, 8, 22, 59)
    assert parse_datetime("08/09/2026 22:59:30") == datetime(2026, 9, 8, 22, 59, 30)


def test_parse_payload_maps_fields_and_prefers_long_text():
    rows = parse_payload(_payload([ROW]))
    assert len(rows) == 1
    assert rows[0].news_id == "12325368"
    assert rows[0].category_label == "公告及通告 - [內幕消息]"
    assert rows[0].published_at == datetime(2026, 9, 8, 22, 59)


def test_fetch_payload_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=_payload([ROW]))

    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    client = httpx.Client(transport=httpx.MockTransport(handler))
    payload = fetch_payload(date(2026, 9, 8), client=client, retries=3)
    assert payload["recordCnt"] == 1
    assert calls["n"] == 2
    assert sleeps == [1]


def test_fetch_payload_gives_up_after_retries(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    monkeypatch.setattr("time.sleep", lambda s: None)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        fetch_payload(date(2026, 9, 8), client=client, retries=2)
    except RuntimeError as exc:
        assert "after 2 attempts" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_fetch_day_payload_merges_both_directions_when_capped():
    middle = {**ROW, "NEWS_ID": "2", "DATE_TIME": "08/09/2026 22:00"}
    oldest = {**ROW, "NEWS_ID": "3", "DATE_TIME": "08/09/2026 07:00"}

    def handler(request: httpx.Request) -> httpx.Response:
        rows = [ROW, middle] if request.url.params.get("sortDir") == "0" else [middle, oldest]
        return httpx.Response(200, json={
            "result": json.dumps(rows, ensure_ascii=False),
            "recordCnt": len(rows),
            "hasNextRow": True,
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    payload = fetch_day_payload(date(2026, 9, 8), client=client)
    rows = json.loads(payload["result"])
    assert [row["NEWS_ID"] for row in rows] == ["3", "2", "12325368"]
    assert payload["recordCnt"] == 3
    assert payload["hasNextRow"] is False


def test_save_snapshot_is_written_verbatim(tmp_path: Path):
    payload = _payload([ROW])
    path = save_snapshot(payload, tmp_path / "announcements.json")
    assert json.loads(path.read_text(encoding="utf-8")) == payload
