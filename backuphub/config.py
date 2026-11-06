"""Configuração da aplicação via variáveis de ambiente."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("BACKUPHUB_DATA_DIR", BASE_DIR.parent / "data")).resolve()


def _load_or_create_secret(name: str, generator) -> str:
    """Lê um segredo do ambiente ou de DATA_DIR; cria e persiste se não existir."""
    env_value = os.environ.get(name)
    if env_value:
        return env_value
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f".{name.lower()}"
    if path.exists():
        return path.read_text().strip()
    value = generator()
    path.write_text(value)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


class Config:
    DATA_DIR = DATA_DIR
    DATABASE = os.environ.get("BACKUPHUB_DATABASE", str(DATA_DIR / "backuphub.db"))
    TIMEZONE = os.environ.get("BACKUPHUB_TIMEZONE", "America/Sao_Paulo")
    MAX_PARALLEL_JOBS = int(os.environ.get("BACKUPHUB_MAX_PARALLEL_JOBS", "4"))
    SCHEDULER_ENABLED = os.environ.get("BACKUPHUB_SCHEDULER", "1") == "1"
    SCHEDULER_INTERVAL_SECONDS = int(os.environ.get("BACKUPHUB_SCHEDULER_INTERVAL", "20"))
    ADMIN_USER = os.environ.get("BACKUPHUB_ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.environ.get("BACKUPHUB_ADMIN_PASSWORD", "admin123")
    # Tempo máximo (s) aguardando snapshots de nuvem concluírem.
    # Sincronização automática do inventário AWS/GCP (minutos; 0 desativa).
    CLOUD_SYNC_MINUTES = int(os.environ.get("BACKUPHUB_CLOUD_SYNC_MINUTES", "60"))
    # Verificação de disponibilidade (online/offline) dos servidores on-premise, em minutos (0 desativa).
    HEALTH_CHECK_MINUTES = int(os.environ.get("BACKUPHUB_HEALTH_MINUTES", "5"))
    SNAPSHOT_WAIT_TIMEOUT = int(os.environ.get("BACKUPHUB_SNAPSHOT_WAIT_TIMEOUT", "3600"))
    PRESIGNED_URL_EXPIRES = int(os.environ.get("BACKUPHUB_PRESIGNED_EXPIRES", "21600"))
    # URL pela qual os servidores Windows alcançam o BackupHub (usada com destino "local").
    PUBLIC_URL = os.environ.get("BACKUPHUB_PUBLIC_URL", "http://localhost:8080").rstrip("/")
    # Webhook (Slack, Teams, Discord, Google Chat...) avisado quando um job falha.
    WEBHOOK_URL = os.environ.get("BACKUPHUB_WEBHOOK_URL")
    HOST = os.environ.get("BACKUPHUB_HOST", "0.0.0.0")
    PORT = int(os.environ.get("BACKUPHUB_PORT", "8080"))
    SESSION_COOKIE_SECURE = os.environ.get("BACKUPHUB_COOKIE_SECURE", "0") == "1"

    @staticmethod
    def secret_key() -> str:
        return _load_or_create_secret("BACKUPHUB_SECRET_KEY", lambda: secrets.token_hex(32))

    @staticmethod
    def encryption_key() -> str:
        from cryptography.fernet import Fernet

        return _load_or_create_secret(
            "BACKUPHUB_ENCRYPTION_KEY", lambda: Fernet.generate_key().decode()
        )
