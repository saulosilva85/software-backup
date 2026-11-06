#!/bin/sh
# =============================================================================
#  BackupHub — instalador universal para Linux
#
#  Funciona em praticamente qualquer distribuição (x86_64 e ARM64):
#    Ubuntu, Debian, Red Hat (RHEL), Rocky, AlmaLinux, Oracle Linux, CentOS,
#    Fedora, Amazon Linux, SUSE/openSUSE, Arch, Alpine e derivadas.
#
#  A ferramenta traz o próprio Python (portátil), então NÃO depende da versão
#  do Python do sistema. Detecta o gerenciador de pacotes (apt, dnf, yum,
#  zypper, apk, pacman) e o sistema de inicialização (systemd, OpenRC, SysV).
#
#  Instalação online (uma linha):
#    curl -fsSL https://raw.githubusercontent.com/saulosilva85/software-backup/main/install.sh | sudo sh
#
#  Instalação offline (servidor sem internet), com o pacote completo:
#    tar xzf backuphub-<versao>-linux-x86_64.tar.gz
#    cd backuphub-<versao>-linux-x86_64 && sudo sh install.sh
#
#  Atualizar: execute o instalador novamente (dados e configuração são mantidos).
#  Remover:   sudo sh install.sh --uninstall   (--purge apaga também os dados)
# =============================================================================
set -eu

# Garante as pastas de comandos administrativos (useradd, adduser...) no PATH:
# com "su" (sem o "-"), o Debian/Ubuntu mantém o PATH do usuário comum, sem /usr/sbin.
PATH="${PATH:-/usr/bin:/bin}:/usr/local/sbin:/usr/sbin:/sbin"; export PATH

REPO="${BACKUPHUB_REPO:-saulosilva85/software-backup}"
BRANCH="${BACKUPHUB_BRANCH:-main}"
PREFIX="${BACKUPHUB_PREFIX:-/opt/backuphub}"
DATA_DIR="${BACKUPHUB_DATA_DIR:-/var/lib/backuphub}"
ENV_FILE="/etc/backuphub.env"
LOG_DIR="/var/log/backuphub"
SVC_USER="backuphub"
PORT="${BACKUPHUB_PORT:-8080}"
# Python portátil (python-build-standalone): roda em qualquer Linux com glibc >= 2.17.
PBS_TAG="${BACKUPHUB_PBS_TAG:-20250205}"
PBS_PY="${BACKUPHUB_PBS_PYTHON:-3.12.9}"

ACTION="install"
NO_SERVICE=0
OPEN_FW=0
SOURCE_DIR=""
OFFLINE=0
PURGE=0
SYSTEM_PY=0
ADMIN_PASSWORD="${BACKUPHUB_ADMIN_PASSWORD:-}"
TIMEZONE="${BACKUPHUB_TIMEZONE:-}"
PUBLIC_URL="${BACKUPHUB_PUBLIC_URL:-}"
GENERATED_PASSWORD=""

