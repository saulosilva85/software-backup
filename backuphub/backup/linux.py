"""Backup e restauração de arquivos em servidores Linux via SSH.

O servidor remoto executa `tar | gzip` e o fluxo é enviado diretamente
para o destino (multipart no S3 / upload resumível no GCS), sem gravar
arquivos temporários nem no cliente nem no BackupHub.
"""
from __future__ import annotations

import shlex
from contextlib import closing

from ..remote.ssh import SSHClient
from ..storage import CountingReader


class BackupError(RuntimeError):
    pass


def _existing_paths(ssh, paths: list[str]) -> list[str]:
    script = 'for p in "$@"; do [ -e "$p" ] && printf "%s\\n" "$p"; done; exit 0'
    cmd = f"sh -c {shlex.quote(script)} _ " + " ".join(shlex.quote(p) for p in paths)
    _, out, _ = ssh.run(cmd, timeout=60)
    return [line for line in out.splitlines() if line.strip()]


def build_tar_command(paths: list[str], excludes: list[str]) -> str:
    rel = [p.lstrip("/") or "." for p in paths]
    excl = " ".join(f"--exclude={shlex.quote(e)}" for e in excludes if e.strip())
    targets = " ".join(shlex.quote(p) for p in rel)
    gnu = f"tar -czf - --ignore-failed-read --warning=no-file-changed --warning=no-file-removed {excl} -C / {targets}"
    plain = f"tar -czf - {excl} -C / {targets}"
    return f"if tar --version 2>/dev/null | grep -q GNU; then {gnu}; else {plain}; fi"


def backup(machine: dict, secret: dict, dest, key: str, paths: list[str], excludes: list[str], log) -> dict:
    with SSHClient(machine["address"], secret) as ssh:
        found = _existing_paths(ssh, paths)
        missing = sorted(set(paths) - set(found))
        if missing:
            log("Caminhos inexistentes ignorados: " + ", ".join(missing))
        if not found:
            raise BackupError("Nenhum dos caminhos configurados existe no servidor")
        log(f"Compactando {len(found)} caminho(s): {', '.join(found)}")
        stdout, stderr, channel = ssh.stream(build_tar_command(found, excludes))
        reader = CountingReader(stdout)
        log(f"Enviando para {dest.describe()}/{key}")
        dest.upload_stream(key, reader)
        code = channel.recv_exit_status()
        err = stderr.read().decode(errors="replace").strip()
    warning = None
    if code == 1:
        warning = "Alguns arquivos mudaram durante a cópia"
    elif code != 0:
        try:
            dest.delete(key)
        except Exception:
            pass
        raise BackupError(f"tar terminou com código {code}: {err[:500]}")
    if err:
        log("Avisos do tar: " + err[:1000])
    if reader.bytes == 0:
        raise BackupError("Nenhum dado recebido do servidor")
    return {"size": reader.bytes, "sha256": reader.sha256, "warning": warning,
            "skipped": missing}


def restore(machine: dict, secret: dict, dest, key: str, target: str, log) -> dict:
    target = target or "/"
    with SSHClient(machine["address"], secret) as ssh:
        cmd = f"mkdir -p {shlex.quote(target)} && tar -xzf - -C {shlex.quote(target)}"
        log(f"Baixando {key} e extraindo em {target}")
        with closing(dest.open_read(key)) as reader:
            code, _out, err, total = ssh.stream_in(cmd, reader)
    if code != 0:
        raise BackupError(f"Falha na extração (código {code}): {err.strip()[:500]}")
    return {"size": total}
