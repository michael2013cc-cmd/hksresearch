from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Mapping

from .config import load_yaml
from .marketdata import Quote, market_cap

DEFAULT_THRESHOLDS = {
    "dilution_p0_pct": 10.0,
    "dilution_p1_pct": 5.0,
    "pipeline_p1_pct": 5.0,
    "buyback_p1_pct": 1.0,
    "cancellation_p1_pct": 2.0,
}

_ISSUANCE = {"配售/認購", "供股", "股份計劃發行", "以股代息", "單位發行", "內資股轉H股"}
_NON_DILUTIVE = {"內資股轉H股", "股份合併/資本重組"}


def attach_market(rows: list[dict], quotes: Mapping[str, Quote]) -> list[dict]:
    for row in rows:
        quote = quotes.get(str(row.get("code", "")).zfill(5))
        cap = market_cap(quote, row.get("end_shares")) if quote else None
        amount = (row.get("buyback_amounts") or {}).get("HKD")
        row["market_cap"] = cap
        row["buyback_to_cap"] = amount / cap * 100 if amount and cap else None
        row["buyback_to_turnover"] = (
            amount / quote.turnover if amount and quote is not None and quote.turnover else None
        )
    return rows


def load_thresholds(root: Path) -> dict:
    loaded = load_yaml(root / "config" / "analyzers" / "ndr.yaml")
    return {**DEFAULT_THRESHOLDS, **loaded.get("thresholds", {})}


def _pct(numerator: int | None, denominator: int | None) -> float | None:
    if not numerator or not denominator or denominator <= 0:
        return None
    return numerator / denominator * 100


def _alert(level: str, rule: str, row: dict, message: str, metric: float) -> dict:
    return {
        "level": level,
        "rule": rule,
        "time": row.get("time", ""),
        "code": row.get("code", ""),
        "name": row.get("name", ""),
        "category": row.get("category", ""),
        "message": message,
        "metric": metric,
        "evidence": row.get("issue_note") or row.get("cancel_note") or row.get("note", ""),
    }


def build_alerts(rows: list[dict], thresholds: dict | None = None) -> list[dict]:
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    alerts: list[dict] = []
    for row in rows:
        dilution = None
        if row.get("category") not in _NON_DILUTIVE:
            dilution = _pct(row.get("issued_new"), row.get("start_shares"))
            if dilution is None and row.get("category") in _ISSUANCE and row.get("pct") is not None:
                dilution = abs(row["pct"])
        if dilution is not None:
            if dilution >= limits["dilution_p0_pct"]:
                alerts.append(_alert(
                    "P0", "dilution", row,
                    f"發行 {row.get('issued_new', 0):,} 股，佔期初股本 {dilution:.1f}%",
                    dilution,
                ))
            elif dilution >= limits["dilution_p1_pct"]:
                alerts.append(_alert(
                    "P1", "dilution", row,
                    f"發行 {row.get('issued_new', 0):,} 股，佔期初股本 {dilution:.1f}%",
                    dilution,
                ))

        pipeline = _pct(row.get("pending_shares"), row.get("end_shares"))
        if pipeline is not None and pipeline >= limits["pipeline_p1_pct"]:
            alerts.append(_alert(
                "P1", "pipeline", row,
                f"待註銷 {row.get('pending_shares', 0):,} 股，佔期末股本 {pipeline:.1f}%",
                pipeline,
            ))

        buyback = _pct(row.get("buyback_shares"), row.get("end_shares"))
        if buyback is not None and buyback >= limits["buyback_p1_pct"]:
            alerts.append(_alert(
                "P1", "buyback", row,
                f"回購 {row.get('buyback_shares', 0):,} 股，佔期末股本 {buyback:.2f}%",
                buyback,
            ))

        cancellation = _pct(row.get("cancelled"), row.get("start_shares"))
        if cancellation is not None and cancellation >= limits["cancellation_p1_pct"]:
            alerts.append(_alert(
                "P1", "cancellation", row,
                f"註銷 {row.get('cancelled', 0):,} 股，佔期初股本 {cancellation:.1f}%",
                cancellation,
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


def render_brief(rows: list[dict], alerts: list[dict], stats: dict, generated_at: datetime) -> str:
    day = stats.get("date") or generated_at.strftime("%Y-%m-%d")
    p0 = [alert for alert in alerts if alert["level"] == "P0"]
    p1 = [alert for alert in alerts if alert["level"] == "P1"]

    lines = [f"# 翌日披露報表決策簡報 · {day}", ""]
    market_note = (
        "回購金額另按當日收市價推算市值與成交額歸一；未做 20 日 ADV。"
        if stats.get("market_quotes") else
        "尚未接入市值/成交額，比例只按股本計算。"
    )
    lines.append(
        f"> 共 {stats.get('total', len(rows))} 份；P0 {len(p0)} 條、P1 {len(p1)} 條。"
        + market_note
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

    lines.append("## 三、回購與發行 Top 5")
    lines.append("")
    top_buyback = sorted(
        (row for row in rows if row.get("buyback_shares")),
        key=lambda row: row["buyback_shares"], reverse=True,
    )[:5]
    top_issue = sorted(
        (row for row in rows if row.get("issued_new")),
        key=lambda row: row["issued_new"], reverse=True,
    )[:5]
    lines.append("回購股數：")
    lines.append("")
    for row in top_buyback:
        amounts = row.get("buyback_amounts") or {}
        money = " / ".join(f"{cur or '?'} {value:,.0f}" for cur, value in amounts.items()) or "—"
        impact = ""
        if row.get("buyback_to_cap") is not None:
            impact += f"，佔市值 {row['buyback_to_cap']:.2f}%"
        if row.get("buyback_to_turnover") is not None:
            impact += f"，成交額 {row['buyback_to_turnover']:.1f}x"
        lines.append(
            f"- {row['time']} {row['code']} {row['name']}："
            f"{row['buyback_shares']:,} 股（{money}{impact}）"
        )
    if not top_buyback:
        lines.append("- 無")
    lines.append("")
    lines.append("發行股數：")
    lines.append("")
    for row in top_issue:
        lines.append(
            f"- {row['time']} {row['code']} {row['name']}：+{row['issued_new']:,} 股（{row['category']}）"
        )
    if not top_issue:
        lines.append("- 無")
    lines.append("")

    lines.append("## 四、數據質量")
    lines.append("")
    failures = stats.get("text_failures") or []
    lines.append(f"- 文字抽取失敗：{len(failures)} 份" + (f"（{', '.join(failures)}）" if failures else ""))
    lines.append(f"- 事件庫寫入：{'完成' if stats.get('stored') else '未寫入'}")
    if stats.get("market_quotes"):
        lines.append(
            f"- 行情：{stats['market_quotes']:,} 隻報價，匹配 "
            f"{stats.get('market_matched', 0)}/{len(rows)} 份；市值為期末股本×收市價 proxy。"
        )
    else:
        lines.append("- 行情：未接入，回購未按市值/成交額歸一。")
    if stats.get("market_error"):
        lines.append(f"- 行情抓取失敗：{stats['market_error']}")
    lines.append("- 口徑：P0/P1 由 config/analyzers/ndr.yaml 閾值觸發；比例按公告股本計算。")
    lines.append("")
    return "\n".join(lines)
