from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from hkexradar.analyzers.trading_status import TradingStatusAnalyzer
from hkexradar.collector import load_snapshot, parse_payload
from hkexradar.htmltext import fetch_html_text
from hkexradar.normalizer import normalize_all
from hkexradar.pdf import download_pdf, extract_pages, pdf_filename
from hkexradar.store import EventStore
from hkexradar.trading_status_brief import build_alerts, dedupe_rows, render_brief

ROOT = Path(__file__).resolve().parents[1]
HTML_SUFFIXES = (".htm", ".html")


def is_html(url: str) -> bool:
    path = (url or "").split("?")[0].lower()
    return path.endswith(HTML_SUFFIXES)


def load_html(url: str, news_id: str, cache_dir: Path) -> tuple[list[tuple[int, str]], str, str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{news_id}.html"
    if cache.exists():
        text = cache.read_text(encoding="utf-8")
    else:
        try:
            text = fetch_html_text(url)
        except Exception:  # noqa: BLE001 - 单份失败只降级该条
            return [], "", "unavailable"
        cache.write_text(text, encoding="utf-8")
    if not text.strip():
        return [], "", "unavailable"
    return [(1, text)], text, "ok"


def load_pdf(url: str, news_id: str, pdf_dir: Path) -> tuple[list[tuple[int, str]], str, str]:
    path = pdf_dir / pdf_filename(news_id)
    if not download_pdf(url, path):
        return [], "", "unavailable"
    return extract_pages(path)


def analyse(day: str) -> tuple[list[dict], list[dict], dict]:
    raw = parse_payload(load_snapshot(ROOT / "data" / "raw" / day / "announcements.json"))
    analyzer = TradingStatusAnalyzer()
    anns = [ann for ann in normalize_all(raw) if analyzer.matches(ann)]
    day_dir = ROOT / "data" / "raw" / day
    pdf_dir = day_dir / "pdf"
    html_dir = day_dir / "html"

    rows: list[dict] = []
    store = EventStore(ROOT / "data" / "events.db")
    stored = 0
    store_errors: list[str] = []
    for ann in anns:
        if is_html(ann.file_url):
            pages, text, status = load_html(ann.file_url, ann.news_id, html_dir)
        else:
            pages, text, status = load_pdf(ann.file_url, ann.news_id, pdf_dir)
        result = analyzer.analyze(ann, text[:30000], pages=pages)
        event = result.events[0]
        facts = {fact.key: fact.value for fact in event.facts}
        evidence = {fact.key: fact.evidence for fact in event.facts}
        note_evidence = evidence.get("status.note")
        page = note_evidence.page if note_evidence else None
        quote = note_evidence.quote if note_evidence else ""
        rows.append({
            "time": ann.published_at.strftime("%H:%M"),
            "code": ann.primary_code,
            "name": ann.stock_name,
            "title": ann.title,
            "status": facts.get("status", ""),
            "source": facts.get("status.source", ""),
            "timing": facts.get("status.timing", ""),
            "reason": facts.get("status.reason", ""),
            "note": facts.get("status.note", ""),
            "page": page,
            "quote": quote,
            "text_status": status,
            "effective_date": event.effective_date.isoformat() if event.effective_date else "",
            "news_id": ann.news_id,
            "warning": result.warnings[0] if result.warnings else "",
        })
        try:
            store.add_result(ann, result)
            stored += 1
        except Exception as exc:  # noqa: BLE001 - 单份归档失败不应中断整日分析
            store_errors.append(f"{ann.primary_code}: {exc}")
    store.close()

    kept, dropped = dedupe_rows(rows)
    stats = {
        "date": day,
        "total": len(rows),
        "unique": len(kept),
        "duplicates": len(dropped),
        "stored": stored,
        "store_errors": store_errors,
        "status_counts": dict(Counter(row["status"] for row in kept)),
        "source_counts": dict(Counter(row["source"] for row in kept)),
        "text_failures": [row["code"] for row in rows if row["text_status"] != "ok"],
        "title_only": sum(1 for row in rows if row["text_status"] != "ok"),
    }
    return kept, dropped, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="HKEX trading suspension / resumption analysis")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    day = args.date

    rows, dropped, stats = analyse(day)
    alerts = build_alerts(rows)
    stats["alert_counts"] = dict(Counter(alert["level"] for alert in alerts))

    now = datetime.now()
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    json_path = reports / f"{day}-trading-status.json"
    md_path = reports / f"{day}-trading-status.md"
    json_path.write_text(
        json.dumps({"stats": stats, "alerts": alerts, "events": rows, "dropped": dropped},
                   ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_brief(rows, alerts, stats, now), encoding="utf-8")

    print(f"announcements={stats['total']} unique={stats['unique']} "
          f"p0={len(alerts)} stored={stats['stored']}")
    print(f"brief: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
