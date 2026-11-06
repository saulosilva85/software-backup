"""Descoberta de servidores on-premise por varredura TCP de uma faixa de rede."""
from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor

PORTS = {22: "ssh", 445: "smb", 3389: "rdp", 5985: "winrm", 5986: "winrm-https"}
MAX_HOSTS = 1024


def _probe(ip: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ssh_banner(ip: str, timeout: float) -> str | None:
    try:
        with socket.create_connection((ip, 22), timeout=timeout) as sock:
            sock.settimeout(timeout)
            return sock.recv(256).decode(errors="replace").strip() or None
    except OSError:
        return None


def classify(open_ports: list[int], banner: str | None) -> str:
    windows_ports = {445, 3389, 5985, 5986}
    if banner and "windows" in banner.lower():
        return "windows"
    if windows_ports & set(open_ports):
        return "windows"
    if 22 in open_ports:
        return "linux"
    return "unknown"


def _nb_encode(name: bytes) -> bytes:
    return bytes(c for b in name for c in (((b >> 4) & 0xF) + 0x41, (b & 0xF) + 0x41))


def netbios_name(ip: str, timeout: float = 0.8) -> tuple[str | None, str | None]:
    """Nome do computador e grupo de trabalho/domínio via NetBIOS (UDP 137), sem credenciais.

    Funciona na maioria dos Windows (e Linux com Samba) na mesma rede ou com UDP 137 liberado.
    """
    query = (b"\x13\x37\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + b"\x20" + _nb_encode(b"*" + b"\x00" * 15)
             + b"\x00\x00\x21\x00\x01")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(query, (ip, 137))
            data, _ = sock.recvfrom(2048)
    except OSError:
        return None, None
    return parse_netbios(data)


def parse_netbios(data: bytes) -> tuple[str | None, str | None]:
    try:
        count = data[56]
        name = group = None
        for i in range(count):
            entry = data[57 + i * 18: 57 + (i + 1) * 18]
            label = entry[:15].decode("ascii", errors="ignore").strip()
            suffix, flags = entry[15], int.from_bytes(entry[16:18], "big")
            if suffix == 0x00 and not flags & 0x8000 and not name:
                name = label
            elif suffix == 0x00 and flags & 0x8000 and not group:
                group = label
        return name or None, group or None
    except (IndexError, ValueError):
        return None, None


def os_hint_from_banner(banner: str | None) -> str | None:
    """Sistema estimado pela identificação do SSH (ex.: 'SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u3')."""
    if not banner:
        return None
    import re
    b = banner.lower()
    m = re.search(r"\+deb(\d+)", b)
    if "debian" in b:
        return f"Debian {m.group(1)}" if m else "Debian"
    if "ubuntu" in b:
        return "Ubuntu"
    if "raspbian" in b:
        return "Raspbian"
    if "freebsd" in b:
        return "FreeBSD"
    if "windows" in b:
        return "Windows (OpenSSH)"
    if "openssh" in b:
        return "Linux/Unix"
    return None


def scan_host(ip: str, timeout: float = 0.6) -> dict | None:
    open_ports = [p for p in PORTS if _probe(ip, p, timeout)]
    if not open_ports:
        return None
    banner = _ssh_banner(ip, timeout * 2) if 22 in open_ports else None
    nb_name, workgroup = netbios_name(ip, timeout + 0.4)
    try:
        dns_name = socket.gethostbyaddr(ip)[0]
    except OSError:
        dns_name = None
    if dns_name and dns_name.replace(".", "").replace("-", "").isdigit():
        dns_name = None  # PTR genérico (ex.: 192-168-0-10.provedor)
    return {
        "ip": ip,
        "hostname": nb_name or dns_name,
        "dns_name": dns_name,
        "workgroup": workgroup,
        "os_hint": os_hint_from_banner(banner),
        "open_ports": open_ports,
        "services": [PORTS[p] for p in open_ports],
        "ssh_banner": banner,
        "platform": classify(open_ports, banner),
    }


def expand_targets(target: str) -> list[str]:
    """Aceita CIDR (10.0.0.0/24), faixa (10.0.0.10-10.0.0.50), IP único ou lista por vírgula."""
    hosts: list[str] = []
    for part in [p.strip() for p in target.split(",") if p.strip()]:
        if "/" in part:
            net = ipaddress.ip_network(part, strict=False)
            hosts.extend(str(h) for h in (net.hosts() if net.num_addresses > 2 else net))
        elif "-" in part:
            start_s, end_s = [x.strip() for x in part.split("-", 1)]
            start = ipaddress.ip_address(start_s)
            if "." not in end_s:  # 10.0.0.10-50
                end_s = start_s.rsplit(".", 1)[0] + "." + end_s
            end = ipaddress.ip_address(end_s)
            if int(end) < int(start):
                raise ValueError("Faixa de IP inválida")
            hosts.extend(str(ipaddress.ip_address(i)) for i in range(int(start), int(end) + 1))
        else:
            try:
                hosts.append(str(ipaddress.ip_address(part)))
            except ValueError:
                hosts.append(socket.gethostbyname(part))
        if len(hosts) > MAX_HOSTS:
            raise ValueError(f"Faixa muito grande (máximo {MAX_HOSTS} hosts por varredura)")
    return hosts


def scan(target: str, timeout: float = 0.6, workers: int = 128) -> list[dict]:
    hosts = expand_targets(target)
    with ThreadPoolExecutor(max_workers=min(workers, max(len(hosts), 1))) as pool:
        results = pool.map(lambda ip: scan_host(ip, timeout), hosts)
    found = [r for r in results if r]
    found.sort(key=lambda r: ipaddress.ip_address(r["ip"]))
    return found


# ----------------------------------------------------------------------------
# Detecção automática das redes do próprio servidor do BackupHub
# ----------------------------------------------------------------------------
# Interfaces virtuais que não representam a rede do cliente (containers, bridges, VPN de pods...).
_SKIP_IFACES = ("lo", "docker", "br-", "veth", "virbr", "cni", "flannel", "cali", "vxlan", "kube", "podman", "lxc")
_DEFAULT_PREFIX = 24  # rede sugerida quando a interface é grande demais (/16) ou ponto a ponto (/32)


def _ip_command() -> list[tuple[str, str]]:
    """[(interface, 'ip/prefixo')] via `ip -o -4 addr` (iproute2)."""
    import subprocess
    try:
        out = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    items = []
    for line in out.splitlines():
        parts = line.split()
        if "inet" in parts:
            items.append((parts[1].rstrip(":"), parts[parts.index("inet") + 1]))
    return items


def _ioctl() -> list[tuple[str, str]]:
    """Alternativa sem o comando `ip`: consulta o kernel diretamente (Linux)."""
    import fcntl
    import struct
    items = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _, name in socket.if_nameindex():
            req = struct.pack("256s", name[:15].encode())
            try:
                addr = socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x8915, req)[20:24])   # SIOCGIFADDR
                mask = socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x891B, req)[20:24])   # SIOCGIFNETMASK
            except OSError:
                continue
            prefix = ipaddress.ip_network(f"0.0.0.0/{mask}").prefixlen
            items.append((name, f"{addr}/{prefix}"))
    finally:
        sock.close()
    return items


