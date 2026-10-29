from __future__ import annotations

from pathlib import Path

from .models import DailyReport, ScoredAnnouncement


def build_overview(report: DailyReport) -> str:
    top_group = report.category_stats[0] if report.category_stats else None
    group_text = (
        f"發布最集中的類別是{top_group.doc_group}（{top_group.count} 條）"
        if top_group else "無分類統計"
    )
    grades = report.grade_counts or {}
    return (
        f"全天共 {report.total} 條公告，進入候選 {report.candidate_count} 條，"
        f"精讀 {report.read_count} 條；S 級 {grades.get('S', 0)} 條、A 級 {grades.get('A', 0)} 條。"
        f"{group_text}。"
    )


def _code_text(item: ScoredAnnouncement) -> str:
    code = item.announcement.primary_code
    suffix = "HK" if len(code) == 5 and code.isdigit() else ""
    return f"{code}.{suffix}" if suffix else code


def _render_item(rank: int, item: ScoredAnnouncement) -> list[str]:
    ann = item.announcement
    insight = item.insight
    lines = [f"### {rank}. [{item.grade}] {ann.stock_name}（{_code_text(item)}）— "
             f"{insight.summary_zh if insight else ann.title}"]
    lines.append(f"- **發布時間**：{ann.published_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **類別**：{ann.category_label}")
    if insight and insight.facts:
        facts = "；".join(f"{fact.key} {fact.value}" for fact in insight.facts)
        lines.append(f"- **關鍵數字**：{facts}")
    if insight:
        lines.append(f"- **方向/確定性**：{insight.direction} / {insight.uncertainty or '未說明'}")
    b = item.breakdown
    lines.append(
        f"- **評分**：{item.final_score} = magnitude {item.magnitude}"
        f"（類別 {b.category_prior * 40:.0f} + 規模 {b.scale * 20:.0f} + 意外 {b.surprise * 40:.0f}）"
        f" + interest {item.interest}"
        f"（稀缺 {b.scarcity * 50:.0f} + 覆蓋 {b.coverage * 30:.0f} + 傳播 {b.spread * 20:.0f}）"
    )
    lines.append(f"- **原文**：[PDF]({ann.file_url})")
    return lines


def _short(text: str, limit: int) -> str:
    text = text.replace("|", "／").replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _render_timeline(items: list[ScoredAnnouncement]) -> list[str]:
    lines = [
        "| 時間 | 代碼 | 公司 | 標題 | 級別 | 分數 | 原文 |",
        "|------|------|------|------|------|------|------|",
    ]
    for item in sorted(items, key=lambda i: i.announcement.published_at):
        ann = item.announcement
        lines.append(
            f"| {ann.published_at.strftime('%H:%M')} | {_code_text(item)} | "
            f"{_short(ann.stock_name, 20)} | {_short(ann.title, 60)} | "
            f"{item.grade} | {item.final_score} | [PDF]({ann.file_url}) |"
        )
    return lines


def render_markdown(report: DailyReport) -> str:
    lines: list[str] = []
    lines.append(f"# 港交所公告日報 · {report.report_date.isoformat()}")
    lines.append("")
    lines.append(
        f"> 共 {report.total} 條公告 · 候選 {report.candidate_count} 條 · "
        f"精讀 {report.read_count} 條 · 生成於 {report.generated_at.strftime('%H:%M')}"
    )
    lines.append("")
    lines.append("## 今日概覽")
    lines.append("")
    lines.append(build_overview(report))
    lines.append("")
    lines.append("## Top 20")
    lines.append("")
    if not report.top:
        lines.append("（今日無入選公告）")
        lines.append("")
    for rank, item in enumerate(report.top, start=1):
        lines.extend(_render_item(rank, item))
        lines.append("")

    lines.append("## 全部候選（按發布時間）")
    lines.append("")
    if report.ranked:
        lines.extend(_render_timeline(report.ranked))
    else:
        lines.append("（無候選）")
    lines.append("")

    lines.append("## 分類統計")
    lines.append("")
    lines.append("| 大類 | 條數 | 佔比 |")
    lines.append("|------|------|------|")
    for stat in report.category_stats:
        share = stat.count / report.total * 100 if report.total else 0
        lines.append(f"| {stat.doc_group} | {stat.count} | {share:.1f}% |")
    lines.append("")

    lines.append("## 數據質量")
    lines.append("")
    errors = "；".join(report.quality.collection_errors) if report.quality.collection_errors else "無"
    lines.append(f"- 採集錯誤：{errors}")
    lines.append(f"- PDF 抽取失敗：{report.quality.pdf_unavailable} 條")
    lines.append(f"- 疑似修訂版：{report.quality.revisions} 條")
    lines.append(f"- LLM 降級：{report.quality.llm_fallbacks} 條")
    lines.append("")
    return "\n".join(lines)


def write_report(report: DailyReport, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report.report_date.isoformat()}-hkex-daily"
    md_path = out_dir / f"{stem}.md"
    json_path = out_dir / f"{stem}.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(report.model_dump_json(indent=1), encoding="utf-8")
    return md_path, json_path
