"""Camada de persistência em SQLite (sem dependências externas).

Cada thread recebe sua própria conexão; o modo WAL permite leituras
concorrentes enquanto os jobs de backup gravam o progresso.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_local = threading.local()
_db_path: str | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,          -- ssh | winrm | aws | gcp
    description TEXT,
    data_enc TEXT NOT NULL,      -- JSON criptografado (Fernet)
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS machines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    platform TEXT NOT NULL DEFAULT 'linux',   -- linux | windows
    provider TEXT NOT NULL DEFAULT 'onprem',  -- onprem | aws | gcp
    credential_id INTEGER REFERENCES credentials(id) ON DELETE SET NULL,
    cloud_credential_id INTEGER REFERENCES credentials(id) ON DELETE SET NULL,
    instance_id TEXT,
    region TEXT,
    os TEXT,
    cpu INTEGER,
    memory_mb INTEGER,
    disks TEXT,           -- JSON
    ip_private TEXT,
    ip_public TEXT,
    state TEXT,
    tags TEXT,            -- JSON
    extra TEXT,           -- JSON
    inventory_status TEXT,
    inventory_message TEXT,
    last_inventory_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(provider, instance_id)
);

CREATE TABLE IF NOT EXISTS destinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,           -- s3 | gcs | local
    config TEXT NOT NULL,         -- JSON (bucket, prefix, region, path...)
    credential_id INTEGER REFERENCES credentials(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    mode TEXT NOT NULL DEFAULT 'auto',     -- auto | files | snapshot
    days TEXT NOT NULL,                    -- JSON [0..6] (0 = segunda)
    times TEXT NOT NULL,                   -- JSON ["02:00", ...]
    all_machines INTEGER NOT NULL DEFAULT 0,
    machine_ids TEXT NOT NULL DEFAULT '[]',
    paths_linux TEXT NOT NULL DEFAULT '["/etc", "/home", "/var/www"]',
    paths_windows TEXT NOT NULL DEFAULT '["C:\\\\Users"]',
    excludes TEXT NOT NULL DEFAULT '[]',
    destination_id INTEGER REFERENCES destinations(id) ON DELETE SET NULL,
    retention_count INTEGER NOT NULL DEFAULT 7,
    next_run_at TEXT,
    last_run_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    policy_id INTEGER REFERENCES policies(id) ON DELETE SET NULL,
    policy_name TEXT,
    machine_id INTEGER REFERENCES machines(id) ON DELETE SET NULL,
    machine_name TEXT,
    kind TEXT NOT NULL DEFAULT 'backup',      -- backup | restore
    trigger TEXT NOT NULL DEFAULT 'manual',   -- manual | schedule
    mode TEXT,                                -- files | snapshot
    status TEXT NOT NULL DEFAULT 'queued',    -- queued | running | success | warning | failed
    destination_id INTEGER REFERENCES destinations(id) ON DELETE SET NULL,
    source_job_id INTEGER,                    -- restauração: job de backup de origem
    size_bytes INTEGER,
    sha256 TEXT,
    artifact TEXT,                            -- chave do objeto ou IDs dos snapshots
    options TEXT,                             -- JSON (caminhos, destino de restauração...)
    message TEXT,
    log TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_machine ON jobs(machine_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

JSON_FIELDS = {
    "disks", "tags", "extra", "config", "days", "times", "machine_ids",
    "paths_linux", "paths_windows", "excludes", "options",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_db(path: str) -> None:
    global _db_path
    _db_path = path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    close_connection()
    conn = connection()
    conn.executescript(SCHEMA)
    conn.commit()


def connection() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None or getattr(_local, "path", None) != _db_path:
        if _db_path is None:
            raise RuntimeError("Banco de dados não inicializado")
        conn = sqlite3.connect(_db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
        _local.path = _db_path
    return conn


def close_connection() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def _decode(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    for key in JSON_FIELDS & data.keys():
        if isinstance(data[key], str):
            try:
                data[key] = json.loads(data[key])
            except ValueError:
                pass
    return data


def _encode(values: dict) -> dict:
    out = {}
    for key, value in values.items():
        if key in JSON_FIELDS and not isinstance(value, str) and value is not None:
            value = json.dumps(value)
        elif isinstance(value, bool):
            value = int(value)
        out[key] = value
    return out


def query(sql: str, params=()) -> list[dict]:
    return [_decode(r) for r in connection().execute(sql, params).fetchall()]


def query_one(sql: str, params=()) -> dict | None:
    return _decode(connection().execute(sql, params).fetchone())


def execute(sql: str, params=()) -> int:
    conn = connection()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


def execute_rowcount(sql: str, params=()) -> int:
    conn = connection()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.rowcount


def insert(table: str, values: dict) -> int:
    values = _encode(values)
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    return execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))


def update(table: str, row_id: int, values: dict) -> None:
    if not values:
        return
    values = _encode(values)
    sets = ", ".join(f"{k} = ?" for k in values)
    execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*values.values(), row_id))


def get(table: str, row_id: int) -> dict | None:
    return query_one(f"SELECT * FROM {table} WHERE id = ?", (row_id,))


def delete(table: str, row_id: int) -> None:
    execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
