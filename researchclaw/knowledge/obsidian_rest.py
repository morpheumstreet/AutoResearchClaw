"""HTTP client for the Obsidian Local REST API (vault file writes).

See: https://github.com/coddingtonbear/obsidian-local-rest-api
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from researchclaw.config import KnowledgeBaseConfig


@dataclass(frozen=True)
class ObsidianRestSettings:
    """Connection settings for PUT /vault/{path}."""

    base_url: str
    api_key: str
    verify_ssl: bool = True
    timeout_sec: float = 60.0


def vault_put_url(base_url: str, vault_relative_path: str) -> str:
    """Build ``{base}/vault/{encoded/segments}`` for the Local REST API."""
    base = base_url.rstrip("/")
    rel = vault_relative_path.strip().replace("\\", "/").strip("/")
    if not rel:
        raise ValueError("vault path must not be empty")
    encoded = "/".join(quote(part, safe="") for part in rel.split("/") if part)
    return f"{base}/vault/{encoded}"


def obsidian_rest_settings_from_config(kb: KnowledgeBaseConfig) -> ObsidianRestSettings | None:
    """Build REST settings when ``backend == \"obsidian_rest\"``; otherwise ``None``."""
    if kb.backend != "obsidian_rest":
        return None
    url = kb.obsidian_rest_base_url.strip()
    env_name = kb.obsidian_rest_api_key_env.strip()
    if not url or not env_name:
        raise ValueError(
            "obsidian_rest requires knowledge_base.obsidian_rest_base_url and "
            "obsidian_rest_api_key_env"
        )
    token = os.environ.get(env_name, "").strip()
    if not token:
        raise ValueError(
            f"obsidian_rest: environment variable {env_name!r} is empty or unset"
        )
    return ObsidianRestSettings(
        base_url=url,
        api_key=token,
        verify_ssl=kb.obsidian_rest_verify_ssl,
    )


def put_vault_markdown(settings: ObsidianRestSettings, vault_path: str, body: str) -> None:
    """Create or replace a note at *vault_path* (relative to vault root)."""
    url = vault_put_url(settings.base_url, vault_path)
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "text/markdown; charset=utf-8",
    }
    with httpx.Client(verify=settings.verify_ssl, timeout=settings.timeout_sec) as client:
        r = client.put(url, content=body.encode("utf-8"), headers=headers)
    if r.status_code not in (200, 204):
        detail = (r.text or "")[:500]
        raise RuntimeError(
            f"Obsidian REST PUT {url!r} failed: {r.status_code} {detail}"
        )