# ----------------------------------------------------------------- utilitários
if [ -t 1 ]; then B="$(printf '\033[1m')"; G="$(printf '\033[32m')"; Y="$(printf '\033[33m')"; R="$(printf '\033[31m')"; C="$(printf '\033[36m')"; N="$(printf '\033[0m')"
else B=""; G=""; Y=""; R=""; C=""; N=""; fi
log()  { printf '%s==>%s %s\n' "$C$B" "$N" "$*"; }
ok()   { printf '%s[OK]%s %s\n' "$G" "$N" "$*"; }
warn() { printf '%s[aviso]%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%s[erro]%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

usage() {
  cat <<EOF
Uso: sudo sh install.sh [opções]

  --admin-password SENHA  Senha inicial do usuário admin (padrão: gerada aleatoriamente)
  --timezone ZONA         Fuso dos agendamentos (ex.: America/Sao_Paulo). Padrão: o do servidor
  --public-url URL        URL que os servidores Windows usam para alcançar o BackupHub
  --port PORTA            Porta da interface web (padrão: 8080)
  --open-firewall         Libera a porta no firewalld/ufw, se estiverem ativos
  --system-python         Usa o Python do sistema (>= 3.9) em vez do Python portátil
  --offline               Instala sem internet a partir do pacote completo (detectado automaticamente)
  --source DIR            Usa o código-fonte deste diretório
  --no-service            Não registra/inicia o serviço (containers, testes)
  --uninstall [--purge]   Remove a ferramenta (--purge apaga também dados e configuração)
  -h, --help              Esta ajuda
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --admin-password) ADMIN_PASSWORD="${2:?}"; shift ;;
    --timezone) TIMEZONE="${2:?}"; shift ;;
    --public-url) PUBLIC_URL="${2:?}"; shift ;;
    --port) PORT="${2:?}"; shift ;;
    --open-firewall) OPEN_FW=1 ;;
    --system-python) SYSTEM_PY=1 ;;
    --offline) OFFLINE=1 ;;
    --source) SOURCE_DIR="${2:?}"; shift ;;
    --no-service) NO_SERVICE=1 ;;
    --uninstall) ACTION="uninstall" ;;
    --purge) PURGE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "Opção desconhecida: $1" ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || die "Execute como root: sudo sh install.sh"

SCRIPT_DIR=""
case "$0" in
  */install.sh|install.sh) SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)" ;;
esac

# ----------------------------------------------------------------- detecção
detect_system() {
  OS_ID="linux"; OS_NAME="Linux"; OS_LIKE=""
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-linux}"; OS_NAME="${PRETTY_NAME:-$OS_ID}"; OS_LIKE="${ID_LIKE:-}"
  elif [ -r /etc/redhat-release ]; then
    OS_ID="rhel"; OS_NAME="$(cat /etc/redhat-release)"
  fi

  case "$(uname -m)" in
    x86_64|amd64) ARCH="x86_64" ;;
    aarch64|arm64) ARCH="aarch64" ;;
    *) die "Arquitetura não suportada: $(uname -m) (suportadas: x86_64 e aarch64/ARM64)" ;;
  esac

  LIBC="glibc"
  if ls /lib/ld-musl-* >/dev/null 2>&1 || (ldd --version 2>&1 | grep -qi musl); then LIBC="musl"; fi

  PKG="none"
  for p in apt-get dnf yum zypper apk pacman; do
    if have "$p"; then PKG="$p"; break; fi
  done

  INIT="none"
  if [ -d /run/systemd/system ]; then INIT="systemd"
  elif have openrc-run || have rc-service; then INIT="openrc"
  elif [ -d /etc/init.d ]; then INIT="sysv"; fi
}

APT_UPDATED=0
pkg_install() {
  [ $# -gt 0 ] || return 0
  [ "$OFFLINE" -eq 1 ] && return 1
  log "Instalando pacotes do sistema: $*"
  case "$PKG" in
    apt-get)
      if [ "$APT_UPDATED" -eq 0 ]; then DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null; APT_UPDATED=1; fi
      if ! DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "$@" >/dev/null; then
        warn "Falha no apt (espelho desatualizado?); atualizando índices e tentando novamente"
        sleep 5; DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null || true
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends --fix-missing "$@" >/dev/null
      fi ;;
    dnf) dnf install -y -q "$@" >/dev/null || { sleep 5; dnf install -y -q --refresh "$@" >/dev/null; } ;;
    yum) yum install -y -q "$@" >/dev/null || { sleep 5; yum clean metadata >/dev/null 2>&1; yum install -y -q "$@" >/dev/null; } ;;
    zypper) zypper --non-interactive --quiet install --no-recommends "$@" >/dev/null ;;
    apk) apk add --no-cache --quiet "$@" >/dev/null ;;
    pacman) pacman -Sy --noconfirm --needed --quiet "$@" >/dev/null ;;
    *) return 1 ;;
  esac
}

