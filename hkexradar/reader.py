from __future__ import annotations

import re
from typing import Any

from .llm import LLMClient, LLMError
from .models import Announcement, AnnouncementInsight, Fact

SYSTEM_PROMPT = (
    "你是香港上市公司公告分析員。只根據用戶提供的公告正文摘錄回答，"
    "不得引入外部資訊，不得給出投資建議。只輸出嚴格 JSON，不要輸出解釋。"
)

SURPRISE_VALUES = {"high", "medium", "low"}
DIRECTION_VALUES = {"positive", "negative", "neutral", "unclear"}


def build_prompt(ann: Announcement) -> str:
    return f"""公告標題：{ann.title}
類別：{ann.category_label}
公司：{ann.stock_name}（{ann.primary_code}）
正文摘錄：
{ann.text_head[:6000]}

請輸出 JSON，欄位如下：
- summary_zh：80 字以內的中文摘要
- facts：陣列，每項含 key / value / quote；quote 必須是正文摘錄中的原句，不得改寫
- surprise_hint：high / medium / low
- direction：positive / negative / neutral / unclear（對公司或股東利益的語義方向，不是股價預測）
- direction_reason：50 字以內
- uncertainty：50 字以內"""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def validate_facts(facts: list[dict], text: str) -> list[Fact]:
    normalized_text = _normalize(text)
    kept: list[Fact] = []
    for item in facts or []:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote", ""))
        if len(_normalize(quote)) < 4:
            continue
        if _normalize(quote) not in normalized_text:
            continue
        kept.append(
            Fact(
                key=str(item.get("key", ""))[:40],
                value=str(item.get("value", ""))[:80],
                quote=quote[:200],
            )
        )
    return kept


def _pick(value: Any, allowed: set[str], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def rule_insight(ann: Announcement) -> AnnouncementInsight:
    summary = f"{ann.doc_group}：{ann.title}"
    if ann.text_head:
        summary = f"{summary}。{ann.text_head[:120]}"
    return AnnouncementInsight(news_id=ann.news_id, summary_zh=summary[:200], source="rule")


def read(ann: Announcement, client: LLMClient | None) -> AnnouncementInsight:
    if client is None or ann.text_status != "ok":
        return rule_insight(ann)

    data: dict | None = None
    for _ in range(2):
        try:
            data = client.complete_json(SYSTEM_PROMPT, build_prompt(ann))
            break
        except LLMError:
            continue
    if data is None:
        return rule_insight(ann)

    return AnnouncementInsight(
        news_id=ann.news_id,
        summary_zh=str(data.get("summary_zh", "")).strip()[:200] or ann.title,
        facts=validate_facts(data.get("facts") or [], ann.text_head),
        surprise_hint=_pick(data.get("surprise_hint"), SURPRISE_VALUES, "medium"),
        direction=_pick(data.get("direction"), DIRECTION_VALUES, "unclear"),
        direction_reason=str(data.get("direction_reason", ""))[:80],
        uncertainty=str(data.get("uncertainty", ""))[:80],
        source="llm",
    )
