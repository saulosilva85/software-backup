from __future__ import annotations

import json

import pytest

from backuphub.backup.windows import ps_literal, render_backup_script
from backuphub.inventory import linux, network, windows

LINUX_OUT = """@@HOSTNAME
web-01
@@OS
Ubuntu 22.04.4 LTS
@@KERNEL
5.15.0-105-generic
@@CPU
4
@@MEM
8048276
@@UPTIME
123456
@@IPS
127.0.0.1 10.0.0.21 172.17.0.1
@@DISKS
/dev/sda1 102400000 51200000 51200000 50% /
/dev/sdb1 20971520 1048576 19922944 5% /data
@@END
"""


def test_linux_parse():
    d = linux.parse(LINUX_OUT)
    assert d["os"] == "Ubuntu 22.04.4 LTS"
    assert d["cpu"] == 4
    assert d["memory_mb"] == 7859
    assert d["ip_private"] == "10.0.0.21"
    assert [x["mount"] for x in d["disks"]] == ["/", "/data"]
    assert d["disks"][1]["size_gb"] == 20.0


def test_windows_parse_single_disk():
    raw = {"hostname": "SRV01", "os": "Microsoft Windows Server 2022", "cpu": 8, "memory_mb": 32768,
           "ip": "10.0.0.11", "disks": {"device": "C:", "size_gb": 120}, "version": "10.0.20348"}
    d = windows.parse("WARNING: x\n" + json.dumps(raw))
    assert d["disks"] == [{"device": "C:", "size_gb": 120}]
    assert d["ip_private"] == "10.0.0.11"


def test_expand_targets():
    assert len(network.expand_targets("192.168.0.0/30")) == 2
    assert network.expand_targets("10.0.0.10-12") == ["10.0.0.10", "10.0.0.11", "10.0.0.12"]
    assert network.expand_targets("10.0.0.1, 10.0.0.2") == ["10.0.0.1", "10.0.0.2"]
    with pytest.raises(ValueError):
        network.expand_targets("10.0.0.0/16")


def test_classify():
    assert network.classify([22], "SSH-2.0-OpenSSH_8.9p1 Ubuntu") == "linux"
    assert network.classify([3389, 5985], None) == "windows"
    assert network.classify([22, 445], None) == "windows"


def test_powershell_escaping():
    assert ps_literal("C:\\O'Brien") == "'C:\\O''Brien'"
    script = render_backup_script(["C:\\Users", "D:\\Dados d'agua"], [], "https://x/?a=1&b='2'", {"A": "b"})
    assert "'[\"C:\\\\Users\", \"D:\\\\Dados d''agua\"]'" in script
    assert "'https://x/?a=1&b=''2'''" in script
