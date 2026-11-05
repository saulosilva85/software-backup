"""Execução remota em servidores Windows via WinRM (pywinrm)."""


class WinRMError(RuntimeError):
    pass


class WinRMClient:
    def __init__(self, host: str, secret: dict, timeout: int = 60):
        self.host = host
        self.secret = secret
        self.timeout = timeout
        try:
            import winrm
        except ImportError as exc:
            raise WinRMError("Pacote 'pywinrm' não instalado") from exc
        use_https = bool(self.secret.get("use_https"))
        port = int(self.secret.get("port") or (5986 if use_https else 5985))
        scheme = "https" if use_https else "http"
        self.session = winrm.Session(
            f"{scheme}://{host}:{port}/wsman",
            auth=(self.secret.get("username"), self.secret.get("password")),
            transport=self.secret.get("transport") or "ntlm",
            server_cert_validation="ignore" if self.secret.get("ignore_cert", True) else "validate",
            read_timeout_sec=max(timeout + 10, 70),
            operation_timeout_sec=timeout,
        )

    def run_ps(self, script: str) -> tuple[int, str, str]:
        try:
            result = self.session.run_ps(script)
        except Exception as exc:
            raise WinRMError(f"Falha WinRM em {self.host}: {exc}") from exc
        return (
            result.status_code,
            result.std_out.decode("utf-8", errors="replace"),
            result.std_err.decode("utf-8", errors="replace"),
        )

    def check(self, script: str) -> str:
        code, out, err = self.run_ps(script)
        if code != 0:
            raise WinRMError(f"Comando PowerShell falhou ({code}): {err.strip() or out.strip()}")
        return out
