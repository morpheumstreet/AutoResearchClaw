#!/usr/bin/env bash
# Build the AutoResearchClaw Docker image (CLI + optional extras + FastAPI/uvicorn for `researchclaw serve`).
# Optionally tag and push to Docker Hub or another registry.
#
# Usage:
#   bash docker-build.sh [tag]
#   bash docker-build.sh [--push] [tag]     # tag and push after build
#
# If tag is omitted: git describe --tags --always, or "latest" if not in a git repo.
#
# Environment — build:
#   RESEARCHCLAW_IMAGE_NAME   Image name (default: researchclaw)
#   PIP_EXTRAS                Comma-separated pyproject optional extras (default: anthropic,pdf).
#                             Use "all" for full web/crawl stack (larger image; crawl4ai may need
#                             browser setup at runtime — see project docs).
#   PIP_TRUSTED_HOSTS         Optional. Space-separated hosts for pip --trusted-host during build
#                             (helps when TLS to PyPI fails behind SSL inspection). If unset, the
#                             Dockerfile default applies. For strict verification: PIP_TRUSTED_HOSTS= bash docker-build.sh
#   RESEARCHCLAW_DOCKERFILE   Path to Dockerfile (default: Dockerfile next to this script)
#
# Environment — push (--push):
#   DOCKER_SPACE_SORA         Registry username or full path (e.g. myuser or ghcr.io/myorg)
#   DOCKER_TOKEN_SORA         Registry password or API token (stdin to docker login)
#   SKIP_BUILD                If 1, skip build and only tag/push existing local image
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

PUSH=0
TAG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) PUSH=1; shift ;;
    *) TAG="${1}"; shift ;;
  esac
done

if [[ -z "${TAG}" ]]; then
  TAG="$(git -C "${ROOT}" describe --tags --always 2>/dev/null || echo latest)"
fi

IMAGE_NAME="autoresearchdepartment"
DOCKERFILE="Dockerfile"
PIP_EXTRAS="${PIP_EXTRAS:-anthropic,pdf}"

DOCKER_REGISTRY="${DOCKER_SPACE_SORA}"
DOCKER_TOKEN="${DOCKER_TOKEN_SORA}"

if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "Error: Dockerfile not found: ${DOCKERFILE}" >&2
  exit 1
fi

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  echo "Building ${IMAGE_NAME}:${TAG} (PIP_EXTRAS=${PIP_EXTRAS})..."
  BUILD_ARGS=( -f "${DOCKERFILE}" --build-arg "PIP_EXTRAS=${PIP_EXTRAS}" )
  if [[ "${PIP_TRUSTED_HOSTS+x}" ]]; then
    BUILD_ARGS+=( --build-arg "PIP_TRUSTED_HOSTS=${PIP_TRUSTED_HOSTS}" )
  fi
  docker build \
    "${BUILD_ARGS[@]}" \
    -t "${IMAGE_NAME}:${TAG}" \
    "${ROOT}"
  echo "OK: ${IMAGE_NAME}:${TAG}"
fi

if [[ "${PUSH}" != "1" ]]; then
  exit 0
fi

if [[ -z "${DOCKER_REGISTRY}" || -z "${DOCKER_TOKEN}" ]]; then
  echo "Error: --push requires DOCKER_SPACE_SORA and DOCKER_TOKEN_SORA (or RESEARCHCLAW_DOCKER_REGISTRY and RESEARCHCLAW_DOCKER_TOKEN)." >&2
  echo "  DOCKER_SPACE_SORA = Docker Hub user or ghcr.io/org namespace" >&2
  echo "  DOCKER_TOKEN_SORA = registry password or token" >&2
  exit 1
fi

REMOTE_IMAGE="${DOCKER_REGISTRY}/${IMAGE_NAME}:${TAG}"
echo "Tagging and pushing ${REMOTE_IMAGE}..."

if [[ "${DOCKER_REGISTRY}" == *"/"* ]]; then
  REGISTRY_HOST="${DOCKER_REGISTRY%%/*}"
  echo "${DOCKER_TOKEN}" | docker login "${REGISTRY_HOST}" -u "${DOCKER_REGISTRY#*/}" --password-stdin
else
  echo "${DOCKER_TOKEN}" | docker login -u "${DOCKER_REGISTRY}" --password-stdin
fi

docker tag "${IMAGE_NAME}:${TAG}" "${REMOTE_IMAGE}"
docker push "${REMOTE_IMAGE}"

REMOTE_LATEST="${DOCKER_REGISTRY}/${IMAGE_NAME}:latest"
docker tag "${IMAGE_NAME}:${TAG}" "${REMOTE_LATEST}"
docker push "${REMOTE_LATEST}"

echo "Published ${REMOTE_IMAGE} and ${REMOTE_LATEST}"
echo "https://hub.docker.com/r/sorajez/autoresearchdepartment"