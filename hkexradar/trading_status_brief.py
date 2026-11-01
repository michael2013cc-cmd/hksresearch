from __future__ import annotations

from collections import defaultdict
from datetime import datetime

SOURCE_COMPANY = "公司公告"
SOURCE_EXCHANGE = "交易所通告"


def _canonical_status(status: str) -> str:
    return "停牌" if status == "繼續停牌" else status


def dedupe_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row.get("code", ""), _canonical_status(row.get("status", "")))].append(row)

    kept: list[dict] = []
    dropped: list[dict] = []
    for group in groups.values():
        best = max(
            group,
            key=lambda row: (
                1 if row.get("source") == SOURCE_COMPANY else 0,
                len(row.get("note") or ""),
                row.get("time") or "",
            ),
        )
        merged = dict(best)
        for row in group:
            if row is best:
                continue
            for key in ("timing", "reason", "page", "quote"):
                if not merged.get(key) and row.get(key):
                    merged[key] = row[key]
        kept.append(merged)
        dropped.extend(row for row in group if row is not best)

    kept.sort(key=lambda row: (row.get("time") or "", row.get("code") or ""))
    return kept, dropped


def build_alerts(rows: list[dict]) -> list[dict]:
    alerts: list[dict] = []
    for row in rows:
        evidence = row.get("quote") or row.get("note") or ""
        if row.get("page"):
            evidence = f"第 {row['page']} 頁｜{evidence}"
        reason = row.get("reason") or ""
        message = row.get("status", "")
        if reason:
            message += f"：{reason}"
        alerts.append({
            "level": "P0",
            "rule": "trading_status",
            "time": row.get("time", ""),
            "code": row.get("code", ""),
            "name": row.get("name", ""),
            "category": row.get("status", ""),
            "message": message,
            "metric": 100.0,
            "evidence": evidence,
        })
    alerts.sort(key=lambda alert: (alert["time"], alert["code"]))
    return alerts


def _cell(value: str | None, limit: int = 120) -> str:
    text = (value or "—").replace("|", "／")
    return text[:limit]


def render_brief(rows: list[dict], alerts: list[dict], stats: dict,
                 generated_at: datetime) -> str:
    day = stats.get("date") or generated_at.strftime("%Y-%m-%d")
    status_counts = stats.get("status_counts") or {}
    source_counts = stats.get("source_counts") or {}

    lines = [f"# 停復牌事件簡報 · {day}", ""]
    lines.append(
        f"> 共 {stats.get('total', len(rows))} 份命中，去重後 {len(rows)} 個事件；全部 P0。"
        f"其中 {stats.get('duplicates', 0)} 份因同日同代碼同狀態被去重"
        "（交易所通告與公司公告並存時保留公司公告）。"
    )
    lines.append("")

    lines.append("## 一、P0 事件")
    lines.append("")
    if rows:
        lines.append("| 時間 | 代碼 | 公司 | 狀態 | 生效時間 | 原因 | 來源 | 證據 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for row in rows:
            lines.append(
                f"| {_cell(row.get('time'))} | {_cell(row.get('code'))} | {_cell(row.get('name'))} | "
                f"{_cell(row.get('status'))} | {_cell(row.get('timing'))} | {_cell(row.get('reason'))} | "
                f"{_cell(row.get('source'))} | {_cell(row.get('quote') or row.get('note'))} |"
            )
    else:
        lines.append("無。")
    lines.append("")

    lines.append("## 二、狀態分布")
    lines.append("")
    if status_counts:
        lines.append("| 狀態 | 事件數 |")
        lines.append("|---|---|")
        for status, count in sorted(status_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"| {status} | {count} |")
    else:
        lines.append("無。")
    lines.append("")

    lines.append("## 三、數據質量")
    lines.append("")
    failures = stats.get("text_failures") or []
    lines.append(f"- 文字抽取失敗：{len(failures)} 份" + (f"（{', '.join(failures)}）" if failures else ""))
    lines.append(f"- 僅標題判斷：{stats.get('title_only', 0)} 份")
    lines.append(f"- 去重丟棄：{stats.get('duplicates', 0)} 份")
    if source_counts:
        lines.append("- 來源：" + "、".join(
            f"{source} {count}" for source, count in sorted(source_counts.items())
        ))
    lines.append("- 口徑：停牌/復牌直接 P0；「繼續停牌」是延續既有停牌，不代表當日新停牌。")
    lines.append("")
    return "\n".join(lines)
