# ResearchClaw CLI manual

This document describes the `researchclaw` command-line interface: how to invoke it, how configuration is resolved, and what each subcommand does.

## Invocation

After installing the package (for example `pip install -e .` from the repository root), the entry point is:

```bash
researchclaw <subcommand> [options]
```

You can also run the module directly:

```bash
python -m researchclaw <subcommand> [options]
```

With no subcommand, the CLI prints help and exits with status `0`.

---

## Configuration file discovery

Many commands load a YAML config. If you omit `--config` / `-c`, ResearchClaw searches the current working directory in this order:

1. `config.arc.yaml`
2. `config.yaml`

If neither file exists, commands that require a config fail with a message suggesting `researchclaw init`.

Some subcommands (`serve`, `dashboard`, `wizard`, parts of `project`, etc.) default `--config` to `config.yaml` explicitly—create or copy a config file if you rely on those defaults.

---

## Subcommands overview

| Command | Purpose |
|--------|---------|
| `run` | Execute the full multi-stage research pipeline |
| `validate` | Validate the YAML config schema and paths |
| `doctor` | Environment and configuration health check |
| `init` | Create `config.arc.yaml` from the bundled example template |
| `setup` | Check or install optional tools (OpenCode, with environment hints) |
| `report` | Print or save a human-readable report for a finished run |
| `serve` | Start the FastAPI web server (requires `researchclaw[web]`) |
| `dashboard` | Start dashboard-only web UI (requires `researchclaw[web]`) |
| `wizard` | Interactive setup wizard; prints or writes YAML |
| `project` | Multi-project management (list, create, switch, compare, …) |
| `mcp` | List MCP tools or start the MCP server |
| `overleaf` | Overleaf sync status or sync for a run directory |
| `trends` | Research trend digest, analysis, or topic suggestions |
| `calendar` | Conference deadlines and submission planning |

---

## `researchclaw run`

Runs the autonomous research pipeline. Outputs under `artifacts/` by default unless you set `--output`.

**Options**

| Option | Short | Description |
|--------|-------|-------------|
| `--topic` | `-t` | Override the research topic from the config |
| `--config` | `-c` | Config file (default: auto-detect `config.arc.yaml` or `config.yaml`) |
| `--output` | `-o` | Run output directory (default: `artifacts/rc-YYYYMMDD-HHMMSS-<hash>/`) |
| `--from-stage` | | Start from a pipeline stage by **enum name** (see below), e.g. `PAPER_OUTLINE` |
| `--auto-approve` | | Auto-approve gate stages (overrides semi-auto blocking) |
| `--skip-preflight` | | Skip the LLM connectivity preflight check |
| `--resume` | | Resume from `checkpoint.json` in the run directory |
| `--skip-noncritical-stage` | | On failure in a non-critical stage, skip instead of aborting |
| `--no-graceful-degradation` | | Fail the pipeline on quality gate failure instead of degrading |

**Gate behavior**

- `--auto-approve` forces gates to auto-approve.
- If `project.mode` in config is `full-auto`, gates are auto-approved even without the flag.
- For `semi-auto` and `docs-first`, the pipeline can **stop on gates** unless you pass `--auto-approve`.

**Resume without `--output`**

If you use `--resume` and do **not** pass `--output`, the CLI looks under `artifacts/` for the newest `rc-*-<topic_hash>` directory that contains `checkpoint.json` and matches the current topic hash. If none is found, it starts a new run and prints a warning.

**Valid `--from-stage` names**

Use the stage **names** as in the `Stage` enum (case-insensitive in the CLI). Examples:

`TOPIC_INIT`, `PROBLEM_DECOMPOSE`, `SEARCH_STRATEGY`, `LITERATURE_COLLECT`, `LITERATURE_SCREEN`, `KNOWLEDGE_EXTRACT`, `SYNTHESIS`, `HYPOTHESIS_GEN`, `EXPERIMENT_DESIGN`, `CODE_GENERATION`, `RESOURCE_PLANNING`, `EXPERIMENT_RUN`, `ITERATIVE_REFINE`, `RESULT_ANALYSIS`, `RESEARCH_DECISION`, `PAPER_OUTLINE`, `PAPER_DRAFT`, `PEER_REVIEW`, `PAPER_REVISION`, `QUALITY_GATE`, `KNOWLEDGE_ARCHIVE`, `EXPORT_PUBLISH`, `CITATION_VERIFY`.

**Exit code**

- `0` if every stage completes successfully.
- `1` if any stage fails.

---

## `researchclaw validate`

Validates the config file structure (and optionally that referenced paths exist).

**Options**

| Option | Short | Description |
|--------|-------|-------------|
| `--config` | `-c` | Config file (default: auto-detect) |
| `--no-check-paths` | | Skip filesystem path existence checks |

**Exit code**

- `0` if validation passes (warnings may still print).
- `1` if validation fails.

---

