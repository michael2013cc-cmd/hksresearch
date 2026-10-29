from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path

from .collector import fetch_payload, load_snapshot, next_snapshot_path, parse_payload, save_snapshot
from .config import load_priors, load_rules, load_settings
from .models import CategoryStat, DailyReport, Quality
from .normalizer import normalize_all
from .pdf import download_pdf, extract_text, pdf_filename
from .reader import read, rule_insight
from .reporter import build_overview, write_report
from .scorer import category_prior, score
from .triage import triage


def _attach_pdf(ann, raw_dir: Path) -> None:
    dest = raw_dir / "pdf" / pdf_filename(ann.news_id)
    if not download_pdf(ann.file_url, dest):
        ann.text_status = "unavailable"
        return
    ann.pdf_path = str(dest)
    ann.text_head, ann.text_status = extract_text(dest)


def run_day(day_text: str, *, root: Path, llm=None, raw_path: Path | None = None,
            download_pdf: bool = True, out_dir: Path | None = None,
            read_top_n: int | None = None, report_top_n: int | None = None) -> DailyReport:
    settings = load_settings(root)
    rules = load_rules(root)
    priors = load_priors(root)
    day = date.fromisoformat(day_text)
    raw_dir = root / "data" / "raw" / day_text
    out_dir = out_dir or (root / "reports")
    errors: list[str] = []

    if raw_path is not None:
        payload = load_snapshot(raw_path)
    else:
        try:
            payload = fetch_payload(
                day,
                timeout=settings["collector"]["timeout_seconds"],
                retries=settings["collector"]["retries"],
            )
            save_snapshot(payload, next_snapshot_path(raw_dir))
        except Exception as exc:  # noqa: BLE001 - 采集失败必须显式记录
            raise RuntimeError(f"collection failed: {exc}") from exc

    raws = parse_payload(payload)
    announcements = normalize_all(raws)

    candidates, reasons = triage(announcements, rules)
    candidates.sort(
        key=lambda a: (category_prior(a, priors), a.file_bytes or 0), reverse=True
    )

    limit = read_top_n if read_top_n is not None else settings["pipeline"]["read_top_n"]
    to_read = candidates[:limit] if limit else []

    if download_pdf:
        for ann in to_read:
            _attach_pdf(ann, raw_dir)

    insights = {}
    for ann in to_read:
        insight = read(ann, llm)
        insights[ann.news_id] = insight

    day_counts = Counter(
        (ann.doc_group, tuple(sorted(ann.headline_tags))) for ann in announcements
    )
    scored = [
        score(ann, insights.get(ann.news_id) or rule_insight(ann), priors,
              day_counts, len(announcements), reasons.get(ann.news_id, ""))
        for ann in candidates
    ]
    scored.sort(key=lambda item: item.final_score, reverse=True)

    top_n = report_top_n if report_top_n is not None else settings["pipeline"]["report_top_n"]
    grade_counts: dict[str, int] = {}
    for item in scored:
        grade_counts[item.grade] = grade_counts.get(item.grade, 0) + 1

    category_counts = Counter(ann.doc_group for ann in announcements)
    category_stats = [
        CategoryStat(doc_group=group, count=count)
        for group, count in category_counts.most_common()
    ]

    report = DailyReport(
        report_date=day,
        generated_at=datetime.now(),
        total=len(announcements),
        candidate_count=len(candidates),
        read_count=len(insights),
        grade_counts=grade_counts,
        category_stats=category_stats,
        top=scored[:top_n],
        quality=Quality(
            collection_errors=errors,
            pdf_unavailable=sum(1 for a in to_read if a.text_status == "unavailable"),
            revisions=sum(1 for a in announcements if a.is_revision),
            llm_fallbacks=sum(1 for i in insights.values() if i.source == "rule"),
            total_records=len(announcements),
        ),
    )
    report.overview = build_overview(report)
    write_report(report, out_dir)
    return report