ensure_prereqs() {
  missing=""
  have tar || missing="$missing tar"
  have gzip || missing="$missing gzip"
  if [ "$OFFLINE" -eq 0 ] && ! have curl && ! have wget; then missing="$missing curl"; fi
  if ! have useradd && ! have adduser; then
    case "$PKG" in
      apt-get) missing="$missing passwd" ;;
      dnf|yum) missing="$missing shadow-utils" ;;
      zypper|pacman) missing="$missing shadow" ;;
    esac
  fi
  if [ "$OFFLINE" -eq 0 ] && [ ! -e /etc/ssl/certs/ca-certificates.crt ] && [ ! -e /etc/pki/tls/certs/ca-bundle.crt ] \
     && [ ! -e /etc/ssl/ca-bundle.pem ] && [ ! -e /etc/ssl/cert.pem ]; then
    missing="$missing ca-certificates"
  fi
  if [ -n "$missing" ]; then
    # shellcheck disable=SC2086
    pkg_install $missing || die "Instale manualmente:$missing"
  fi
  have tar && have gzip || die "tar e gzip são necessários"
}

download() { # url destino
  if have curl; then curl -fsSL --retry 3 --connect-timeout 20 -o "$2" "$1"
  else wget -q -T 20 -t 3 -O "$2" "$1"; fi
}

version_ge() { # $1 >= $2 (ex.: 2.28 2.17)
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -t. -k1,1n -k2,2n | head -n1)" = "$2" ]
}

# ----------------------------------------------------------------- Python
system_python() {
  for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if have "$c" && "$c" -c 'import sys, venv, ensurepip; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      command -v "$c"; return 0
    fi
  done
  return 1
}

install_system_python() {
  case "$PKG" in
    apt-get) pkg_install python3 python3-venv python3-pip ;;
    dnf|yum) pkg_install python3.11 python3.11-pip 2>/dev/null || pkg_install python3 python3-pip ;;
    zypper) pkg_install python311 python311-pip 2>/dev/null || pkg_install python3 python3-pip ;;
    apk) pkg_install python3 py3-pip ;;
    pacman) pkg_install python python-pip ;;
    *) return 1 ;;
  esac
}

setup_python() {
  if [ "$LIBC" = "musl" ]; then SYSTEM_PY=1; fi
  if [ "$SYSTEM_PY" -eq 0 ]; then
    glibc="$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}')"
    if [ -n "$glibc" ] && ! version_ge "$glibc" "2.17"; then
      warn "glibc $glibc é anterior à 2.17; tentando o Python do sistema"; SYSTEM_PY=1
    fi
  fi

  if [ "$SYSTEM_PY" -eq 0 ] && [ -x "$PREFIX/python/bin/python3" ] \
     && [ "$("$PREFIX/python/bin/python3" -c 'import platform; print(platform.python_version())' 2>/dev/null)" = "$PBS_PY" ]; then
    PY="$PREFIX/python/bin/python3"
    ok "Python portátil $PBS_PY já instalado (reaproveitado, sem download)"
    return
  fi

  if [ "$SYSTEM_PY" -eq 0 ]; then
    tarball=""
    if [ "$OFFLINE" -eq 1 ]; then
      tarball="$BUNDLE_DIR/python.tar.gz"
      [ -f "$tarball" ] || die "Pacote offline sem python.tar.gz"
    else
      url="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PBS_PY}+${PBS_TAG}-${ARCH}-unknown-linux-gnu-install_only.tar.gz"
      tarball="$TMP/python.tar.gz"
      log "Baixando Python portátil ${PBS_PY} (${ARCH})"
      if ! download "$url" "$tarball"; then
        warn "Não foi possível baixar o Python portátil; tentando o Python do sistema"; SYSTEM_PY=1
      fi
    fi
    if [ "$SYSTEM_PY" -eq 0 ]; then
      rm -rf "$PREFIX/python"
      tar -xzf "$tarball" -C "$PREFIX"   # cria $PREFIX/python
      PY="$PREFIX/python/bin/python3"
      "$PY" -c 'import ssl, sqlite3' || die "Python portátil inválido"
      ok "Python portátil $("$PY" -c 'import platform; print(platform.python_version())') instalado em $PREFIX/python"
      return
    fi
  fi

  PY="$(system_python || true)"
  if [ -z "$PY" ]; then
    install_system_python || true
    PY="$(system_python || true)"
  fi
  [ -n "$PY" ] || die "Não foi encontrado Python >= 3.9 com venv. Instale-o ou use o pacote offline."
  ok "Usando Python do sistema: $PY ($("$PY" -c 'import platform; print(platform.python_version())'))"
}

