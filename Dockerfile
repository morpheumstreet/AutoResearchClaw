# syntax=docker/dockerfile:1.7
# AutoResearchClaw — CLI + optional web server (FastAPI is not in base pyproject extras).
#
# Build (default, smaller image — no crawl4ai/playwright):
#   bash docker-build.sh
#
# Full optional deps (larger; crawl4ai may need extra browser setup at runtime):
#   PIP_EXTRAS=all bash docker-build.sh
#
# Build and push (set DOCKER_SPACE_SORA + DOCKER_TOKEN_SORA):
#   bash docker-build.sh --push
#
# Run (mount your config and artifacts directory):
#   docker run --rm -v "$PWD/config.yaml:/workspace/config.yaml:ro" \
#     -v "$PWD/artifacts:/workspace/artifacts" -w /workspace \
#     researchclaw:latest run --config config.yaml --topic "..." --auto-approve

FROM python:3.12-slim-bookworm AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY pyproject.toml README.md LICENSE prompts.default.yaml ./
COPY researchclaw ./researchclaw
COPY config.researchclaw.example.yaml ./config.researchclaw.example.yaml

# Comma-separated optional dependency groups from pyproject.toml (e.g. anthropic,pdf or all).
ARG PIP_EXTRAS=anthropic,pdf

RUN pip install --no-cache-dir ".[${PIP_EXTRAS}]" \
    && pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30"

# Ship example config for first-time bind-mount copy
RUN install -d /opt/researchclaw \
    && cp /src/config.researchclaw.example.yaml /opt/researchclaw/config.researchclaw.example.yaml

WORKDIR /workspace

RUN useradd --create-home --uid 1000 --shell /bin/bash researcher \
    && chown researcher:researcher /workspace

USER researcher

ENV PATH="/usr/local/bin:${PATH}"

EXPOSE 8080

ENTRYPOINT ["researchclaw"]
CMD ["--help"]
