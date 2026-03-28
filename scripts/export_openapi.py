#!/usr/bin/env python3
"""Emit OpenAPI 3 schema for the ResearchClaw FastAPI app (researchclaw serve).

Usage (from repo root):
  python scripts/export_openapi.py
  python scripts/export_openapi.py --output docs/openapi.yaml

Requires optional web deps (fastapi, etc.) like a normal `researchclaw serve` install.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _build_app(*, include_voice: bool):
    from researchclaw.config import RCConfig
    from researchclaw.server.app import create_app

    cfg_path = ROOT / "config.researchclaw.example.yaml"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Config not found: {cfg_path}")

    config = RCConfig.load(cfg_path, check_paths=False)
    if include_voice:
        server = dataclasses.replace(config.server, voice_enabled=True)
        config = dataclasses.replace(config, server=server)

    return create_app(config, dashboard_only=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "openapi.yaml",
        help="Write path (default: ./openapi.yaml)",
    )
    parser.add_argument(
        "--include-voice",
        action="store_true",
        help="Include /api/voice/* (requires python-multipart for FastAPI to load routes)",
    )
    args = parser.parse_args()

    try:
        import yaml
    except ImportError:
        print("PyYAML is required: pip install pyyaml", file=sys.stderr)
        return 1

    app = _build_app(include_voice=args.include_voice)
    schema = app.openapi()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        yaml.dump(
            schema,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )

    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
