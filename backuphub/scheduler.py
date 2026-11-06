"""Agendador de backups.

Cada política define dias da semana (0 = segunda ... 6 = domingo) e horários
("HH:MM"), no fuso configurado. Exemplos:
- diário às 02:00            → days=[0..6], times=["02:00"]
- 1x por semana (domingo)    → days=[6],    times=["01:00"]
- 2x por semana (ter e sex)  → days=[1, 4], times=["23:30"]
- 2x por dia                 → days=[0..6], times=["06:00", "18:00"]

O próximo disparo fica gravado em `policies.next_run_at` (UTC). A "reserva"
do disparo é feita com UPDATE condicional, evitando execuções duplicadas
mesmo se houver mais de um processo rodando.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, jobs
from .config import Config

log = logging.getLogger("backuphub.scheduler")
_sync_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cloud-sync")
_sync_running: set[int] = set()
_sync_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()


def parse_time(value: str) -> tuple[int, int]:
    hh, mm = value.strip().split(":")
    h, m = int(hh), int(mm)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"Horário inválido: {value}")
    return h, m


def next_run(days: list[int], times: list[str], after: datetime, tz: str | None = None) -> datetime | None:
    """Próximo horário (UTC) estritamente depois de `after`."""
    if not days or not times:
        return None
    zone = ZoneInfo(tz or Config.TIMEZONE)
    local = after.astimezone(zone)
    slots = sorted(parse_time(t) for t in times)
    for offset in range(0, 8):
        day = (local + timedelta(days=offset)).date()
        if day.weekday() not in days:
            continue
        for h, m in slots:
            candidate = datetime(day.year, day.month, day.day, h, m, tzinfo=zone)
            if candidate > local:
                return candidate.astimezone(timezone.utc).replace(microsecond=0)
    return None


def upcoming(days, times, count: int = 5, tz: str | None = None) -> list[str]:
    out, cursor = [], datetime.now(timezone.utc)
    for _ in range(count):
        nxt = next_run(days, times, cursor, tz)
        if not nxt:
            break
        out.append(nxt.isoformat())
        cursor = nxt
    return out


def refresh_policy(policy_id: int) -> None:
    p = db.get("policies", policy_id)
    if not p:
        return
    nxt = next_run(p["days"], p["times"], datetime.now(timezone.utc)) if p["enabled"] else None
    db.update("policies", policy_id, {"next_run_at": nxt.isoformat() if nxt else None})


def policy_machine_ids(policy: dict) -> list[int]:
    if policy["all_machines"]:
        rows = db.query("SELECT id FROM machines WHERE COALESCE(state, '') != 'terminated'")
        return [r["id"] for r in rows]
    return [int(i) for i in (policy["machine_ids"] or [])]


def tick(now: datetime | None = None) -> list[int]:
    """Dispara as políticas vencidas; retorna os IDs disparados."""
    now = now or datetime.now(timezone.utc)
    fired = []
    due = db.query("SELECT * FROM policies WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?",
                   (now.isoformat(),))
    for p in due:
        nxt = next_run(p["days"], p["times"], now)
        claimed = db.execute_rowcount(
            "UPDATE policies SET next_run_at = ?, last_run_at = ? WHERE id = ? AND next_run_at = ?",
            (nxt.isoformat() if nxt else None, now.replace(microsecond=0).isoformat(), p["id"], p["next_run_at"]))
        if not claimed:
            continue
        ids = policy_machine_ids(p)
        log.info("Política '%s' disparada para %d máquina(s)", p["name"], len(ids))
        if ids:
            jobs.enqueue_backup(ids, policy=p, trigger="schedule")
        fired.append(p["id"])
    return fired


def _run_sync(credential_id: int) -> None:
    from . import inventory
    try:
        r = inventory.sync_cloud(credential_id)
        log.info("Sincronização automática da conta %s: %s", credential_id, r)
    except Exception as exc:
        log.warning("Falha na sincronização automática da conta %s: %s", credential_id, exc)
    finally:
        with _sync_lock:
            _sync_running.discard(credential_id)


def due_cloud_syncs(now: datetime | None = None) -> list[int]:
    """Contas AWS/GCP com sincronização automática vencida."""
    minutes = Config.CLOUD_SYNC_MINUTES
    if minutes <= 0:
        return []
    now = now or datetime.now(timezone.utc)
    limit = (now - timedelta(minutes=max(minutes, 5))).isoformat()
    rows = db.query("SELECT id FROM credentials WHERE type IN ('aws', 'gcp') AND sync_enabled = 1 "
                    "AND (last_sync_at IS NULL OR last_sync_at <= ?)", (limit,))
    return [r["id"] for r in rows]


def cloud_sync_tick(now: datetime | None = None, wait: bool = False) -> list[int]:
    started = []
    for cid in due_cloud_syncs(now):
        with _sync_lock:
            if cid in _sync_running:
                continue
            _sync_running.add(cid)
        future = _sync_pool.submit(_run_sync, cid)
        if wait:
            future.result()
        started.append(cid)
    return started


def _loop() -> None:
    # Recalcula horários ao iniciar (o serviço pode ter ficado parado).
    for p in db.query("SELECT id, next_run_at FROM policies WHERE enabled = 1"):
        if not p["next_run_at"]:
            refresh_policy(p["id"])
    while not _stop.wait(Config.SCHEDULER_INTERVAL_SECONDS):
        try:
            tick()
        except Exception:
            log.exception("Erro no agendador")
        try:
            cloud_sync_tick()
        except Exception:
            log.exception("Erro na sincronização automática de nuvem")
        try:
            from . import health
            threading.Thread(target=health.tick, daemon=True, name="health").start()
        except Exception:
            log.exception("Erro na verificação de disponibilidade")


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
