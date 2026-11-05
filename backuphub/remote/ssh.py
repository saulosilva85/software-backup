"""Execução remota em servidores Linux via SSH (paramiko)."""
import io
import shlex


class SSHError(RuntimeError):
    pass


def _load_key(private_key: str, passphrase: str | None):
    import paramiko

    errors = []
    for key_cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return key_cls.from_private_key(io.StringIO(private_key), password=passphrase or None)
        except Exception as exc:  # tenta o próximo formato
            errors.append(str(exc))
    raise SSHError("Chave privada inválida ou formato não suportado: " + "; ".join(errors))


class SSHClient:
    def __init__(self, host: str, secret: dict, timeout: int = 15):
        self.host = host
        self.secret = secret
        self.timeout = timeout
        self.client = None
        self._sudo_nopass: bool | None = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()

    def connect(self):
        try:
            import paramiko
        except ImportError as exc:
            raise SSHError("Pacote 'paramiko' não instalado") from exc
        client = paramiko.SSHClient()
        # MVP: aceita a chave do host na primeira conexão (TOFU).
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = dict(
            hostname=self.host,
            port=int(self.secret.get("port") or 22),
            username=self.secret.get("username"),
            timeout=self.timeout,
            banner_timeout=self.timeout,
            auth_timeout=self.timeout,
            allow_agent=False,
            look_for_keys=False,
        )
        if self.secret.get("private_key"):
            kwargs["pkey"] = _load_key(self.secret["private_key"], self.secret.get("passphrase"))
        else:
            kwargs["password"] = self.secret.get("password")
        try:
            client.connect(**kwargs)
        except Exception as exc:
            raise SSHError(f"Falha ao conectar via SSH em {self.host}: {exc}") from exc
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(30)
        self.client = client

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

    def _sudo_without_password(self) -> bool:
        """Verifica (uma vez por conexão) se o sudo funciona sem senha (regra NOPASSWD)."""
        if self._sudo_nopass is None:
            _, stdout, _ = self.client.exec_command("sudo -n sh -c true 2>/dev/null && echo BH_SUDO_OK", timeout=30)
            self._sudo_nopass = "BH_SUDO_OK" in stdout.read().decode(errors="replace")
        return self._sudo_nopass

    def _wrap(self, command: str, sudo: bool) -> tuple[str, bool]:
        """Retorna o comando final e se a senha deve ser enviada ao stdin.

        A senha só é enviada quando o sudo realmente a exige; caso contrário ela
        "vazaria" para o stdin do comando (ex.: o tar da restauração).
        """
        if not sudo or self.secret.get("username") == "root":
            return command, False
        if self._sudo_without_password() or not self.secret.get("password"):
            return f"sudo -n sh -c {shlex.quote(command)}", False
        return f"sudo -S -p '' sh -c {shlex.quote(command)}", True

    def run(self, command: str, timeout: int = 120, sudo: bool | None = None) -> tuple[int, str, str]:
        sudo = self.secret.get("use_sudo", False) if sudo is None else sudo
        final, send_pw = self._wrap(command, sudo)
        stdin, stdout, stderr = self.client.exec_command(final, timeout=timeout)
        if send_pw:
            stdin.write(self.secret["password"] + "\n")
            stdin.flush()
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        return stdout.channel.recv_exit_status(), out, err

    def stream_in(self, command: str, reader, sudo: bool | None = None, chunk: int = 4 * 1024 * 1024):
        """Executa um comando enviando o conteúdo de `reader` para o stdin (ex.: restauração)."""
        sudo = self.secret.get("use_sudo", False) if sudo is None else sudo
        final, send_pw = self._wrap(command, sudo)
        stdin, stdout, stderr = self.client.exec_command(final, bufsize=chunk)
        channel = stdin.channel
        if send_pw:
            channel.sendall((self.secret["password"] + "\n").encode())
        total = 0
        while True:
            data = reader.read(chunk)
            if not data:
                break
            channel.sendall(data)
            total += len(data)
        channel.shutdown_write()
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        return channel.recv_exit_status(), out, err, total

    def stream(self, command: str, sudo: bool | None = None):
        """Executa e devolve (stdout, stderr, channel) para leitura em streaming."""
        sudo = self.secret.get("use_sudo", False) if sudo is None else sudo
        final, send_pw = self._wrap(command, sudo)
        stdin, stdout, stderr = self.client.exec_command(final, bufsize=1024 * 1024)
        if send_pw:
            stdin.write(self.secret["password"] + "\n")
            stdin.flush()
        stdout.channel.settimeout(600)
        return stdout, stderr, stdout.channel