def local_networks() -> list[dict]:
    """Redes IPv4 do servidor, prontas para varredura (no máximo MAX_HOSTS endereços cada)."""
    raw = _ip_command()
    if not raw:
        try:
            raw = _ioctl()
        except Exception:
            raw = []
    result, seen = [], set()
    for iface, cidr in raw:
        if iface.startswith(_SKIP_IFACES):
            continue
        intf = ipaddress.ip_interface(cidr)
        if intf.ip.is_loopback or intf.ip.is_link_local:
            continue
        net, note = intf.network, None
        if net.num_addresses > MAX_HOSTS + 2:
            net = ipaddress.ip_interface(f"{intf.ip}/{_DEFAULT_PREFIX}").network
            note = f"A rede {intf.network} é grande; sugerida a faixa /{_DEFAULT_PREFIX} deste servidor"
        elif net.prefixlen >= 31:  # comum em nuvem (GCP usa /32)
            net = ipaddress.ip_interface(f"{intf.ip}/{_DEFAULT_PREFIX}").network
            note = f"Interface ponto a ponto; sugerida a faixa /{_DEFAULT_PREFIX} deste servidor"
        if str(net) in seen:
            continue
        seen.add(str(net))
        result.append({"interface": iface, "address": str(intf.ip), "network": str(net),
                       "hosts": max(net.num_addresses - 2, 1), "note": note})
    return result


def inventory_networks(addresses: list[str], exclude: list[str]) -> list[dict]:
    """Faixas /24 onde já existem máquinas no inventário e que não são redes deste servidor."""
    excluded = [ipaddress.ip_network(n) for n in exclude]
    counts: dict[str, int] = {}
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.version != 4 or ip.is_loopback or any(ip in n for n in excluded):
            continue
        net = str(ipaddress.ip_interface(f"{ip}/24").network)
        counts[net] = counts.get(net, 0) + 1
    return [{"network": n, "hosts": 254, "machines": c} for n, c in sorted(counts.items())]


# ----------------------------------------------------------------------------
# Disponibilidade (online/offline)
# ----------------------------------------------------------------------------
PROBE_PORTS = {"linux": (22,), "windows": (5985, 5986, 445, 3389)}


def is_reachable(address: str, platform: str, timeout: float = 2.0) -> bool:
    """Responde em alguma porta de gerenciamento? (sem credencial, apenas conexão TCP)."""
    ports = PROBE_PORTS.get(platform, (22, 5985, 445, 3389))
    return any(_probe(address, p, timeout) for p in ports)
