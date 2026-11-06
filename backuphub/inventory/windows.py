"""Coleta de inventário de servidores Windows via WinRM/PowerShell."""
from __future__ import annotations

import json

from ..remote.winrm import WinRMClient

SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$disks = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
  [pscustomobject]@{ device = $_.DeviceID; mount = $_.DeviceID; label = $_.VolumeName;
    size_gb = [math]::Round($_.Size / 1GB, 1); used_gb = [math]::Round(($_.Size - $_.FreeSpace) / 1GB, 1) }
}
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254*' } | Select-Object -First 1).IPAddress
[pscustomobject]@{
  hostname = $env:COMPUTERNAME
  os = $os.Caption
  version = $os.Version
  cpu = $cs.NumberOfLogicalProcessors
  memory_mb = [int]($cs.TotalPhysicalMemory / 1MB)
  domain = $cs.Domain
  ip = $ip
  disks = @($disks)
  last_boot = $os.LastBootUpTime.ToString('o')
} | ConvertTo-Json -Depth 4 -Compress
"""


def parse(output: str) -> dict:
    raw = json.loads(output.strip().splitlines()[-1])
    disks = raw.get("disks") or []
    if isinstance(disks, dict):
        disks = [disks]
    return {
        "hostname": raw.get("hostname"),
        "os": raw.get("os"),
        "cpu": raw.get("cpu"),
        "memory_mb": raw.get("memory_mb"),
        "disks": disks,
        "ip_private": raw.get("ip"),
        "extra": {"version": raw.get("version"), "domain": raw.get("domain"), "last_boot": raw.get("last_boot")},
    }


def collect(address: str, secret: dict) -> dict:
    out = WinRMClient(address, secret).check(SCRIPT)
    data = parse(out)
    data["state"] = "online"
    return data
