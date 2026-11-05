"""Backup por snapshot dos discos de VMs na AWS (EBS) e GCP (Persistent Disk).

Cada execução recebe uma etiqueta com o run_id, o que permite aplicar a
retenção por "conjunto de snapshots" (todos os discos da mesma execução).
"""
import time

from ..cloud import aws_session, gcp_credentials
from ..config import Config
from . import slug


class SnapshotError(RuntimeError):
    pass


def _label(value) -> str:
    """Valores de label GCP: minúsculas, dígitos, '-' e '_', até 63 caracteres."""
    return slug(str(value), 63) or "x"


# ----------------------------------------------------------------------- AWS
def aws_backup(machine: dict, secret: dict, policy: dict | None, run_id: str, keep: int, log) -> dict:
    session = aws_session(secret, machine.get("region"))
    ec2 = session.client("ec2")
    policy_tag = str(policy["id"]) if policy else "manual"
    tags = [
        {"Key": "Name", "Value": f"backuphub-{machine['name']}-{run_id[:8]}"},
        {"Key": "backuphub:machine", "Value": machine["instance_id"]},
        {"Key": "backuphub:policy", "Value": policy_tag},
        {"Key": "backuphub:run", "Value": run_id},
    ]
    log(f"Criando snapshots EBS da instância {machine['instance_id']} ({machine.get('region')})")
    resp = ec2.create_snapshots(
        InstanceSpecification={"InstanceId": machine["instance_id"], "ExcludeBootVolume": False},
        Description=f"BackupHub {machine['name']} run {run_id}",
        TagSpecifications=[{"ResourceType": "snapshot", "Tags": tags}],
        CopyTagsFromSource="volume",
    )
    snaps = resp.get("Snapshots", [])
    ids = [s["SnapshotId"] for s in snaps]
    size_gb = sum(s.get("VolumeSize") or 0 for s in snaps)
    log(f"Snapshots iniciados: {', '.join(ids)} ({size_gb} GB provisionados)")

    warning = None
    if Config.SNAPSHOT_WAIT_TIMEOUT > 0 and ids:
        log("Aguardando conclusão dos snapshots...")
        waiter = ec2.get_waiter("snapshot_completed")
        delay = 15
        try:
            waiter.wait(SnapshotIds=ids, WaiterConfig={"Delay": delay,
                                                      "MaxAttempts": max(1, Config.SNAPSHOT_WAIT_TIMEOUT // delay)})
            log("Snapshots concluídos")
        except Exception as exc:
            warning = f"Snapshots ainda em andamento após o tempo limite: {exc}"

    removed = 0
    if keep and keep > 0:
        existing = ec2.describe_snapshots(OwnerIds=["self"], Filters=[
            {"Name": "tag:backuphub:machine", "Values": [machine["instance_id"]]},
            {"Name": "tag:backuphub:policy", "Values": [policy_tag]},
        ])["Snapshots"]
        runs: dict[str, list] = {}
        for s in existing:
            run = next((t["Value"] for t in s.get("Tags", []) if t["Key"] == "backuphub:run"), s["SnapshotId"])
            runs.setdefault(run, []).append(s)
        ordered = sorted(runs.items(), key=lambda kv: max(x["StartTime"] for x in kv[1]), reverse=True)
        for run, items in ordered[keep:]:
            for s in items:
                ec2.delete_snapshot(SnapshotId=s["SnapshotId"])
                removed += 1
                log(f"Retenção: snapshot {s['SnapshotId']} removido (run {run[:8]})")
    return {"size": size_gb * 1024 ** 3, "artifact": ",".join(ids), "warning": warning, "removed": removed}


# ----------------------------------------------------------------------- GCP
def gcp_backup(machine: dict, secret: dict, policy: dict | None, run_id: str, keep: int, log) -> dict:
    from google.cloud import compute_v1

    creds, _ = gcp_credentials(secret)
    extra = machine.get("extra") or {}
    project, zone = extra.get("project"), extra.get("zone")
    name = machine["instance_id"].rsplit("/", 1)[-1]
    if not project or not zone:
        raise SnapshotError("VM GCP sem projeto/zona no inventário; sincronize a conta novamente")

    instances = compute_v1.InstancesClient(credentials=creds)
    disks = compute_v1.DisksClient(credentials=creds)
    snapshots = compute_v1.SnapshotsClient(credentials=creds)
    inst = instances.get(project=project, zone=zone, instance=name)

    policy_label = _label(policy["id"]) if policy else "manual"
    labels = {"backuphub-machine": _label(machine["id"]), "backuphub-policy": policy_label,
              "backuphub-run": _label(run_id)}
    stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    created, size_gb, ops = [], 0, []
    for d in inst.disks:
        if not d.source:
            continue
        disk_name = d.source.rsplit("/", 1)[-1]
        snap_name = f"bh-{slug(name, 20)}-{slug(disk_name, 16)}-{stamp}"[:62].rstrip("-")
        log(f"Criando snapshot {snap_name} do disco {disk_name}")
        snap = compute_v1.Snapshot(name=snap_name, labels=labels,
                                   description=f"BackupHub {machine['name']} run {run_id}")
        ops.append(disks.create_snapshot(project=project, zone=zone, disk=disk_name, snapshot_resource=snap))
        created.append(snap_name)
        size_gb += d.disk_size_gb or 0

    warning = None
    for op in ops:
        try:
            op.result(timeout=max(Config.SNAPSHOT_WAIT_TIMEOUT, 60))
        except Exception as exc:
            warning = f"Snapshot ainda em andamento ou com erro: {exc}"
    if not warning:
        log("Snapshots concluídos")

    removed = 0
    if keep and keep > 0:
        flt = f'labels.backuphub-machine = "{labels["backuphub-machine"]}" AND labels.backuphub-policy = "{policy_label}"'
        runs: dict[str, list] = {}
        for s in snapshots.list(project=project, filter=flt):
            runs.setdefault(s.labels.get("backuphub-run", s.name), []).append(s)
        ordered = sorted(runs.items(), key=lambda kv: max(x.creation_timestamp for x in kv[1]), reverse=True)
        for run, items in ordered[keep:]:
            for s in items:
                snapshots.delete(project=project, snapshot=s.name)
                removed += 1
                log(f"Retenção: snapshot {s.name} removido")
    return {"size": size_gb * 1024 ** 3, "artifact": ",".join(created), "warning": warning, "removed": removed}
