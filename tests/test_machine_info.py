"""Hostname, discos (livre), identificação sem credencial e monitor online/offline."""
from __future__ import annotations

from conftest import HEADERS

from backuphub import db, health, jobs
from backuphub.inventory import network, normalize_disks


def nb_response(entries):
    data = bytearray(56)
    data += bytes([len(entries)])
    for name, suffix, group in entries:
        data += name.ljust(15).encode()[:15] + bytes([suffix]) + (0x8400 if group else 0x0400).to_bytes(2, "big")
    return bytes(data)


def test_parse_netbios():
    pkt = nb_response([("SRV-ARQUIVOS", 0x00, False), ("EMPRESA", 0x00, True), ("SRV-ARQUIVOS", 0x20, False)])
    assert network.parse_netbios(pkt) == ("SRV-ARQUIVOS", "EMPRESA")
    assert network.parse_netbios(b"\x00" * 10) == (None, None)


def test_os_hint():
    assert network.os_hint_from_banner("SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u3") == "Debian 12"
    assert network.os_hint_from_banner("SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.10") == "Ubuntu"
    assert network.os_hint_from_banner("SSH-2.0-OpenSSH_for_Windows_8.1") == "Windows (OpenSSH)"
    assert network.os_hint_from_banner(None) is None


def test_normalize_disks():
    d = normalize_disks([{"size_gb": 100, "used_gb": 40}, {"size_gb": 50, "free_gb": 10}, {"size_gb": 8}])
    assert d[0]["free_gb"] == 60 and d[1]["used_gb"] == 40 and "free_gb" not in d[2]


def test_collect_saves_hostname_and_renames(client, monkeypatch):
    from backuphub.inventory import windows
    cred = client.post("/api/credentials", json={"name": "w", "type": "winrm", "data": {"username": "a", "password": "b"}},
                       headers=HEADERS).json["id"]
    mid = client.post("/api/machines", json={"name": "192.168.18.13", "address": "192.168.18.13", "platform": "windows"},
                      headers=HEADERS).json["id"]
    monkeypatch.setattr(windows, "collect", lambda addr, secret: {
        "hostname": "DESKTOP-SAULO", "os": "Microsoft Windows 11 Pro", "cpu": 8, "memory_mb": 16384, "state": "online",
        "disks": [{"device": "C:", "mount": "C:", "size_gb": 476.3, "used_gb": 210.5, "free_gb": 265.8}],
        "ip_private": "192.168.18.13", "extra": {"cpu_model": "Intel Core i7", "domain": "WORKGROUP"}})
    db.update("machines", mid, {"credential_id": cred})
    from backuphub.inventory import collect_machine
    m = collect_machine(mid)
    assert m["name"] == "DESKTOP-SAULO" and m["hostname"] == "DESKTOP-SAULO"
    assert m["os"] == "Microsoft Windows 11 Pro" and m["cpu"] == 8 and m["memory_mb"] == 16384
    assert m["disks"][0]["free_gb"] == 265.8 and m["last_seen_at"] and m["state"] == "online"


def test_custom_name_is_kept(client, monkeypatch):
    from backuphub.inventory import linux
    cred = client.post("/api/credentials", json={"name": "l", "type": "ssh", "data": {"username": "a", "password": "b"}},
                       headers=HEADERS).json["id"]
    mid = client.post("/api/machines", json={"name": "Servidor ERP", "address": "10.0.0.5", "platform": "linux",
                                             "credential_id": cred}, headers=HEADERS).json["id"]
    monkeypatch.setattr(linux, "collect", lambda a, s: {"hostname": "erp01", "os": "Debian 12", "state": "online",
                                                        "disks": [{"size_gb": 20, "used_gb": 5}]})
    from backuphub.inventory import collect_machine
    m = collect_machine(mid)
    assert m["name"] == "Servidor ERP" and m["hostname"] == "erp01" and m["disks"][0]["free_gb"] == 15


def test_associating_credential_triggers_inventory(client, monkeypatch):
    import backuphub.app as appmod
    cred = client.post("/api/credentials", json={"name": "l", "type": "ssh", "data": {"username": "a"}},
                       headers=HEADERS).json["id"]
    mid = db.insert("machines", {"name": "x", "address": "10.9.9.9", "platform": "linux", "provider": "onprem",
                                 "created_at": db.utcnow()})
    submitted = []
    monkeypatch.setattr(appmod._inventory_pool, "submit", lambda fn, *a: submitted.append(a))
    client.put(f"/api/machines/{mid}", json={"credential_id": cred}, headers=HEADERS)
    assert submitted == [(mid,)] and db.get("machines", mid)["inventory_status"] == "running"


def test_health_online_offline_and_alert(app, monkeypatch):
    sent = []
    monkeypatch.setattr(jobs, "send_webhook", lambda text, payload=None: sent.append(text))
    up = {"10.0.0.1": True}
    monkeypatch.setattr(network, "is_reachable", lambda addr, platform, timeout=2.0: up.get(addr, False))
    mid = db.insert("machines", {"name": "srv", "address": "10.0.0.1", "platform": "linux", "provider": "onprem",
                                 "state": "unknown", "created_at": db.utcnow()})
    db.insert("jobs", {"run_id": "r", "kind": "backup", "machine_id": mid, "machine_name": "srv", "status": "success",
                       "created_at": db.utcnow()})
    assert health.check_all() == {mid: "online"}
    seen = db.get("machines", mid)["last_seen_at"]
    assert seen
    up["10.0.0.1"] = False                      # máquina desligada
    assert health.check_all() == {mid: "offline"}
    m = db.get("machines", mid)
    assert m["state"] == "offline" and m["last_seen_at"] == seen
    assert len(sent) == 1 and "OFFLINE" in sent[0]
    health.check_all()                          # continua offline: não repete o alerta
    assert len(sent) == 1
    up["10.0.0.1"] = True
    assert health.check_all() == {mid: "online"}


