"""Destinos de backup: Amazon S3 (e compatíveis), Google Cloud Storage e disco local.

Todos os destinos expõem a mesma interface, de modo que o motor de backup
não precisa saber onde os dados serão gravados.
"""
import hashlib
import os
import secrets
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db
from .cloud import CloudError, aws_session, gcp_credentials
from .config import Config
from .security import credential_secret

CHUNK = 8 * 1024 * 1024


class StorageError(RuntimeError):
    pass


class CountingReader:
    """Envolve um stream contando bytes e calculando SHA-256 durante a leitura."""

    def __init__(self, raw):
        self.raw = raw
        self.bytes = 0
        self._hash = hashlib.sha256()

    def read(self, size: int = -1) -> bytes:
        data = self.raw.read(size if size and size > 0 else CHUNK)
        if data:
            self.bytes += len(data)
            self._hash.update(data)
        return data

    def readable(self) -> bool:
        return True

    @property
    def sha256(self) -> str:
        return self._hash.hexdigest()


# --------------------------------------------------------------------------
# Tokens de transferência: permitem que servidores Windows enviem/baixem
# arquivos através do BackupHub quando o destino é local.
# --------------------------------------------------------------------------
_tokens: dict[str, dict] = {}
_tokens_lock = threading.Lock()


def issue_token(destination_id: int, key: str, method: str, expires: int) -> str:
    token = secrets.token_urlsafe(32)
    with _tokens_lock:
        now = time.time()
        for t in [t for t, v in _tokens.items() if v["expires"] < now]:
            _tokens.pop(t, None)
        _tokens[token] = {"destination_id": destination_id, "key": key, "method": method,
                          "expires": now + expires}
    return token


def consume_token(token: str, method: str) -> dict | None:
    with _tokens_lock:
        info = _tokens.get(token)
        if not info or info["expires"] < time.time() or info["method"] != method:
            return None
        if method == "PUT":  # upload é de uso único
            _tokens.pop(token, None)
        return info


class Destination:
    type = "base"

    def __init__(self, row: dict, secret: dict):
        self.row = row
        self.id = row.get("id")
        self.config = row.get("config") or {}
        self.secret = secret
        self.prefix = (self.config.get("prefix") or "").strip("/")

    def full_key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    # Interface -------------------------------------------------------------
    def upload_stream(self, key: str, stream) -> None:
        raise NotImplementedError

    def open_read(self, key: str):
        raise NotImplementedError

    def list(self, folder: str) -> list[dict]:
        """Lista objetos sob uma "pasta" (relativa ao prefixo) → [{key, size, modified}]."""
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def upload_url(self, key: str, expires: int) -> tuple[str, dict]:
        """URL que aceita PUT do arquivo; retorna (url, cabeçalhos obrigatórios)."""
        raise NotImplementedError

    def download_url(self, key: str, expires: int) -> str:
        raise NotImplementedError

    def test(self) -> str:
        raise NotImplementedError

    def describe(self) -> str:
        return self.type


class S3Destination(Destination):
    """Amazon S3 ou qualquer serviço compatível (MinIO, Wasabi, Ceph...) via endpoint_url."""

    type = "s3"

    def __init__(self, row, secret):
        super().__init__(row, secret)
        self.bucket = self.config.get("bucket")
        if not self.bucket:
            raise StorageError("Destino S3 sem bucket configurado")
        session = aws_session(secret, self.config.get("region"))
        kwargs = {}
        if self.config.get("endpoint_url"):
            kwargs["endpoint_url"] = self.config["endpoint_url"]
        self.client = session.client("s3", **kwargs)

    def _extra(self) -> dict:
        extra = {}
        if self.config.get("storage_class"):
            extra["StorageClass"] = self.config["storage_class"]
        if self.config.get("sse"):
            extra["ServerSideEncryption"] = self.config["sse"]  # AES256 | aws:kms
        return extra

    def upload_stream(self, key, stream):
        from boto3.s3.transfer import TransferConfig

        cfg = TransferConfig(multipart_chunksize=64 * 1024 * 1024, max_concurrency=4)
        self.client.upload_fileobj(stream, self.bucket, self.full_key(key), ExtraArgs=self._extra(), Config=cfg)

    def open_read(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=self.full_key(key))["Body"]

    def list(self, folder):
        base = self.full_key(folder.strip("/")) + "/"
        items = []
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=base):
            for obj in page.get("Contents", []):
                items.append({"key": obj["Key"][len(self.prefix) + 1:] if self.prefix else obj["Key"],
                              "size": obj["Size"], "modified": obj["LastModified"].isoformat()})
        return items

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=self.full_key(key))

    def upload_url(self, key, expires):
        params = {"Bucket": self.bucket, "Key": self.full_key(key), "ContentType": "application/octet-stream"}
        headers = {"Content-Type": "application/octet-stream"}
        extra = self._extra()
        if "ServerSideEncryption" in extra:
            params["ServerSideEncryption"] = extra["ServerSideEncryption"]
            headers["x-amz-server-side-encryption"] = extra["ServerSideEncryption"]
        if "StorageClass" in extra:
            params["StorageClass"] = extra["StorageClass"]
            headers["x-amz-storage-class"] = extra["StorageClass"]
        url = self.client.generate_presigned_url("put_object", Params=params, ExpiresIn=expires)
        return url, headers

    def download_url(self, key, expires):
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": self.full_key(key)}, ExpiresIn=expires)

    def test(self):
        self.client.head_bucket(Bucket=self.bucket)
        probe = self.full_key(".backuphub-test")
        self.client.put_object(Bucket=self.bucket, Key=probe, Body=b"ok")
        self.client.delete_object(Bucket=self.bucket, Key=probe)
        return f"Bucket s3://{self.bucket} acessível com permissão de escrita"

    def describe(self):
        return f"s3://{self.bucket}/{self.prefix}".rstrip("/")


