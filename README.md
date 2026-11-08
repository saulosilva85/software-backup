# BackupHub

Plataforma web de **inventário e backup** de servidores **Windows e Linux on-premise** e de máquinas virtuais na **AWS** e no **Google Cloud**, com agendamento e armazenamento em **Amazon S3** (ou compatíveis), **Google Cloud Storage** ou disco local/NAS.

**Sem agente:** nada é instalado nos servidores protegidos. O BackupHub roda em um único servidor Linux e acessa os demais pelos protocolos nativos (SSH no Linux, WinRM no Windows), do mesmo modo que o Rundeck e o Ansible.

> Status: **MVP / primeiro esboço** para testes com clientes piloto. Veja [Limitações conhecidas](#limitações-conhecidas-do-mvp) e o [Roadmap](#roadmap).

## Sumário

- [Funcionalidades](#funcionalidades)
- [Instalação](#instalação)
- [Requisitos](#requisitos)
- [Operação do serviço](#operação-do-serviço)
- [Primeiros passos](#primeiros-passos)
- [Inventário](#inventário)
- [Preparando os servidores do cliente](#preparando-os-servidores-do-cliente)
- [Configuração](#configuração-variáveis-de-ambiente)
- [Segurança e antivírus](#segurança)
- [Desenvolvimento](#desenvolvimento)
- [Limitações e roadmap](#limitações-conhecidas-do-mvp)

## Funcionalidades

| Área | O que faz |
|---|---|
| **Descoberta de rede** | Ao abrir *Descobrir na rede*, detecta as redes do próprio servidor e já inicia a varredura (SSH 22, SMB 445, RDP 3389, WinRM 5985/5986). Aceita outras faixas (CIDR, intervalos, IPs ou nomes) e sugere redes onde já há servidores no inventário. |
| **Inventário on-premise** | Sem credencial (**Básico**): hostname, IP, **versão do sistema** (ex.: *Windows 11 24H2*, *Windows Server 2022*, *Ubuntu 22.04*, *Debian 12*) e estado online/offline. Com credencial (**Completo**): dados lidos do próprio sistema. As credenciais cadastradas são **testadas automaticamente** nas máquinas que ainda não têm acesso. |
| **Online / offline** | Verificação a cada 5 min (TCP nas portas de gerenciamento e ping), botão *Verificar estado* e alerta quando um servidor que tem backup fica offline. |
| **Inventário de nuvem** | Instâncias **EC2** (regiões escolhidas ou todas, com IAM Role/AssumeRole) e VMs do **Compute Engine**. **Sincronização automática** (padrão: 60 min): instâncias novas entram sozinhas; EC2 terminadas e VMs excluídas saem do inventário e dos backups (histórico e backups preservados), com alerta se estavam protegidas. |
| **Backup de arquivos** | Linux: `tar.gz` transmitido via SSH direto para o destino (multipart no S3, upload resumível no GCS), sem arquivos temporários. Windows: o servidor compacta em `.zip` (`tar.exe` nativo ou `Compress-Archive`) e envia para uma URL assinada. |
| **Backup por snapshot** | Snapshots nativos de discos EBS (AWS, multi-volume consistente) e Persistent Disk (GCP), sem acesso ao sistema operacional. |
| **Agendador** | Todos os dias, 1x ou 2x por semana, dias úteis ou qualquer combinação de dias, com vários horários por dia, no fuso configurado. Pré-visualização das próximas execuções. Máquinas escolhidas uma a uma ou **todas** (inclusive as que entrarem depois). |
| **Retenção** | Mantém as N cópias mais recentes por máquina e política (arquivos e snapshots). |
| **Restauração** | Restaura um backup de arquivos no mesmo servidor ou em outro, no diretório escolhido. Download do backup pelo navegador. |
| **Destinos** | Amazon S3 (classes de armazenamento, SSE-S3/KMS), S3 compatível (MinIO, Wasabi, Ceph...), Google Cloud Storage e disco local/NAS. |
| **Operação** | Painel com cobertura de backup e histórico de 14 dias, logs em tempo real por execução, SHA-256 dos arquivos e webhook (Slack, Teams, Discord) para falhas e alertas. |
| **Segurança** | Perfis Administrador, Operador e Somente leitura; credenciais criptografadas (Fernet/AES); proteção CSRF; senhas com hash. |

## Arquitetura

```
                        ┌──────────────────────────────────────────────┐
  Navegador ──HTTP(S)─▶ │ BackupHub (Python / Flask, 1 processo)       │
                        │  • API REST + interface web                  │
                        │  • Agendador • Fila de jobs • Monitor online │
                        │  • SQLite (inventário, políticas, histórico) │
                        └───────┬────────────────┬─────────────┬───────┘
                     SSH (22)   │  WinRM (5985/6)│     APIs AWS / GCP
                ┌───────────────▼─┐   ┌──────────▼───────┐  ┌──▼───────────────────┐
                │ Servidores Linux│   │Servidores Windows│  │ EC2 / Compute Engine │
                │ tar | gzip ─────┼─┐ │ zip ──PUT URL ───┼┐ │ snapshots de disco   │
                └─────────────────┘ │ └──────────────────┘│ └──────────────────────┘
                                    ▼                      ▼
                         ┌──────────────────────────────────────────┐
                         │ Amazon S3 / S3 compatível / GCS / NAS     │
                         └──────────────────────────────────────────┘
```

## Instalação

O BackupHub roda em **qualquer distribuição Linux** (x86_64 e ARM64). O instalador `install.sh`:
- detecta a distribuição, a arquitetura, o gerenciador de pacotes (`apt`, `dnf`, `yum`, `zypper`, `apk`, `pacman`) e o sistema de inicialização (`systemd`, `OpenRC`, `SysV`);
- traz um **Python próprio** (portátil), sem depender do Python do sistema;
- registra o serviço para **iniciar com o sistema** e reiniciar sozinho em caso de falha.

### Distribuições testadas automaticamente (a cada alteração, via GitHub Actions)

| Família | Versões |
|---|---|
| Ubuntu | 18.04, 20.04, 22.04, 24.04 (x86_64 e ARM64) |
| Debian | 10, 11, 12 |
| Red Hat e derivados | CentOS 7, Rocky 8 e 9 (x86_64 e ARM64), AlmaLinux 9, Oracle Linux 8 e 9, Fedora |
| Amazon Linux | 2 e 2023 (x86_64 e ARM64/Graviton) |
| Outras | openSUSE Leap 15, Arch Linux, Alpine |

O teste instala do zero, roda a atualização (que precisa reaproveitar Python e dependências), inicia o servidor, faz login e testa um destino. A instalação offline é testada com a rede desligada (CentOS 7, Ubuntu 18.04/24.04, Debian 11 e ARM64). O registro do serviço no systemd foi validado em Debian 12 real.

### Instalação online (uma linha)

```bash
curl -fsSL https://raw.githubusercontent.com/saulosilva85/software-backup/main/install.sh | sudo sh
```

Sem `curl` (comum no Debian): `wget -qO- https://raw.githubusercontent.com/saulosilva85/software-backup/main/install.sh | sudo sh`

Ao final, o instalador mostra o endereço do painel e a **senha inicial do admin** (gerada aleatoriamente e guardada em `/etc/backuphub.env`). Com opções:

```bash
curl -fsSL https://raw.githubusercontent.com/saulosilva85/software-backup/main/install.sh | sudo sh -s -- \
  --admin-password 'MinhaSenhaForte' --timezone America/Fortaleza --open-firewall
```

| Opção | Descrição |
|---|---|
| `--admin-password` | Senha inicial do admin (padrão: aleatória, exibida no final). Vale só na primeira instalação |
| `--timezone` | Fuso dos agendamentos (padrão: o do servidor) |
| `--public-url` | URL que os servidores Windows usam para alcançar o BackupHub (destino local) |
| `--port` | Porta do painel (padrão 8080) |
| `--open-firewall` | Libera a porta no firewalld/ufw do servidor |
| `--system-python` | Usa o Python do sistema (>= 3.9) em vez do portátil |
| `--uninstall [--purge]` | Remove (com `--purge`, apaga também dados e configuração) |

Execute como root. Se usar `su`, prefira `su -` (com hífen).

### Instalação na AWS (EC2) pelo User data

Crie a instância com a IAM Role do BackupHub (política em `deploy/cloud/aws-iam-policy.json`) e cole em **Advanced details → User data**:

```bash
#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/saulosilva85/software-backup/main/install.sh | sh -s -- --admin-password 'TroqueEstaSenha' --timezone America/Fortaleza
```

Em cerca de 3 minutos a ferramenta está no ar. O log fica em `/var/log/cloud-init-output.log`. Na credencial AWS, deixe access key e secret **em branco** para usar a IAM Role.

### Instalação offline (servidor sem internet)

O pacote completo (Python, dependências e código) é gerado automaticamente pelo GitHub Actions:

- **Versões numeradas (recomendado para clientes):** página [Releases](https://github.com/saulosilva85/software-backup/releases). Ao publicar uma release (ex.: tag `v0.1.0`), os pacotes `backuphub-<versão>-linux-x86_64.tar.gz` e `-aarch64.tar.gz` são anexados automaticamente.
- **Versão de desenvolvimento:** seção *Artifacts* da execução mais recente em [Actions](https://github.com/saulosilva85/software-backup/actions) (requer login; expira em 90 dias).

```bash
tar xzf backuphub-*-linux-x86_64.tar.gz
cd backuphub-*-linux-x86_64
sudo sh install.sh --admin-password 'MinhaSenhaForte' --timezone America/Fortaleza
```

Use `x86_64` para servidores Intel/AMD (VMware, Hyper-V, EC2 t3/m5) e `aarch64` para ARM (EC2 Graviton t4g/m7g). O mesmo pacote serve para qualquer distribuição com glibc (o Alpine requer a instalação online).

### Atualização

Execute o instalador novamente. Configuração, senha e dados são mantidos, e o banco de dados é migrado automaticamente:

```bash
wget -O /tmp/install.sh https://raw.githubusercontent.com/saulosilva85/software-backup/main/install.sh && sudo sh /tmp/install.sh
```

A atualização leva **poucos segundos**: o Python portátil e as dependências são reaproveitados quando não mudaram; apenas o código é baixado. Sem internet, use o pacote offline da nova versão. Após atualizar, recarregue o navegador com **Ctrl+F5**.

### Onde os arquivos ficam

| Caminho | Conteúdo |
|---|---|
| `/opt/backuphub` | Programa: `app/` (código), `python/` (Python portátil), `venv/` (dependências), `bin/backuphub-server` |
| `/etc/backuphub.env` | Configuração (porta, fuso, URL pública, webhook, intervalos) |
| `/var/lib/backuphub` | Banco de dados, chaves de criptografia e `backups/` (destino local) |
| `/var/log/backuphub` | Logs (apenas em sistemas sem systemd) |

> Faça backup de `/var/lib/backuphub`, em especial do arquivo `.backuphub_encryption_key`: sem ele as credenciais cadastradas não podem ser lidas.

### Docker (alternativa)

```bash
git clone https://github.com/saulosilva85/software-backup.git && cd software-backup
mkdir -p backups && sudo chown 10001:10001 backups
BACKUPHUB_ADMIN_PASSWORD='troque-esta-senha' docker compose up -d --build
```

## Requisitos

**Servidor do BackupHub:** qualquer Linux com glibc 2.17+ (2014 em diante) ou Alpine; x86_64 ou ARM64; 2 vCPU, 2–4 GB de RAM e 20 GB de disco (mais o espaço dos backups, se o destino for local); acesso root. Internet apenas durante a instalação (ou pacote offline). Na AWS, equivale a uma `t3.small` / `t4g.small`. O servidor do BackupHub precisa ser Linux (Windows ainda não é suportado).

**Rede:**

| Comunicação | Porta | Sentido |
|---|---|---|
| Painel no navegador | 8080 (ou `--port`) | Usuários → BackupHub |
| Servidores Linux | 22 (SSH) | BackupHub → Linux |
| Servidores Windows | 5985/5986 (WinRM); 445 ajuda na identificação do sistema | BackupHub → Windows |
| AWS, GCP, S3 e GCS | 443 | BackupHub → nuvem |
| Envio dos backups Windows | 443 (S3/GCS) ou 8080 (destino local) | Windows → destino |

Durante a instalação online: `raw.githubusercontent.com`, `codeload.github.com`, `github.com`, `pypi.org` e `files.pythonhosted.org` (HTTPS). Com proxy: `export https_proxy=http://proxy:3128` antes de instalar.

O BackupHub alcança qualquer faixa de IP roteável a partir dele (VLANs, filiais, datacenters): basta liberar no firewall o IP do servidor do BackupHub para as portas acima. Na AWS, use o **IP privado** dentro da VPC (a sincronização já registra as EC2 pelo IP privado).

## Operação do serviço

| Ação | Comando (systemd) |
|---|---|
| Ver se está em execução | `systemctl status backuphub` |
| Iniciar / parar / reiniciar | `systemctl start backuphub` · `systemctl stop backuphub` · `systemctl restart backuphub` |
| Confirmar início junto com o sistema | `systemctl is-enabled backuphub` (deve responder `enabled`) |
| Logs ao vivo / últimas linhas | `journalctl -u backuphub -f` · `journalctl -u backuphub -n 100 --no-pager` |
| Testar o painel | `curl -s localhost:8080/api/health` |
| Ver a senha inicial do admin | `grep ADMIN_PASSWORD /etc/backuphub.env` |

Em OpenRC (Alpine) use `rc-service backuphub status|start|stop|restart`; em SysV, `/etc/init.d/backuphub status|start|stop|restart`. Nesses casos os logs ficam em `/var/log/backuphub/backuphub.log`.

## Primeiros passos

1. **Credenciais** → cadastre o acesso SSH (Linux), WinRM (Windows) e as contas AWS/GCP. Credenciais SSH/WinRM novas são testadas automaticamente nos servidores on-premise sem acesso (nas VMs de nuvem, associe a credencial na máquina); contas AWS/GCP disparam a primeira sincronização.
2. **Destinos** → cadastre o bucket S3/GCS ou o diretório local (`/var/lib/backuphub/backups`) e clique em **Testar conexão**.
3. **Inventário** → *Descobrir na rede* (varre automaticamente as redes do servidor), *Adicionar servidor* ou *Sincronizar nuvem*.
4. **Agendamentos** → *Nova política*: frequência, horários, máquinas (algumas ou todas), destino, caminhos e retenção.
5. **Execuções** → logs em tempo real, download e **restauração**.

Para um backup pontual: selecione máquinas no Inventário → **Backup agora**.

### Tipos de backup

| Modo | Quando usar | Para onde vai |
|---|---|---|
| **Automático** (padrão) | VMs de nuvem **sem** credencial de SO → snapshot; demais → arquivos | — |
| **Arquivos** | Servidores on-premise; VMs de nuvem quando os dados devem ir para o bucket | Bucket S3 / GCS / NAS |
| **Snapshot** | VMs AWS/GCP inteiras (restauração de disco completo) | Snapshots EBS / GCE na própria conta |

## Inventário

| Coluna / status | Significado |
|---|---|
| **Hostname** | Nome do servidor. *Não identificado* quando o servidor não divulga o nome pela rede (comum em Linux); aparece ao cadastrar a credencial ou pode ser informado em **Editar** |
| **Estado** | **Online / Offline** (on-premise, verificado a cada 5 min ou por *Verificar estado*); **Ligada / Desligada / Removida** (nuvem) |
| **Inventário Básico** | Informações obtidas pela rede, sem credencial |
| **Inventário Completo** | Informações lidas do próprio sistema, via credencial |
| **Inventário Erro** | Existe credencial, mas o acesso falhou (senha, porta bloqueada) |

**Como o sistema e o hostname são identificados sem credencial:**

- **Windows:** o desafio NTLM (SMB 445 ou WinRM 5985) informa o build e o nome do computador antes de qualquer senha. Builds compartilhados por estação e servidor (ex.: 26100 = Windows 11 24H2 / Server 2025; 17763 = Windows 10 1809 / Server 2019) são desempatados por indícios de servidor: controlador de domínio (88/389/3268), DNS/SQL Server/IIS (53/1433/80/443) ou RDP e WinRM habilitados juntos. Também usa NetBIOS (UDP 137).
- **Linux:** a identificação do SSH informa a distribuição e a versão no Ubuntu e no Debian (ex.: *Debian 12*); na família Red Hat, a versão principal (ex.: *Red Hat / Rocky / AlmaLinux / Oracle Linux 9*). O hostname vem de DNS reverso ou mDNS/LLMNR, quando disponíveis.
- Os valores sem credencial são marcados como **(estimado)**; com credencial, o nome exato do sistema os substitui.

## Preparando os servidores do cliente

**Linux:** usuário dedicado com chave SSH e sudo para leitura completa.
```bash
sudo ./scripts/prepare-linux.sh "ssh-ed25519 AAAA... backuphub"
```
Na credencial SSH, marque *Executar backup com sudo*. O BackupHub detecta se o sudo exige senha.

**Windows:** habilita o WinRM e libera o firewall apenas para o IP do BackupHub.
```powershell
.\scripts\prepare-windows.ps1 -BackupHubIP 10.0.0.5 -CreateUser
```
Em domínio, prefira uma **conta de serviço** (`EMPRESA\svc-backuphub`) e GPO habilitando o WinRM. Para o estado online/offline de estações com firewall ativo, libere também o ping:
`New-NetFirewallRule -DisplayName "BackupHub Ping" -Protocol ICMPv4 -IcmpType 8 -Direction Inbound -RemoteAddress <IP-BackupHub> -Action Allow`.
Em testes com Windows 10/11 logado com conta Microsoft, crie um usuário local administrador para o WinRM.

**Em massa com Ansible:**
```bash
cd deploy/ansible
ansible-playbook -i inventory.ini prepare-servers.yml -e backuphub_ip=10.0.0.5 \
  -e "backuphub_pubkey='ssh-ed25519 AAAA... backuphub'"
```

### Permissões na nuvem

- **AWS:** política mínima em `deploy/cloud/aws-iam-policy.json` (inventário, snapshots, exclusão restrita a snapshots com a tag `backuphub:run` e acesso ao bucket). Troque `NOME-DO-BUCKET`. Funciona em qualquer região.
- **GCP:** `deploy/cloud/gcp-setup.sh <PROJETO> <BUCKET>` cria a service account com `compute.viewer`, `compute.storageAdmin` e `storage.objectAdmin` no bucket.

## Configuração (variáveis de ambiente)

Definidas em `/etc/backuphub.env` (o instalador cria o arquivo). Após alterar: `systemctl restart backuphub`.

| Variável | Padrão | Descrição |
|---|---|---|
| `BACKUPHUB_TIMEZONE` | o do servidor (instalador) | Fuso dos agendamentos (independe da região da nuvem) |
| `BACKUPHUB_PORT` / `BACKUPHUB_HOST` | `8080` / `0.0.0.0` | Porta e endereço do painel |
| `BACKUPHUB_PUBLIC_URL` | `http://<IP do servidor>:8080` | URL que os servidores Windows usam para enviar ao destino local |
| `BACKUPHUB_MAX_PARALLEL_JOBS` | `4` | Backups simultâneos |
| `BACKUPHUB_HEALTH_MINUTES` | `5` | Intervalo da verificação online/offline (0 = desativa) |
| `BACKUPHUB_CLOUD_SYNC_MINUTES` | `60` | Intervalo da sincronização AWS/GCP (0 = desativa; também desligável por conta) |
| `BACKUPHUB_WEBHOOK_URL` | — | Webhook para falhas, avisos, servidor protegido offline e máquina removida da nuvem |
| `BACKUPHUB_SNAPSHOT_WAIT_TIMEOUT` | `3600` | Segundos aguardando snapshots concluírem (0 = não aguarda) |
| `BACKUPHUB_PRESIGNED_EXPIRES` | `21600` | Validade das URLs assinadas (s) |
| `BACKUPHUB_ADMIN_USER` / `BACKUPHUB_ADMIN_PASSWORD` | `admin` / aleatória (instalador) | Usuário criado na primeira execução |
| `BACKUPHUB_DATA_DIR` | `/var/lib/backuphub` (instalador) | Banco SQLite e chaves geradas |
| `BACKUPHUB_SECRET_KEY` / `BACKUPHUB_ENCRYPTION_KEY` | gerados | Chave de sessão e chave Fernet das credenciais |
| `BACKUPHUB_COOKIE_SECURE` | `0` | `1` quando o painel é servido via HTTPS |
| `BACKUPHUB_SCHEDULER` | `1` | `0` desativa o agendador |

## Segurança

- Credenciais (senhas, chaves SSH, secret keys, JSON de service account) são criptografadas com Fernet e nunca retornam para a interface.
- Perfis: **Administrador** (tudo), **Operador** (inventário, políticas, backup e restauração), **Somente leitura**.
- Requisições que alteram dados exigem o cabeçalho `X-Requested-With` (proteção CSRF); o cookie de sessão é `HttpOnly`/`SameSite=Lax`.
- Destinos S3 usam SSE-S3 (AES256) por padrão.
- Recomendações para produção: troque a senha do `admin` (a interface avisa); use **uma senha diferente por cliente**, guardada em cofre de senhas; crie usuários próprios para o cliente (Operador ou Somente leitura); coloque o painel atrás de HTTPS (Nginx, Traefik, ALB) com `BACKUPHUB_COOKIE_SECURE='1'`; restrinja a porta 8080 aos IPs de administração.

### Antivírus e EDR

A ferramenta **ainda não foi validada com antivírus/EDR corporativos**. Antivírus por assinatura tendem a não interferir (nada é instalado nos servidores), mas EDRs comportamentais (Defender for Endpoint, CrowdStrike, SentinelOne etc.) podem alertar sobre:
- PowerShell remoto codificado via WinRM;
- compactação e envio de pastas para a nuvem;
- teste automático de várias credenciais;
- varredura de rede.

Antes de implantar, combine com o time de segurança do cliente:
- liberar o **IP do servidor BackupHub** e a **conta de serviço** usada;
- liberar a pasta temporária `%TEMP%\backuphub-*.zip`;
- informar os horários dos backups.

## Desenvolvimento

```
backuphub/
  app.py             API REST e rotas da interface
  scheduler.py       agendador de backups e da sincronização de nuvem
  health.py          monitor online/offline
  jobs.py            fila e execução de backups/restaurações, webhook
  storage.py         destinos: S3, GCS, local (+ tokens de transferência)
  backup/            linux.py (SSH+tar), windows.py (WinRM+zip), snapshots.py (EBS/GCE)
  inventory/         linux.py, windows.py, aws.py, gcp.py, network.py (descoberta), osdetect.py (versão do SO)
  remote/            clientes SSH e WinRM
  security.py        criptografia de credenciais, usuários
  static/            interface web (HTML/CSS/JS, sem dependências externas)
install.sh           instalador universal
packaging/           geração do pacote offline e testes de instalação
deploy/              systemd, permissões AWS/GCP, playbook Ansible
scripts/             preparação de servidores Linux e Windows
tests/               testes automatizados (pytest)
```

Executar localmente: `pip install -r requirements-dev.txt && python -m backuphub` (dados em `./data`, usuário `admin` / `admin123`).

Testes: `pytest -q`. Cobrem:
- agendador e sincronização automática;
- descoberta e identificação do sistema (com servidores SMB/WinRM simulados);
- monitor online/offline e credenciais automáticas;
- API (permissões, validação, criptografia);
- fluxo completo de backup Linux (tar real → destino → retenção → download → restauração).

O GitHub Actions roda os testes em Python 3.9 e 3.12, a instalação nas distribuições listadas acima e gera os pacotes offline.

### API

Toda a interface usa a API REST em `/api` (JSON, autenticação por sessão). Principais rotas:

```
POST /api/auth/login                     GET  /api/dashboard           GET /api/settings
GET  /api/machines   POST /api/machines   PUT|DELETE /api/machines/<id>
POST /api/machines/inventory {ids}       POST /api/machines/health {ids?}
GET  /api/discovery/networks             POST /api/discovery/scan {target}   POST /api/discovery/import
POST /api/cloud/sync {credential_id}
GET|POST|PUT|DELETE /api/credentials, /api/destinations, /api/policies, /api/users
POST /api/credentials/<id>/test          POST /api/destinations/<id>/test
POST /api/backups/run {machine_ids|all, destination_id, mode, paths_linux, paths_windows}
POST /api/policies/<id>/run              POST /api/schedule/preview {days, times}
GET  /api/jobs  /api/jobs/<id>           GET  /api/jobs/<id>/download
POST /api/jobs/<id>/restore {machine_id, target_path}
```

## Limitações conhecidas do MVP

- **Validação em ambiente real em andamento:**
  - instalação, descoberta, identificação de Windows 11 e estado online/offline validados em Debian 12 e Windows 11 reais;
  - backup e restauração de Windows, IAM Role, S3 e snapshots ainda **não validados** em ambiente real.
- **Backups completos** a cada execução (sem incremental/deduplicação).
- **Windows → S3:** envio por URL assinada de PUT único, limitado a **5 GB** por arquivo (use GCS, destino local ou divida os caminhos). Arquivos abertos/bloqueados são ignorados com aviso (ainda sem VSS).
- **Bancos de dados:** copiados a partir de dumps (agende `pg_dump`/`mysqldump`/backup do SQL Server para uma pasta incluída no backup).
- **Snapshots:** a restauração é feita criando volume/disco no console da nuvem.
- **Identificação sem credencial é estimada:**
  - um Windows Server sem nenhum serviço típico pode aparecer como estação;
  - servidores Linux sem DNS reverso nem mDNS ficam com hostname *Não identificado* até o cadastro da credencial.
- **Pastas de bucket montadas** (s3fs, rclone, Mountpoint) não são ignoradas automaticamente nos caminhos de backup Linux; evite incluí-las. Prefira cadastrar o bucket diretamente como destino S3.
- **Servidor e licenciamento:**
  - um cliente por instalação (sem multi-tenant);
  - servidor do BackupHub apenas Linux;
  - sem controle de licença.
- **Segurança da conexão:** chaves de host SSH aceitas na primeira conexão (TOFU).
- **Escala:** SQLite e processo único, adequado para centenas de servidores por instalação.

## Roadmap

1. **Ambientes corporativos:**
   - PowerShell Remoting (PSRP) no lugar do PowerShell codificado, para reduzir alertas de EDR;
   - opção para desligar o teste automático de credenciais;
   - documento de exclusões para antivírus.
2. **Upload grande e arquivos abertos:** upload multipart assinado para Windows (> 5 GB) e VSS para arquivos abertos.
3. **Motor de backup:** incremental com deduplicação, criptografia no cliente e imutabilidade (S3 Object Lock), usando restic/kopia como motor.
4. **Multi-tenant e escala:**
   - multi-cliente / multi-time, com painel central e coletores leves nas redes isoladas (conexão de saída, sem abrir portas no cliente);
   - PostgreSQL.
5. **Novas fontes e destinos:**
   - backup de bucket S3 (S3 → S3);
   - exclusão automática de pastas montadas de rede;
   - integração com vCenter/Hyper-V;
   - Azure.
6. **Gestão:** chave de licença, relatórios por e-mail, MFA, SSO (Entra ID / Google), auditoria e tokens de API.
