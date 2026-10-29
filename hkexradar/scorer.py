from __future__ import annotations

import math
import re

from .models import (
    Announcement,
    AnnouncementInsight,
    Fact,
    Grade,
    ScoreBreakdown,
    ScoredAnnouncement,
)

_UNITS = {"億": 1e8, "亿": 1e8, "百萬": 1e6, "百万": 1e6, "萬": 1e4, "万": 1e4, "千": 1e3}
_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(億|亿|百萬|百万|萬|万|千)?\s*(港元|港幣|人民幣|人民幣|美元|元)?")
_SURPRISE = {"high": 1.0, "medium": 0.6, "low": 0.2}


def category_prior(ann: Announcement, priors: dict) -> float:
    group_prior = float((priors.get("by_group") or {}).get(ann.doc_group, 0.3))
    tag_map = priors.get("by_tag") or {}
    tag_prior = max([float(tag_map.get(tag, 0.0)) for tag in ann.headline_tags] + [0.0])
    return max(group_prior, tag_prior)


def scale_factor(facts: list[Fact]) -> tuple[float, bool]:
    best = 0.0
    for fact in facts or []:
        for match in _AMOUNT.finditer(fact.value):
            if not match.group(2) and not match.group(3):
                continue
            multiplier = _UNITS.get(match.group(2) or "", 1.0)
            best = max(best, float(match.group(1).replace(",", "")) * multiplier)
    if best <= 0:
        return 0.4, False
    for cut, value in ((1e10, 1.0), (1e9, 0.85), (1e8, 0.7), (1e7, 0.5), (1e6, 0.3)):
        if best >= cut:
            return value, True
    return 0.15, True


def surprise_factor(hint: str) -> float:
    return _SURPRISE.get(hint, 0.5)


def scarcity_factor(ann: Announcement, day_counts: dict, total: int) -> float:
    key = (ann.doc_group, tuple(sorted(ann.headline_tags)))
    count = day_counts.get(key, 0)
    if total <= 1:
        return 0.5
    return max(0.0, 1.0 - min(1.0, math.log10(1 + count) / math.log10(1 + total)))


def coverage_factor(ann: Announcement) -> float:
    subjects = 1 + len(ann.alt_codes)
    return 0.5 * min(1.0, subjects / 5) + 0.5 * (1.0 if ann.alt_codes else 0.3)


def spread_factor(ann: Announcement, insight: AnnouncementInsight | None) -> float:
    facts = insight.facts if insight else []
    text = ann.title + " " + " ".join(f"{fact.key} {fact.value}" for fact in facts)
    density = min(1.0, len(re.findall(r"\d+(?:\.\d+)?%?", text)) / 4)
    has_amount = any(re.search(r"億|亿|萬|万|港元|元|%", fact.value) for fact in facts)
    return 0.5 * density + 0.5 * (1.0 if has_amount else 0.4)


def grade_of(final_score: float) -> Grade:
    if final_score >= 80:
        return "S"
    if final_score >= 65:
        return "A"
    if final_score >= 50:
        return "B"
    return "C"


def score(ann: Announcement, insight: AnnouncementInsight | None, priors: dict,
          day_counts: dict, total: int, triage_reason: str = "") -> ScoredAnnouncement:
    prior = category_prior(ann, priors)
    scale, scale_known = scale_factor(insight.facts if insight else [])
    surprise = surprise_factor(insight.surprise_hint if insight else "medium")
    scarcity = scarcity_factor(ann, day_counts, total)
    coverage = coverage_factor(ann)
    spread = spread_factor(ann, insight)

    magnitude = 40 * prior + 20 * scale + 40 * surprise
    interest = 50 * scarcity + 30 * coverage + 20 * spread
    final_score = 0.6 * magnitude + 0.4 * interest
    flags = [] if scale_known else ["scale_unknown"]
    if ann.is_revision:
        flags.append("revision")

    return ScoredAnnouncement(
        announcement=ann,
        insight=insight,
        magnitude=round(magnitude, 2),
        interest=round(interest, 2),
        final_score=round(final_score, 2),
        grade=grade_of(final_score),
        breakdown=ScoreBreakdown(
            category_prior=round(prior, 3),
            scale=round(scale, 3),
            surprise=round(surprise, 3),
            scarcity=round(scarcity, 3),
            coverage=round(coverage, 3),
            spread=round(spread, 3),
        ),
        triage_reason=triage_reason,
        flags=flags,
    )
