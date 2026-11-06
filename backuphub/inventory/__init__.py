"""Orquestração do inventário: on-premise (SSH/WinRM) e nuvem (AWS/GCP)."""
from __future__ import annotations

from .. import db
from ..security import credential_secret

UPDATABLE = ("hostname", "os", "cpu", "memory_mb", "disks", "ip_private", "ip_public", "state", "extra")


def normalize_disks(disks):
    """Garante tamanho, usado e livre (GB) em todos os discos."""
    out = []
    for d in disks or []:
        d = dict(d)
        size, used, free = d.get("size_gb"), d.get("used_gb"), d.get("free_gb")
        if free is None and size is not None and used is not None:
            d["free_gb"] = round(size - used, 1)
        if used is None and size is not None and free is not None:
            d["used_gb"] = round(size - free, 1)
        out.append(d)
    return out


def _collect_os(machine: dict, secret: dict) -> dict:
    if machine["platform"] == "windows":
        from . import windows
        return windows.collect(machine["address"], secret)
    from . import linux
    return linux.collect(machine["address"], secret)


_NETWORK_ERRORS = ("timed out", "timeout", "refused", "unreachable", "no route", "name or service not known",
                   "nodename nor servname", "connection reset", "max retries exceeded", "failed to establish",
                   "unable to connect", "network is unreachable", "host is down")


def _is_network_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(t in text for t in _NETWORK_ERRORS)


class NoCredentials(Exception):
    """Não há credencial cadastrada para a plataforma: não é uma falha, apenas falta configuração."""


def candidate_credentials(machine: dict) -> list[dict]:
    """Credenciais cadastradas compatíveis com a plataforma da máquina (SSH para Linux, WinRM para Windows)."""
    ctype = "winrm" if machine["platform"] == "windows" else "ssh"
    return db.query("SELECT id, name FROM credentials WHERE type = ? ORDER BY id", (ctype,))


def collect_machine(machine_id: int) -> dict:
    """Atualiza o inventário de uma máquina conectando-se a ela.

    Sem credencial associada, testa automaticamente as credenciais cadastradas do tipo
    certo (SSH/WinRM) e associa à máquina a primeira que funcionar.
    """
    machine = db.get("machines", machine_id)
    if not machine:
        raise ValueError("Máquina não encontrada")
    cred, secret = credential_secret(machine.get("credential_id"))
    try:
        if not cred:
            if machine["provider"] in ("aws", "gcp"):
                # VM de nuvem sem credencial de SO: dados vêm da API da nuvem (backup por snapshot).
                if machine.get("cloud_credential_id"):
                    sync_cloud(machine["cloud_credential_id"])
                    return db.get("machines", machine_id)
                raise ValueError("Associe uma credencial SSH/WinRM à máquina para coletar o inventário")
            data, found_id = _try_credentials(machine)
            db.update("machines", machine_id, {"credential_id": found_id})
        else:
            data = _collect_os(machine, secret)
        _save_collected(machine, data)
    except NoCredentials:
        db.update("machines", machine_id, {"inventory_status": "pending", "inventory_message": None})
        return db.get("machines", machine_id)
    except Exception as exc:
        db.update("machines", machine_id, {
            "inventory_status": "error",
            "inventory_message": str(exc)[:500],
            "last_inventory_at": db.utcnow(),
        })
        raise
    return db.get("machines", machine_id)


def _try_credentials(machine: dict) -> tuple[dict, int]:
    kind = "WinRM (Windows)" if machine["platform"] == "windows" else "SSH (Linux)"
    candidates = candidate_credentials(machine)
    if not candidates:
        raise NoCredentials(f"Nenhuma credencial {kind} cadastrada")
    failures = []
    for c in candidates:
        _, secret = credential_secret(c["id"])
        try:
            return _collect_os(machine, secret), c["id"]
        except Exception as exc:
            if _is_network_error(exc):
                port = "5985 (WinRM)" if machine["platform"] == "windows" else "22 (SSH)"
                raise RuntimeError(f"Não foi possível conectar em {machine['address']} na porta {port}: "
                                   f"{str(exc)[:200]}") from exc
            failures.append(f"'{c['name']}': {str(exc)[:120]}")
    raise ValueError(f"Nenhuma credencial {kind} cadastrada funcionou nesta máquina — " + "; ".join(failures))


