"""Descoberta de servidores on-premise por varredura TCP de uma faixa de rede."""
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


def scan_host(ip: str, timeout: float = 0.6) -> dict | None:
    open_ports = [p for p in PORTS if _probe(ip, p, timeout)]
    if not open_ports:
        return None
    banner = _ssh_banner(ip, timeout * 2) if 22 in open_ports else None
    try:
        hostname = socket.gethostbyaddr(ip)[0]
    except OSError:
        hostname = None
    return {
        "ip": ip,
        "hostname": hostname,
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