# ----------------------------------------------------------------- código
fetch_source() {
  if [ -n "$SOURCE_DIR" ]; then :
  elif [ -n "$SCRIPT_DIR" ] && [ "$SCRIPT_DIR" != "$PREFIX/app" ] && [ -f "$SCRIPT_DIR/backuphub/__init__.py" ]; then
    SOURCE_DIR="$SCRIPT_DIR"   # pacote offline ou cópia do repositório (a cópia instalada baixa a versão nova)
  elif [ "$OFFLINE" -eq 1 ]; then die "Pacote offline incompleto (pasta backuphub/ não encontrada)"
  else
    log "Baixando o BackupHub ($REPO@$BRANCH)"
    download "https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH" "$TMP/src.tar.gz" \
      || die "Falha ao baixar o código. Use o pacote offline."
    mkdir -p "$TMP/src" && tar -xzf "$TMP/src.tar.gz" -C "$TMP/src" --strip-components=1
    SOURCE_DIR="$TMP/src"
  fi
  [ -f "$SOURCE_DIR/backuphub/__init__.py" ] || die "Código-fonte não encontrado em $SOURCE_DIR"
  rm -rf "$PREFIX/app.new"
  mkdir -p "$PREFIX/app.new"
  cp -R "$SOURCE_DIR/backuphub" "$SOURCE_DIR/requirements.txt" "$PREFIX/app.new/"
  for extra in README.md deploy scripts install.sh; do
    [ -e "$SOURCE_DIR/$extra" ] && cp -R "$SOURCE_DIR/$extra" "$PREFIX/app.new/"
  done
  find "$PREFIX/app.new" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  rm -rf "$PREFIX/app" && mv "$PREFIX/app.new" "$PREFIX/app"
  ok "Código instalado em $PREFIX/app"
}

file_hash() {
  if have sha256sum; then sha256sum "$1" | cut -d' ' -f1
  elif have shasum; then shasum -a 256 "$1" | cut -d' ' -f1
  else cksum "$1" | cut -d' ' -f1; fi
}

