from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_DATA = tempfile.mkdtemp(prefix="backuphub-test-")
os.environ["BACKUPHUB_DATA_DIR"] = _DATA
os.environ["BACKUPHUB_SCHEDULER"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from backuphub import db  # noqa: E402
from backuphub.app import create_app  # noqa: E402
from backuphub.config import Config  # noqa: E402

HEADERS = {"X-Requested-With": "BackupHub"}


@pytest.fixture()
def app(tmp_path):
    class TestConfig(Config):
        DATABASE = str(tmp_path / "test.db")
    application = create_app(TestConfig, start_background=False)
    application.testing = True
    yield application
    db.close_connection()


@pytest.fixture()
def client(app):
    c = app.test_client()
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"}, headers=HEADERS)
    assert r.status_code == 200
    return c


class FakeChannel:
    def __init__(self, proc):
        self.proc = proc

    def recv_exit_status(self):
        return self.proc.wait()


class FakeSSH:
    """Substitui o SSH executando os comandos localmente (simula um servidor Linux)."""

    def __init__(self, host, secret, timeout=15):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def run(self, command, timeout=120, sudo=None):
        p = subprocess.run(["sh", "-c", command], capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode(), p.stderr.decode()

    def stream(self, command, sudo=None):
        p = subprocess.Popen(["sh", "-c", command], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return p.stdout, p.stderr, FakeChannel(p)

    def stream_in(self, command, reader, sudo=None, chunk=1 << 20):
        p = subprocess.Popen(["sh", "-c", command], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        total = 0
        while True:
            data = reader.read(chunk)
            if not data:
                break
            p.stdin.write(data)
            total += len(data)
        out, err = p.communicate()
        return p.returncode, out.decode(), err.decode(), total


@pytest.fixture()
def fake_ssh(monkeypatch):
    from backuphub.backup import linux
    monkeypatch.setattr(linux, "SSHClient", FakeSSH)
    return FakeSSH
