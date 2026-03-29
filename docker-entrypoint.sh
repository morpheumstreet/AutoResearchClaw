#!/usr/bin/env bash
# Run as root so bind-mounted host dirs (often created as root) can be chown'd to 1000:1000.
set -e
if [[ "$(id -u)" -eq 0 ]]; then
  chown -R 1000:1000 /workspace /opt/researchclaw /home/researcher 2>/dev/null || true
  exec gosu 1000:1000 researchclaw "$@"
fi
exec researchclaw "$@"
