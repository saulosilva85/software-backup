#!/usr/bin/env bash
# Prepara um servidor Linux para ser protegido pelo BackupHub (sem agente).
# Cria o usuário "backuphub", instala a chave pública do BackupHub e libera
# somente o tar via sudo (sem senha).
#
# Uso (como root):  ./prepare-linux.sh "ssh-ed25519 AAAA... backuphub"
set -euo pipefail
PUBKEY="${1:?informe a chave pública SSH do BackupHub}"
USER_NAME="${BACKUPHUB_USER:-backuphub}"

id "$USER_NAME" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$USER_NAME"
install -d -m 700 -o "$USER_NAME" -g "$USER_NAME" "/home/$USER_NAME/.ssh"
grep -qxF "$PUBKEY" "/home/$USER_NAME/.ssh/authorized_keys" 2>/dev/null || echo "$PUBKEY" >> "/home/$USER_NAME/.ssh/authorized_keys"
chown "$USER_NAME:$USER_NAME" "/home/$USER_NAME/.ssh/authorized_keys"
chmod 600 "/home/$USER_NAME/.ssh/authorized_keys"

cat > "/etc/sudoers.d/backuphub" <<SUDO
# BackupHub: leitura completa do sistema para backup e extração na restauração.
# Atenção: equivale a acesso root para este usuário — proteja a chave privada.
$USER_NAME ALL=(root) NOPASSWD: /bin/sh -c *, /usr/bin/sh -c *
SUDO
chmod 440 /etc/sudoers.d/backuphub
visudo -cf /etc/sudoers.d/backuphub
echo "OK: cadastre no BackupHub uma credencial SSH com usuário '$USER_NAME', a chave privada correspondente e 'Executar com sudo' marcado."
