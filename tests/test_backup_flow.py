"""Fluxo completo: backup Linux (tar via "SSH") → destino local → retenção → download → restauração."""
from __future__ import annotations

import io
import tarfile
import time

from conftest import HEADERS

from backuphub import db, jobs


def wait_job(job_id, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        j = db.get("jobs", job_id)
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.1)
    raise AssertionError("job não terminou")


def setup_env(client, tmp_path):
    src = tmp_path / "srv" / "app"
    (src / "conf").mkdir(parents=True)
    (src / "conf" / "app.ini").write_text("porta=8080\n")
    (src / "data.bin").write_bytes(b"x" * 100_000)
    (src / "lixo.tmp").write_text("ignorar")
    store = tmp_path / "store"
    cred = client.post("/api/credentials", json={"name": "lin", "type": "ssh", "data": {"username": "u", "password": "p"}},
                       headers=HEADERS).json["id"]
    dest = client.post("/api/destinations", json={"name": "nas", "type": "local", "config": {"path": str(store),
                                                                                         "prefix": "bh"}},
                       headers=HEADERS).json["id"]
    mid = client.post("/api/machines", json={"name": "web-01", "address": "127.0.0.1", "platform": "linux",
                                             "credential_id": cred}, headers=HEADERS).json["id"]
    return src, store, dest, mid


def test_backup_retention_download_restore(client, tmp_path, fake_ssh):
    jobs.init(2)
    src, store, dest, mid = setup_env(client, tmp_path)
    body = {"machine_ids": [mid], "destination_id": dest, "mode": "auto",
            "paths_linux": f"{src}\n/caminho/inexistente", "excludes": "*.tmp", "retention_count": 2}

    finished = []
    for _ in range(3):
        r = client.post("/api/backups/run", json=body, headers=HEADERS)
        assert r.status_code == 202
        finished.append(wait_job(r.json["job_ids"][0]))
        time.sleep(1.1)  # nomes de arquivo têm resolução de segundos

    job = finished[-1]
    assert job["status"] == "success", job["log"]
    assert job["mode"] == "files" and job["size_bytes"] > 0 and len(job["sha256"]) == 64
    assert "inexistente" in job["log"]

    # retenção: só 2 arquivos permanecem
    archives = sorted(p for p in store.rglob("*.tar.gz"))
    assert len(archives) == 2
    with tarfile.open(archives[-1]) as tf:
        names = tf.getnames()
    assert any(n.endswith("conf/app.ini") for n in names)
    assert not any(n.endswith(".tmp") for n in names)

    # download
    r = client.get(f"/api/jobs/{job['id']}/download")
    assert r.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(r.data)) as tf:
        assert any(n.endswith("data.bin") for n in tf.getnames())

    # restauração em outro diretório
    target = tmp_path / "restore"
    r = client.post(f"/api/jobs/{job['id']}/restore", json={"target_path": str(target)}, headers=HEADERS)
    assert r.status_code == 202
    rj = wait_job(r.json["job_id"])
    assert rj["status"] == "success", rj["log"]
    restored = target / str(src).lstrip("/") / "conf" / "app.ini"
    assert restored.read_text() == "porta=8080\n"


def test_backup_fails_without_credential(client, tmp_path):
    jobs.init(1)
    dest = client.post("/api/destinations", json={"name": "nas", "type": "local", "config": {"path": str(tmp_path)}},
                       headers=HEADERS).json["id"]
    mid = client.post("/api/machines", json={"name": "x", "address": "1.2.3.4", "platform": "linux"},
                      headers=HEADERS).json["id"]
    r = client.post("/api/backups/run", json={"machine_ids": [mid], "destination_id": dest}, headers=HEADERS)
    j = wait_job(r.json["job_ids"][0])
    assert j["status"] == "failed" and "credencial" in j["message"]


def test_transfer_token_upload(client, tmp_path):
    """Simula o servidor Windows enviando o .zip para um destino local via token."""
    from backuphub import storage
    dest = client.post("/api/destinations", json={"name": "nas", "type": "local", "config": {"path": str(tmp_path)}},
                       headers=HEADERS).json["id"]
    url, headers = storage.open_destination(dest).upload_url("srv/manual/x.zip", 60)
    token = url.rsplit("/", 1)[-1]
    anon = client.application.test_client()
    assert anon.put(f"/api/transfer/{token}", data=b"PK\x03\x04zip", headers=headers).status_code == 200
    assert (tmp_path / "srv/manual/x.zip").read_bytes() == b"PK\x03\x04zip"
    assert anon.put(f"/api/transfer/{token}", data=b"again").status_code == 403  # uso único
