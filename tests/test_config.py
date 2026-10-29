from pathlib import Path

from hkexradar.config import DEFAULT_SETTINGS, api_key, load_priors, load_rules, load_settings


def test_defaults_without_files(tmp_path: Path):
    s = load_settings(tmp_path)
    assert s["pipeline"]["read_top_n"] == 60
    assert s["llm"]["model"] == "deepseek-chat"


def test_settings_override_merges(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(
        "llm:\n  model: gpt-4o\ncollector:\n  rate_limit_per_sec: 1\n", encoding="utf-8"
    )
    s = load_settings(tmp_path)
    assert s["llm"]["model"] == "gpt-4o"
    assert s["llm"]["base_url"] == DEFAULT_SETTINGS["llm"]["base_url"]
    assert s["collector"]["rate_limit_per_sec"] == 1
    assert s["collector"]["retries"] == 3


def test_api_key_from_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    assert api_key(load_settings(tmp_path)) == "sk-test"


def test_rules_and_priors_load(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "routine_rules.yaml").write_text(
        "drop_groups:\n  - 月報表\nforce_keywords:\n  - 復牌\n", encoding="utf-8"
    )
    (tmp_path / "config" / "category_prior.yaml").write_text(
        "by_group:\n  公告及通告: 0.55\n", encoding="utf-8"
    )
    assert "月報表" in load_rules(tmp_path)["drop_groups"]
    assert load_priors(tmp_path)["by_group"]["公告及通告"] == 0.55
