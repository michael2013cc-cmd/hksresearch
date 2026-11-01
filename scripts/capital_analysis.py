from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from hkexradar.analyzers.capital import CapitalActionsAnalyzer
from hkexradar.capital_brief import (
    attach_market,
    build_alerts,
    load_thresholds,
    render_brief,
    shares_for_market,
)
from hkexradar.collector import load_snapshot, parse_payload
from hkexradar.marketdata import fetch_day
from hkexradar.normalizer import normalize_all
from hkexradar.pdf import download_pdf, extract_pages, extract_text, pdf_filename
from hkexradar.store import EventStore

ROOT = Path(__file__).resolve().parents[1]


def ensure_pdfs(anns, pdf_dir: Path) -> dict[str, str]:
    pdf_dir.mkdir(parents=True, exist_ok=True)

    def work(ann):
        path = pdf_dir / pdf_filename(ann.news_id)
        if not download_pdf(ann.file_url, path):
            return ann.news_id, "download_failed"
        _, status = extract_text(path, max_chars=100)
        return ann.news_id, status

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(work, anns))


def _value(facts: dict, key: str) -> float | None:
    raw = facts.get(key)
    return float(raw) if raw not in (None, "") else None


def _evidence(facts_evidence: dict, keys: tuple[str, ...]) -> tuple[int | None, str]:
    for key in keys:
        evidence = facts_evidence.get(key)
        if evidence:
            return evidence.page, evidence.quote
    return None, ""


def analyse(day: str) -> tuple[list[dict], dict]:
    raw = parse_payload(load_snapshot(ROOT / "data" / "raw" / day / "announcements.json"))
    analyzer = CapitalActionsAnalyzer()
    anns = [ann for ann in normalize_all(raw) if analyzer.matches(ann)]
    ensure_pdfs(anns, ROOT / "data" / "raw" / day / "pdf")

    rows: list[dict] = []
    store = EventStore(ROOT / "data" / "events.db")
    stored = 0
    store_errors: list[str] = []
    for ann in anns:
        path = ROOT / "data" / "raw" / day / "pdf" / pdf_filename(ann.news_id)
        pages, text, status = extract_pages(path)
        result = analyzer.analyze(ann, text[:30000], pages=pages)
        event = result.events[0]
        facts = {fact.key: fact.value for fact in event.facts}
        evidence = {fact.key: fact.evidence for fact in event.facts}
        page, quote = _evidence(evidence, (
            "ratio.existing", "ratio.post", "proceeds.net", "proceeds.gross",
            "issue.shares", "rights.undersubscribed.shares",
        ))
        shares = _value(facts, "issue.shares")
        ratio_existing = _value(facts, "ratio.existing")
        ratio_post = _value(facts, "ratio.post")
        announced = _value(facts, "shares.outstanding")
        prior = store.latest_fact(ann.primary_code, "shares.end", on_or_before=day)
        ndr_shares = float(prior["value"]) if prior else None
        market_shares, shares_source = shares_for_market(
            announced=announced,
            shares=shares,
            ratio_existing=ratio_existing,
            ratio_post=ratio_post,
            ndr_shares=ndr_shares,
        )
        if shares_source == "NDR" and prior:
            shares_source = f"NDR {prior['published_at'][:10]}"
        rows.append({
            "time": ann.published_at.strftime("%H:%M"),
            "code": ann.primary_code,
            "name": ann.stock_name,
            "title": ann.title,
            "type": event.type,
            "shares": shares,
            "price": _value(facts, "issue.price"),
            "gross": _value(facts, "proceeds.gross"),
            "net": _value(facts, "proceeds.net"),
            "ratio_existing": ratio_existing,
            "ratio_post": ratio_post,
            "shares_outstanding": market_shares,
            "shares_source": shares_source,
            "derived_shares": market_shares,
            "acceptance": _value(facts, "rights.acceptance_pct"),
            "undersubscribed": _value(facts, "rights.undersubscribed.shares"),
            "summary": event.summary,
            "page": page,
            "quote": quote,
            "text_status": status,
            "warning": result.warnings[0] if result.warnings else "",
        })
        try:
            store.add_result(ann, result)
            stored += 1
        except Exception as exc:  # noqa: BLE001 - 单份归档失败不应中断整日分析
            store_errors.append(f"{ann.primary_code}: {exc}")
    store.close()

    stats = {
        "date": day,
        "total": len(rows),
        "stored": stored,
        "store_errors": store_errors,
        "text_failures": [row["code"] for row in rows if row["text_status"] != "ok"],
        "type_counts": {},
    }
    for row in rows:
        stats["type_counts"][row["type"]] = stats["type_counts"].get(row["type"], 0) + 1
    return rows, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="HKEX capital actions analysis")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--no-market", action="store_true",
                        help="skip HKEX daily quotation lookup")
    args = parser.parse_args()
    day = args.date

    rows, stats = analyse(day)
    quotes = {}
    market_error = ""
    if not args.no_market:
        try:
            quotes = fetch_day(date.fromisoformat(day), ROOT / "data" / "cache" / "market")
        except Exception as exc:  # noqa: BLE001 - 行情失败不应中断公告分析
            market_error = str(exc)
    attach_market(rows, quotes)
    stats["market_quotes"] = len(quotes)
    stats["market_matched"] = sum(1 for row in rows if row.get("close") is not None)
    stats["market_error"] = market_error

    alerts = build_alerts(rows, load_thresholds(ROOT))
    stats["alert_counts"] = {}
    for alert in alerts:
        stats["alert_counts"][alert["level"]] = stats["alert_counts"].get(alert["level"], 0) + 1

    now = datetime.now()
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / f"{day}-capital-actions.json").write_text(
        json.dumps({"stats": stats, "alerts": alerts, "rows": rows},
                   ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (reports / f"{day}-capital-actions.md").write_text(
        render_brief(rows, alerts, stats, now), encoding="utf-8"
    )

    print(f"announcements={stats['total']} alerts={len(alerts)} stored={stats['stored']}")
    print(f"brief: {reports / f'{day}-capital-actions.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
