from __future__ import annotations

import html
import re

from .collector import FILE_HOST
from .models import Announcement, AnnouncementRaw

_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_REVISION = re.compile(r"[（(]\s*經修訂\s*[）)]|[（(]\s*Revised\s*[）)]", re.IGNORECASE)
_SIZE = re.compile(r"^\s*([\d.]+)\s*(B|KB|MB)\s*$", re.IGNORECASE)
_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024 * 1024}


def _parts(value: str) -> list[str]:
    return [part.strip() for part in _BR.split(html.unescape(value or "")) if part.strip()]


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def split_codes(value: str) -> tuple[str, list[str]]:
    parts = _parts(value)
    if not parts:
        return "", []
    return parts[0], parts[1:]


def parse_category(label: str) -> tuple[str, list[str]]:
    text = html.unescape(label or "").strip()
    if " - [" not in text:
        return text, []
    group, rest = text.split(" - [", 1)
    if not rest.endswith("]"):
        return group.strip(), []
    tags = [tag.strip() for tag in rest[:-1].split("/") if tag.strip()]
    return group.strip(), tags


def parse_size(info: str) -> int | None:
    match = _SIZE.match(info or "")
    if not match:
        return None
    return int(float(match.group(1)) * _SIZE_UNITS[match.group(2).upper()])


def normalize_row(raw: AnnouncementRaw) -> Announcement:
    code, alt_codes = split_codes(raw.stock_code)
    group, tags = parse_category(raw.category_label)
    names = _parts(raw.stock_name)
    return Announcement(
        news_id=raw.news_id,
        primary_code=code,
        alt_codes=alt_codes,
        stock_name=names[0] if names else raw.stock_name,
        published_at=raw.published_at,
        title=_clean_text(raw.title),
        doc_group=group,
        headline_tags=tags,
        category_label=_clean_text(raw.category_label),
        file_url=FILE_HOST + raw.file_link,
        file_bytes=parse_size(raw.file_info),
        is_revision=bool(_REVISION.search(raw.title)),
    )


def base_title(title: str) -> str:
    return _REVISION.sub("", title).strip()


def merge_duplicates(items: list[Announcement]) -> list[Announcement]:
    seen: dict[str, Announcement] = {}
    result: list[Announcement] = []
    for item in items:
        keeper = seen.get(item.file_url)
        if keeper is None:
            seen[item.file_url] = item
            result.append(item)
            continue
        if item.primary_code not in [keeper.primary_code, *keeper.alt_codes]:
            keeper.alt_codes.append(item.primary_code)
        for code in item.alt_codes:
            if code not in keeper.alt_codes:
                keeper.alt_codes.append(code)
    return result


def link_revisions(items: list[Announcement]) -> list[Announcement]:
    originals: dict[tuple[str, str], Announcement] = {}
    for item in sorted(items, key=lambda a: a.published_at):
        if item.is_revision:
            original = originals.get((item.primary_code, base_title(item.title)))
            if original is not None:
                item.revision_of = original.news_id
            continue
        originals[(item.primary_code, item.title)] = item
    return items


def normalize_all(raws: list[AnnouncementRaw]) -> list[Announcement]:
    items = merge_duplicates([normalize_row(raw) for raw in raws])
    link_revisions(items)
    return sorted(items, key=lambda a: a.published_at)
