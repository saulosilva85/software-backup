"""Descoberta de servidores on-premise por varredura TCP de uma faixa de rede."""
from __future__ import annotations

import ipaddress
import os
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


def _dns_name(msg: bytes, offset: int, depth: int = 0) -> tuple[str, int]:
    """Lê um nome DNS (com compressão) e retorna (nome, offset após o nome)."""
    labels, jumped, end = [], False, offset
    while True:
        length = msg[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 == 0xC0:
            if depth > 10:
                raise ValueError("compressão inválida")
            pointer = ((length & 0x3F) << 8) | msg[offset + 1]
            name, _ = _dns_name(msg, pointer, depth + 1)
            labels.append(name)
            offset += 2
            jumped = True
            break
        labels.append(msg[offset + 1: offset + 1 + length].decode("utf-8", errors="replace"))
        offset += 1 + length
    end = offset
    return ".".join(x for x in labels if x), end if not jumped else offset


def parse_ptr_response(msg: bytes) -> str | None:
    """Extrai o primeiro registro PTR de uma resposta DNS/mDNS/LLMNR."""
    try:
        qd, an = int.from_bytes(msg[4:6], "big"), int.from_bytes(msg[6:8], "big")
        off = 12
        for _ in range(qd):
            _, off = _dns_name(msg, off)
            off += 4
        for _ in range(an):
            _, off = _dns_name(msg, off)
            rtype = int.from_bytes(msg[off:off + 2], "big")
            rdlen = int.from_bytes(msg[off + 8:off + 10], "big")
            off += 10
            if rtype == 12:
                name, _ = _dns_name(msg, off)
                return name
            off += rdlen
    except (IndexError, ValueError):
        return None
    return None


def _ptr_query(ip: str, port: int, unicast_bit: bool) -> bytes:
    rev = ".".join(reversed(ip.split("."))) + ".in-addr.arpa"
    qname = b"".join(bytes([len(p)]) + p.encode() for p in rev.split(".")) + b"\x00"
    qclass = 0x8001 if unicast_bit else 0x0001
    return b"\x42\x42\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + qname + b"\x00\x0c" + qclass.to_bytes(2, "big")


def multicast_name(ip: str, timeout: float = 0.8) -> str | None:
    """Nome via mDNS (Avahi/Bonjour, porta 5353) ou LLMNR (porta 5355), sem credencial.

    Muitos Linux (Avahi) e Windows (LLMNR) respondem; servidores mínimos podem não responder.
    """
    for port, unicast in ((5353, True), (5355, False)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                sock.sendto(_ptr_query(ip, port, unicast), (ip, port))
                data, _ = sock.recvfrom(4096)
        except OSError:
            continue
        name = parse_ptr_response(data)
        if name:
            return name[:-6] if name.endswith(".local") else name
    return None


_local_ips_cache: set[str] | None = None


def local_ips() -> set[str]:
    global _local_ips_cache
    if _local_ips_cache is None:
        ips = set()
        for _, cidr in (_ip_command() or []):
            ips.add(cidr.split("/")[0])
        if not ips:
            try:
                ips = {cidr.split("/")[0] for _, cidr in _ioctl()}
            except Exception:
                pass
        _local_ips_cache = ips
    return _local_ips_cache


def os_hint_from_banner(banner: str | None) -> str | None:
    """Sistema estimado pela identificação do SSH (ver osdetect.linux_from_banner)."""
    from .osdetect import linux_from_banner
    return linux_from_banner(banner)


def identify(address: str, platform: str, open_ports: list[int] | None = None, timeout: float = 2.0) -> dict:
    """Sistema (versão) e hostname sem credencial: NTLM no Windows, identificação SSH no Linux."""
    from .osdetect import windows_info
    result: dict = {}
    if platform == "windows" or (open_ports and (445 in open_ports or 5985 in open_ports)):
        info = windows_info(address, open_ports, timeout)
        if info:
            result["os"] = info.get("os")
            result["hostname"] = info.get("netbios_name") or (info.get("dns_name") or "").split(".")[0] or None
            result["domain"] = info.get("dns_domain") or None
    if not result.get("os") and (platform == "linux" or (open_ports and 22 in open_ports)):
        result["os"] = os_hint_from_banner(_ssh_banner(address, timeout))
    if not result.get("hostname"):
        result["hostname"] = resolve_hostname(address)
    return {k: v for k, v in result.items() if v}


def resolve_hostname(address: str, timeout: float = 0.8) -> str | None:
    """Nome sem credencial: o próprio servidor, DNS reverso (PTR) ou mDNS/LLMNR."""
    if address in local_ips():
        return socket.gethostname().split(".")[0]
    try:
        name = socket.gethostbyaddr(address)[0]
        if name and not name.replace(".", "").replace("-", "").isdigit() and not name.startswith("localhost"):
            return name.split(".")[0]
    except OSError:
        pass
    return multicast_name(address, timeout)


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
    if dns_name and (dns_name.replace(".", "").replace("-", "").isdigit() or dns_name.startswith("localhost")):
        dns_name = None  # PTR genérico (ex.: 192-168-0-10.provedor)
    own = socket.gethostname().split(".")[0] if ip in local_ips() else None  # o próprio servidor do BackupHub
    win = {}
    if 445 in open_ports or 5985 in open_ports:
        from .osdetect import windows_info
        win = windows_info(ip, open_ports, timeout * 3) or {}
    win_name = win.get("netbios_name") or ((win.get("dns_name") or "").split(".")[0] or None)
    mc_name = None if (nb_name or own or win_name) else multicast_name(ip, timeout + 0.4)
    return {
        "ip": ip,
        "hostname": nb_name or win_name or own or mc_name or (dns_name.split(".")[0] if dns_name else None),
        "dns_name": dns_name,
        "workgroup": workgroup,
        "os_hint": win.get("os") or os_hint_from_banner(banner),
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
PROBE_PORTS = {"linux": (22,), "windows": (5985, 5986, 445, 3389, 135)}


def _alive_tcp(ip: str, port: int, timeout: float) -> bool:
    """Máquina respondeu? Conexão aceita OU recusada (RST) indicam que ela está ligada."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except ConnectionRefusedError:
        return True
    except OSError:
        return False


def _ping(ip: str, timeout: float) -> bool:
    import shutil
    import subprocess
    exe = shutil.which("ping") or next((p for p in ("/usr/bin/ping", "/bin/ping") if os.path.exists(p)), None)
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "-c", "1", "-W", str(max(1, int(timeout))), ip],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout + 2)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def is_reachable(address: str, platform: str, timeout: float = 2.0) -> bool:
    """A máquina está ligada na rede? Sem credencial: TCP nas portas de gerenciamento e, se preciso, ping."""
    if address in local_ips():
        return True  # o próprio servidor do BackupHub
    try:
        ip = socket.gethostbyname(address)
    except OSError:
        return False
    ports = PROBE_PORTS.get(platform, (22, 5985, 445, 3389))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        if any(pool.map(lambda p: _alive_tcp(ip, p, timeout), ports)):
            return True
    return _ping(ip, timeout)
