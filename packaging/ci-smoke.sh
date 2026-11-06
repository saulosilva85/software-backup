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
if [ -z "${BUNDLE:-}" ]; then
  echo "==> Segunda execução (atualização): deve reaproveitar Python e dependências"
  sh /src/install.sh --source /src --no-service ${INSTALL_ARGS:-} > /tmp/upgrade.log 2>&1 || { cat /tmp/upgrade.log; exit 1; }
  cat /tmp/upgrade.log
  grep -q "Dependências já instaladas" /tmp/upgrade.log || { echo "ERRO: dependências não foram reaproveitadas"; exit 1; }
  if [ -z "${INSTALL_ARGS:-}" ] && [ -z "$(ls /lib/ld-musl-* 2>/dev/null)" ]; then
    grep -q "Python portátil .* já instalado" /tmp/upgrade.log || { echo "ERRO: Python não foi reaproveitado"; exit 1; }
  fi
fi
SMOKE_PASSWORD=SmokeTest123 /opt/backuphub/venv/bin/python /src/packaging/smoke_test.py
