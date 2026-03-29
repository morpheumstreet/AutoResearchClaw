"""Knowledge base integration for ARC pipeline.

Supports backends:
- ``markdown`` (default): Plain Markdown files under ``knowledge_base.root``
- ``obsidian``: Markdown with Obsidian-compatible wikilinks, tags, and frontmatter
  on the local filesystem
- ``obsidian_rest``: Same note shape as ``obsidian``, but writes via the
  `Obsidian Local REST API <https://github.com/coddingtonbear/obsidian-local-rest-api>`_
  (HTTPS default port 27124). ``knowledge_base.root`` is the vault-relative
  folder prefix for KB files (e.g. ``ResearchClaw/kb``).

With ``knowledge_base.topic_prefix: auto`` (default), entries are stored under
``{root}/{domain-slugs}__{topic-slug}/{category}/…`` using ``research.domains``
and ``research.topic`` so each major topic has its own subtree.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from researchclaw.knowledge.obsidian_rest import ObsidianRestSettings, put_vault_markdown


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# KB Entry
# ---------------------------------------------------------------------------


@dataclass
class KBEntry:
    """A single knowledge-base entry to be written."""

    category: (
        str  # questions | literature | experiments | findings | decisions | reviews
    )
    entry_id: str  # Unique ID (e.g. "goal-define-run-abc")
    title: str
    content: str  # Markdown body
    source_stage: str  # e.g. "01-goal_define"
    run_id: str
    evidence_refs: list[str] | None = None
    tags: list[str] | None = None
    links: list[str] | None = None  # For Obsidian wikilinks


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _markdown_frontmatter(entry: KBEntry) -> str:
    """Generate YAML frontmatter block."""
    meta: dict[str, Any] = {
        "id": entry.entry_id,
        "title": entry.title,
        "stage": entry.source_stage,
        "run_id": entry.run_id,
        "created": _utcnow_iso(),
    }
    if entry.tags:
        meta["tags"] = entry.tags
    if entry.evidence_refs:
        meta["evidence"] = entry.evidence_refs
    return (
        "---\n"
        + yaml.dump(meta, default_flow_style=False, allow_unicode=True).rstrip()
        + "\n---\n"
    )


def _obsidian_enhancements(entry: KBEntry) -> str:
    """Add Obsidian-compatible wikilinks and tag line at end of content."""
    extras: list[str] = []
    if entry.tags:
        tag_line = " ".join(f"#{t}" for t in entry.tags)
        extras.append(f"\n{tag_line}")
    if entry.links:
        link_line = "Related: " + ", ".join(f"[[{l}]]" for l in entry.links)
        extras.append(link_line)
    return "\n".join(extras)


def _slug_segment(s: str, max_len: int = 64) -> str:
    """Lowercase path segment: letters, digits, hyphen; empty input → stable hash."""
    t = s.lower().strip()
    t = re.sub(r"[^\w\s-]+", "", t, flags=re.UNICODE)
    t = re.sub(r"[-\s]+", "-", t).strip("-")
    if not t:
        h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]
        return f"topic-{h}"
    return t[:max_len]


def slug_kb_topic_with_domains(topic: str, domains: tuple[str, ...]) -> str:
    """Build a single folder name: ``{domain}-{domain}__{topic}`` or topic only."""
    dom_parts = [_slug_segment(str(d), 48) for d in domains if str(d).strip()]
    dom_parts = [p for p in dom_parts if p]
    topic_part = _slug_segment(topic, 96)
    if dom_parts:
        domain_join = "-".join(dom_parts)[:80]
        return f"{domain_join}__{topic_part}"
    return topic_part


def kb_topic_path_segment(
    topic: str,
    domains: tuple[str, ...],
    *,
    topic_prefix_mode: str,
) -> str | None:
    """Return extra path segment under ``knowledge_base.root``, or ``None``."""
    if topic_prefix_mode != "auto":
        return None
    t = (topic or "").strip()
    if not t:
        return None
    return slug_kb_topic_with_domains(t, domains)


def effective_kb_root(
    kb_root: Path,
    topic: str,
    domains: tuple[str, ...],
    *,
    topic_prefix_mode: str,
) -> Path:
    """``kb_root`` optionally extended with domain/topic slug (see ``topic_prefix``)."""
    seg = kb_topic_path_segment(topic, domains, topic_prefix_mode=topic_prefix_mode)
    if seg is None:
        return kb_root
    return kb_root / seg


def _kb_vault_relative(kb_root: Path, category: str, filename: str) -> str:
    prefix = kb_root.as_posix().strip("/")
    if prefix:
        return f"{prefix}/{category}/{filename}"
    return f"{category}/{filename}"


def write_kb_entry(
    kb_root: Path,
    entry: KBEntry,
    *,
    backend: str = "markdown",
    obsidian_rest: ObsidianRestSettings | None = None,
) -> Path:
    """Write a single KB entry to the appropriate category directory.

    For ``obsidian_rest``, *kb_root* is a vault-relative path prefix only;
    the note is sent with ``PUT /vault/...`` and the returned :class:`~pathlib.Path`
    is the logical location for logging.

    Returns the path to the written file (or logical path for REST).
    """
    # Build content
    parts: list[str] = []
    parts.append(_markdown_frontmatter(entry))
    parts.append(f"# {entry.title}\n")
    parts.append(entry.content)

    if backend in ("obsidian", "obsidian_rest"):
        obs = _obsidian_enhancements(entry)
        if obs:
            parts.append(obs)

    filename = f"{entry.entry_id}.md"
    body = "\n".join(parts)

    if backend == "obsidian_rest":
        if obsidian_rest is None:
            raise ValueError(
                "obsidian_rest backend requires obsidian_rest settings (API URL and key)"
            )
        vault_rel = _kb_vault_relative(kb_root, entry.category, filename)
        put_vault_markdown(obsidian_rest, vault_rel, body)
        return kb_root / entry.category / filename

    category_dir = kb_root / entry.category
    category_dir.mkdir(parents=True, exist_ok=True)
    filepath = category_dir / filename
    filepath.write_text(body, encoding="utf-8")
    return filepath


# ---------------------------------------------------------------------------
# Pipeline KB integration
# ---------------------------------------------------------------------------

KB_CATEGORY_MAP: dict[int, str] = {
    1: "questions",
    2: "questions",
    3: "decisions",
    4: "literature",
    5: "literature",
    6: "literature",
    7: "findings",
    8: "questions",
    9: "decisions",
    10: "experiments",
    11: "decisions",
    12: "experiments",
    13: "experiments",
    14: "findings",
    15: "decisions",
    16: "reviews",
    17: "reviews",
    18: "reviews",
    19: "reviews",
    20: "decisions",
    21: "decisions",
    22: "reviews",
}


def write_stage_to_kb(
    kb_root: Path,
    stage_id: int,
    stage_name: str,
    run_id: str,
    artifacts: list[str],
    stage_dir: Path,
    *,
    backend: str = "markdown",
    topic: str = "",
    domains: tuple[str, ...] = (),
    topic_prefix_mode: str = "auto",
    obsidian_rest: ObsidianRestSettings | None = None,
) -> list[Path]:
    """Write stage results to the knowledge base.

    Reads the primary output artifact and creates a KB entry
    in the appropriate category directory.

    Returns list of paths written.
    """
    category = KB_CATEGORY_MAP.get(stage_id, "findings")
    written: list[Path] = []

    # Read the primary artifact content
    content_parts: list[str] = []
    evidence: list[str] = []
    for artifact_name in artifacts:
        artifact_path = stage_dir / artifact_name.rstrip("/")
        if artifact_path.is_file():
            text = artifact_path.read_text(encoding="utf-8")
            # Truncate very large files for KB entry
            if len(text) > 5000:
                text = text[:5000] + "\n\n... (truncated, see full artifact)\n"
            content_parts.append(text)
            evidence.append(f"stage-{stage_id:02d}/{artifact_name}")
        elif artifact_path.is_dir():
            files = sorted(artifact_path.iterdir())
            content_parts.append(
                f"Directory with {len(files)} files: {', '.join(f.name for f in files[:10])}"
            )
            evidence.append(f"stage-{stage_id:02d}/{artifact_name}/")

    if not content_parts:
        content_parts.append(
            f"Stage {stage_id:02d} ({stage_name}) completed. See artifacts directory for details."
        )

    entry = KBEntry(
        category=category,
        entry_id=f"{stage_name}-{run_id}",
        title=f"Stage {stage_id:02d}: {stage_name.replace('_', ' ').title()}",
        content="\n\n".join(content_parts),
        source_stage=f"{stage_id:02d}-{stage_name}",
        run_id=run_id,
        evidence_refs=evidence,
        tags=[stage_name, f"stage-{stage_id:02d}", f"run-{run_id[:8]}"],
        links=[f"run-{run_id}"] if backend in ("obsidian", "obsidian_rest") else None,
    )

    root = effective_kb_root(
        kb_root,
        topic,
        domains,
        topic_prefix_mode=topic_prefix_mode,
    )
    path = write_kb_entry(
        root, entry, backend=backend, obsidian_rest=obsidian_rest
    )
    written.append(path)
    return written


# ---------------------------------------------------------------------------
# Weekly report generation (#19)
# ---------------------------------------------------------------------------


def generate_weekly_report(
    kb_root: Path,
    run_dirs: list[Path],
    *,
    backend: str = "markdown",
    week_label: str = "",
    obsidian_rest: ObsidianRestSettings | None = None,
    research_topic: str = "",
    research_domains: tuple[str, ...] = (),
    topic_prefix_mode: str = "auto",
) -> Path:
    """Generate a weekly summary report from completed pipeline runs.

    Scans ``run_dirs`` for ``pipeline_summary.json`` files and aggregates
    statistics into a Markdown report written to ``kb_root/reviews/`` (or under
    the same topic prefix as stage KB when *research_topic* is set and
    *topic_prefix_mode* is ``auto``).
    """
    if not week_label:
        week_label = datetime.now(timezone.utc).strftime("%Y-W%W")

    runs_data: list[dict] = []
    for run_dir in run_dirs:
        summary_path = run_dir / "pipeline_summary.json"
        if summary_path.exists():
            runs_data.append(json.loads(summary_path.read_text(encoding="utf-8")))

    # Build report
    total_runs = len(runs_data)
    total_stages = sum(r.get("stages_executed", 0) for r in runs_data)
    total_done = sum(r.get("stages_done", 0) for r in runs_data)
    total_failed = sum(r.get("stages_failed", 0) for r in runs_data)
    total_blocked = sum(r.get("stages_blocked", 0) for r in runs_data)

    report_lines = [
        f"## Summary",
        f"- Week: {week_label}",
        f"- Pipeline runs: {total_runs}",
        f"- Stages executed: {total_stages}",
        f"- Stages completed: {total_done}",
        f"- Stages failed: {total_failed}",
        f"- Stages blocked (gate): {total_blocked}",
        f"- Success rate: {total_done / total_stages * 100:.1f}%"
        if total_stages > 0
        else "- Success rate: N/A",
        "",
        "## Run Details",
    ]
    for rd in runs_data:
        run_id = rd.get("run_id", "unknown")
        report_lines.append(
            f"- **{run_id}**: {rd.get('stages_done', 0)}/{rd.get('stages_executed', 0)} stages done, final={rd.get('final_status', '?')}"
        )

    report_lines.extend(["", "## Recommendations"])
    if total_failed > 0:
        report_lines.append(
            f"- ⚠️ {total_failed} stage failures detected. Review error logs."
        )
    if total_blocked > 0:
        report_lines.append(f"- 🔒 {total_blocked} stages awaiting gate approval.")
    if total_failed == 0 and total_blocked == 0:
        report_lines.append("- ✅ All stages completed successfully.")

    content = "\n".join(report_lines)

    entry = KBEntry(
        category="reviews",
        entry_id=f"weekly-report-{week_label}",
        title=f"Weekly Report — {week_label}",
        content=content,
        source_stage="report",
        run_id=week_label,
        tags=["weekly-report", week_label],
    )
    root = effective_kb_root(
        kb_root,
        research_topic,
        research_domains,
        topic_prefix_mode=topic_prefix_mode,
    )
    return write_kb_entry(
        root, entry, backend=backend, obsidian_rest=obsidian_rest
    )