setup_venv() {
  req="$PREFIX/app/requirements.txt"
  stamp="$PREFIX/venv/.backuphub-deps"
  want="$(file_hash "$req") $("$PY" -c 'import sys; print(sys.executable)')"
  # Reaproveita quando: mesma lista de dependências (ou instalação anterior sem registro), mesmo Python
  # de base e todas as bibliotecas importáveis.
  if [ -x "$PREFIX/venv/bin/python" ] && { [ ! -f "$stamp" ] || [ "$(cat "$stamp")" = "$want" ]; } \
     && [ "$("$PREFIX/venv/bin/python" -c 'import sys; print(sys.base_prefix)' 2>/dev/null)" = "$("$PY" -c 'import sys; print(sys.base_prefix)')" ] \
     && "$PREFIX/venv/bin/python" -c 'import flask, cryptography, paramiko, winrm, boto3, gunicorn' 2>/dev/null; then
    echo "$want" > "$stamp"
    ok "Dependências já instaladas e atualizadas (reaproveitadas, sem download)"
    return
  fi
  log "Criando ambiente Python e instalando dependências (pode levar alguns minutos)"
  rm -rf "$PREFIX/venv"
  "$PY" -m venv "$PREFIX/venv"
  VPY="$PREFIX/venv/bin/python"
  if [ "$OFFLINE" -eq 1 ]; then
    "$VPY" -m pip install -q --no-index --find-links "$BUNDLE_DIR/wheels" -r "$req" \
      || die "Falha ao instalar dependências do pacote offline"
  else
    "$VPY" -m pip install -q --upgrade pip >/dev/null 2>&1 || true
    if ! "$VPY" -m pip install -q --only-binary=:all: -r "$req"; then
      warn "Pacotes binários indisponíveis para este sistema; tentando compilar o que faltar"
      "$VPY" -m pip install -q --prefer-binary -r "$req" || die "Falha ao instalar as dependências Python"
    fi
  fi
  "$VPY" -c 'import flask, cryptography, paramiko, winrm, boto3, gunicorn' || die "Dependências incompletas"
  echo "$want" > "$stamp"
  ok "Dependências instaladas"
}

# ----------------------------------------------------------------- usuário, configuração
nologin_shell() {
  for s in /usr/sbin/nologin /sbin/nologin /bin/false; do [ -x "$s" ] && { echo "$s"; return; }; done
  echo /bin/false
}

setup_user() {
  if ! id "$SVC_USER" >/dev/null 2>&1; then
    shell="$(nologin_shell)"
    if have useradd; then
      useradd --system --home-dir "$DATA_DIR" --no-create-home --shell "$shell" "$SVC_USER" 2>/dev/null \
        || useradd -r -d "$DATA_DIR" -M -s "$shell" "$SVC_USER"
    else
      addgroup -S "$SVC_USER" 2>/dev/null || true
      adduser -S -D -H -h "$DATA_DIR" -s "$shell" -G "$SVC_USER" "$SVC_USER"
    fi
    ok "Usuário de serviço '$SVC_USER' criado"
  fi
  mkdir -p "$DATA_DIR/backups" "$LOG_DIR"
  chown -R "$SVC_USER" "$DATA_DIR" "$LOG_DIR"
  chmod 750 "$DATA_DIR"
}

detect_timezone() {
  tz=""
  if have timedatectl; then tz="$(timedatectl show -p Timezone --value 2>/dev/null || true)"; fi
  [ -z "$tz" ] && [ -r /etc/timezone ] && tz="$(head -n1 /etc/timezone)"
  if [ -z "$tz" ] && [ -L /etc/localtime ]; then tz="$(readlink /etc/localtime | sed 's|.*zoneinfo/||')"; fi
  case "$tz" in ""|UTC|Etc/UTC|Universal) tz="America/Sao_Paulo" ;; esac
  echo "$tz"
}

primary_ip() {
  ip="$( (hostname -I 2>/dev/null || true) | awk '{print $1}')"
  [ -z "$ip" ] && have ip && ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  echo "${ip:-127.0.0.1}"
}

quote() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

