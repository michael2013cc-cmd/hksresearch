from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_SETTINGS: dict[str, Any] = {
    "llm": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "timeout_seconds": 90,
        "reasoning_effort": None,
    },
    "collector": {"rate_limit_per_sec": 2, "timeout_seconds": 60, "retries": 3},
    "pipeline": {"read_top_n": 60, "report_top_n": 20},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_settings(root: Path) -> dict[str, Any]:
    for name in ("settings.yaml", "settings.example.yaml"):
        path = root / "config" / name
        if path.exists():
            return _deep_merge(DEFAULT_SETTINGS, load_yaml(path))
    return dict(DEFAULT_SETTINGS)


def load_rules(root: Path) -> dict:
    return load_yaml(root / "config" / "routine_rules.yaml")


def load_priors(root: Path) -> dict:
    return load_yaml(root / "config" / "category_prior.yaml")


def api_key(settings: dict[str, Any]) -> str | None:
    return os.environ.get(settings["llm"]["api_key_env"]) or os.environ.get("OPENAI_API_KEY")
