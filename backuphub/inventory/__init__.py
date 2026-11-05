"""Orquestração do inventário: on-premise (SSH/WinRM) e nuvem (AWS/GCP)."""
from .. import db
from ..security import credential_secret

UPDATABLE = ("os", "cpu", "memory_mb", "disks", "ip_private", "ip_public", "state", "extra")


def collect_machine(machine_id: int) -> dict:
    """Atualiza o inventário de uma máquina conectando-se a ela."""
    machine = db.get("machines", machine_id)
    if not machine:
        raise ValueError("Máquina não encontrada")
    cred, secret = credential_secret(machine.get("credential_id"))
    try:
        if not cred:
            if machine["provider"] in ("aws", "gcp"):
                # Sem credencial de SO: atualiza pelos dados da nuvem.
                if machine.get("cloud_credential_id"):
                    sync_cloud(machine["cloud_credential_id"])
                    return db.get("machines", machine_id)
            raise ValueError("Associe uma credencial SSH/WinRM à máquina para coletar o inventário")
        if machine["platform"] == "windows":
            from . import windows
            data = windows.collect(machine["address"], secret)
        else:
            from . import linux
            data = linux.collect(machine["address"], secret)
        values = {k: data[k] for k in UPDATABLE if data.get(k) is not None}
        if machine["provider"] != "onprem":
            values.pop("state", None)
            values.pop("ip_public", None)
            # Mantém dados da nuvem e acrescenta os do SO.
            values["extra"] = {**(machine.get("extra") or {}), **(data.get("extra") or {})}
            if machine.get("disks"):  # discos da nuvem (volumes) têm prioridade
                values.pop("disks", None)
        values.update(inventory_status="ok", inventory_message=None, last_inventory_at=db.utcnow())
        db.update("machines", machine_id, values)
    except Exception as exc:
        db.update("machines", machine_id, {
            "inventory_status": "error",
            "inventory_message": str(exc)[:500],
            "last_inventory_at": db.utcnow(),
            **({"state": "unreachable"} if machine["provider"] == "onprem" else {}),
        })
        raise
    return db.get("machines", machine_id)


def sync_cloud(credential_id: int) -> dict:
    """Sincroniza as VMs de uma conta AWS/GCP com o inventário."""
    cred, secret = credential_secret(credential_id)
    if not cred:
        raise ValueError("Credencial não encontrada")
    if cred["type"] == "aws":
        from . import aws
        found, errors = aws.list_instances(secret)
    elif cred["type"] == "gcp":
        from . import gcp
        found, errors = gcp.list_instances(secret)
    else:
        raise ValueError("A credencial precisa ser do tipo AWS ou GCP")

    provider = cred["type"]
    created = updated = 0
    seen = set()
    now = db.utcnow()
    for item in found:
        seen.add(item["instance_id"])
        existing = db.query_one(
            "SELECT id FROM machines WHERE provider = ? AND instance_id = ?", (provider, item["instance_id"])
        )
        values = {**item, "cloud_credential_id": credential_id, "inventory_status": "ok",
                  "inventory_message": None, "last_inventory_at": now}
        if existing:
            db.update("machines", existing["id"], values)
            updated += 1
        else:
            db.insert("machines", {**values, "provider": provider, "created_at": now})
            created += 1

    # VMs que sumiram da conta são marcadas como removidas (o histórico é preservado).
    removed = 0
    if not errors:
        for m in db.query("SELECT id, instance_id FROM machines WHERE provider = ? AND cloud_credential_id = ?",
                          (provider, credential_id)):
            if m["instance_id"] not in seen:
                db.update("machines", m["id"], {"state": "terminated", "last_inventory_at": now})
                removed += 1
    return {"created": created, "updated": updated, "removed": removed, "errors": errors, "total": len(found)}