setup_config() {
  if [ -f "$ENV_FILE" ]; then
    ok "Configuração existente mantida ($ENV_FILE)"
    PORT="$(sed -n "s/^BACKUPHUB_PORT=['\"]*\([0-9]*\).*/\1/p" "$ENV_FILE" | head -n1)"; PORT="${PORT:-8080}"
    return
  fi
  if [ -z "$ADMIN_PASSWORD" ]; then
    ADMIN_PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c 16 || true)"
    [ -n "$ADMIN_PASSWORD" ] || ADMIN_PASSWORD="Bh$(date +%s)x"
    GENERATED_PASSWORD="$ADMIN_PASSWORD"
  fi
  [ -n "$TIMEZONE" ] || TIMEZONE="$(detect_timezone)"
  [ -n "$PUBLIC_URL" ] || PUBLIC_URL="http://$(primary_ip):$PORT"
  umask 077
  cat > "$ENV_FILE" <<EOF
# Configuração do BackupHub — após alterar: reinicie o serviço
BACKUPHUB_DATA_DIR=$(quote "$DATA_DIR")
BACKUPHUB_PORT=$(quote "$PORT")
BACKUPHUB_HOST='0.0.0.0'
BACKUPHUB_TIMEZONE=$(quote "$TIMEZONE")
BACKUPHUB_PUBLIC_URL=$(quote "$PUBLIC_URL")
BACKUPHUB_MAX_PARALLEL_JOBS='4'
# Sincronização automática do inventário AWS/GCP, em minutos (0 desativa)
BACKUPHUB_CLOUD_SYNC_MINUTES='60'
# Senha usada apenas na criação do usuário admin (primeira execução)
BACKUPHUB_ADMIN_USER='admin'
BACKUPHUB_ADMIN_PASSWORD=$(quote "$ADMIN_PASSWORD")
# Alertas de falha (Slack, Teams, Discord, Google Chat...)
#BACKUPHUB_WEBHOOK_URL=''
# Use '1' quando o painel for servido via HTTPS (proxy reverso / load balancer)
#BACKUPHUB_COOKIE_SECURE='1'
EOF
  umask 022
  chmod 600 "$ENV_FILE"
  ok "Configuração criada em $ENV_FILE"
}

write_launcher() {
  mkdir -p "$PREFIX/bin"
  cat > "$PREFIX/bin/backuphub-server" <<EOF
#!/bin/sh
# Inicia o BackupHub com a configuração de $ENV_FILE
set -a
[ -r "$ENV_FILE" ] && . "$ENV_FILE"
set +a
: "\${BACKUPHUB_PORT:=8080}"
: "\${BACKUPHUB_HOST:=0.0.0.0}"
cd "$PREFIX/app"
exec "$PREFIX/venv/bin/gunicorn" --workers 1 --threads 32 --timeout 0 \\
  --bind "\${BACKUPHUB_HOST}:\${BACKUPHUB_PORT}" --access-logfile - backuphub.wsgi:app
EOF
  chmod 755 "$PREFIX/bin/backuphub-server"
  # O serviço lê a configuração (contém a senha inicial): permite leitura ao usuário do serviço
  chown root:"$(id -gn "$SVC_USER")" "$ENV_FILE" && chmod 640 "$ENV_FILE"
}

# ----------------------------------------------------------------- serviço
install_service() {
  if [ "$NO_SERVICE" -eq 1 ] || [ "$INIT" = "none" ]; then
    warn "Serviço não registrado. Para iniciar manualmente: su -s /bin/sh $SVC_USER -c $PREFIX/bin/backuphub-server"
    return
  fi
  case "$INIT" in
    systemd)
      cat > /etc/systemd/system/backuphub.service <<EOF
[Unit]
Description=BackupHub - backup de servidores on-premise, AWS e GCP
After=network-online.target
Wants=network-online.target

[Service]
User=$SVC_USER
ExecStart=$PREFIX/bin/backuphub-server
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
      systemctl daemon-reload
      systemctl enable backuphub >/dev/null 2>&1
      systemctl restart backuphub
      STATUS_CMD="systemctl status backuphub"; LOGS_CMD="journalctl -u backuphub -f"; RESTART_CMD="systemctl restart backuphub" ;;
    openrc)
      cat > /etc/init.d/backuphub <<EOF
#!/sbin/openrc-run
description="BackupHub"
command="$PREFIX/bin/backuphub-server"
command_user="$SVC_USER"
command_background=true
pidfile="/run/backuphub.pid"
output_log="$LOG_DIR/backuphub.log"
error_log="$LOG_DIR/backuphub.log"
depend() { need net; }
EOF
      chmod 755 /etc/init.d/backuphub
      rc-update add backuphub default >/dev/null 2>&1 || true
      rc-service backuphub restart >/dev/null 2>&1 || rc-service backuphub start
      STATUS_CMD="rc-service backuphub status"; LOGS_CMD="tail -f $LOG_DIR/backuphub.log"; RESTART_CMD="rc-service backuphub restart" ;;
    sysv)
      cat > /etc/init.d/backuphub <<EOF
