from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import httpx

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, cache_dir: Path,
                 timeout: float = 90, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.client = httpx.Client(timeout=timeout, transport=transport)

    def _cache_path(self, system: str, user: str) -> Path:
        digest = hashlib.sha256(
            f"{self.model}\n{system}\n{user}".encode("utf-8")
        ).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def complete_json(self, system: str, user: str) -> dict:
        cache_path = self._cache_path(system, user)
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise LLMError(str(exc)) from exc

        content = _FENCE.sub("", content).strip()
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"invalid JSON: {content[:200]}") from exc

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
