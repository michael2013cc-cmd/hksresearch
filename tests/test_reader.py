from hkexradar.llm import LLMError
from hkexradar.models import Announcement
from hkexradar.reader import build_prompt, read, rule_insight, validate_facts


def _ann(**overrides) -> Announcement:
    base = dict(
        news_id="1",
        primary_code="01234",
        stock_name="示例控股",
        published_at="2026-09-08T17:30:00",
        title="私有化建議",
        doc_group="公告及通告",
        headline_tags=["私有化"],
        category_label="公告及通告 - [私有化]",
        file_url="https://example.com/a.pdf",
        text_head="要約人擬以每股現金12.5港元私有化本公司，較最後交易日收市價溢價約32%。",
        text_status="ok",
    )
    base.update(overrides)
    return Announcement(**base)


class FakeClient:
    def __init__(self, payload, fail_times: int = 0):
        self.payload = payload
        self.fail_times = fail_times
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise LLMError("boom")
        return self.payload


def test_build_prompt_contains_title_and_text():
    prompt = build_prompt(_ann())
    assert "私有化建議" in prompt
    assert "12.5港元" in prompt
    assert "quote" in prompt


def test_validate_facts_drops_unverifiable_quotes():
    facts = [
        {"key": "對價", "value": "12.5 港元/股", "quote": "每股現金12.5港元"},
        {"key": "假數字", "value": "99%", "quote": "這句話不在原文裡"},
        {"key": "太短", "value": "x", "quote": "溢價"},
    ]
    kept = validate_facts(facts, _ann().text_head)
    assert [f.key for f in kept] == ["對價"]


def test_read_uses_llm_result_and_validates_facts():
    client = FakeClient(
        {
            "summary_zh": "溢價 32% 私有化。",
            "facts": [{"key": "對價", "value": "12.5 港元/股", "quote": "每股現金12.5港元"}],
            "surprise_hint": "high",
            "direction": "positive",
            "direction_reason": "溢價交易",
            "uncertainty": "需股東批准",
        }
    )
    insight = read(_ann(), client)
    assert insight.source == "llm"
    assert insight.surprise_hint == "high"
    assert insight.direction == "positive"
    assert len(insight.facts) == 1


def test_read_retries_once_then_succeeds():
    client = FakeClient({"summary_zh": "ok", "facts": []}, fail_times=1)
    insight = read(_ann(), client)
    assert insight.source == "llm"
    assert client.calls == 2


def test_read_falls_back_after_two_failures():
    client = FakeClient({}, fail_times=5)
    insight = read(_ann(), client)
    assert insight.source == "rule"
    assert client.calls == 2


def test_read_without_text_skips_llm():
    client = FakeClient({})
    insight = read(_ann(text_status="skipped", text_head=""), client)
    assert insight.source == "rule"
    assert client.calls == 0


def test_invalid_enum_values_are_normalized():
    client = FakeClient({"summary_zh": "ok", "surprise_hint": "extreme", "direction": "up"})
    insight = read(_ann(), client)
    assert insight.surprise_hint == "medium"
    assert insight.direction == "unclear"


def test_rule_insight_uses_title_when_no_text():
    insight = rule_insight(_ann(text_status="unavailable", text_head=""))
    assert insight.source == "rule"
    assert "私有化建議" in insight.summary_zh
