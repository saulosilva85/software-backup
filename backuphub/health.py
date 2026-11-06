"""Monitor de disponibilidade: marca servidores on-premise como online/offline.

A cada BACKUPHUB_HEALTH_MINUTES (padrão 5), testa a conexão TCP nas portas de
gerenciamento (SSH 22 no Linux; WinRM/SMB/RDP no Windows). Não precisa de credencial.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import db
from .config import Config
from .inventory import network

log = logging.getLogger("backuphub.health")
_lock = threading.Lock()
_last_run: datetime | None = None


def check_machine(machine: dict) -> str:
    online = bool(machine.get("address")) and network.is_reachable(machine["address"], machine["platform"])
    new_state = "online" if online else "offline"
    values = {"state": new_state}
    if online:
        values["last_seen_at"] = db.utcnow()
    db.update("machines", machine["id"], values)
    if machine.get("state") == "online" and new_state == "offline":
        _alert_offline(machine)
    return new_state


def _alert_offline(machine: dict) -> None:
    protected = db.query_one("SELECT 1 FROM jobs WHERE machine_id = ? AND kind = 'backup' "
                             "AND status IN ('success','warning') LIMIT 1", (machine["id"],))
    if not protected:
        return
    from .jobs import send_webhook
    send_webhook(f"BackupHub: o servidor protegido *{machine['name']}* ({machine['address']}) está OFFLINE "
                 f"(não responde na rede).", {"event": "machine_offline",
                                             "machine": {"id": machine["id"], "name": machine["name"],
                                                         "address": machine["address"]}})


def check_all(ids: list[int] | None = None) -> dict:
    sql = "SELECT * FROM machines WHERE provider = 'onprem' AND address IS NOT NULL"
    params: tuple = ()
    if ids:
        sql += f" AND id IN ({','.join('?' * len(ids))})"
        params = tuple(ids)
    machines = db.query(sql, params)
    if not machines:
        return {}
    with ThreadPoolExecutor(max_workers=min(32, len(machines))) as pool:
        states = list(pool.map(check_machine, machines))
    return {m["id"]: st for m, st in zip(machines, states)}


def tick(now: datetime | None = None) -> bool:
    """Executa a verificação se o intervalo venceu (chamado pelo agendador)."""
    global _last_run
    if Config.HEALTH_CHECK_MINUTES <= 0:
        return False
    now = now or datetime.now(timezone.utc)
    if _last_run and now - _last_run < timedelta(minutes=Config.HEALTH_CHECK_MINUTES):
        return False
    if not _lock.acquire(blocking=False):
        return False
    try:
        _last_run = now
        check_all()
        return True
    finally:
        _lock.release()


def check_async(ids: list[int]) -> None:
    threading.Thread(target=lambda: _safe(ids), daemon=True, name="health-check").start()


def _safe(ids):
    try:
        check_all(ids)
    except Exception:
        log.exception("Falha ao verificar disponibilidade")
