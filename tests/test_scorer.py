from collections import Counter

from hkexradar.models import Announcement, AnnouncementInsight, Fact
from hkexradar.scorer import (
    category_prior,
    coverage_factor,
    grade_of,
    scale_factor,
    scarcity_factor,
    score,
    surprise_factor,
)

PRIORS = {
    "by_group": {"公告及通告": 0.55, "月報表": 0.05},
    "by_tag": {"內幕消息": 0.95, "私有化": 0.95},
}


def _ann(**overrides) -> Announcement:
    base = dict(
        news_id="1",
        primary_code="01234",
        stock_name="示例",
        published_at="2026-09-08T17:30:00",
        title="私有化建議",
        doc_group="公告及通告",
        headline_tags=["私有化"],
        category_label="公告及通告 - [私有化]",
        file_url="https://example.com/a.pdf",
        file_bytes=100_000,
    )
    base.update(overrides)
    return Announcement(**base)


def _insight(**overrides) -> AnnouncementInsight:
    base = dict(
        news_id="1",
        summary_zh="私有化",
        facts=[Fact(key="對價", value="12.5 億港元", quote="12.5 億港元")],
        surprise_hint="high",
    )
    base.update(overrides)
    return AnnouncementInsight(**base)


def test_category_prior_uses_max_of_group_and_tags():
    assert category_prior(_ann(), PRIORS) == 0.95
    assert category_prior(_ann(headline_tags=[]), PRIORS) == 0.55
    assert category_prior(_ann(doc_group="未知", headline_tags=[]), PRIORS) == 0.3


def test_scale_factor_buckets():
    assert scale_factor([Fact(key="a", value="500 萬港元", quote="x")]) == (0.3, True)
    assert scale_factor([Fact(key="a", value="12.5 億港元", quote="x")]) == (0.85, True)
    assert scale_factor([]) == (0.4, False)


def test_surprise_factor_mapping():
    assert surprise_factor("high") == 1.0
    assert surprise_factor("medium") == 0.6
    assert surprise_factor("low") == 0.2
    assert surprise_factor("unknown") == 0.5


def test_scarcity_is_lower_for_common_tags():
    common = Counter({("公告及通告", ("其他-雜項",)): 100})
    rare = Counter({("公告及通告", ("私有化",)): 2})
    assert scarcity_factor(_ann(headline_tags=["其他-雜項"]), common, 590) > 0
    assert scarcity_factor(_ann(headline_tags=["私有化"]), rare, 590) > scarcity_factor(
        _ann(headline_tags=["其他-雜項"]), common, 590
    )


def test_coverage_rewards_multi_counter():
    assert coverage_factor(_ann()) < coverage_factor(_ann(alt_codes=["80700"]))


def test_grade_thresholds():
    assert grade_of(80) == "S"
    assert grade_of(79.9) == "A"
    assert grade_of(65) == "A"
    assert grade_of(64.9) == "B"
    assert grade_of(50) == "B"
    assert grade_of(49.9) == "C"


def test_score_is_bounded_and_ordered():
    priors = PRIORS
    counts = Counter({("公告及通告", ("私有化",)): 2})
    high = score(_ann(), _insight(), priors, counts, 590)
    low = score(
        _ann(doc_group="月報表", headline_tags=[], title="月報表"),
        _insight(surprise_hint="low", facts=[]),
        priors,
        counts,
        590,
    )
    assert 0 <= low.final_score < high.final_score <= 100
    assert high.grade in {"S", "A"}
