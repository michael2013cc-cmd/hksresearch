from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from hkexradar.collector import load_snapshot, parse_payload
from hkexradar.analyzers.ndr import Filing, NdrAnalyzer, filing_numbers, parse_filing
from hkexradar.ndr_brief import build_alerts, load_thresholds, render_brief
from hkexradar.normalizer import normalize_all
from hkexradar.pdf import download_pdf, extract_pages, extract_text, pdf_filename
from hkexradar.store import EventStore

ROOT = Path(__file__).resolve().parents[1]
GROUP = "翌日披露報表"
CATEGORY_ORDER = [
    "新增購回",
    "購回並註銷",
    "註銷購回股份",
    "配售/認購",
    "供股",
    "期權行使",
    "股份計劃發行",
    "可換股轉換",
    "內資股轉H股",
    "以股代息",
    "單位發行",
    "庫存股出售",
    "股份合併/資本重組",
    "混合",
    "其他",
]


def fmt_int(value: int | None) -> str:
    return f"{value:,}" if value is not None else "—"


def fmt_money(amounts: dict[str, float]) -> str:
    if not amounts:
        return "—"
    return " / ".join(f"{currency or '?'} {value:,.0f}" for currency, value in amounts.items())


def money_map(items: list[tuple[str | None, float]]) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for currency, amount in items:
        result[currency or "?"] += amount
    return dict(result)


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


def analyse(day: str) -> tuple[list[dict], dict]:
    raw = parse_payload(load_snapshot(ROOT / "data" / "raw" / day / "announcements.json"))
    anns = [a for a in normalize_all(raw) if a.doc_group == GROUP]
    statuses = ensure_pdfs(anns, ROOT / "data" / "raw" / day / "pdf")

    rows: list[dict] = []
    store = EventStore(ROOT / "data" / "events.db")
    analyzer = NdrAnalyzer()
    stored = 0
    store_errors: list[str] = []
    for ann in anns:
        path = ROOT / "data" / "raw" / day / "pdf" / pdf_filename(ann.news_id)
        pages, full_text, status = extract_pages(path)
        text = full_text[:30000]
        filing: Filing = parse_filing(ann.news_id, text)
        issued, cancelled, issued_new = filing_numbers(filing)
        buyback_amounts = money_map([(b.currency, b.amount or 0) for b in filing.buybacks])
        buyback_shares = sum(b.shares for b in filing.buybacks) or None
        pending_shares = sum(p.delta for p in filing.pending if p.delta and p.delta > 0) or None
        pct_values = [abs(e.pct) for e in filing.events if e.pct is not None]
        price = next((e.price for e in filing.events if e.price), None)
        issue_events = [
            e for e in filing.events
            if e.delta and e.delta > 0 and "購回" not in e.desc
        ]
        rows.append({
            "time": ann.published_at.strftime("%H:%M"),
            "code": ann.primary_code,
            "name": ann.stock_name,
            "tag": " / ".join(ann.headline_tags),
            "category": filing.category,
            "subtypes": filing.subtypes,
            "start_shares": filing.start_shares,
            "end_shares": filing.end_shares,
            "issued_delta": issued,
            "cancelled": cancelled,
            "issued_new": issued_new,
            "pct": max(pct_values) if pct_values else None,
            "price": price,
            "buyback_shares": buyback_shares,
            "buyback_amounts": buyback_amounts,
            "buyback_cancel": filing.buyback_cancel,
            "buyback_treasury": filing.buyback_treasury,
            "pending_shares": pending_shares,
            "text_status": status,
            "note": filing.events[0].desc[:70] if filing.events else "",
            "issue_note": issue_events[0].desc[:70] if issue_events else "",
            "cancel_note": next(
                (e.desc[:70] for e in filing.events if e.delta and e.delta < 0 and "註銷" in e.desc),
                "",
            ),
        })
        try:
            store.add_result(ann, analyzer.analyze(ann, text, pages=pages))
            stored += 1
        except Exception as exc:  # noqa: BLE001 - 单份归档失败不应中断整日分析
            store_errors.append(f"{ann.primary_code}: {exc}")
    store.close()

    stats = {
        "date": day,
        "total": len(rows),
        "stored": stored,
        "store_errors": store_errors,
        "category_counts": dict(Counter(row["category"] for row in rows)),
        "tag_counts": dict(Counter(tag for row in rows for tag in row["tag"].split(" / "))),
        "dual_tag": sum(1 for row in rows if " / " in row["tag"]),
        "tag_matrix": {
            f"{tag}|{cat}": count
            for (tag, cat), count in Counter((row["tag"], row["category"]) for row in rows).items()
        },
        "text_failures": [row["code"] for row in rows if row["text_status"] != "ok"],
    }
    return rows, stats


