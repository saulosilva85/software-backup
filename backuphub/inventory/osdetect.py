"""Identificação da versão do sistema operacional SEM credenciais.

Windows: ao iniciar uma autenticação NTLM (SMB 445 ou WinRM 5985), o Windows responde
com uma mensagem CHALLENGE que traz a versão do sistema (major.minor.build) e o nome
do computador — antes de qualquer senha. Pelo número do build identificamos a edição.

Linux: a identificação do servidor SSH traz a versão do OpenSSH e, em muitas
distribuições, o pacote da distribuição (ex.: "Ubuntu-3ubuntu0.10", "Debian-2+deb12u3").
Pela combinação estimamos a distribuição e a versão.

Os resultados são marcados como "estimado"; com credencial o inventário completo
substitui pelo nome exato informado pelo próprio sistema.
"""
from __future__ import annotations

import base64
import os
import re
import socket
import struct

# --------------------------------------------------------------------------- Windows
# Builds do Windows NT 10.0. Quando o mesmo build é usado por versão cliente e servidor,
# as duas são indicadas (a NTLM não informa se é edição Server).
WINDOWS_BUILDS = {
    10240: "Windows 10 1507", 10586: "Windows 10 1511",
    14393: "Windows 10 1607 / Windows Server 2016", 15063: "Windows 10 1703", 16299: "Windows 10 1709",
    17134: "Windows 10 1803", 17763: "Windows 10 1809 / Windows Server 2019", 18362: "Windows 10 1903",
    18363: "Windows 10 1909", 19041: "Windows 10 2004", 19042: "Windows 10 20H2", 19043: "Windows 10 21H1",
    19044: "Windows 10 21H2", 19045: "Windows 10 22H2", 20348: "Windows Server 2022",
    22000: "Windows 11 21H2", 22621: "Windows 11 22H2", 22631: "Windows 11 23H2",
    25398: "Windows Server 23H2", 26100: "Windows 11 24H2 / Windows Server 2025", 26200: "Windows 11 25H2",
}
LEGACY_WINDOWS = {
    (6, 0): "Windows Vista / Windows Server 2008", (6, 1): "Windows 7 / Windows Server 2008 R2",
    (6, 2): "Windows 8 / Windows Server 2012", (6, 3): "Windows 8.1 / Windows Server 2012 R2",
    (5, 1): "Windows XP", (5, 2): "Windows Server 2003",
}


def windows_name(major: int, minor: int, build: int) -> str:
    if (major, minor) == (10, 0):
        if build in WINDOWS_BUILDS:
            return WINDOWS_BUILDS[build]
        return f"Windows {'11' if build >= 22000 else '10'} build {build}"
    return LEGACY_WINDOWS.get((major, minor), f"Windows {major}.{minor} build {build}")


NTLM_FLAGS = 0xE2888207  # UNICODE|OEM|REQUEST_TARGET|NTLM|ALWAYS_SIGN|EXTENDED_SESSION|TARGET_INFO|VERSION|128|KEY_EXCH|56


def ntlm_negotiate() -> bytes:
    return b"NTLMSSP\x00" + struct.pack("<II", 1, NTLM_FLAGS) + b"\x00" * 16 + b"\x0a\x00\x63\x45\x00\x00\x00\x0f"


def _der(tag: int, content: bytes) -> bytes:
    n = len(content)
    if n < 0x80:
        length = bytes([n])
    elif n < 0x100:
        length = b"\x81" + bytes([n])
    else:
        length = b"\x82" + n.to_bytes(2, "big")
    return bytes([tag]) + length + content


def spnego_init(token: bytes) -> bytes:
    ntlm_oid = b"\x06\x0a\x2b\x06\x01\x04\x01\x82\x37\x02\x02\x0a"
    mech_types = _der(0xA0, _der(0x30, ntlm_oid))
    mech_token = _der(0xA2, _der(0x04, token))
    neg_init = _der(0xA0, _der(0x30, mech_types + mech_token))
    return _der(0x60, b"\x06\x06\x2b\x06\x01\x05\x05\x02" + neg_init)


def parse_ntlm_challenge(data: bytes) -> dict | None:
    """Extrai versão e nomes de uma mensagem NTLM CHALLENGE (procura a assinatura nos bytes)."""
    i = data.find(b"NTLMSSP\x00\x02\x00\x00\x00")
    if i < 0:
        return None
    msg = data[i:]
    try:
        flags = struct.unpack_from("<I", msg, 20)[0]
        info = {}
        if flags & 0x02000000 and len(msg) >= 56:  # NEGOTIATE_VERSION
            major, minor, build = msg[48], msg[49], struct.unpack_from("<H", msg, 50)[0]
            if major:
                info.update(major=major, minor=minor, build=build, os=windows_name(major, minor, build))
        ti_len, _, ti_off = struct.unpack_from("<HHI", msg, 40)
        ti = msg[ti_off:ti_off + ti_len]
        pos = 0
        names = {1: "netbios_name", 2: "netbios_domain", 3: "dns_name", 4: "dns_domain"}
        while pos + 4 <= len(ti):
            av_id, av_len = struct.unpack_from("<HH", ti, pos)
            if av_id == 0:
                break
            if av_id in names:
                info[names[av_id]] = ti[pos + 4:pos + 4 + av_len].decode("utf-16-le", errors="ignore")
            pos += 4 + av_len
        return info or None
    except (struct.error, IndexError):
        return None


