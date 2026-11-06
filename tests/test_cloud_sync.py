"""Sincronização automática do inventário de nuvem e detecção de máquinas removidas."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from conftest import HEADERS

from backuphub import db, jobs, scheduler
from backuphub.config import Config
from backuphub.inventory import aws


def ec2(instance_id, name, state="running"):
    return {"name": name, "instance_id": instance_id, "region": "sa-east-1", "platform": "linux", "os": "Linux/UNIX",
            "cpu": 2, "memory_mb": 4096, "disks": [], "ip_private": "172.31.0.10", "ip_public": None,
            "address": "172.31.0.10", "state": state, "tags": {"Name": name}, "extra": {}}


@pytest.fixture()
def fake_aws(monkeypatch):
    state = {"instances": [], "errors": []}
    monkeypatch.setattr(aws, "list_instances", lambda secret: (list(state["instances"]), list(state["errors"])))
    return state


@pytest.fixture()
def alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(jobs, "send_webhook", lambda text, payload=None: sent.append((text, payload)))
    return sent


def aws_credential(client):
    return client.post("/api/credentials", json={"name": "aws", "type": "aws", "data": {"regions": "sa-east-1"}},
                       headers=HEADERS).json


def visible(client):
    return sorted(m["name"] for m in client.get("/api/machines").json)


def test_terminated_instance_leaves_inventory_and_alerts(client, fake_aws, alerts):
    cred = aws_credential(client)
    assert cred["sync_enabled"] == 1
    fake_aws["instances"] = [ec2("i-1", "erp"), ec2("i-2", "web")]
    scheduler.cloud_sync_tick(wait=True)          # primeira sincronização: automática
    assert visible(client) == ["erp", "web"]

    erp = db.query_one("SELECT id FROM machines WHERE instance_id='i-1'")["id"]
    db.insert("jobs", {"run_id": "r", "kind": "backup", "machine_id": erp, "machine_name": "erp", "mode": "snapshot",
                       "status": "success", "created_at": db.utcnow(), "finished_at": db.utcnow()})

    # EC2 "erp" terminada (some da listagem) e "web" terminada mas ainda listada pela AWS
    fake_aws["instances"] = [ec2("i-2", "web", state="terminated")]
    from backuphub.inventory import sync_cloud
    r = sync_cloud(cred["id"])
    assert r["removed"] == 2 and sorted(r["removed_names"]) == ["erp", "web"]
    assert visible(client) == []
    all_rows = client.get("/api/machines?include_terminated=1").json
    assert {m["name"]: m["state"] for m in all_rows} == {"erp": "terminated", "web": "terminated"}
    assert all(m["terminated_at"] for m in all_rows)
    # alerta somente para a máquina que tinha backup
    assert len(alerts) == 1 and "erp" in alerts[0][0]
    # nova sincronização não repete o alerta
    sync_cloud(cred["id"])
    assert len(alerts) == 1, alerts
    # status da sincronização registrado na conta
    c = client.get("/api/credentials").json[0]
    assert c["last_sync_status"] == "ok" and "0 removida" in c["last_sync_message"]  # última: nada novo


def test_partial_listing_does_not_remove(client, fake_aws, alerts):
    cred = aws_credential(client)
    fake_aws["instances"] = [ec2("i-1", "erp")]
    scheduler.cloud_sync_tick(wait=True)
    fake_aws["instances"], fake_aws["errors"] = [], ["us-east-1: AccessDenied"]
    from backuphub.inventory import sync_cloud
    sync_cloud(cred["id"])
    assert visible(client) == ["erp"]            # falha de permissão não "some" com máquinas
    assert client.get("/api/credentials").json[0]["last_sync_status"] == "warning"


def test_reappearing_instance_is_restored(client, fake_aws, alerts):
    cred = aws_credential(client)
    from backuphub.inventory import sync_cloud
    fake_aws["instances"] = [ec2("i-1", "erp")]
    sync_cloud(cred["id"])
    fake_aws["instances"] = []
    sync_cloud(cred["id"])
    fake_aws["instances"] = [ec2("i-1", "erp", state="stopped")]
    sync_cloud(cred["id"])
    m = client.get("/api/machines").json[0]
    assert m["state"] == "stopped" and m["terminated_at"] is None


def test_schedule_interval_and_toggle(client, fake_aws, monkeypatch):
    monkeypatch.setattr(Config, "CLOUD_SYNC_MINUTES", 60)
    cred = aws_credential(client)
    assert scheduler.due_cloud_syncs() == [cred["id"]]
    scheduler.cloud_sync_tick(wait=True)
    assert scheduler.due_cloud_syncs() == []                       # acabou de sincronizar
    later = datetime.now(timezone.utc) + timedelta(minutes=61)
    assert scheduler.due_cloud_syncs(later) == [cred["id"]]        # vence após o intervalo
    client.put(f"/api/credentials/{cred['id']}", json={"sync_enabled": False}, headers=HEADERS)
    assert scheduler.due_cloud_syncs(later) == []                  # desativada na conta
    monkeypatch.setattr(Config, "CLOUD_SYNC_MINUTES", 0)
    client.put(f"/api/credentials/{cred['id']}", json={"sync_enabled": True}, headers=HEADERS)
    assert scheduler.due_cloud_syncs(later) == []                  # desativada no servidor


def test_gcp_stopped_vm_is_not_removed():
    from backuphub.inventory.gcp import GCP_STATES
    assert GCP_STATES["TERMINATED"] == "stopped"


def test_migration_adds_columns_to_old_database(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE credentials (id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL, "
                 "description TEXT, data_enc TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO credentials VALUES (1, 'x', 'aws', NULL, 'e', '2026-01-01')")
    conn.commit(); conn.close()
    db.init_db(str(path))
    row = db.query_one("SELECT sync_enabled, last_sync_at FROM credentials WHERE id = 1")
    assert row["sync_enabled"] == 1 and row["last_sync_at"] is None
