#!/bin/sh
# Executado dentro de um container da distribuição testada (ver .github/workflows/ci.yml).
set -eu
if [ -n "${PREP:-}" ]; then sh -c "$PREP"; fi
if [ -n "${BUNDLE:-}" ]; then
  mkdir -p /tmp/b && tar -xzf "$BUNDLE" -C /tmp/b
  sh /tmp/b/*/install.sh --no-service --admin-password SmokeTest123
else
  sh /src/install.sh --source /src --no-service --admin-password SmokeTest123 ${INSTALL_ARGS:-}
fi
SMOKE_PASSWORD=SmokeTest123 /opt/backuphub/venv/bin/python /src/packaging/smoke_test.py
