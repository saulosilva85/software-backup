"""Coleta de inventário de servidores Linux via SSH."""
from __future__ import annotations

from ..remote.ssh import SSHClient

SCRIPT = r"""
echo "@@HOSTNAME"; hostname 2>/dev/null
echo "@@OS"; ( . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" ) || uname -s
echo "@@KERNEL"; uname -r
echo "@@CPU"; nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo
echo "@@MEM"; grep MemTotal /proc/meminfo | awk '{print $2}'
echo "@@UPTIME"; cut -d. -f1 /proc/uptime 2>/dev/null
echo "@@IPS"; hostname -I 2>/dev/null || ip -o -4 addr show | awk '{print $4}'
echo "@@DISKS"; df -P -k -x tmpfs -x devtmpfs -x overlay -x squashfs 2>/dev/null | tail -n +2
echo "@@END"
"""


def parse(output: str) -> dict:
    sections: dict[str, list[str]] = {}
    current = None
    for line in output.splitlines():
        if line.startswith("@@"):
            current = line[2:].strip()
            sections[current] = []
        elif current:
            if line.strip():
                sections[current].append(line.strip())

    def first(key, default=None):
        values = sections.get(key) or []
        return values[0] if values else default

    disks = []
    for line in sections.get("DISKS", []):
        parts = line.split()
        if len(parts) >= 6 and parts[1].isdigit():
            disks.append({
                "device": parts[0],
                "mount": parts[5],
                "size_gb": round(int(parts[1]) / 1024 / 1024, 1),
                "used_gb": round(int(parts[2]) / 1024 / 1024, 1),
            })
    mem_kb = first("MEM")
    ips = " ".join(sections.get("IPS", [])).split()
    return {
        "hostname": first("HOSTNAME"),
        "os": first("OS"),
        "cpu": int(first("CPU")) if (first("CPU") or "").isdigit() else None,
        "memory_mb": int(mem_kb) // 1024 if (mem_kb or "").isdigit() else None,
        "disks": disks,
        "ip_private": next((ip.split("/")[0] for ip in ips if not ip.startswith("127.")), None),
        "extra": {"kernel": first("KERNEL"), "uptime_s": first("UPTIME")},
    }


def collect(address: str, secret: dict) -> dict:
    with SSHClient(address, secret) as ssh:
        code, out, err = ssh.run(SCRIPT, timeout=60, sudo=False)
    if "@@END" not in out:
        raise RuntimeError(f"Saída de inventário incompleta: {err.strip()[:300]}")
    data = parse(out)
    data["state"] = "online"
    return data
