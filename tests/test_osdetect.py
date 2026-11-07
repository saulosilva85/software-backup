"""Identificação da versão do sistema sem credencial (NTLM no Windows, SSH no Linux)."""
from __future__ import annotations

import base64
import socket
import struct
import threading

from backuphub.inventory import osdetect


def challenge(major=10, minor=0, build=22631, names=None):
    names = names or {1: "SAULOSILVA", 2: "WORKGROUP", 3: "SaulosSilva.local", 4: "local"}
    ti = b"".join(struct.pack("<HH", k, len(v.encode("utf-16-le"))) + v.encode("utf-16-le") for k, v in names.items())
    ti += b"\x00\x00\x00\x00"
    target = "WORKGROUP".encode("utf-16-le")
    head_len = 56
    flags = 0xE2898215 | 0x02000000
    msg = (b"NTLMSSP\x00" + struct.pack("<I", 2) + struct.pack("<HHI", len(target), len(target), head_len)
           + struct.pack("<I", flags) + b"\x11" * 8 + b"\x00" * 8
           + struct.pack("<HHI", len(ti), len(ti), head_len + len(target))
           + bytes([major, minor]) + struct.pack("<H", build) + b"\x00\x00\x00\x0f")
    return msg + target + ti


def test_windows_build_names():
    assert osdetect.windows_name(10, 0, 22631) == "Windows 11 23H2"
    assert osdetect.windows_name(10, 0, 19045) == "Windows 10 22H2"
    assert osdetect.windows_name(10, 0, 20348) == "Windows Server 2022"
    assert osdetect.windows_name(10, 0, 17763) == "Windows 10 1809 / Windows Server 2019"
    assert osdetect.windows_name(6, 3, 9600) == "Windows 8.1 / Windows Server 2012 R2"
    assert osdetect.windows_name(10, 0, 27000) == "Windows 11 build 27000"


def test_parse_challenge():
    info = osdetect.parse_ntlm_challenge(b"lixo" + challenge())
    assert info["os"] == "Windows 11 23H2" and info["build"] == 22631
    assert info["netbios_name"] == "SAULOSILVA" and info["dns_domain"] == "local"


def test_spnego_lengths():
    blob = osdetect.spnego_init(osdetect.ntlm_negotiate())
    assert blob[0] == 0x60 and blob[1] == len(blob) - 2 and osdetect.ntlm_negotiate() in blob


def _serve(handler):
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    threading.Thread(target=lambda: handler(srv.accept()[0]), daemon=True).start()
    return srv.getsockname()[1]


def test_smb_end_to_end():
    def handler(conn):
        def recv():
            size = int.from_bytes(conn.recv(4)[1:], "big"); data = b""
            while len(data) < size:
                data += conn.recv(size - len(data))
            return data
        req = recv(); assert req[:4] == b"\xfeSMB" and struct.unpack_from("<H", req, 12)[0] == 0
        conn.sendall(b"\x00" + (70).to_bytes(3, "big") + b"\xfeSMB" + b"\x00" * 66)
        req = recv(); assert struct.unpack_from("<H", req, 12)[0] == 1 and b"NTLMSSP\x00\x01" in req
        body = b"\xfeSMB" + b"\x00" * 60 + b"\xa1\x81\x99" + challenge(10, 0, 20348, {1: "SRV-ARQUIVOS"})
        conn.sendall(b"\x00" + len(body).to_bytes(3, "big") + body); conn.close()
    port = _serve(handler)
    info = osdetect.smb_ntlm_info("127.0.0.1", 2.0, port=port)
    assert info["os"] == "Windows Server 2022" and info["netbios_name"] == "SRV-ARQUIVOS"


def test_winrm_end_to_end():
    def handler(conn):
        req = conn.recv(65536)
        assert b"Authorization: Negotiate TlRMTVNTUAAB" in req
        token = base64.b64encode(challenge(10, 0, 19045)).decode()
        conn.sendall(f"HTTP/1.1 401 \r\nWWW-Authenticate: Negotiate {token}\r\nContent-Length: 0\r\n\r\n".encode())
        conn.close()
    port = _serve(handler)
    info = osdetect.winrm_ntlm_info("127.0.0.1", port, 2.0)
    assert info["os"] == "Windows 10 22H2" and info["netbios_name"] == "SAULOSILVA"


def test_linux_from_banner():
    f = osdetect.linux_from_banner
    assert f("SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.10") == "Ubuntu 22.04"
    assert f("SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13.5") == "Ubuntu 24.04"
    assert f("SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u3") == "Debian 12"
    assert f("SSH-2.0-OpenSSH_8.4p1 Debian-5+deb11u3") == "Debian 11"
    assert f("SSH-2.0-OpenSSH_8.7") == "Red Hat / Rocky / AlmaLinux / Oracle Linux 9 ou Amazon Linux 2023"
    assert f("SSH-2.0-OpenSSH_8.0") == "Red Hat / Rocky / AlmaLinux / Oracle Linux 8"
    assert f("SSH-2.0-OpenSSH_7.4") == "Red Hat / CentOS / Oracle Linux 7 ou Amazon Linux 2"
    assert f("SSH-2.0-OpenSSH_for_Windows_9.5") == "Windows (OpenSSH)"
    assert f(None) is None
