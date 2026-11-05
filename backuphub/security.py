"""Criptografia de credenciais e autenticação."""
import json
from functools import wraps

from cryptography.fernet import Fernet, InvalidToken
from flask import jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

from . import db

_fernet: Fernet | None = None

# Campos que nunca são devolvidos à interface.
SECRET_FIELDS = {"password", "private_key", "passphrase", "secret_access_key", "service_account_json", "session_token"}


def init_crypto(key: str) -> None:
    global _fernet
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(data: dict) -> str:
    return _fernet.encrypt(json.dumps(data).encode()).decode()


def decrypt(token: str) -> dict:
    try:
        return json.loads(_fernet.decrypt(token.encode()).decode())
    except InvalidToken as exc:  # chave trocada ou dado corrompido
        raise RuntimeError("Não foi possível descriptografar a credencial (chave inválida)") from exc


def credential_secret(credential_id: int | None) -> tuple[dict | None, dict]:
    """Retorna (registro, dados descriptografados) de uma credencial."""
    if not credential_id:
        return None, {}
    row = db.get("credentials", credential_id)
    if not row:
        return None, {}
    return row, decrypt(row["data_enc"])


def mask(data: dict) -> dict:
    return {k: ("••••••" if k in SECRET_FIELDS and v else v) for k, v in data.items()}


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(hashed: str, password: str) -> bool:
    return check_password_hash(hashed, password)


def ensure_admin(username: str, password: str) -> None:
    if not db.query_one("SELECT id FROM users LIMIT 1"):
        db.insert("users", {
            "username": username,
            "name": "Administrador",
            "password_hash": hash_password(password),
            "role": "admin",
            "created_at": db.utcnow(),
        })


def current_user() -> dict | None:
    uid = session.get("user_id")
    if not uid:
        return None
    user = db.get("users", uid)
    if user:
        user.pop("password_hash", None)
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return jsonify({"error": "Não autenticado"}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "Não autenticado"}), 401
        if user["role"] != "admin":
            return jsonify({"error": "Permissão negada"}), 403
        return fn(*args, **kwargs)
    return wrapper
