from conftest import HEADERS


def test_requires_login(app):
    c = app.test_client()
    assert c.get("/api/machines").status_code == 401


def test_csrf_header_required(client):
    r = client.post("/api/machines", json={"name": "x", "address": "1.1.1.1", "platform": "linux"})
    assert r.status_code == 400


def test_credentials_are_masked_and_kept(client):
    r = client.post("/api/credentials", json={"name": "lin", "type": "ssh",
                                              "data": {"username": "backup", "password": "s3cr3t"}}, headers=HEADERS)
    assert r.status_code == 201
    cid = r.json["id"]
    assert r.json["data"]["password"] != "s3cr3t"
    # edição sem senha mantém a anterior
    client.put(f"/api/credentials/{cid}", json={"data": {"username": "root", "password": ""}}, headers=HEADERS)
    from backuphub.security import credential_secret
    _, secret = credential_secret(cid)
    assert secret == {"username": "root", "password": "s3cr3t"}


def test_machine_crud_and_filters(client):
    for name, plat in (("web", "linux"), ("ad", "windows")):
        assert client.post("/api/machines", json={"name": name, "address": f"10.0.0.{len(name)}", "platform": plat},
                           headers=HEADERS).status_code == 201
    assert len(client.get("/api/machines").json) == 2
    assert [m["name"] for m in client.get("/api/machines?platform=windows").json] == ["ad"]
    assert [m["name"] for m in client.get("/api/machines?q=we").json] == ["web"]


def test_policy_validation_and_next_run(client, tmp_path):
    d = client.post("/api/destinations", json={"name": "nas", "type": "local", "config": {"path": str(tmp_path)}},
                    headers=HEADERS).json
    bad = client.post("/api/policies", json={"name": "p", "days": [], "times": ["02:00"], "all_machines": True,
                                             "destination_id": d["id"]}, headers=HEADERS)
    assert bad.status_code == 400
    bad = client.post("/api/policies", json={"name": "p", "days": [1], "times": ["25:00"], "all_machines": True,
                                             "destination_id": d["id"]}, headers=HEADERS)
    assert bad.status_code == 400
    ok = client.post("/api/policies", json={"name": "p", "days": [1, 4], "times": "23:30", "all_machines": True,
                                            "destination_id": d["id"], "retention_count": 5}, headers=HEADERS)
    assert ok.status_code == 201
    assert ok.json["next_run_at"] and len(ok.json["upcoming"]) == 3
    assert client.post("/api/destinations/%d/test" % d["id"], headers=HEADERS).json["ok"]


def test_viewer_cannot_change(client, app):
    client.post("/api/users", json={"username": "ana", "password": "12345678", "role": "viewer"}, headers=HEADERS)
    v = app.test_client()
    v.post("/api/auth/login", json={"username": "ana", "password": "12345678"}, headers=HEADERS)
    assert v.get("/api/machines").status_code == 200
    assert v.post("/api/machines", json={"name": "x", "address": "y", "platform": "linux"},
                  headers=HEADERS).status_code == 403
    assert v.get("/api/credentials").status_code == 403


def test_dashboard(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200 and len(r.json["history"]) == 14
