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
# Run — mount a config *directory* (not a missing config.yaml file, or Docker may create a folder):
#   mkdir -p config && cp config.researchclaw.example.yaml config/config.yaml
#   docker run --rm \
#     -v "$PWD/config:/workspace/user-config" \
#     -v "$PWD/artifacts:/workspace/artifacts" -w /workspace \
#     researchclaw:latest run --config /workspace/user-config/config.yaml --topic "..." --auto-approve

FROM python:3.12-slim-bookworm AS runtime

# Pip pulls build deps (e.g. hatchling) from PyPI; TLS can fail behind SSL-inspecting proxies
# (CERTIFICATE_VERIFY_FAILED / hostname mismatch for files.pythonhosted.org). Relax verification
# only for PyPI hosts. For strict TLS: docker build --build-arg PIP_TRUSTED_HOSTS="" .
ARG PIP_TRUSTED_HOSTS="pypi.org files.pythonhosted.org"
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOSTS}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        coreutils \
        git \
        gosu \
        nano \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY pyproject.toml README.md LICENSE prompts.default.yaml ./
COPY researchclaw ./researchclaw
COPY config.researchclaw.example.yaml ./config.researchclaw.yaml

# Comma-separated optional dependency groups from pyproject.toml (e.g. anthropic,pdf or all).
ARG PIP_EXTRAS=anthropic,pdf

RUN pip install --no-cache-dir ".[${PIP_EXTRAS}]" \
    && pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30"

# Do not keep pip trusted-host settings in the final image.
ENV PIP_TRUSTED_HOST=

# Ship default config for first-time bind-mount copy (same content as example template)
RUN install -d /opt/researchclaw \
    && cp /src/config.researchclaw.yaml /opt/researchclaw/config.researchclaw.yaml

WORKDIR /workspace

# UID/GID 1000 — entrypoint chowns bind mounts then drops to this user (see docker-entrypoint.sh).
RUN groupadd -g 1000 researcher \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash researcher \
    && chown -R 1000:1000 /workspace /opt/researchclaw

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod 755 /docker-entrypoint.sh

ENV PATH="/usr/local/bin:${PATH}"

EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["--help"]
