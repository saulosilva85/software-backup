<#
  Prepara um servidor Windows para ser protegido pelo BackupHub (sem agente).
  - Habilita o WinRM (HTTP 5985; opcionalmente HTTPS 5986 com certificado autoassinado)
  - Libera o firewall apenas para o IP do BackupHub
  - Cria (opcional) um usuário local de serviço membro de "Backup Operators" e "Remote Management Users"

  Uso (PowerShell como Administrador):
    .\prepare-windows.ps1 -BackupHubIP 10.0.0.5 [-CreateUser] [-Https]
#>
param(
  [Parameter(Mandatory = $true)][string]$BackupHubIP,
  [switch]$CreateUser,
  [string]$UserName = "svc-backuphub",
  [switch]$Https
)
$ErrorActionPreference = "Stop"

Enable-PSRemoting -Force -SkipNetworkProfileCheck
Set-Item -Path WSMan:\localhost\Service\AllowUnencrypted -Value $false
Set-Item -Path WSMan:\localhost\Shell\MaxMemoryPerShellMB -Value 2048

if ($Https) {
  $cert = New-SelfSignedCertificate -DnsName $env:COMPUTERNAME -CertStoreLocation Cert:\LocalMachine\My
  if (-not (Get-ChildItem WSMan:\localhost\Listener | Where-Object { $_.Keys -contains "Transport=HTTPS" })) {
    New-Item -Path WSMan:\localhost\Listener -Transport HTTPS -Address * -CertificateThumbPrint $cert.Thumbprint -Force | Out-Null
  }
}

$ports = if ($Https) { "5985,5986" } else { "5985" }
Get-NetFirewallRule -DisplayName "BackupHub WinRM" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "BackupHub WinRM" -Direction Inbound -Protocol TCP -LocalPort $ports.Split(",") `
  -RemoteAddress $BackupHubIP -Action Allow | Out-Null

if ($CreateUser) {
  $pwd = Read-Host "Senha para $UserName" -AsSecureString
  if (-not (Get-LocalUser -Name $UserName -ErrorAction SilentlyContinue)) {
    New-LocalUser -Name $UserName -Password $pwd -PasswordNeverExpires -Description "BackupHub" | Out-Null
  }
  Add-LocalGroupMember -Group "Backup Operators" -Member $UserName -ErrorAction SilentlyContinue
  Add-LocalGroupMember -Group "Remote Management Users" -Member $UserName -ErrorAction SilentlyContinue
  # Necessário para gravar o arquivo temporário e ler arquivos protegidos via WinRM
  Add-LocalGroupMember -Group "Administrators" -Member $UserName -ErrorAction SilentlyContinue
}

$tar = Get-Command tar.exe -ErrorAction SilentlyContinue
Write-Host "WinRM habilitado. tar.exe: $(if ($tar) { 'disponível' } else { 'ausente (usará Compress-Archive)' })"
Write-Host "Cadastre no BackupHub uma credencial WinRM (NTLM) para este servidor."