#!/bin/sh
### BEGIN INIT INFO
# Provides:          backuphub
# Required-Start:    \$network \$remote_fs
# Required-Stop:     \$network \$remote_fs
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: BackupHub
### END INIT INFO
# chkconfig: 2345 90 10
PID=/var/run/backuphub.pid
LOG=$LOG_DIR/backuphub.log
start() {
  if [ -f \$PID ] && kill -0 "\$(cat \$PID)" 2>/dev/null; then echo "BackupHub já está em execução"; return 0; fi
  su -s /bin/sh $SVC_USER -c "nohup $PREFIX/bin/backuphub-server >>\$LOG 2>&1 & echo \\\$!" > \$PID
  echo "BackupHub iniciado"
}
stop() { [ -f \$PID ] && kill "\$(cat \$PID)" 2>/dev/null; rm -f \$PID; echo "BackupHub parado"; }
case "\$1" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 2; start ;;
  status) if [ -f \$PID ] && kill -0 "\$(cat \$PID)" 2>/dev/null; then echo "em execução"; else echo "parado"; exit 3; fi ;;
  *) echo "Uso: \$0 {start|stop|restart|status}"; exit 2 ;;
esac
EOF
      chmod 755 /etc/init.d/backuphub
      if have chkconfig; then chkconfig --add backuphub; elif have update-rc.d; then update-rc.d backuphub defaults >/dev/null; fi
      /etc/init.d/backuphub restart >/dev/null
      STATUS_CMD="/etc/init.d/backuphub status"; LOGS_CMD="tail -f $LOG_DIR/backuphub.log"; RESTART_CMD="/etc/init.d/backuphub restart" ;;
  esac
  ok "Serviço registrado ($INIT) e iniciado"
}

open_firewall() {
  fw_hint=""
  if have firewall-cmd && firewall-cmd --state >/dev/null 2>&1; then
    if [ "$OPEN_FW" -eq 1 ]; then firewall-cmd --permanent --add-port="$PORT/tcp" >/dev/null && firewall-cmd --reload >/dev/null && ok "Porta $PORT liberada no firewalld"
    else fw_hint="firewall-cmd --permanent --add-port=$PORT/tcp && firewall-cmd --reload"; fi
  elif have ufw && ufw status 2>/dev/null | grep -q "Status: active"; then
    if [ "$OPEN_FW" -eq 1 ]; then ufw allow "$PORT/tcp" >/dev/null && ok "Porta $PORT liberada no ufw"
    else fw_hint="ufw allow $PORT/tcp"; fi
  fi
}

wait_health() {
  [ "$NO_SERVICE" -eq 1 ] || [ "$INIT" = "none" ] && return 0
  i=0
  while [ $i -lt 40 ]; do
    if "$PREFIX/venv/bin/python" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:$PORT/api/health', timeout=2)" 2>/dev/null; then
      ok "BackupHub respondendo na porta $PORT"; return 0
    fi
    i=$((i + 1)); sleep 1
  done
  warn "O serviço não respondeu em 40s. Verifique: ${LOGS_CMD:-os logs}"
}

