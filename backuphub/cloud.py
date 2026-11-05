"""Fábricas de clientes para AWS (boto3) e GCP (google-cloud)."""
from __future__ import annotations

import json


class CloudError(RuntimeError):
    pass


def aws_session(secret: dict, region: str | None = None):
    try:
        import boto3
    except ImportError as exc:
        raise CloudError("Pacote 'boto3' não instalado") from exc
    kwargs = {"region_name": region or secret.get("default_region") or "us-east-1"}
    if secret.get("access_key_id"):
        kwargs["aws_access_key_id"] = secret["access_key_id"]
        kwargs["aws_secret_access_key"] = secret.get("secret_access_key")
        if secret.get("session_token"):
            kwargs["aws_session_token"] = secret["session_token"]
    session = boto3.Session(**kwargs)
    if secret.get("role_arn"):
        sts = session.client("sts")
        creds = sts.assume_role(RoleArn=secret["role_arn"], RoleSessionName="backuphub")["Credentials"]
        session = boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=kwargs["region_name"],
        )
    return session


def aws_regions(secret: dict) -> list[str]:
    configured = [r.strip() for r in (secret.get("regions") or "").split(",") if r.strip()]
    if configured:
        return configured
    ec2 = aws_session(secret).client("ec2")
    return sorted(r["RegionName"] for r in ec2.describe_regions()["Regions"])


def gcp_credentials(secret: dict):
    try:
        from google.oauth2 import service_account
    except ImportError as exc:
        raise CloudError("Pacotes 'google-cloud-*' não instalados") from exc
    raw = secret.get("service_account_json")
    if not raw:
        raise CloudError("Credencial GCP sem JSON da service account")
    info = json.loads(raw) if isinstance(raw, str) else raw
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    return creds, info


def gcp_projects(secret: dict) -> list[str]:
    configured = [p.strip() for p in (secret.get("projects") or "").split(",") if p.strip()]
    if configured:
        return configured
    _, info = gcp_credentials(secret)
    return [info["project_id"]]