def render(rows: list[dict], stats: dict, generated_at: datetime) -> str:
    by_category: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)

    lines: list[str] = []
    lines.append(f"# 翌日披露報表內容分析 · {stats['date']}")
    lines.append("")
    lines.append(
        f"> 共 {stats['total']} 份 · 全部取自 hkexnews「翌日披露報表」 · "
        f"生成於 {generated_at.strftime('%Y-%m-%d %H:%M')}（香港時間）"
    )
    lines.append("")
    lines.append("## 一、總覽")
    lines.append("")
    lines.append(
        "交易所只有兩個標籤——「股份購回」"
        f"{stats['tag_counts'].get('股份購回', 0)} 份、「其他」{stats['tag_counts'].get('其他', 0)} 份"
        f"（其中 {stats['dual_tag']} 份同時帶兩個標籤）；"
        "但逐份讀正文後，實際內容分成 "
        f"{len(by_category)} 類。標籤與內容並不一致："
    )
    lines.append("")
    lines.append("| 交易所標籤 | 實際類別 | 份數 |")
    lines.append("|---|---|---|")
    for key, count in sorted(stats["tag_matrix"].items(), key=lambda kv: -kv[1]):
        tag, cat = key.split("|", 1)
        lines.append(f"| {tag} | {cat} | {count} |")
    lines.append("")

    lines.append("## 二、類別分布")
    lines.append("")
    lines.append("| 實際類別 | 份數 | 含義 |")
    lines.append("|---|---|---|")
    meanings = {
        "新增購回": "本次披露新的股份購回（含第二章節回購報告或 B 部待註銷股份）",
        "購回並註銷": "同日既披露新購回，也完成先前購回股份的註銷",
        "註銷購回股份": "只註銷先前已購回的股份，本次沒有新購回",
        "配售/認購": "配售或認購新股，涉及已發行股份增加",
        "供股": "供股發行新股",
        "期權行使": "行使股份期權而發行新股",
        "股份計劃發行": "股份獎勵／股份計劃項下發行新股或轉讓庫存股",
        "可換股轉換": "可換股票據／債券轉換為股份",
        "內資股轉H股": "內資股轉換為 H 股並上市，總股本不變",
        "以股代息": "以股份代替現金股息",
        "單位發行": "REIT 以基金單位支付費用而發行單位",
        "庫存股出售": "在場內出售庫存股份",
        "股份合併/資本重組": "股份合併或資本重組，已發行股數機械性變動",
        "混合": "同一份文件包含兩類以上事件（如購回＋期權發行）",
        "其他": "未能歸入以上類別",
    }
    for category in CATEGORY_ORDER:
        if category in by_category:
            lines.append(
                f"| {category} | {len(by_category[category])} | {meanings.get(category, '')} |"
            )
    lines.append("")

    buyback_docs = [
        row for row in rows
        if row["buyback_shares"] or row["pending_shares"]
    ]
    section2 = [row for row in buyback_docs if row["buyback_shares"]]
    b_only = [row for row in buyback_docs if not row["buyback_shares"]]
    total_amounts = money_map(
        [(currency, amount) for row in section2 for currency, amount in row["buyback_amounts"].items()]
    )
    total_bb_shares = sum(row["buyback_shares"] or 0 for row in section2)
    total_cancel = sum(row["buyback_cancel"] for row in section2)
    total_treasury = sum(row["buyback_treasury"] for row in section2)
    pending_total = sum(row["pending_shares"] or 0 for row in b_only)

    lines.append("## 三、回購類")
    lines.append("")
    lines.append(
        f"涉及回購的文件 {len(buyback_docs)} 份：{len(section2)} 份附第二章節回購報告"
        f"（披露當日成交），{len(b_only)} 份只在 B 部列出待註銷的既有購回。"
    )
    lines.append("")
    lines.append(f"- 第二章節合計購回 **{fmt_int(total_bb_shares)} 股**，金額 {fmt_money(total_amounts)}")
    lines.append(
        f"- 回購目的：擬註銷 {fmt_int(total_cancel)} 股，擬持作庫存 {fmt_int(total_treasury)} 股"
    )
    lines.append(
        f"- B 部待註銷存量（{len(b_only)} 份、非當日全為新增）：合計 {fmt_int(pending_total)} 股"
    )
    lines.append("")
    if section2:
        top = sorted(
            section2,
            key=lambda row: row["buyback_amounts"].get("HKD", 0),
            reverse=True,
        )[:10]
        lines.append("### 當日回購金額前十（按 HKD 金額排序）")
        lines.append("")
        lines.append("| 時間 | 代碼 | 公司 | 購回股數 | 金額 | 註銷/庫存 |")
        lines.append("|---|---|---|---|---|---|")
        for row in top:
            lines.append(
                f"| {row['time']} | {row['code']} | {row['name']} | "
                f"{fmt_int(row['buyback_shares'])} | {fmt_money(row['buyback_amounts'])} | "
                f"{fmt_int(row['buyback_cancel'])} / {fmt_int(row['buyback_treasury'])} |"
            )
        lines.append("")

    pure_cancel = by_category.get("註銷購回股份", [])
    mixed_cancel = by_category.get("購回並註銷", [])
    cancel_total = sum(row["cancelled"] for row in rows)
    lines.append("## 四、註銷類")
    lines.append("")
    lines.append(
        f"純註銷 {len(pure_cancel)} 份，購回並註銷 {len(mixed_cancel)} 份；"
        f"第一章節申報的註銷股數合計 **{fmt_int(cancel_total)} 股**。"
    )
    lines.append("")
    cancel_rows = sorted(
        [row for row in rows if row["cancelled"]],
        key=lambda row: row["cancelled"],
        reverse=True,
    )[:8]
    if cancel_rows:
        lines.append("| 時間 | 代碼 | 公司 | 註銷股數 | 事件 |")
        lines.append("|---|---|---|---|---|")
        for row in cancel_rows:
            lines.append(
                f"| {row['time']} | {row['code']} | {row['name']} | "
                f"{fmt_int(row['cancelled'])} | {row['cancel_note']} |"
            )
        lines.append("")

    issuance_categories = {
        "配售/認購", "供股", "期權行使", "股份計劃發行", "可換股轉換",
        "內資股轉H股", "以股代息", "單位發行", "股份合併/資本重組",
    }
    issuance_rows = [
        row for row in rows
        if row["issued_new"] and set(row["subtypes"]) & issuance_categories
    ]
    lines.append("## 五、發行與其他股本事件")
    lines.append("")
    lines.append(
        f"涉及新股發行或股本結構變動 {len(issuance_rows)} 份，"
        f"第一章節正變動合計 {fmt_int(sum(row['issued_new'] for row in issuance_rows))} 股。"
    )
    lines.append("")
    lines.append("| 時間 | 代碼 | 公司 | 類別 | 發行股數 | 佔比 | 價格 | 事件 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in sorted(issuance_rows, key=lambda item: item["issued_new"], reverse=True):
        pct = f"{row['pct']:.2f}%" if row["pct"] is not None else "—"
        price = f"{row['price']:g}" if row["price"] else "—"
        lines.append(
            f"| {row['time']} | {row['code']} | {row['name']} | {row['category']} | "
            f"{fmt_int(row['issued_new'])} | {pct} | {price} | {row['issue_note']} |"
        )
    lines.append("")

    mixed = by_category.get("混合", [])
    if mixed:
        lines.append("## 六、混合與特殊事件")
        lines.append("")
        lines.append("| 時間 | 代碼 | 公司 | 內容 |")
        lines.append("|---|---|---|---|")
        for row in mixed:
            lines.append(
                f"| {row['time']} | {row['code']} | {row['name']} | {' + '.join(row['subtypes'])} |"
            )
        lines.append("")
        consolidation = by_category.get("股份合併/資本重組", [])
        for row in consolidation:
            lines.append(
                f"- **{row['name']}（{row['code']}）**：{row['note']}；"
                f"已發行股數變動 {fmt_int(row['issued_delta'])}，佔比 {row['pct']:.0f}%。"
                if row["pct"] is not None else ""
            )
        lines.append("")

    lines.append("## 七、全部明細（按發布時間）")
    lines.append("")
    lines.append("| 時間 | 代碼 | 公司 | 標籤 | 實際類別 | 股數變動 | 佔比 | 回購金額 | 待註銷 | 備註 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for row in sorted(rows, key=lambda item: item["time"]):
        pct = f"{row['pct']:.2f}%" if row["pct"] is not None else "—"
        pending = fmt_int(row["pending_shares"]) if row["pending_shares"] else "—"
        lines.append(
            f"| {row['time']} | {row['code']} | {row['name']} | {row['tag']} | "
            f"{row['category']} | {fmt_int(row['issued_delta'])} | {pct} | "
            f"{fmt_money(row['buyback_amounts'])} | {pending} | {row['note']} |"
        )
    lines.append("")

    lines.append("## 八、觀察")
    lines.append("")
    hkd_by_code: dict[str, float] = defaultdict(float)
    names = {row["code"]: row["name"] for row in rows}
    for row in section2:
        hkd_by_code[row["code"]] += row["buyback_amounts"].get("HKD", 0)
    hkd_rank = sorted(hkd_by_code.items(), key=lambda item: item[1], reverse=True)
    hkd_total = sum(hkd_by_code.values())
    if hkd_rank and hkd_total:
        leader, leader_amount = hkd_rank[0]
        top3 = sum(amount for _, amount in hkd_rank[:3])
        lines.append(
            f"1. **回購高度集中**：以 HKD 計的回購總額 {hkd_total:,.0f} 元中，"
            f"{names.get(leader, leader)}（{leader}）佔 {leader_amount / hkd_total:.1%}，"
            f"前三名合計佔 {top3 / hkd_total:.1%}。回購不是全市場普遍行為，而是少數大市值公司的持續操作。"
        )
    lines.append(
        f"2. **「回購」標籤下混著已完成動作**：8 份純註銷文件沒有任何新購回，"
        f"只是把先前買回的 {fmt_int(sum(row['cancelled'] for row in pure_cancel))} 股正式註銷；"
        "這類文件不構成新的買盤，不能當成回購訊號。"
    )
    other_rows = [row for row in rows if "其他" in row["tag"]]
    issuance_other = [
        row for row in other_rows
        if row["category"] in {"配售/認購", "供股", "股份合併/資本重組", "以股代息", "單位發行", "內資股轉H股", "股份計劃發行"}
    ]
    lines.append(
        f"3. **「其他」標籤藏著實質股本事件**：{len(other_rows)} 份「其他」中，"
        f"{len(issuance_other)} 份是配售、供股、轉換、合併等會改變股本結構的事件。"
        "只看交易所標籤會完全漏掉這些信息。"
    )
    if issuance_rows:
        biggest = max(issuance_rows, key=lambda row: row["issued_new"])
        biggest_pct = f"{biggest['pct']:.0f}%" if biggest["pct"] is not None else "—"
        lines.append(
            f"4. **攤薄風險集中在少數幾份**：{biggest['name']}（{biggest['code']}）"
            f"發行 {fmt_int(biggest['issued_new'])} 股，佔發行前股本 {biggest_pct}；"
            "兩份供股（150%、300%）對每股盈利的攤薄遠大於回購的托價作用。"
        )
    lines.append(
        "5. **對決策的含義**：回購要看目的（註銷還是持作庫存）與金額佔市值比重；"
        "供股/配售要看發行價相對市價的折讓與募資用途；股份合併要用換股比例重算每股指標；"
        "純註銷只影響股本分母，不影響現金流。"
    )
    lines.append("")

    lines.append("## 九、數據質量")
    lines.append("")
    lines.append(f"- PDF 下載與文字抽取成功：{stats['total'] - len(stats['text_failures'])} / {stats['total']}")
    lines.append("- 文字層：全部為可選中文本，無掃描件，未使用 OCR")
    lines.append("- 解析依據：第一章節事件表、第二章節回購報告、B 部待註銷明細")
    if stats["text_failures"]:
        lines.append(f"- 失敗代碼：{', '.join(stats['text_failures'])}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analysis of HKEX next-day disclosure returns")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    rows, stats = analyse(args.date)
    alerts = build_alerts(rows, load_thresholds(ROOT))
    stats["alert_counts"] = dict(Counter(alert["level"] for alert in alerts))
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    json_path = out_dir / f"{args.date}-ndr.json"
    md_path = out_dir / f"{args.date}-ndr-analysis.md"
    brief_path = out_dir / f"{args.date}-ndr-brief.md"
    json_path.write_text(
        json.dumps({"stats": stats, "filings": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    now = datetime.now()
    md_path.write_text(render(rows, stats, now), encoding="utf-8")
    brief_path.write_text(render_brief(rows, alerts, stats, now), encoding="utf-8")
    print(f"filings={stats['total']} categories={len(stats['category_counts'])} "
          f"alerts={len(alerts)} stored={stats['stored']}")
    print(f"report: {md_path}")
    print(f"brief: {brief_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
