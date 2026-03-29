from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from researchclaw.config import KnowledgeBaseConfig
from researchclaw.knowledge.base import KBEntry, write_kb_entry
from researchclaw.knowledge.obsidian_rest import (
    ObsidianRestSettings,
    obsidian_rest_settings_from_config,
    put_vault_markdown,
    vault_put_url,
)


def test_vault_put_url_encodes_segments() -> None:
    u = vault_put_url("https://127.0.0.1:27124", "ResearchClaw/kb/questions/q-1.md")
    assert u == "https://127.0.0.1:27124/vault/ResearchClaw/kb/questions/q-1.md"


def test_vault_put_url_encodes_spaces() -> None:
    u = vault_put_url("https://127.0.0.1:27124", "My Notes/q 1.md")
    assert "My%20Notes" in u
    assert "q%201.md" in u


def test_obsidian_rest_settings_from_config_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBS_TEST_KEY", "secret-token")
    kb = KnowledgeBaseConfig(
        backend="obsidian_rest",
        root="KB",
        obsidian_rest_base_url="https://127.0.0.1:27124",
        obsidian_rest_api_key_env="OBS_TEST_KEY",
        obsidian_rest_verify_ssl=False,
    )
    s = obsidian_rest_settings_from_config(kb)
    assert s is not None
    assert s.base_url == "https://127.0.0.1:27124"
    assert s.api_key == "secret-token"
    assert s.verify_ssl is False


def test_obsidian_rest_settings_from_config_wrong_backend() -> None:
    kb = KnowledgeBaseConfig(backend="markdown", root="docs/kb")
    assert obsidian_rest_settings_from_config(kb) is None


def test_obsidian_rest_settings_from_config_missing_env_raises() -> None:
    kb = KnowledgeBaseConfig(
        backend="obsidian_rest",
        root="KB",
        obsidian_rest_base_url="https://127.0.0.1:27124",
        obsidian_rest_api_key_env="OBS_MISSING_XYZ",
    )
    if "OBS_MISSING_XYZ" in os.environ:
        del os.environ["OBS_MISSING_XYZ"]
    with pytest.raises(ValueError, match="empty or unset"):
        obsidian_rest_settings_from_config(kb)


@patch("researchclaw.knowledge.obsidian_rest.httpx.Client")
def test_put_vault_markdown_uses_bearer(mock_client_cls: object) -> None:
    mock_inst = mock_client_cls.return_value.__enter__.return_value
    mock_inst.put.return_value.status_code = 204

    s = ObsidianRestSettings(
        base_url="https://127.0.0.1:27124",
        api_key="tok",
        verify_ssl=False,
    )
    put_vault_markdown(s, "kb/q.md", "# Hello")

    mock_inst.put.assert_called_once()
    call_kw = mock_inst.put.call_args
    assert "Bearer tok" in call_kw[1]["headers"]["Authorization"]
    assert call_kw[0][0].endswith("/vault/kb/q.md")


def test_write_kb_entry_obsidian_rest_without_settings_raises() -> None:
    entry = KBEntry(
        "questions",
        "q-1",
        "Q",
        "Body",
        "01-goal_define",
        "run-a",
    )
    with pytest.raises(ValueError, match="obsidian_rest settings"):
        write_kb_entry(Path("prefix"), entry, backend="obsidian_rest")


def test_write_kb_entry_obsidian_rest_delegates_to_put(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    def fake_put(settings: ObsidianRestSettings, vault_path: str, body: str) -> None:
        called["vault_path"] = vault_path
        called["body"] = body

    monkeypatch.setattr(
        "researchclaw.knowledge.base.put_vault_markdown", fake_put
    )
    settings = ObsidianRestSettings(
        base_url="https://127.0.0.1:27124", api_key="x", verify_ssl=False
    )
    entry = KBEntry(
        "questions",
        "q-9",
        "Q",
        "Body",
        "01-goal_define",
        "run-a",
        tags=["t1"],
        links=["run-run-a"],
    )
    out = write_kb_entry(
        Path("VaultPrefix"),
        entry,
        backend="obsidian_rest",
        obsidian_rest=settings,
    )
    assert out == Path("VaultPrefix") / "questions" / "q-9.md"
    assert called["vault_path"] == "VaultPrefix/questions/q-9.md"
    assert "#t1" in str(called["body"])
    assert "[[run-run-a]]" in str(called["body"])
