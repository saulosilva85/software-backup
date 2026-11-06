"""Backup e restauração de arquivos em servidores Windows via WinRM.

Fluxo de backup:
1. O BackupHub gera uma URL de upload assinada (S3/GCS) ou um token de
   transferência (destino local).
2. Via PowerShell remoto, o servidor compacta os caminhos (tar.exe nativo do
   Windows Server 2019+/Windows 10+, ou Compress-Archive como alternativa).
3. O próprio servidor envia o .zip para a URL e remove o arquivo temporário.
"""
from __future__ import annotations

import json

from ..config import Config
from ..remote.winrm import WinRMClient


class BackupError(RuntimeError):
    pass


def ps_literal(value: str) -> str:
    """String literal segura para PowerShell (aspas simples)."""
    return "'" + str(value).replace("'", "''") + "'"


BACKUP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$paths = @(__PATHS__ | ConvertFrom-Json | ForEach-Object { $_ })
$excludes = @(__EXCLUDES__ | ConvertFrom-Json | ForEach-Object { $_ })
$url = __URL__
$headers = __HEADERS__ | ConvertFrom-Json
$found = @($paths | Where-Object { Test-Path -LiteralPath $_ })
$missing = @($paths | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($found.Count -eq 0) { throw 'Nenhum dos caminhos configurados existe no servidor' }
$tmp = Join-Path $env:TEMP ('backuphub-' + [guid]::NewGuid().ToString() + '.zip')
$warn = $null
try {
  $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
  if ($tar) {
    $targs = @('-a', '-c', '-f', $tmp)
    foreach ($e in $excludes) { $targs += "--exclude=$e" }
    $targs += $found
    $ErrorActionPreference = 'Continue'   # avisos do tar.exe no stderr não devem abortar
    $out = (& tar.exe @targs 2>&1 | Out-String)
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) { $warn = 'Alguns arquivos não puderam ser lidos (em uso ou sem permissão)' }
  } else {
    Compress-Archive -LiteralPath $found -DestinationPath $tmp -CompressionLevel Optimal -Force
  }
  if (-not (Test-Path -LiteralPath $tmp)) { throw "Falha ao gerar o arquivo compactado: $out" }
  $file = Get-Item -LiteralPath $tmp
  $hash = (Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash.ToLower()
  $req = [System.Net.HttpWebRequest]::Create($url)
  $req.Method = 'PUT'
  $req.Timeout = 6 * 3600 * 1000
  $req.ReadWriteTimeout = 6 * 3600 * 1000
  $req.AllowWriteStreamBuffering = $false
  $req.ContentLength = $file.Length
  foreach ($p in $headers.PSObject.Properties) {
    if ($p.Name -eq 'Content-Type') { $req.ContentType = $p.Value } else { $req.Headers.Add($p.Name, $p.Value) }
  }
  $stream = $req.GetRequestStream()
  $fs = [System.IO.File]::OpenRead($tmp)
  try { $fs.CopyTo($stream, 4MB) } finally { $fs.Close(); $stream.Close() }
  $resp = $req.GetResponse(); $resp.Close()
  [pscustomobject]@{ size = $file.Length; sha256 = $hash; warning = $warn; missing = $missing; found = $found } | ConvertTo-Json -Compress
} finally {
  Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}
"""

RESTORE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$url = __URL__
$target = __TARGET__
$tmp = Join-Path $env:TEMP ('backuphub-restore-' + [guid]::NewGuid().ToString() + '.zip')
try {
  (New-Object System.Net.WebClient).DownloadFile($url, $tmp)
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
  if ($tar) { & tar.exe -x -f $tmp -C $target; if ($LASTEXITCODE -ne 0) { throw 'Falha ao extrair' } }
  else { Expand-Archive -LiteralPath $tmp -DestinationPath $target -Force }
  [pscustomobject]@{ size = (Get-Item -LiteralPath $tmp).Length } | ConvertTo-Json -Compress
} finally {
  Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}
"""


def render_backup_script(paths, excludes, url, headers) -> str:
    return (BACKUP_SCRIPT
            .replace("__PATHS__", ps_literal(json.dumps(list(paths))))
            .replace("__EXCLUDES__", ps_literal(json.dumps(list(excludes))))
            .replace("__URL__", ps_literal(url))
            .replace("__HEADERS__", ps_literal(json.dumps(headers))))


def _last_json(output: str) -> dict:
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise BackupError(f"Resposta inesperada do servidor: {output[-500:]}")


def backup(machine: dict, secret: dict, dest, key: str, paths: list[str], excludes: list[str], log) -> dict:
    url, headers = dest.upload_url(key, Config.PRESIGNED_URL_EXPIRES)
    log(f"Compactando {len(paths)} caminho(s) no servidor e enviando para {dest.describe()}/{key}")
    client = WinRMClient(machine["address"], secret, timeout=6 * 3600)
    code, out, err = client.run_ps(render_backup_script(paths, excludes, url, headers))
    if code != 0:
        raise BackupError(f"PowerShell falhou ({code}): {(err or out).strip()[:800]}")
    result = _last_json(out)
    missing = result.get("missing") or []
    if isinstance(missing, str):
        missing = [missing]
    if missing:
        log("Caminhos inexistentes ignorados: " + ", ".join(missing))
    return {"size": int(result.get("size") or 0), "sha256": result.get("sha256"),
            "warning": result.get("warning"), "skipped": missing}


def restore(machine: dict, secret: dict, dest, key: str, target: str, log) -> dict:
    target = target or "C:\\BackupHub-Restore"
    url = dest.download_url(key, Config.PRESIGNED_URL_EXPIRES)
    log(f"Baixando {key} no servidor e extraindo em {target}")
    script = RESTORE_SCRIPT.replace("__URL__", ps_literal(url)).replace("__TARGET__", ps_literal(target))
    code, out, err = WinRMClient(machine["address"], secret, timeout=6 * 3600).run_ps(script)
    if code != 0:
        raise BackupError(f"PowerShell falhou ({code}): {(err or out).strip()[:800]}")
    return {"size": int(_last_json(out).get("size") or 0)}
