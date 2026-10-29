import json
from pathlib import Path

import httpx

from hkexradar.llm import LLMClient, LLMError


def _client(tmp_path: Path, handler, model: str = "test-model") -> LLMClient:
    return LLMClient(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model=model,
        cache_dir=tmp_path / "cache",
        transport=httpx.MockTransport(handler),
    )


def test_complete_json_parses_response(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-test"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"summary_zh": "ok"}'}}]},
        )

    client = _client(tmp_path, handler)
    assert client.complete_json("sys", "user") == {"summary_zh": "ok"}


def test_second_call_hits_cache(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    client = _client(tmp_path, handler)
    client.complete_json("sys", "user")
    client.complete_json("sys", "user")
    assert calls["n"] == 1


def test_different_prompt_does_not_hit_cache(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    client = _client(tmp_path, handler)
    client.complete_json("sys", "user-1")
    client.complete_json("sys", "user-2")
    assert calls["n"] == 2


def test_code_fence_is_stripped(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '```json\n{"a": 2}\n```'}}]}
        )

    client = _client(tmp_path, handler)
    assert client.complete_json("sys", "user") == {"a": 2}


def test_reasoning_effort_is_sent_when_configured(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["reasoning_effort"] == "low"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    client = LLMClient(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="test-model",
        cache_dir=tmp_path / "cache",
        transport=httpx.MockTransport(handler),
        reasoning_effort="low",
    )
    assert client.complete_json("sys", "user") == {"a": 1}


def test_reasoning_effort_omitted_by_default(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "reasoning_effort" not in body
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    client = _client(tmp_path, handler)
    assert client.complete_json("sys", "user") == {"a": 1}


def test_http_error_raises_llm_error(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = _client(tmp_path, handler)
    try:
        client.complete_json("sys", "user")
    except LLMError as exc:
        assert "500" in str(exc) or "boom" in str(exc)
    else:
        raise AssertionError("expected LLMError")


def test_invalid_json_raises_llm_error(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    client = _client(tmp_path, handler)
    try:
        client.complete_json("sys", "user")
    except LLMError:
        pass
    else:
        raise AssertionError("expected LLMError")
