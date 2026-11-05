"""Motor de backup.

Modos suportados:
- files:    copia diretórios/arquivos do sistema operacional (Linux via SSH + tar,
            Windows via WinRM + zip) e grava no destino (S3, GCS ou local).
- snapshot: snapshot nativo dos discos da VM na nuvem (EBS na AWS, Persistent Disk na GCP),
            sem necessidade de acesso ao sistema operacional.
- auto:     VMs de nuvem sem credencial de SO → snapshot; demais → files.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

ARCHIVE_SUFFIXES = (".tar.gz", ".zip")


def slug(value: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return (s or "item")[:max_len].strip("-")


def resolve_mode(requested: str | None, machine: dict) -> str:
    requested = requested or "auto"
    if requested != "auto":
        return requested
    if machine["provider"] in ("aws", "gcp") and not machine.get("credential_id"):
        return "snapshot"
    return "files"


def machine_folder(machine: dict, policy: dict | None) -> str:
    """Pasta do backup no destino: <maquina>-<id>/<politica|manual>."""
    m = f"{slug(machine['name'])}-{machine['id']}"
    p = f"{slug(policy['name'])}-{policy['id']}" if policy else "manual"
    return f"{m}/{p}"


def archive_key(machine: dict, policy: dict | None, platform: str, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    ext = ".zip" if platform == "windows" else ".tar.gz"
    return f"{machine_folder(machine, policy)}/{when.strftime('%Y%m%dT%H%M%SZ')}{ext}"


def apply_retention(dest, folder: str, keep: int, log) -> int:
    """Mantém apenas os `keep` arquivos mais recentes da pasta; retorna quantos foram removidos."""
    if not keep or keep <= 0:
        return 0
    items = [i for i in dest.list(folder) if i["key"].endswith(ARCHIVE_SUFFIXES)]
    items.sort(key=lambda i: i["key"], reverse=True)  # nomes são timestamps ISO
    removed = 0
    for item in items[keep:]:
        dest.delete(item["key"])
        log(f"Retenção: removido {item['key']}")
        removed += 1
    return removed