def _smb2_header(command: int, message_id: int) -> bytes:
    return (b"\xfeSMB" + struct.pack("<HHIHHIIQIIQ", 64, 0, 0, command, 31, 0, 0, message_id, 0xFEFF, 0, 0)
            + b"\x00" * 16)


def _netbios(payload: bytes) -> bytes:
    return b"\x00" + len(payload).to_bytes(3, "big") + payload


def _recv_netbios(sock: socket.socket) -> bytes:
    head = b""
    while len(head) < 4:
        chunk = sock.recv(4 - len(head))
        if not chunk:
            raise ConnectionError("conexão encerrada")
        head += chunk
    size = int.from_bytes(head[1:4], "big")
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            break
        data += chunk
    return data


def smb_ntlm_info(ip: str, timeout: float = 2.0, port: int = 445) -> dict | None:
    """Versão do Windows via SMB2 (porta 445): NEGOTIATE + SESSION_SETUP com NTLM, sem credencial."""
    dialects = [0x0202, 0x0210, 0x0300, 0x0302]
    negotiate = (_smb2_header(0, 0) + struct.pack("<HHHHI", 36, len(dialects), 1, 0, 0) + os.urandom(16)
                 + b"\x00" * 8 + b"".join(struct.pack("<H", d) for d in dialects))
    blob = spnego_init(ntlm_negotiate())
    setup = (_smb2_header(1, 1) + struct.pack("<HBBIIHHQ", 25, 0, 1, 0, 0, 64 + 24, len(blob), 0) + blob)
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(_netbios(negotiate))
            _recv_netbios(sock)
            sock.sendall(_netbios(setup))
            return parse_ntlm_challenge(_recv_netbios(sock))
    except (OSError, ConnectionError):
        return None


def winrm_ntlm_info(ip: str, port: int = 5985, timeout: float = 2.0) -> dict | None:
    """Versão do Windows via WinRM (HTTP 5985): resposta 401 com o desafio NTLM, sem credencial."""
    token = base64.b64encode(ntlm_negotiate()).decode()
    request = (f"POST /wsman HTTP/1.1\r\nHost: {ip}:{port}\r\nAuthorization: Negotiate {token}\r\n"
               f"Content-Type: application/soap+xml;charset=UTF-8\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request.encode())
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 65536:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
    except OSError:
        return None
    m = re.search(rb"WWW-Authenticate:\s*(?:Negotiate|NTLM)\s+([A-Za-z0-9+/=]+)", data, re.I)
    if not m:
        return None
    try:
        return parse_ntlm_challenge(base64.b64decode(m.group(1)))
    except (ValueError, TypeError):
        return None


def windows_info(ip: str, open_ports: list[int] | None = None, timeout: float = 2.0) -> dict | None:
    ports = open_ports or [445, 5985]
    if 445 in ports:
        info = smb_ntlm_info(ip, timeout)
        if info and info.get("os"):
            return info
    if 5985 in ports:
        return winrm_ntlm_info(ip, 5985, timeout)
    return None


# --------------------------------------------------------------------------- Linux (SSH)
# Versão do OpenSSH empacotada por padrão em cada release.
UBUNTU_BY_OPENSSH = {"7.2": "16.04", "7.6": "18.04", "8.2": "20.04", "8.9": "22.04", "9.3": "23.10",
                     "9.6": "24.04", "9.7": "24.10", "9.9": "25.04", "10.0": "25.10"}
DEBIAN_BY_OPENSSH = {"7.4": "9", "7.9": "10", "8.4": "11", "9.2": "12", "10.0": "13"}
RHEL_BY_OPENSSH = {"7.4": "Red Hat / CentOS / Oracle Linux 7 ou Amazon Linux 2",
                   "8.0": "Red Hat / Rocky / AlmaLinux / Oracle Linux 8",
                   "8.7": "Red Hat / Rocky / AlmaLinux / Oracle Linux 9 ou Amazon Linux 2023"}


def linux_from_banner(banner: str | None) -> str | None:
    """Ex.: 'SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.10' -> 'Ubuntu 22.04'."""
    if not banner:
        return None
    b = banner.strip()
    low = b.lower()
    m = re.search(r"openssh_(\d+\.\d+)", low)
    ver = m.group(1) if m else None
    if "windows" in low:
        return "Windows (OpenSSH)"
    if "ubuntu" in low:
        rel = UBUNTU_BY_OPENSSH.get(ver or "")
        return f"Ubuntu {rel}" if rel else "Ubuntu"
    if "raspbian" in low:
        return "Raspberry Pi OS"
    if "debian" in low:
        d = re.search(r"\+deb(\d+)", low)
        rel = d.group(1) if d else DEBIAN_BY_OPENSSH.get(ver or "")
        return f"Debian {rel}" if rel else "Debian"
    if "freebsd" in low:
        return "FreeBSD"
    if ver and re.fullmatch(r"ssh-2\.0-openssh_[\d.p]+", low):  # sem rótulo de distribuição: família Red Hat
        return RHEL_BY_OPENSSH.get(ver, "Linux")
    return "Linux" if ver else None
