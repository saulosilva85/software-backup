"""Inventário de VMs do Google Compute Engine."""
from __future__ import annotations

from ..cloud import gcp_credentials, gcp_projects


# No GCP, "TERMINATED" significa VM DESLIGADA (não excluída). VMs excluídas simplesmente
# deixam de aparecer na listagem e são marcadas como removidas pelo sincronismo.
GCP_STATES = {"RUNNING": "running", "TERMINATED": "stopped", "STOPPING": "stopping", "STOPPED": "stopped",
              "SUSPENDED": "suspended", "SUSPENDING": "stopping", "PROVISIONING": "pending",
              "STAGING": "pending", "REPAIRING": "pending"}


def _last(url: str | None) -> str | None:
    return url.rsplit("/", 1)[-1] if url else None


def list_instances(secret: dict) -> tuple[list[dict], list[str]]:
    from google.cloud import compute_v1

    creds, _ = gcp_credentials(secret)
    instances_client = compute_v1.InstancesClient(credentials=creds)
    types_client = compute_v1.MachineTypesClient(credentials=creds)
    disks_client = compute_v1.DisksClient(credentials=creds)
    type_cache: dict = {}
    machines, errors = [], []

    for project in gcp_projects(secret):
        try:
            for zone_path, scoped in instances_client.aggregated_list(project=project):
                for inst in scoped.instances or []:
                    zone = _last(zone_path)
                    mtype = _last(inst.machine_type)
                    if (zone, mtype) not in type_cache:
                        try:
                            t = types_client.get(project=project, zone=zone, machine_type=mtype)
                            type_cache[(zone, mtype)] = (t.guest_cpus, t.memory_mb)
                        except Exception:
                            type_cache[(zone, mtype)] = (None, None)
                    cpu, mem = type_cache[(zone, mtype)]
                    disks, is_windows = [], False
                    for d in inst.disks:
                        licenses = " ".join(d.licenses or []).lower()
                        is_windows = is_windows or "windows" in licenses
                        size = d.disk_size_gb or None
                        if not size and d.source:
                            try:
                                size = disks_client.get(project=project, zone=zone, disk=_last(d.source)).size_gb
                            except Exception:
                                size = None
                        disks.append({"device": d.device_name, "disk": _last(d.source), "size_gb": size, "boot": d.boot})
                    nic = inst.network_interfaces[0] if inst.network_interfaces else None
                    ip_private = nic.network_i_p if nic else None
                    ip_public = None
                    if nic and nic.access_configs:
                        ip_public = nic.access_configs[0].nat_i_p or None
                    machines.append({
                        "name": inst.name,
                        "instance_id": f"{project}/{zone}/{inst.name}",
                        "region": zone,
                        "platform": "windows" if is_windows else "linux",
                        "os": "Windows" if is_windows else "Linux",
                        "cpu": cpu,
                        "memory_mb": mem,
                        "disks": disks,
                        "ip_private": ip_private,
                        "ip_public": ip_public,
                        "address": ip_private or ip_public,
                        "state": GCP_STATES.get(inst.status, inst.status.lower()),
                        "tags": dict(inst.labels or {}),
                        "extra": {"project": project, "zone": zone, "machine_type": mtype, "id": str(inst.id)},
                    })
        except Exception as exc:
            errors.append(f"{project}: {exc}")
    return machines, errors