def _save_collected(machine: dict, data: dict) -> None:
    data["disks"] = normalize_disks(data.get("disks"))
    values = {k: data[k] for k in UPDATABLE if data.get(k) is not None}
    # Máquinas importadas sem nome (nome = IP) passam a usar o hostname real
    if data.get("hostname") and machine["name"] in (machine.get("address"), machine.get("hostname"), None, ""):
        values["name"] = data["hostname"]
    if machine["provider"] != "onprem":
        values.pop("state", None)
        values.pop("ip_public", None)
        # Mantém dados da nuvem e acrescenta os do SO.
        values["extra"] = {**(machine.get("extra") or {}), **(data.get("extra") or {})}
        if machine.get("disks"):  # discos da nuvem (volumes) têm prioridade
            values.pop("disks", None)
    else:
        values["extra"] = {**(machine.get("extra") or {}), **(data.get("extra") or {})}
        values["last_seen_at"] = db.utcnow()
    values.update(inventory_status="ok", inventory_message=None, last_inventory_at=db.utcnow())
    db.update("machines", machine["id"], values)


def _is_protected(machine_id: int) -> dict | None:
    """Retorna o último backup bem-sucedido da máquina, ou None se ela nunca teve backup."""
    return db.query_one("SELECT id, finished_at, mode, artifact FROM jobs WHERE machine_id = ? AND kind = 'backup' "
                        "AND status IN ('success', 'warning') ORDER BY id DESC LIMIT 1", (machine_id,))


def _alert_removed(machines: list[dict], cred: dict) -> None:
    from ..jobs import send_webhook
    for m in machines:
        last = _is_protected(m["id"])
        if not last:
            continue
        when = (last["finished_at"] or "")[:16].replace("T", " ")
        send_webhook(
            f"BackupHub: a máquina protegida *{m['name']}* ({m['instance_id']}) foi REMOVIDA da conta "
            f"{cred['type'].upper()} '{cred['name']}'. Último backup disponível: {when} UTC "
            f"({'snapshot' if last['mode'] == 'snapshot' else 'arquivos'}).",
            {"event": "machine_removed", "machine": {"id": m["id"], "name": m["name"],
                                                     "instance_id": m["instance_id"]},
             "last_backup": last})


def sync_cloud(credential_id: int) -> dict:
    """Sincroniza as VMs de uma conta AWS/GCP com o inventário.

    - Instâncias novas são adicionadas; as existentes, atualizadas.
    - Instâncias que deixaram de existir (EC2 terminada, VM excluída) são marcadas como
      "removidas": saem do inventário e dos backups, mas o histórico e os backups são mantidos.
    - Se a máquina tinha backup, é enviado um alerta (webhook).
    """
    cred, secret = credential_secret(credential_id)
    if not cred:
        raise ValueError("Credencial não encontrada")
    if cred["type"] not in ("aws", "gcp"):
        raise ValueError("A credencial precisa ser do tipo AWS ou GCP")
    now = db.utcnow()
    try:
        if cred["type"] == "aws":
            from . import aws
            found, errors = aws.list_instances(secret)
        else:
            from . import gcp
            found, errors = gcp.list_instances(secret)
    except Exception as exc:
        db.update("credentials", credential_id, {"last_sync_at": now, "last_sync_status": "error",
                                                 "last_sync_message": str(exc)[:500]})
        raise

    provider = cred["type"]
    created = updated = 0
    seen = set()
    newly_removed = []
    for item in found:
        seen.add(item["instance_id"])
        existing = db.query_one("SELECT id, name, instance_id, state FROM machines WHERE provider = ? "
                                "AND instance_id = ?", (provider, item["instance_id"]))
        values = {**item, "cloud_credential_id": credential_id, "inventory_status": "ok",
                  "inventory_message": None, "last_inventory_at": now}
        if item.get("state") == "terminated":  # EC2 terminada ainda listada pela AWS (≈1 hora)
            values["terminated_at"] = now
            if existing and existing["state"] != "terminated":
                newly_removed.append(existing)
        else:
            values["terminated_at"] = None
        if existing:
            db.update("machines", existing["id"], values)
            updated += 1
        else:
            db.insert("machines", {**values, "provider": provider, "created_at": now})
            created += 1

    # Instâncias que sumiram da conta. Só aplica quando a listagem foi completa (sem erros),
    # para que uma falha de permissão em uma região não "esconda" máquinas existentes.
    if not errors:
        for m in db.query("SELECT id, name, instance_id, state FROM machines WHERE provider = ? "
                          "AND cloud_credential_id = ?", (provider, credential_id)):
            if m["instance_id"] not in seen and m["state"] != "terminated":
                db.update("machines", m["id"], {"state": "terminated", "terminated_at": now,
                                                "last_inventory_at": now})
                newly_removed.append(m)

    _alert_removed(newly_removed, cred)
    status = "warning" if errors else "ok"
    message = (f"{len(found)} instância(s): {created} nova(s), {updated} atualizada(s), "
               f"{len(newly_removed)} removida(s)")
    if errors:
        message += " — " + "; ".join(errors)[:300]
    db.update("credentials", credential_id, {"last_sync_at": now, "last_sync_status": status,
                                             "last_sync_message": message})
    return {"created": created, "updated": updated, "removed": len(newly_removed),
            "removed_names": [m["name"] for m in newly_removed], "errors": errors, "total": len(found)}
