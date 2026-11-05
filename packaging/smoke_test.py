"""Teste rápido de uma instalação: inicia o servidor, faz login, cria e testa um destino local."""
import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.request

PREFIX = os.environ.get("BACKUPHUB_PREFIX", "/opt/backuphub")
PORT = os.environ.get("SMOKE_PORT", "8080")
BASE = f"http://127.0.0.1:{PORT}"

proc = subprocess.Popen([f"{PREFIX}/bin/backuphub-server"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(path, body=None):
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Requested-With": "BackupHub"})
    with opener.open(req, timeout=10) as r:
        return json.loads(r.read())


try:
    for _ in range(60):
        try:
            call("/api/health")
            break
        except Exception:
            if proc.poll() is not None:
                print(proc.stdout.read().decode(errors="replace"))
                sys.exit("servidor encerrou")
            time.sleep(1)
    else:
        sys.exit("servidor não respondeu")
    call("/api/auth/login", {"username": "admin", "password": os.environ["SMOKE_PASSWORD"]})
    dest = call("/api/destinations", {"name": "local", "type": "local", "config": {"path": "/tmp/bh-smoke"}})
    res = call(f"/api/destinations/{dest['id']}/test", {})
    assert res["ok"], res
    assert len(call("/api/dashboard")["history"]) == 14
    import platform
    print(f"SMOKE OK — Python {sys.version.split()[0]} — {res['message']}")
finally:
    proc.terminate()
