"""Inventário de instâncias EC2 em todas as regiões configuradas."""
from ..cloud import aws_regions, aws_session


def _instance_types(ec2, types: set[str]) -> dict:
    info = {}
    names = list(types)
    for i in range(0, len(names), 100):
        resp = ec2.describe_instance_types(InstanceTypes=names[i:i + 100])
        for t in resp["InstanceTypes"]:
            info[t["InstanceType"]] = {
                "cpu": t["VCpuInfo"]["DefaultVCpus"],
                "memory_mb": t["MemoryInfo"]["SizeInMiB"],
            }
    return info


def _volumes(ec2, volume_ids: list[str]) -> dict:
    sizes = {}
    for i in range(0, len(volume_ids), 200):
        for v in ec2.describe_volumes(VolumeIds=volume_ids[i:i + 200])["Volumes"]:
            sizes[v["VolumeId"]] = v
    return sizes


def list_instances(secret: dict) -> tuple[list[dict], list[str]]:
    machines, errors = [], []
    for region in aws_regions(secret):
        try:
            ec2 = aws_session(secret, region).client("ec2")
            instances = []
            for page in ec2.get_paginator("describe_instances").paginate(
                Filters=[{"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}]
            ):
                for res in page["Reservations"]:
                    instances.extend(res["Instances"])
            if not instances:
                continue
            types = _instance_types(ec2, {i["InstanceType"] for i in instances})
            vol_ids = [m["Ebs"]["VolumeId"] for i in instances for m in i.get("BlockDeviceMappings", []) if "Ebs" in m]
            volumes = _volumes(ec2, vol_ids) if vol_ids else {}
            for inst in instances:
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                platform = "windows" if (inst.get("Platform") == "windows" or "windows" in (inst.get("PlatformDetails") or "").lower()) else "linux"
                disks = []
                for m in inst.get("BlockDeviceMappings", []):
                    vol = volumes.get(m.get("Ebs", {}).get("VolumeId"))
                    if vol:
                        disks.append({"device": m["DeviceName"], "volume_id": vol["VolumeId"], "size_gb": vol["Size"], "type": vol["VolumeType"]})
                spec = types.get(inst["InstanceType"], {})
                machines.append({
                    "name": tags.get("Name") or inst["InstanceId"],
                    "instance_id": inst["InstanceId"],
                    "region": region,
                    "platform": platform,
                    "os": inst.get("PlatformDetails") or platform.title(),
                    "cpu": spec.get("cpu"),
                    "memory_mb": spec.get("memory_mb"),
                    "disks": disks,
                    "ip_private": inst.get("PrivateIpAddress"),
                    "ip_public": inst.get("PublicIpAddress"),
                    "address": inst.get("PrivateIpAddress") or inst.get("PublicIpAddress"),
                    "state": inst["State"]["Name"],
                    "tags": tags,
                    "extra": {"instance_type": inst["InstanceType"], "az": inst["Placement"]["AvailabilityZone"],
                              "vpc_id": inst.get("VpcId"), "image_id": inst.get("ImageId")},
                })
        except Exception as exc:  # uma região com erro não interrompe as demais
            errors.append(f"{region}: {exc}")
    return machines, errors
