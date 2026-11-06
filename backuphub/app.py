"""Aplicação web (API REST + interface) do BackupHub."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, request, send_from_directory, session, stream_with_context

from . import db, inventory, jobs, scheduler, security, storage
from .config import Config
from .inventory import network
from .security import credential_secret, current_user

STATIC_DIR = Path(__file__).resolve().parent / "static"
ROLES = {"viewer": 0, "operator": 1, "admin": 2}

CREDENTIAL_FIELDS = {
    "ssh": ["username", "password", "private_key", "passphrase", "port", "use_sudo"],
    "winrm": ["username", "password", "port", "use_https", "transport", "ignore_cert"],
    "aws": ["access_key_id", "secret_access_key", "session_token", "role_arn", "default_region", "regions"],
    "gcp": ["service_account_json", "projects"],
}
DEST_FIELDS = {
    "s3": ["bucket", "prefix", "region", "endpoint_url", "storage_class", "sse"],
    "gcs": ["bucket", "prefix", "storage_class"],
    "local": ["path", "prefix"],
}
MODES = ("auto", "files", "snapshot")

_inventory_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="inventory")


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def role_required(min_role: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"error": "Não autenticado"}), 401
            if ROLES.get(user["role"], 0) < ROLES[min_role]:
                return jsonify({"error": "Permissão negada para o seu perfil"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return deco


def body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ApiError("JSON inválido")
    return data


def require(data: dict, *fields):
    missing = [f for f in fields if data.get(f) in (None, "", [])]
    if missing:
        raise ApiError("Campos obrigatórios: " + ", ".join(missing))


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.replace("\r", "").replace(",", "\n").split("\n")
    return [str(v).strip() for v in value if str(v).strip()]


def get_or_404(table: str, row_id: int) -> dict:
    row = db.get(table, row_id)
    if not row:
        raise ApiError("Registro não encontrado", 404)
    return row


def create_app(config: type[Config] = Config, start_background: bool = True) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.secret_key = config.secret_key()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
                      MAX_CONTENT_LENGTH=None)
    db.init_db(config.DATABASE)
    security.init_crypto(config.encryption_key())
    security.ensure_admin(config.ADMIN_USER, config.ADMIN_PASSWORD)
    if start_background:
        jobs.init(config.MAX_PARALLEL_JOBS)
        if config.SCHEDULER_ENABLED:
            scheduler.start()

    @app.errorhandler(ApiError)
    def _api_error(exc):
        return jsonify({"error": str(exc)}), exc.status

    @app.errorhandler(Exception)
    def _unexpected(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return jsonify({"error": exc.description}), exc.code
        logging.getLogger("backuphub").exception("Erro na requisição")
        return jsonify({"error": str(exc)}), 500

    @app.before_request
    def _csrf():
        # Requisições que alteram estado exigem um cabeçalho customizado (bloqueia CSRF por formulário).
        if request.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE") \
                and not request.path.startswith("/api/transfer/"):
            if request.headers.get("X-Requested-With") != "BackupHub":
                return jsonify({"error": "Cabeçalho X-Requested-With ausente"}), 400

    # ------------------------------------------------------------- Interface
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "time": db.utcnow()})

    # ------------------------------------------------------------- Autenticação
    @app.post("/api/auth/login")
    def login():
        data = body()
        user = db.query_one("SELECT * FROM users WHERE username = ?", (data.get("username", ""),))
        if not user or not security.verify_password(user["password_hash"], data.get("password", "")):
            time.sleep(0.5)
            raise ApiError("Usuário ou senha inválidos", 401)
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        default_pw = data.get("password") == "admin123"
        return jsonify({"user": current_user(), "default_password": default_pw})

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/auth/me")
    @role_required("viewer")
    def me():
        return jsonify({"user": current_user()})

    @app.post("/api/auth/password")
    @role_required("viewer")
    def change_password():
        data = body()
        require(data, "current_password", "new_password")
        user = db.get("users", current_user()["id"])
        if not security.verify_password(user["password_hash"], data["current_password"]):
            raise ApiError("Senha atual incorreta")
        if len(data["new_password"]) < 8:
            raise ApiError("A nova senha deve ter pelo menos 8 caracteres")
        db.update("users", user["id"], {"password_hash": security.hash_password(data["new_password"])})
        return jsonify({"ok": True})

    # ------------------------------------------------------------- Dashboard
    @app.get("/api/dashboard")
    @role_required("viewer")
    def dashboard():
        machines = db.query("SELECT provider, platform, state FROM machines WHERE COALESCE(state,'') != 'terminated'")
        by_provider, by_platform = {}, {}
        for m in machines:
            by_provider[m["provider"]] = by_provider.get(m["provider"], 0) + 1
            by_platform[m["platform"]] = by_platform.get(m["platform"], 0) + 1
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        protected = db.query_one(
            "SELECT COUNT(DISTINCT machine_id) AS n FROM jobs WHERE kind='backup' AND status IN ('success','warning') "
            "AND finished_at >= ?", (since,))["n"]
        day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        last24 = {r["status"]: r["n"] for r in db.query(
            "SELECT status, COUNT(*) AS n FROM jobs WHERE created_at >= ? GROUP BY status", (day_ago,))}
        stored = db.query_one("SELECT COALESCE(SUM(size_bytes),0) AS b FROM jobs WHERE kind='backup' AND mode='files' "
                              "AND status IN ('success','warning')")["b"]
        start = (datetime.now(timezone.utc) - timedelta(days=13)).date()
        history = {(start + timedelta(days=i)).isoformat(): {"success": 0, "failed": 0, "bytes": 0} for i in range(14)}
        for r in db.query("SELECT substr(created_at,1,10) AS d, status, COUNT(*) AS n, COALESCE(SUM(size_bytes),0) AS b "
                          "FROM jobs WHERE kind='backup' AND created_at >= ? GROUP BY d, status", (start.isoformat(),)):
            if r["d"] in history:
                key = "failed" if r["status"] == "failed" else "success"
                if r["status"] in ("success", "warning", "failed"):
                    history[r["d"]][key] += r["n"]
                    history[r["d"]]["bytes"] += r["b"] if key == "success" else 0
        upcoming = db.query("SELECT id, name, next_run_at FROM policies WHERE enabled=1 AND next_run_at IS NOT NULL "
                            "ORDER BY next_run_at LIMIT 5")
        recent = db.query("SELECT id, kind, machine_name, policy_name, status, mode, size_bytes, created_at, finished_at, "
                          "message FROM jobs ORDER BY id DESC LIMIT 8")
        return jsonify({
            "machines": {"total": len(machines), "by_provider": by_provider, "by_platform": by_platform,
                         "protected_7d": protected},
            "jobs_24h": last24, "stored_bytes": stored, "running": db.query_one(
                "SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued','running')")["n"],
            "history": [{"date": d, **v} for d, v in history.items()],
            "upcoming": upcoming, "recent": recent,
            "policies": db.query_one("SELECT COUNT(*) AS n FROM policies WHERE enabled=1")["n"],
            "destinations": db.query_one("SELECT COUNT(*) AS n FROM destinations")["n"],
        })

    # ------------------------------------------------------------- Credenciais
    def credential_out(row):
        data = security.decrypt(row["data_enc"])
        return {k: v for k, v in row.items() if k != "data_enc"} | {"data": security.mask(data)}

    def credential_data(ctype: str, incoming: dict, current: dict | None = None) -> dict:
        data = dict(current or {})
        for field in CREDENTIAL_FIELDS[ctype]:
            if field not in incoming:
                continue
            value = incoming[field]
            if field in security.SECRET_FIELDS and value in ("", None, "••••••"):
                continue  # mantém o segredo já salvo
            data[field] = value
        return data

    @app.get("/api/credentials")
    @role_required("operator")
    def list_credentials():
        rows = db.query("SELECT c.*, (SELECT COUNT(*) FROM machines m WHERE m.credential_id=c.id "
                        "OR m.cloud_credential_id=c.id) AS usage FROM credentials c ORDER BY name")
        return jsonify([credential_out(r) for r in rows])

    @app.post("/api/credentials")
    @role_required("admin")
    def create_credential():
        data = body()
        require(data, "name", "type")
        if data["type"] not in CREDENTIAL_FIELDS:
            raise ApiError("Tipo de credencial inválido")
        secret = credential_data(data["type"], data.get("data") or {})
        if data["type"] in ("ssh", "winrm"):
            require(secret, "username")
        if data["type"] == "gcp":
            require(secret, "service_account_json")
        cid = db.insert("credentials", {"name": data["name"], "type": data["type"],
                                        "description": data.get("description"),
                                        "sync_enabled": 1 if data.get("sync_enabled", True) else 0,
                                        "data_enc": security.encrypt(secret), "created_at": db.utcnow()})
        return jsonify(credential_out(db.get("credentials", cid))), 201

    @app.put("/api/credentials/<int:cid>")
    @role_required("admin")
    def update_credential(cid):
        row = get_or_404("credentials", cid)
        data = body()
        secret = credential_data(row["type"], data.get("data") or {}, security.decrypt(row["data_enc"]))
        db.update("credentials", cid, {"name": data.get("name", row["name"]),
                                       "description": data.get("description", row["description"]),
                                       "sync_enabled": (1 if data["sync_enabled"] else 0) if "sync_enabled" in data
                                       else row["sync_enabled"],
                                       "data_enc": security.encrypt(secret)})
        return jsonify(credential_out(db.get("credentials", cid)))

    @app.delete("/api/credentials/<int:cid>")
    @role_required("admin")
    def delete_credential(cid):
        get_or_404("credentials", cid)
        db.delete("credentials", cid)
        return jsonify({"ok": True})

    @app.post("/api/credentials/<int:cid>/test")
    @role_required("operator")
    def test_credential(cid):
        row, secret = credential_secret(cid)
        if not row:
            raise ApiError("Credencial não encontrada", 404)
        host = body().get("host")
        try:
            if row["type"] == "ssh":
                require({"host": host}, "host")
                from .remote.ssh import SSHClient
                with SSHClient(host, secret) as ssh:
                    _, out, _ = ssh.run("uname -a", sudo=False)
                msg = out.strip()
            elif row["type"] == "winrm":
                require({"host": host}, "host")
                from .remote.winrm import WinRMClient
                msg = WinRMClient(host, secret).check("(Get-CimInstance Win32_OperatingSystem).Caption").strip()
            elif row["type"] == "aws":
                from .cloud import aws_session
                ident = aws_session(secret).client("sts").get_caller_identity()
                msg = f"Conta {ident['Account']} — {ident['Arn']}"
            else:
                from .cloud import gcp_credentials
                from google.auth.transport.requests import Request
                creds, info = gcp_credentials(secret)
                creds.refresh(Request())
                msg = f"Service account {info.get('client_email')} (projeto {info.get('project_id')})"
        except ApiError:
            raise
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)})
        return jsonify({"ok": True, "message": msg})

    # ------------------------------------------------------------- Inventário
    MACHINE_FIELDS = ("name", "address", "platform", "credential_id", "tags", "os")

    def machine_out(m: dict, last_jobs: dict) -> dict:
        m["last_backup"] = last_jobs.get(m["id"])
        return m

    def last_backup_map() -> dict:
        rows = db.query("SELECT j.machine_id, j.status, j.finished_at, j.size_bytes FROM jobs j JOIN "
                        "(SELECT machine_id, MAX(id) AS id FROM jobs WHERE kind='backup' AND status NOT IN "
                        "('queued','running') GROUP BY machine_id) x ON x.id = j.id")
        return {r["machine_id"]: r for r in rows}

    @app.get("/api/machines")
    @role_required("viewer")
    def list_machines():
        sql, params = "SELECT * FROM machines WHERE 1=1", []
        for f in ("provider", "platform"):
            if request.args.get(f):
                sql += f" AND {f} = ?"
                params.append(request.args[f])
        if request.args.get("q"):
            sql += " AND (name LIKE ? OR address LIKE ? OR instance_id LIKE ? OR os LIKE ?)"
            params += [f"%{request.args['q']}%"] * 4
        if request.args.get("include_terminated") != "1":
            sql += " AND COALESCE(state,'') != 'terminated'"
        last = last_backup_map()
        return jsonify([machine_out(m, last) for m in db.query(sql + " ORDER BY provider, name", params)])

    @app.get("/api/machines/<int:mid>")
    @role_required("viewer")
    def get_machine(mid):
        m = get_or_404("machines", mid)
        m["jobs"] = db.query("SELECT id, kind, status, mode, size_bytes, created_at, finished_at, message, policy_name "
                             "FROM jobs WHERE machine_id = ? ORDER BY id DESC LIMIT 20", (mid,))
        return jsonify(m)

    @app.post("/api/machines")
    @role_required("operator")
    def create_machine():
        data = body()
        require(data, "name", "address", "platform")
        if data["platform"] not in ("linux", "windows"):
            raise ApiError("Plataforma deve ser linux ou windows")
        mid = db.insert("machines", {**{k: data.get(k) for k in MACHINE_FIELDS}, "provider": "onprem",
                                     "state": "unknown", "inventory_status": "pending", "created_at": db.utcnow()})
        if data.get("collect") and data.get("credential_id"):
            _queue_inventory([mid])
        return jsonify(db.get("machines", mid)), 201

    @app.put("/api/machines/<int:mid>")
    @role_required("operator")
    def update_machine(mid):
        m = get_or_404("machines", mid)
        data = body()
        allowed = MACHINE_FIELDS if m["provider"] == "onprem" else ("credential_id", "address", "tags", "platform")
        db.update("machines", mid, {k: data[k] for k in allowed if k in data})
        return jsonify(db.get("machines", mid))

    @app.delete("/api/machines/<int:mid>")
    @role_required("operator")
    def delete_machine(mid):
        get_or_404("machines", mid)
        db.delete("machines", mid)
        return jsonify({"ok": True})

    def _collect(mid):
        try:
            inventory.collect_machine(mid)
        except Exception:
            pass  # erro já gravado na máquina

    def _queue_inventory(ids):
        for mid in ids:
            db.update("machines", mid, {"inventory_status": "running"})
            _inventory_pool.submit(_collect, mid)

    @app.post("/api/machines/inventory")
    @role_required("operator")
    def bulk_inventory():
        ids = [int(i) for i in body().get("ids") or []]
        if not ids:
            raise ApiError("Selecione ao menos uma máquina")
        _queue_inventory(ids)
        return jsonify({"queued": len(ids)}), 202

    @app.post("/api/discovery/scan")
    @role_required("operator")
    def discovery_scan():
        data = body()
        require(data, "target")
        try:
            hosts = network.scan(data["target"], timeout=float(data.get("timeout") or 0.6))
        except ValueError as exc:
            raise ApiError(str(exc))
        known = {m["address"] for m in db.query("SELECT address FROM machines WHERE address IS NOT NULL")}
        for h in hosts:
            h["known"] = h["ip"] in known or (h["hostname"] in known if h["hostname"] else False)
        return jsonify(hosts)

    @app.post("/api/discovery/import")
    @role_required("operator")
    def discovery_import():
        data = body()
        hosts = data.get("hosts") or []
        known = {m["address"] for m in db.query("SELECT address FROM machines WHERE address IS NOT NULL")}
        created = []
        for h in hosts:
            if h.get("ip") in known:
                continue
            platform = h.get("platform") if h.get("platform") in ("linux", "windows") else "linux"
            cred = data.get("credential_windows") if platform == "windows" else data.get("credential_linux")
            mid = db.insert("machines", {"name": h.get("hostname") or h["ip"], "address": h["ip"],
                                         "platform": platform, "provider": "onprem", "credential_id": cred or None,
                                         "state": "online", "inventory_status": "pending",
                                         "created_at": db.utcnow()})
            created.append(mid)
        to_collect = [mid for mid in created if db.get("machines", mid)["credential_id"]]
        if data.get("collect", True) and to_collect:
            _queue_inventory(to_collect)
        return jsonify({"created": len(created), "inventory_queued": len(to_collect)})

    @app.post("/api/cloud/sync")
    @role_required("operator")
    def cloud_sync():
        data = body()
        require(data, "credential_id")
        try:
            result = inventory.sync_cloud(int(data["credential_id"]))
        except ValueError as exc:
            raise ApiError(str(exc))
        return jsonify(result)

    # ------------------------------------------------------------- Destinos
    def destination_in(data: dict, current: dict | None = None) -> dict:
        dtype = data.get("type") or (current or {}).get("type")
        if dtype not in DEST_FIELDS:
            raise ApiError("Tipo de destino inválido (s3, gcs ou local)")
        incoming = data.get("config") or {}
        config = {f: incoming.get(f) for f in DEST_FIELDS[dtype] if incoming.get(f) not in (None, "")}
        if dtype in ("s3", "gcs"):
            require(config, "bucket")
        else:
            require(config, "path")
        return {"name": data.get("name") or (current or {}).get("name"), "type": dtype, "config": config,
                "credential_id": data.get("credential_id") or None}

    @app.get("/api/destinations")
    @role_required("viewer")
    def list_destinations():
        rows = db.query("SELECT d.*, (SELECT COUNT(*) FROM policies p WHERE p.destination_id = d.id) AS policies, "
                        "(SELECT COALESCE(SUM(size_bytes),0) FROM jobs j WHERE j.destination_id = d.id AND "
                        "j.kind='backup' AND j.status IN ('success','warning')) AS stored_bytes "
                        "FROM destinations d ORDER BY name")
        return jsonify(rows)

    @app.post("/api/destinations")
    @role_required("admin")
    def create_destination():
        values = destination_in(body())
        require(values, "name")
        did = db.insert("destinations", {**values, "created_at": db.utcnow()})
        return jsonify(db.get("destinations", did)), 201

    @app.put("/api/destinations/<int:did>")
    @role_required("admin")
    def update_destination(did):
        current = get_or_404("destinations", did)
        db.update("destinations", did, destination_in(body(), current))
        return jsonify(db.get("destinations", did))

    @app.delete("/api/destinations/<int:did>")
    @role_required("admin")
    def delete_destination(did):
        get_or_404("destinations", did)
        db.delete("destinations", did)
        return jsonify({"ok": True})

    @app.post("/api/destinations/<int:did>/test")
    @role_required("operator")
    def test_destination(did):
        get_or_404("destinations", did)
        try:
            return jsonify({"ok": True, "message": storage.open_destination(did).test()})
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)})

    # ------------------------------------------------------------- Políticas / agendamentos
    def policy_in(data: dict) -> dict:
        require(data, "name")
        days = sorted({int(d) for d in data.get("days") or []})
        if any(d < 0 or d > 6 for d in days):
            raise ApiError("Dias da semana devem estar entre 0 (segunda) e 6 (domingo)")
        times = as_list(data.get("times"))
        for t in times:
            try:
                scheduler.parse_time(t)
            except Exception:
                raise ApiError(f"Horário inválido: {t} (use HH:MM)")
        if data.get("enabled", True) and (not days or not times):
            raise ApiError("Escolha ao menos um dia e um horário")
        mode = data.get("mode") or "auto"
        if mode not in MODES:
            raise ApiError("Modo inválido")
        if mode != "snapshot" and not data.get("destination_id"):
            raise ApiError("Escolha o destino (bucket) dos backups")
        if not data.get("all_machines") and not data.get("machine_ids"):
            raise ApiError("Selecione as máquinas ou marque 'todas as máquinas'")
        return {
            "name": data["name"], "enabled": bool(data.get("enabled", True)), "mode": mode,
            "days": days, "times": sorted(times), "all_machines": bool(data.get("all_machines")),
            "machine_ids": [int(i) for i in data.get("machine_ids") or []],
            "paths_linux": as_list(data.get("paths_linux")) or ["/etc", "/home"],
            "paths_windows": as_list(data.get("paths_windows")) or ["C:\\Users"],
            "excludes": as_list(data.get("excludes")),
            "destination_id": data.get("destination_id") or None,
            "retention_count": max(0, int(data.get("retention_count") or 0)),
        }

    def policy_out(p):
        p["upcoming"] = scheduler.upcoming(p["days"], p["times"], 3) if p["enabled"] else []
        p["machine_count"] = len(scheduler.policy_machine_ids(p))
        last = db.query_one("SELECT status, COUNT(*) AS n FROM jobs WHERE policy_id = ? AND run_id = "
                            "(SELECT run_id FROM jobs WHERE policy_id = ? ORDER BY id DESC LIMIT 1) GROUP BY status "
                            "ORDER BY n DESC LIMIT 1", (p["id"], p["id"]))
        p["last_status"] = last["status"] if last else None
        return p

    @app.get("/api/policies")
    @role_required("viewer")
    def list_policies():
        return jsonify([policy_out(p) for p in db.query("SELECT * FROM policies ORDER BY name")])

    @app.post("/api/policies")
    @role_required("operator")
    def create_policy():
        pid = db.insert("policies", {**policy_in(body()), "created_at": db.utcnow()})
        scheduler.refresh_policy(pid)
        return jsonify(policy_out(db.get("policies", pid))), 201

    @app.put("/api/policies/<int:pid>")
    @role_required("operator")
    def update_policy(pid):
        get_or_404("policies", pid)
        db.update("policies", pid, policy_in(body()))
        scheduler.refresh_policy(pid)
        return jsonify(policy_out(db.get("policies", pid)))

    @app.delete("/api/policies/<int:pid>")
    @role_required("operator")
    def delete_policy(pid):
        get_or_404("policies", pid)
        db.delete("policies", pid)
        return jsonify({"ok": True})

    @app.post("/api/policies/<int:pid>/run")
    @role_required("operator")
    def run_policy(pid):
        p = get_or_404("policies", pid)
        ids = scheduler.policy_machine_ids(p)
        if not ids:
            raise ApiError("A política não possui máquinas")
        return jsonify(jobs.enqueue_backup(ids, policy=p, trigger="manual")), 202

    @app.post("/api/schedule/preview")
    @role_required("viewer")
    def schedule_preview():
        data = body()
        try:
            return jsonify(scheduler.upcoming([int(d) for d in data.get("days") or []],
                                              as_list(data.get("times")), 6))
        except Exception:
            return jsonify([])

    # ------------------------------------------------------------- Backups / jobs
    @app.post("/api/backups/run")
    @role_required("operator")
    def run_backup_now():
        data = body()
        if data.get("all"):
            ids = [r["id"] for r in db.query("SELECT id FROM machines WHERE COALESCE(state,'') != 'terminated'")]
        else:
            ids = [int(i) for i in data.get("machine_ids") or []]
        if not ids:
            raise ApiError("Selecione ao menos uma máquina")
        mode = data.get("mode") or "auto"
        if mode not in MODES:
            raise ApiError("Modo inválido")
        overrides = {"mode": mode, "destination_id": data.get("destination_id"),
                     "paths_linux": as_list(data.get("paths_linux")) or None,
                     "paths_windows": as_list(data.get("paths_windows")) or None,
                     "excludes": as_list(data.get("excludes")),
                     "retention_count": int(data.get("retention_count") or 0)}
        if mode != "snapshot" and not overrides["destination_id"]:
            raise ApiError("Escolha o destino do backup")
        return jsonify(jobs.enqueue_backup(ids, trigger="manual", overrides=overrides)), 202

    @app.get("/api/jobs")
    @role_required("viewer")
    def list_jobs():
        sql = ("SELECT id, run_id, kind, trigger, policy_id, policy_name, machine_id, machine_name, mode, status, "
               "size_bytes, artifact, message, created_at, started_at, finished_at FROM jobs WHERE 1=1")
        params = []
        for f in ("status", "kind", "machine_id", "policy_id", "run_id"):
            if request.args.get(f):
                sql += f" AND {f} = ?"
                params.append(request.args[f])
        limit = min(int(request.args.get("limit", 100)), 500)
        offset = int(request.args.get("offset", 0))
        total = db.query_one(f"SELECT COUNT(*) AS n FROM ({sql})", params)["n"]
        rows = db.query(sql + " ORDER BY id DESC LIMIT ? OFFSET ?", (*params, limit, offset))
        return jsonify({"total": total, "items": rows})

    @app.get("/api/jobs/<int:jid>")
    @role_required("viewer")
    def get_job(jid):
        return jsonify(get_or_404("jobs", jid))

    @app.get("/api/jobs/<int:jid>/download")
    @role_required("operator")
    def download_job(jid):
        job = get_or_404("jobs", jid)
        if job["kind"] != "backup" or job["mode"] != "files" or job["status"] not in ("success", "warning"):
            raise ApiError("Download disponível apenas para backups de arquivos concluídos")
        dest = storage.open_destination(job["destination_id"])
        filename = job["artifact"].rsplit("/", 1)[-1]
        if isinstance(dest, storage.LocalDestination):
            fh = dest.open_read(job["artifact"])
            return Response(stream_with_context(iter(lambda: fh.read(1024 * 1024), b"")),
                            mimetype="application/octet-stream",
                            headers={"Content-Disposition": f'attachment; filename="{filename}"'})
        return redirect(dest.download_url(job["artifact"], 3600))

    @app.post("/api/jobs/<int:jid>/restore")
    @role_required("operator")
    def restore_job(jid):
        data = body()
        try:
            new_id = jobs.enqueue_restore(jid, data.get("machine_id"), data.get("target_path") or "")
        except ValueError as exc:
            raise ApiError(str(exc))
        return jsonify({"job_id": new_id}), 202

    # ------------------------------------------------------------- Transferência (Windows ↔ destino local)
    @app.put("/api/transfer/<token>")
    def transfer_put(token):
        info = storage.consume_token(token, "PUT")
        if not info:
            abort(403)
        dest = storage.open_destination(info["destination_id"])
        dest.upload_stream(info["key"], request.stream)
        return jsonify({"ok": True})

    @app.get("/api/transfer/<token>")
    def transfer_get(token):
        info = storage.consume_token(token, "GET")
        if not info:
            abort(403)
        fh = storage.open_destination(info["destination_id"]).open_read(info["key"])
        return Response(stream_with_context(iter(lambda: fh.read(1024 * 1024), b"")),
                        mimetype="application/octet-stream")

    # ------------------------------------------------------------- Usuários
    @app.get("/api/users")
    @role_required("admin")
    def list_users():
        return jsonify(db.query("SELECT id, username, name, role, created_at FROM users ORDER BY username"))

    @app.post("/api/users")
    @role_required("admin")
    def create_user():
        data = body()
        require(data, "username", "password", "role")
        if data["role"] not in ROLES:
            raise ApiError("Perfil inválido")
        if len(data["password"]) < 8:
            raise ApiError("A senha deve ter pelo menos 8 caracteres")
        if db.query_one("SELECT id FROM users WHERE username = ?", (data["username"],)):
            raise ApiError("Usuário já existe")
        uid = db.insert("users", {"username": data["username"], "name": data.get("name"), "role": data["role"],
                                  "password_hash": security.hash_password(data["password"]),
                                  "created_at": db.utcnow()})
        return jsonify({"id": uid}), 201

    @app.put("/api/users/<int:uid>")
    @role_required("admin")
    def update_user(uid):
        get_or_404("users", uid)
        data = body()
        values = {k: data[k] for k in ("name", "role") if k in data}
        if values.get("role") and values["role"] not in ROLES:
            raise ApiError("Perfil inválido")
        if data.get("password"):
            if len(data["password"]) < 8:
                raise ApiError("A senha deve ter pelo menos 8 caracteres")
            values["password_hash"] = security.hash_password(data["password"])
        db.update("users", uid, values)
        return jsonify({"ok": True})

    @app.delete("/api/users/<int:uid>")
    @role_required("admin")
    def delete_user(uid):
        if uid == current_user()["id"]:
            raise ApiError("Você não pode remover o próprio usuário")
        db.delete("users", uid)
        return jsonify({"ok": True})

    @app.get("/api/settings")
    @role_required("viewer")
    def settings():
        return jsonify({"timezone": Config.TIMEZONE, "public_url": Config.PUBLIC_URL,
                        "cloud_sync_minutes": Config.CLOUD_SYNC_MINUTES,
                        "max_parallel_jobs": Config.MAX_PARALLEL_JOBS, "webhook": bool(Config.WEBHOOK_URL),
                        "scheduler": Config.SCHEDULER_ENABLED})

    return app
