from pathlib import Path

from hkexradar.collector import load_snapshot, parse_payload

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "2026-09-08.json"


def test_fixture_matches_official_count():
    payload = load_snapshot(FIXTURE)
    rows = parse_payload(payload)
    assert payload["recordCnt"] == 590
    assert payload["hasNextRow"] is False
    assert len(rows) == 590
    assert rows[0].file_link.endswith(".pdf")
    assert all(row.news_id for row in rows)


def test_fixture_has_category_labels():
    rows = parse_payload(load_snapshot(FIXTURE))
    assert all(row.category_label for row in rows)