# ----------------------------------------------------------------- desinstalação
uninstall() {
  log "Removendo o BackupHub"
  if [ "$INIT" = "systemd" ] && [ -f /etc/systemd/system/backuphub.service ]; then
    systemctl disable --now backuphub >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/backuphub.service; systemctl daemon-reload
  elif [ -f /etc/init.d/backuphub ]; then
    /etc/init.d/backuphub stop >/dev/null 2>&1 || rc-service backuphub stop >/dev/null 2>&1 || true
    rc-update del backuphub >/dev/null 2>&1 || true
    if have chkconfig; then chkconfig --del backuphub >/dev/null 2>&1 || true; elif have update-rc.d; then update-rc.d -f backuphub remove >/dev/null 2>&1 || true; fi
    rm -f /etc/init.d/backuphub
  fi
  rm -rf "$PREFIX"
  if [ "$PURGE" -eq 1 ]; then
    rm -rf "$DATA_DIR" "$LOG_DIR" "$ENV_FILE"
    userdel "$SVC_USER" >/dev/null 2>&1 || deluser "$SVC_USER" >/dev/null 2>&1 || true
    ok "BackupHub removido, incluindo dados e configuração"
  else
    ok "BackupHub removido. Dados mantidos em $DATA_DIR e configuração em $ENV_FILE (use --purge para apagar)"
  fi
}

# ----------------------------------------------------------------- principal
detect_system
printf '\n%sBackupHub — instalador%s\n' "$B" "$N"
printf '  Sistema: %s | Arquitetura: %s | libc: %s | Pacotes: %s | Init: %s\n\n' "$OS_NAME" "$ARCH" "$LIBC" "$PKG" "$INIT"

if [ "$ACTION" = "uninstall" ]; then uninstall; exit 0; fi

BUNDLE_DIR="${SCRIPT_DIR:-}"
if [ -n "$BUNDLE_DIR" ] && [ -f "$BUNDLE_DIR/python.tar.gz" ] && [ -d "$BUNDLE_DIR/wheels" ]; then
  OFFLINE=1; log "Pacote offline detectado: instalação sem internet"
elif [ "$OFFLINE" -eq 1 ]; then
  die "--offline requer o pacote completo (python.tar.gz e wheels/ ao lado do install.sh)"
fi
if [ "$OFFLINE" -eq 1 ] && [ "$LIBC" = "musl" ]; then
  die "O pacote offline é para distribuições com glibc. No Alpine, instale online."
fi

TMP="$(mktemp -d 2>/dev/null || echo /tmp/backuphub-install.$$)"; mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT INT TERM

UPGRADE=0; [ -d "$PREFIX/app" ] && UPGRADE=1
STATUS_CMD=""; LOGS_CMD=""; RESTART_CMD=""

ensure_prereqs
mkdir -p "$PREFIX"
setup_python
fetch_source
setup_venv
setup_user
setup_config
write_launcher
install_service
open_firewall
wait_health

IP="$(primary_ip)"
printf '\n%s%s BackupHub %s com sucesso!%s\n\n' "$G" "$B" "$([ $UPGRADE -eq 1 ] && echo atualizado || echo instalado)" "$N"
printf '  Painel:        http://%s:%s\n' "$IP" "$PORT"
printf '  Usuário:       admin\n'
if [ -n "$GENERATED_PASSWORD" ]; then
  printf '  Senha inicial: %s%s%s   (anote! também está em %s)\n' "$B" "$GENERATED_PASSWORD" "$N" "$ENV_FILE"
elif [ "$UPGRADE" -eq 0 ]; then
  printf '  Senha inicial: a informada em --admin-password\n'
fi
printf '  Configuração:  %s\n  Dados:         %s\n  Backups locais: %s/backups\n' "$ENV_FILE" "$DATA_DIR" "$DATA_DIR"
[ -n "$STATUS_CMD" ] && printf '  Status:        %s\n  Logs:          %s\n  Reiniciar:     %s\n' "$STATUS_CMD" "$LOGS_CMD" "$RESTART_CMD"
[ -n "${fw_hint:-}" ] && printf '\n  %sFirewall ativo:%s libere a porta com: %s\n' "$Y" "$N" "$fw_hint"
printf '\n  Atualizar: execute o instalador novamente | Remover: sh %s/app/install.sh --uninstall\n\n' "$PREFIX"
