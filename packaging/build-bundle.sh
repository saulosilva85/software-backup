#!/bin/sh
# Gera o pacote OFFLINE do BackupHub para uma arquitetura (x86_64 ou aarch64).
# O pacote contém Python portátil + todas as dependências + código + instalador,
# e instala em qualquer Linux com glibc >= 2.17 sem acesso à internet.
#
# Uso: sh packaging/build-bundle.sh x86_64 [versao]
# Requer: internet, python3 com pip, curl (máquina de build, não o cliente).
set -eu
ARCH="${1:?informe a arquitetura: x86_64 ou aarch64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${2:-$(cd "$ROOT" && git describe --tags --always 2>/dev/null || echo dev)}"
PBS_TAG="${BACKUPHUB_PBS_TAG:-20250205}"
PBS_PY="${BACKUPHUB_PBS_PYTHON:-3.12.9}"
PYV="$(echo "$PBS_PY" | cut -d. -f1,2)"; PYTAG="cp$(echo "$PYV" | tr -d .)"
NAME="backuphub-${VERSION}-linux-${ARCH}"
OUT="$ROOT/dist"; STAGE="$OUT/$NAME"

rm -rf "$STAGE"; mkdir -p "$STAGE/wheels"
echo "==> Python portátil $PBS_PY ($ARCH)"
curl -fsSL --retry 3 -o "$STAGE/python.tar.gz" \
  "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PBS_PY}+${PBS_TAG}-${ARCH}-unknown-linux-gnu-install_only.tar.gz"

echo "==> Dependências (wheels compatíveis com glibc 2.17+)"
python3 -m pip download -q -r "$ROOT/requirements.txt" -d "$STAGE/wheels" \
  --only-binary=:all: --implementation cp --python-version "$PYV" \
  --abi "$PYTAG" --abi abi3 --abi none \
  --platform "manylinux2014_${ARCH}" --platform "manylinux_2_17_${ARCH}" --platform any

echo "==> Código"
cp -R "$ROOT/backuphub" "$ROOT/requirements.txt" "$ROOT/install.sh" "$ROOT/README.md" "$ROOT/deploy" "$ROOT/scripts" "$STAGE/"
find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +
echo "$VERSION" > "$STAGE/VERSION"

tar -czf "$OUT/$NAME.tar.gz" -C "$OUT" "$NAME"
( cd "$OUT" && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256" )
rm -rf "$STAGE"
echo "==> Pacote: dist/$NAME.tar.gz ($(du -h "$OUT/$NAME.tar.gz" | cut -f1))"