class GCSDestination(Destination):
    type = "gcs"

    def __init__(self, row, secret):
        super().__init__(row, secret)
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise CloudError("Pacote 'google-cloud-storage' não instalado") from exc
        self.bucket_name = self.config.get("bucket")
        if not self.bucket_name:
            raise StorageError("Destino GCS sem bucket configurado")
        creds, info = gcp_credentials(secret)
        self.client = storage.Client(project=info.get("project_id"), credentials=creds)
        self.bucket = self.client.bucket(self.bucket_name)

    def _blob(self, key):
        blob = self.bucket.blob(self.full_key(key), chunk_size=32 * 1024 * 1024)
        if self.config.get("storage_class"):
            blob.storage_class = self.config["storage_class"]
        return blob

    def upload_stream(self, key, stream):
        self._blob(key).upload_from_file(stream, content_type="application/octet-stream", timeout=600)

    def open_read(self, key):
        return self.bucket.blob(self.full_key(key)).open("rb")

    def list(self, folder):
        base = self.full_key(folder.strip("/")) + "/"
        out = []
        for b in self.client.list_blobs(self.bucket_name, prefix=base):
            out.append({"key": b.name[len(self.prefix) + 1:] if self.prefix else b.name,
                        "size": b.size, "modified": b.updated.isoformat() if b.updated else None})
        return out

    def delete(self, key):
        self.bucket.blob(self.full_key(key)).delete()

    def upload_url(self, key, expires):
        url = self.bucket.blob(self.full_key(key)).generate_signed_url(
            version="v4", expiration=timedelta(seconds=expires), method="PUT",
            content_type="application/octet-stream")
        return url, {"Content-Type": "application/octet-stream"}

    def download_url(self, key, expires):
        return self.bucket.blob(self.full_key(key)).generate_signed_url(
            version="v4", expiration=timedelta(seconds=expires), method="GET")

    def test(self):
        if not self.bucket.exists():
            raise StorageError(f"Bucket gs://{self.bucket_name} não encontrado")
        blob = self.bucket.blob(self.full_key(".backuphub-test"))
        blob.upload_from_string(b"ok")
        blob.delete()
        return f"Bucket gs://{self.bucket_name} acessível com permissão de escrita"

    def describe(self):
        return f"gs://{self.bucket_name}/{self.prefix}".rstrip("/")


class LocalDestination(Destination):
    """Disco local/NAS montado no servidor do BackupHub (útil para testes e ambientes offline)."""

    type = "local"

    def __init__(self, row, secret):
        super().__init__(row, secret)
        path = self.config.get("path")
        if not path:
            raise StorageError("Destino local sem caminho configurado")
        self.root = Path(path).expanduser().resolve()

    def _path(self, key: str) -> Path:
        p = (self.root / self.full_key(key)).resolve()
        if self.root not in p.parents and p != self.root:
            raise StorageError("Caminho inválido")
        return p

    def upload_stream(self, key, stream):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        with open(tmp, "wb") as fh:
            while True:
                chunk = stream.read(CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
        os.replace(tmp, path)

    def open_read(self, key):
        return open(self._path(key), "rb")

    def list(self, folder):
        base = self._path(folder.strip("/"))
        if not base.exists():
            return []
        out = []
        for p in base.rglob("*"):
            if p.is_file() and not p.name.endswith(".part"):
                st = p.stat()
                rel = p.relative_to(self.root).as_posix()
                out.append({"key": rel[len(self.prefix) + 1:] if self.prefix else rel, "size": st.st_size,
                            "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()})
        return out

    def delete(self, key):
        path = self._path(key)
        if path.exists():
            path.unlink()

    def upload_url(self, key, expires):
        token = issue_token(self.id, key, "PUT", expires)
        return f"{Config.PUBLIC_URL}/api/transfer/{token}", {"Content-Type": "application/octet-stream"}

    def download_url(self, key, expires):
        token = issue_token(self.id, key, "GET", expires)
        return f"{Config.PUBLIC_URL}/api/transfer/{token}"

    def test(self):
        self.root.mkdir(parents=True, exist_ok=True)
        probe = self._path(".backuphub-test")
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"ok")
        probe.unlink()
        free = shutil.disk_usage(self.root).free / 1024 ** 3
        return f"Diretório {self.root} gravável ({free:.1f} GB livres)"

    def describe(self):
        return str(self.root / self.prefix) if self.prefix else str(self.root)


TYPES = {"s3": S3Destination, "gcs": GCSDestination, "local": LocalDestination}


def open_destination(destination_id: int) -> Destination:
    row = db.get("destinations", destination_id)
    if not row:
        raise StorageError("Destino de backup não encontrado")
    return build(row)


def build(row: dict) -> Destination:
    cls = TYPES.get(row["type"])
    if not cls:
        raise StorageError(f"Tipo de destino desconhecido: {row['type']}")
    _, secret = credential_secret(row.get("credential_id"))
    return cls(row, secret)