## `researchclaw doctor`

Runs health checks for the environment and configuration, then prints a report.

**Options**

| Option | Short | Description |
|--------|-------|-------------|
| `--config` | `-c` | Config file (default: auto-detect) |
| `--output` | `-o` | Write a JSON report to this path |

**Exit code**

- `0` if overall status is `pass`.
- `1` otherwise.

---

## `researchclaw init`

Creates **`config.arc.yaml`** in the current directory by copying and customizing the bundled example (`config.researchclaw.example.yaml`). You can pick an LLM provider interactively when stdin is a TTY; otherwise defaults apply.

**Options**

| Option | Description |
|--------|-------------|
| `--force` | Overwrite an existing `config.arc.yaml` |

After creation, follow the printed next steps (API key, optional `researchclaw doctor`, OpenCode prompt).

---

## `researchclaw setup`

Checks optional dependencies: OpenCode (`opencode`), Docker, LaTeX (`pdflatex`). May offer to install OpenCode via `npm` when run interactively.

**Exit code**

Always `0` from the current implementation (informational run).

---

## `researchclaw report`

Generates a human-readable summary for a completed pipeline run directory.

**Options**

| Option | Short | Description |
|--------|-------|-------------|
| `--run-dir` | **required** | Path to the run’s artifact directory |
| `--output` | `-o` | Write the report to a file |

**Exit code**

- `0` on success.
- `1` if the run directory is missing or invalid for report generation.

---

## `researchclaw serve`

Starts the full web application (FastAPI + Uvicorn). Requires web extras: `pip install researchclaw[web]`.

**Options**

| Option | Short | Description |
|--------|-------|-------------|
| `--config` | `-c` | Config file (default: `config.yaml`) |
| `--host` | | Bind address (default: `server.host` from config) |
| `--port` | | Port (default: `server.port` from config; `0` means use config) |
| `--monitor-dir` | | Directory of run artifacts to monitor in the UI |

---

## `researchclaw dashboard`

Same stack as `serve`, but **dashboard-only** (no pipeline control). Same options as `serve`.

---

## `researchclaw wizard`

Runs the interactive QuickStart wizard and prints YAML to stdout, or writes it with `--output`.

**Options**

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Write generated config to a file |

---

## `researchclaw project`

Multi-project management. Requires `--config` pointing to a valid config (default: `config.yaml`).

**Syntax**

```bash
researchclaw project <action> [options]
```

**Actions**

| Action | Description |
|--------|-------------|
| `list` | List projects; active project is marked with `*` |
| `status` | Show totals and active project |
| `create` | Create a project (`--name` / `-n` required; optional `--topic` / `-t`) |
| `switch` | Switch active project (`--name` / `-n` required) |
| `compare` | Compare two projects (`--names` with exactly two names) |

---

## `researchclaw mcp`

**Without `--start`:** prints the list of available MCP tool names.

**With `--start`:** starts the ResearchClaw MCP server (long-running).

```bash
researchclaw mcp --start
```

---

## `researchclaw overleaf`

Requires `overleaf.enabled: true` in config.

**Options**

| Option | Description |
|--------|-------------|
| `--status` | Print sync status |
| `--sync` | Run sync for a run directory (`--run-dir` required) |
| `--run-dir` | Path to run artifacts (for `--sync`) |
| `--config` | `-c` (default: `config.yaml`) |

Use either `--sync` or `--status`.

---

## `researchclaw trends`

Uses config-driven trend sources and domains. Requires one mode flag.

**Options**

| Option | Description |
|--------|-------------|
| `--digest` | Generate a daily digest |
| `--analyze` | Analyze trends from recent papers |
| `--suggest-topics` | Suggest research topic candidates |
| `--config` | `-c` (default: `config.yaml`) |
| `--domains` | One or more domain strings (overrides `research.domains`; default domain list may fall back to e.g. `machine learning` if empty) |

---

## `researchclaw calendar`

**Options**

| Option | Description |
|--------|-------------|
| `--upcoming` | Show upcoming conference deadlines (optional `--domains` to filter) |
| `--plan` | Submission timeline for a **venue** identifier |
| `--domains` | Filter domains for `--upcoming` |

Example:

```bash
researchclaw calendar --upcoming
researchclaw calendar --plan neurips
```

---

## Quick start (typical flow)

```bash
researchclaw setup
researchclaw init
# Set API key per printed instructions, edit config.arc.yaml as needed
researchclaw doctor
researchclaw validate
researchclaw run --topic "Your research question" --auto-approve
```

For a full pipeline run with gates that pause for approval, omit `--auto-approve` and use a `semi-auto` or `docs-first` `project.mode` in config.

---

## See also

- Example configuration: `config.researchclaw.example.yaml` in the repository root
- Community testing walkthrough: [TESTER_GUIDE.md](TESTER_GUIDE.md)
- Integration topics: [integration-guide.md](integration-guide.md)
