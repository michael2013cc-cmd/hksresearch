from pathlib import Path

from hkexradar.collector import load_snapshot, parse_payload
from hkexradar.config import load_priors, load_rules
from hkexradar.models import Announcement
from hkexradar.normalizer import normalize_all
from hkexradar.triage import should_drop, triage

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "2026-09-08.json"


def _ann(**overrides) -> Announcement:
    base = dict(
        news_id="1",
        primary_code="00001",
        stock_name="測試",
        published_at="2026-09-08T17:00:00",
        title="公告",
        doc_group="公告及通告",
        headline_tags=[],
        category_label="公告及通告",
        file_url="https://example.com/a.pdf",
        file_bytes=100 * 1024,
    )
    base.update(overrides)
    return Announcement(**base)


def test_routine_groups_are_dropped():
    rules = {"drop_groups": ["月報表"]}
    assert should_drop(_ann(doc_group="月報表"), rules) == (True, "group")


def test_drop_group_tags_are_respected():
    rules = {"drop_group_tags": {"公告及通告": ["董事名單和他們的地位和作用"]}}
    assert should_drop(_ann(headline_tags=["董事名單和他們的地位和作用"]), rules)[0] is True
    assert should_drop(_ann(headline_tags=["內幕消息"]), rules)[0] is False


def test_keyword_override_beats_drop():
    rules = {"drop_groups": ["月報表"], "force_keywords": ["復牌"]}
    assert should_drop(_ann(doc_group="月報表", title="復牌公告"), rules) == (False, "keyword:復牌")


def test_size_override_keeps_large_document_in_eligible_group():
    rules = {
        "drop_group_tags": {"公告及通告": ["董事名單和他們的地位和作用"]},
        "size_override_bytes": 1024 * 1024,
        "size_override_groups": ["公告及通告"],
    }
    ann = _ann(headline_tags=["董事名單和他們的地位和作用"], file_bytes=2 * 1024 * 1024)
    assert should_drop(ann, rules) == (False, "size_override")


def test_size_override_does_not_rescue_routine_group():
    rules = {
        "drop_groups": ["月報表"],
        "size_override_bytes": 1024 * 1024,
        "size_override_groups": ["公告及通告"],
    }
    assert should_drop(_ann(doc_group="月報表", file_bytes=5 * 1024 * 1024), rules) == (True, "group")


def test_full_day_candidate_pool_is_in_expected_range():
    rules = load_rules(ROOT)
    rows = parse_payload(load_snapshot(FIXTURE))
    announcements = normalize_all(rows)
    kept, reasons = triage(announcements, rules)
    assert 80 <= len(kept) <= 150, f"candidate pool={len(kept)}"
    assert len(reasons) == len(kept)
    assert any("內幕消息" in a.headline_tags for a in kept)
    assert not any(a.doc_group == "月報表" for a in kept)


def test_priors_exist_for_kept_groups():
    priors = load_priors(ROOT)
    rows = parse_payload(load_snapshot(FIXTURE))
    kept, _ = triage(normalize_all(rows), load_rules(ROOT))
    by_group = priors["by_group"]
    assert all(a.doc_group in by_group for a in kept)
