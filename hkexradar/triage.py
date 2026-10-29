from __future__ import annotations

from .models import Announcement


def _keyword_hits(ann: Announcement, keywords: list[str]) -> list[str]:
    text = f"{ann.title} {ann.category_label}"
    return [keyword for keyword in keywords if keyword in text]


def should_drop(ann: Announcement, rules: dict) -> tuple[bool, str]:
    hits = _keyword_hits(ann, rules.get("force_keywords", []) or [])
    if hits:
        return False, "keyword:" + ",".join(hits)

    threshold = int(rules.get("size_override_bytes", 0) or 0)
    eligible = rules.get("size_override_groups") or []
    if (
        threshold
        and ann.doc_group in eligible
        and ann.file_bytes is not None
        and ann.file_bytes >= threshold
    ):
        return False, "size_override"

    if ann.doc_group in (rules.get("drop_groups") or []):
        return True, "group"

    tag_rules = (rules.get("drop_group_tags") or {}).get(ann.doc_group) or []
    for tag in ann.headline_tags:
        if tag in tag_rules:
            return True, "group_tag:" + tag

    return False, ""


def triage(items: list[Announcement], rules: dict) -> tuple[list[Announcement], dict[str, str]]:
    kept: list[Announcement] = []
    reasons: dict[str, str] = {}
    for item in items:
        drop, reason = should_drop(item, rules)
        if drop:
            continue
        kept.append(item)
        reasons[item.news_id] = reason or "kept"
    return kept, reasons
