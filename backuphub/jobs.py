"""Fila e execução de jobs de backup/restauração em threads de trabalho."""
from __future__ import annotations

import json
import logging
import threading
import traceback
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import db
from .backup import apply_retention, archive_key, linux, machine_folder, resolve_mode, snapshots, windows
from .config import Config
from .security import credential_secret
from .storage import open_destination

log = logging.getLogger("backuphub.jobs")

_executor: ThreadPoolExecutor | None = None
_machine_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def init(max_workers: int | None = None) -> None:
    global _executor
    _executor = ThreadPoolExecutor(max_workers=max_workers or Config.MAX_PARALLEL_JOBS,
                                   thread_name_prefix="backup-job")
    # Jobs que estavam em execução quando o serviço parou não serão retomados.
    db.execute("UPDATE jobs SET status = 'failed', message = 'Interrompido por reinício do serviço', "
               "finished_at = ? WHERE status IN ('queued', 'running')", (db.utcnow(),))


def shutdown() -> None:
    if _executor:
        _executor.shutdown(wait=False, cancel_futures=True)


def _machine_lock(machine_id: int) -> threading.Lock:
    with _locks_guard:
        return _machine_locks.setdefault(machine_id, threading.Lock())


def append_log(job_id: int, message: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
    db.execute("UPDATE jobs SET log = log || ? WHERE id = ?", (line, job_id))


def _submit(fn, *args):
    if _executor is None:
        init()
    _executor.submit(fn, *args)


# ------------------------------------------------------------------ Enfileirar
def enqueue_backup(machine_ids: list[int], policy: dict | None = None, trigger: str = "manual",
                   overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    source = policy or {}
    options = {
        "mode": overrides.get("mode") or source.get("mode") or "auto",
        "destination_id": overrides.get("destination_id") or source.get("destination_id"),
        "paths_linux": overrides.get("paths_linux") or source.get("paths_linux") or ["/etc", "/home"],
        "paths_windows": overrides.get("paths_windows") or source.get("paths_windows") or ["C:\\Users"],
        "excludes": overrides.get("excludes") if overrides.get("excludes") is not None else (source.get("excludes") or []),
        "retention_count": overrides.get("retention_count") or source.get("retention_count") or 0,
    }
    run_id = uuid.uuid4().hex
    job_ids = []
    for mid in machine_ids:
        machine = db.get("machines", mid)
        if not machine:
            continue
        job_id = db.insert("jobs", {
            "run_id": run_id, "kind": "backup", "trigger": trigger,
            "policy_id": policy["id"] if policy else None, "policy_name": policy["name"] if policy else None,
            "machine_id": mid, "machine_name": machine["name"],
            "mode": resolve_mode(options["mode"], machine), "status": "queued",
            "destination_id": options["destination_id"], "options": options, "created_at": db.utcnow(),
        })
        job_ids.append(job_id)
        _submit(run_backup, job_id)
    return {"run_id": run_id, "job_ids": job_ids}


def enqueue_restore(source_job_id: int, target_machine_id: int | None, target_path: str) -> int:
    src = db.get("jobs", source_job_id)
    if not src or src["kind"] != "backup" or src["status"] not in ("success", "warning"):
        raise ValueError("Selecione um backup concluído com sucesso")
    if src["mode"] != "files":
        raise ValueError("Restauração automática está disponível para backups de arquivos. "
                         "Para snapshots, crie um volume/disco a partir do snapshot no console da nuvem.")
    machine_id = target_machine_id or src["machine_id"]
    machine = db.get("machines", machine_id)
    if not machine:
        raise ValueError("Máquina de destino não encontrada")
    job_id = db.insert("jobs", {
        "run_id": uuid.uuid4().hex, "kind": "restore", "trigger": "manual", "machine_id": machine_id,
        "machine_name": machine["name"], "mode": "files", "status": "queued",
        "destination_id": src["destination_id"], "source_job_id": source_job_id, "artifact": src["artifact"],
        "options": {"target_path": target_path}, "created_at": db.utcnow(),
    })
    _submit(run_restore, job_id)
    return job_id


# ------------------------------------------------------------------ Execução
def _start(job_id: int) -> dict:
    db.update("jobs", job_id, {"status": "running", "started_at": db.utcnow()})
    return db.get("jobs", job_id)


def _finish(job_id: int, status: str, **values) -> None:
    db.update("jobs", job_id, {"status": status, "finished_at": db.utcnow(), **values})
    if status in ("failed", "warning"):
        _notify(db.get("jobs", job_id))


def send_webhook(text: str, payload: dict | None = None) -> None:
    """Envia um aviso ao webhook configurado (Slack, Teams, Discord, Google Chat...)."""
    url = Config.WEBHOOK_URL
    if not url:
        return
    body = json.dumps({"text": text, **(payload or {})}, default=str).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).close()
    except Exception as exc:  # notificação nunca derruba o processo
        log.warning("Falha ao enviar webhook: %s", exc)


def _notify(job: dict) -> None:
    text = (f"BackupHub: {job['kind']} de *{job['machine_name']}* terminou com status "
            f"*{job['status']}* — {job.get('message') or ''}")
    send_webhook(text, {"job": {k: job[k] for k in ("id", "machine_name", "status", "message",
                                                     "policy_name", "kind")}})


def run_backup(job_id: int) -> None:
    job = db.get("jobs", job_id)
    machine = db.get("machines", job["machine_id"]) if job else None
    if not machine:
        _finish(job_id, "failed", message="Máquina removida do inventário")
        return
    with _machine_lock(machine["id"]):
        _start(job_id)
        opts = job.get("options") or {}
        policy = db.get("policies", job["policy_id"]) if job.get("policy_id") else None
        say = lambda msg: append_log(job_id, msg)  # noqa: E731
        try:
            if machine.get("state") == "terminated":
                raise RuntimeError("A instância não existe mais na nuvem")
            say(f"Iniciando backup de {machine['name']} ({machine['provider']}/{machine['platform']}) "
                f"modo={job['mode']}")
            keep = int(opts.get("retention_count") or 0)
            if job["mode"] == "snapshot":
                _, secret = credential_secret(machine.get("cloud_credential_id"))
                if machine["provider"] == "aws":
                    res = snapshots.aws_backup(machine, secret, policy, job["run_id"], keep, say)
                elif machine["provider"] == "gcp":
                    res = snapshots.gcp_backup(machine, secret, policy, job["run_id"], keep, say)
                else:
                    raise RuntimeError("Snapshot disponível apenas para VMs AWS/GCP")
                artifact, sha = res["artifact"], None
            else:
                cred, secret = credential_secret(machine.get("credential_id"))
                if not cred:
                    raise RuntimeError("Máquina sem credencial SSH/WinRM associada")
                if not opts.get("destination_id"):
                    raise RuntimeError("Nenhum destino de backup definido")
                if not machine.get("address"):
                    raise RuntimeError("Máquina sem endereço IP/hostname")
                dest = open_destination(opts["destination_id"])
                key = archive_key(machine, policy, machine["platform"])
                if machine["platform"] == "windows":
                    res = windows.backup(machine, secret, dest, key, opts.get("paths_windows") or [],
                                         opts.get("excludes") or [], say)
                else:
                    res = linux.backup(machine, secret, dest, key, opts.get("paths_linux") or [],
                                       opts.get("excludes") or [], say)
                artifact, sha = key, res.get("sha256")
                say(f"Upload concluído: {res['size']} bytes, sha256={sha}")
                removed = apply_retention(dest, machine_folder(machine, policy), keep, say)
                if removed:
                    say(f"Retenção aplicada: {removed} backup(s) antigo(s) removido(s)")
            status = "warning" if res.get("warning") else "success"
            message = res.get("warning") or "Backup concluído"
            if res.get("skipped"):
                message += f" ({len(res['skipped'])} caminho(s) inexistente(s) ignorado(s))"
            say(message)
            _finish(job_id, status, message=message, size_bytes=res.get("size"), sha256=sha, artifact=artifact)
        except Exception as exc:
            say("ERRO: " + str(exc))
            log.debug(traceback.format_exc())
            _finish(job_id, "failed", message=str(exc)[:500])


def run_restore(job_id: int) -> None:
    job = db.get("jobs", job_id)
    machine = db.get("machines", job["machine_id"])
    with _machine_lock(machine["id"]):
        _start(job_id)
        say = lambda msg: append_log(job_id, msg)  # noqa: E731
        try:
            cred, secret = credential_secret(machine.get("credential_id"))
            if not cred:
                raise RuntimeError("Máquina sem credencial SSH/WinRM associada")
            dest = open_destination(job["destination_id"])
            target = (job.get("options") or {}).get("target_path")
            mod = windows if job["artifact"].endswith(".zip") else linux
            if (machine["platform"] == "windows") != (mod is windows):
                raise RuntimeError("O backup selecionado é de outra plataforma (Linux/Windows)")
            res = mod.restore(machine, secret, dest, job["artifact"], target, say)
            say("Restauração concluída")
            _finish(job_id, "success", message="Restauração concluída", size_bytes=res.get("size"))
        except Exception as exc:
            say("ERRO: " + str(exc))
            _finish(job_id, "failed", message=str(exc)[:500])
