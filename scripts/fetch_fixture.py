"""Fetch one day of HKEX announcements into data/fixtures/<date>.json."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hkexradar.collector import fetch_payload, save_snapshot  # noqa: E402


def main(day_text: str) -> None:
    day = date.fromisoformat(day_text)
    payload = fetch_payload(day)
    path = save_snapshot(payload, ROOT / "data" / "fixtures" / f"{day_text}.json")
    print(f"wrote {path} recordCnt={payload.get('recordCnt')}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-09-08")