def test_auto_credential_tries_registered(client, monkeypatch):
    """Sem credencial escolhida: testa as cadastradas do tipo certo e associa a que funcionar."""
    from backuphub.inventory import collect_machine, linux
    bad = client.post("/api/credentials", json={"name": "errada", "type": "ssh", "data": {"username": "x", "password": "1"}},
                      headers=HEADERS).json["id"]
    client.post("/api/credentials", json={"name": "win", "type": "winrm", "data": {"username": "w", "password": "1"}},
                headers=HEADERS)
    good = client.post("/api/credentials", json={"name": "certa", "type": "ssh", "data": {"username": "ok", "password": "2"}},
                       headers=HEADERS).json["id"]
    tried = []

    def fake_collect(addr, secret):
        tried.append(secret["username"])
        if secret["username"] != "ok":
            raise RuntimeError("Authentication failed.")
        return {"hostname": "debian-srv", "os": "Debian GNU/Linux 12", "cpu": 2, "memory_mb": 2048, "state": "online",
                "disks": [{"device": "/dev/sda1", "mount": "/", "size_gb": 20, "used_gb": 4}]}
    monkeypatch.setattr(linux, "collect", fake_collect)
    mid = db.insert("machines", {"name": "192.168.18.180", "address": "192.168.18.180", "platform": "linux",
                                 "provider": "onprem", "created_at": db.utcnow()})
    m = collect_machine(mid)
    assert tried == ["x", "ok"]                  # só SSH; a WinRM não é testada em Linux
    assert m["credential_id"] == good and m["name"] == "debian-srv" and m["cpu"] == 2
    assert bad != good


def test_auto_credential_stops_on_network_error(client, monkeypatch):
    from backuphub.inventory import collect_machine, linux
    for n in ("a", "b"):
        client.post("/api/credentials", json={"name": n, "type": "ssh", "data": {"username": n}}, headers=HEADERS)
    tried = []
    monkeypatch.setattr(linux, "collect", lambda a, s: (tried.append(1), (_ for _ in ()).throw(OSError("timed out")))[1])
    mid = db.insert("machines", {"name": "x", "address": "10.1.1.1", "platform": "linux", "provider": "onprem",
                                 "created_at": db.utcnow()})
    import pytest
    with pytest.raises(RuntimeError, match="porta 22"):
        collect_machine(mid)
    assert len(tried) == 1                        # não insiste em todas as credenciais se a máquina não responde


def test_no_credentials_registered_message(app):
    from backuphub.inventory import collect_machine
    import pytest
    mid = db.insert("machines", {"name": "x", "address": "10.1.1.2", "platform": "windows", "provider": "onprem",
                                 "created_at": db.utcnow()})
    with pytest.raises(ValueError, match="Nenhuma credencial WinRM"):
        collect_machine(mid)


def test_new_credential_is_tested_on_machines_without_access(client, monkeypatch):
    import backuphub.app as appmod
    submitted = []
    monkeypatch.setattr(appmod._inventory_pool, "submit", lambda fn, *a: submitted.append(a[0]))
    lin = db.insert("machines", {"name": "l", "address": "10.0.0.1", "platform": "linux", "provider": "onprem",
                                 "created_at": db.utcnow()})
    db.insert("machines", {"name": "w", "address": "10.0.0.2", "platform": "windows", "provider": "onprem",
                           "created_at": db.utcnow()})
    client.post("/api/credentials", json={"name": "ssh", "type": "ssh", "data": {"username": "u"}}, headers=HEADERS)
    assert submitted == [lin]


def test_mdns_ptr_parse():
    # resposta mDNS: 1 pergunta, 1 resposta PTR -> "debian-srv.local" (com compressão)
    q = b"\x03180\x0218\x03168\x03192\x07in-addr\x04arpa\x00"
    msg = b"\x00\x00\x84\x00\x00\x01\x00\x01\x00\x00\x00\x00" + q + b"\x00\x0c\x00\x01"
    rdata = b"\x0adebian-srv\x05local\x00"
    msg += b"\xc0\x0c" + b"\x00\x0c\x00\x01\x00\x00\x00\x78" + len(rdata).to_bytes(2, "big") + rdata
    assert network.parse_ptr_response(msg) == "debian-srv.local"


def test_scan_uses_own_hostname(monkeypatch):
    import socket
    monkeypatch.setattr(network, "_probe", lambda ip, port, t: port == 22)
    monkeypatch.setattr(network, "_ssh_banner", lambda ip, t: "SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u3")
    monkeypatch.setattr(network, "netbios_name", lambda ip, t=0.8: (None, None))
    monkeypatch.setattr(network, "local_ips", lambda: {"192.168.18.180"})
    monkeypatch.setattr(socket, "gethostbyaddr", lambda ip: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(socket, "gethostname", lambda: "backup")
    h = network.scan_host("192.168.18.180")
    assert h["hostname"] == "backup" and h["os_hint"] == "Debian 12" and h["platform"] == "linux"
