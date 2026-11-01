from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import load_yaml

DEFAULT_THRESHOLDS = {
    "dilution_p0_pct": 10.0,
    "dilution_p1_pct": 5.0,
    "rights_low_acceptance_pct": 90.0,
}

_ISSUANCE = {"配售/認購", "配售/認購（上限）", "配售/認購完成", "供股", "供股結果", "可換股債券"}


def load_thresholds(root: Path) -> dict:
    loaded = load_yaml(root / "config" / "analyzers" / "capital.yaml")
    return {**DEFAULT_THRESHOLDS, **loaded.get("thresholds", {})}


def _alert(level: str, rule: str, row: dict, message: str, metric: float) -> dict:
    evidence = row.get("quote") or ""
    if row.get("page"):
        evidence = f"第 {row['page']} 頁｜{evidence}"
    return {
        "level": level,
        "rule": rule,
        "time": row.get("time", ""),
        "code": row.get("code", ""),
        "name": row.get("name", ""),
        "category": row.get("type", ""),
        "message": message,
        "metric": metric,
        "evidence": evidence,
    }


def build_alerts(rows: list[dict], thresholds: dict | None = None) -> list[dict]:
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    alerts: list[dict] = []
    for row in rows:
        if row.get("type") not in _ISSUANCE:
            continue

        dilution = row.get("ratio_existing") or row.get("ratio_post")
        if dilution is not None:
            shares = row.get("shares") or 0
            prefix = "最多發行" if str(row.get("type", "")).endswith("（上限）") else "發行"
            if dilution >= limits["dilution_p0_pct"]:
                alerts.append(_alert(
                    "P0", "dilution", row,
                    f"{prefix} {int(shares):,} 股，佔發行前股本 {dilution:.1f}%", dilution,
                ))
            elif dilution >= limits["dilution_p1_pct"]:
                alerts.append(_alert(
                    "P1", "dilution", row,
                    f"{prefix} {int(shares):,} 股，佔發行前股本 {dilution:.1f}%", dilution,
                ))

        acceptance = row.get("acceptance")
        if acceptance is not None and acceptance < limits["rights_low_acceptance_pct"]:
            alerts.append(_alert(
                "P1", "rights_acceptance", row,
                f"供股認購率 {acceptance:.1f}%，低於 {limits['rights_low_acceptance_pct']:g}%",
                limits["rights_low_acceptance_pct"] - acceptance,
            ))

    order = {"P0": 0, "P1": 1}
    alerts.sort(key=lambda item: (order.get(item["level"], 9), -item["metric"], item["code"]))
    return alerts


def _alert_table(alerts: list[dict]) -> list[str]:
    lines = [
        "| 時間 | 代碼 | 公司 | 類別 | 觸發 | 數據 | 證據 |",
        "|---|---|---|---|---|---|---|",
    ]
    for alert in alerts:
        evidence = (alert["evidence"] or "—").replace("|", "／")
        lines.append(
            f"| {alert['time']} | {alert['code']} | {alert['name']} | {alert['category']} | "
            f"{alert['rule']} | {alert['message']} | {evidence} |"
        )
    return lines


def _num(value, fmt: str = ",.0f") -> str:
    return f"{value:{fmt}}" if value is not None else "—"


def render_brief(rows: list[dict], alerts: list[dict], stats: dict, generated_at: datetime) -> str:
    day = stats.get("date") or generated_at.strftime("%Y-%m-%d")
    p0 = [alert for alert in alerts if alert["level"] == "P0"]
    p1 = [alert for alert in alerts if alert["level"] == "P1"]
    rank = {alert["code"] + alert["time"]: 0 for alert in alerts}

    lines = [f"# 資本動作簡報 · {day}", ""]
    lines.append(
        f"> 掃描 {stats.get('total', len(rows))} 條公告；P0 {len(p0)} 條、P1 {len(p1)} 條。"
        "金額為公告口徑，未接入市值/成交額，未做跨公司歸一。"
    )
    lines.append("")

    lines.append("## 一、P0 必看")
    lines.append("")
    lines.extend(_alert_table(p0) if p0 else ["無。"])
    lines.append("")

    lines.append("## 二、P1 關注")
    lines.append("")
    lines.extend(_alert_table(p1) if p1 else ["無。"])
    lines.append("")

    lines.append("## 三、完成與終止")
    lines.append("")
    lines.append("| 時間 | 代碼 | 公司 | 類型 | 股數 | 價格 | 總額 | 淨額 | 佔發行前 | 證據 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    key_types = {"配售/認購完成", "供股結果", "終止配售"}
    detail = [
        row for row in rows
        if row.get("shares") or row.get("gross") or row.get("type") in key_types
    ]
    others = [row for row in rows if id(row) not in {id(item) for item in detail}]
    detail.sort(
        key=lambda row: (rank.get(row.get("code", "") + row.get("time", ""), 9), row.get("time", ""))
    )
    for row in detail:
        evidence = row.get("quote") or row.get("summary") or "—"
        if row.get("page"):
            evidence = f"第 {row['page']} 頁｜{evidence}"
        ratio = row.get("ratio_existing") or row.get("ratio_post")
        ratio_text = f"{ratio:,.2f}%" if ratio is not None else "—"
        lines.append(
            f"| {row.get('time', '')} | {row.get('code', '')} | {row.get('name', '')} | "
            f"{row.get('type', '')} | {_num(row.get('shares'))} | {_num(row.get('price'), ',.3f')} | "
            f"{_num(row.get('gross'))} | {_num(row.get('net'))} | {ratio_text} | {evidence[:100]} |"
        )
    lines.append("")

    lines.append("## 四、其他命中（進展/延遲/待核實）")
    lines.append("")
    if others:
        for row in sorted(others, key=lambda item: item.get("time", "")):
            note = f"（{row['warning']}）" if row.get("warning") else ""
            lines.append(
                f"- {row.get('time', '')} {row.get('code', '')} {row.get('name', '')}："
                f"{row.get('type', '')} — {row.get('title', '')[:80]}{note}"
            )
    else:
        lines.append("無。")
    lines.append("")

    lines.append("## 五、數據質量")
    lines.append("")
    failures = stats.get("text_failures") or []
    lines.append(f"- 文字抽取失敗：{len(failures)} 份" + (f"（{', '.join(failures)}）" if failures else ""))
    lines.append(f"- 事件庫寫入：{stats.get('stored', 0)} 條")
    lines.append("- 口徑：攤薄按公告披露的發行前股本比例；未接入行情前不做絕對金額排序。")
    lines.append("")
    return "\n".join(lines)
