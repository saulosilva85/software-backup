# BackupHub

Plataforma web de **inventário e backup** de servidores **Windows e Linux on-premise** e de máquinas virtuais na **AWS** e no **Google Cloud**, com agendamento e armazenamento em **Amazon S3** (ou compatíveis) e **Google Cloud Storage**.

> Status: **MVP / primeiro esboço** para testes com clientes piloto. Veja [Limitações conhecidas](#limitações-conhecidas-do-mvp) e o [Roadmap](#roadmap).

## Funcionalidades

| Área | O que faz |
|---|---|
| **Inventário on-premise** | Descoberta por varredura de rede (CIDR, faixas ou lista de IPs) detectando SSH, SMB, RDP e WinRM; cadastro manual; coleta de SO, CPU, memória, discos e IPs via SSH (Linux) e WinRM/PowerShell (Windows). **Sem agente.** |
| **Inventário de nuvem** | Sincroniza instâncias **EC2** (todas as regiões ou as escolhidas, com AssumeRole) e VMs do **Compute Engine** (um ou mais projetos), com tipo, vCPU, memória, volumes, IPs e tags. VMs removidas da nuvem são marcadas como "removidas". |
| **Backup de arquivos** | Linux: `tar.gz` transmitido via SSH direto para o bucket (multipart no S3, upload resumível no GCS) — sem arquivos temporários. Windows: o servidor compacta em `.zip` (`tar.exe` nativo ou `Compress-Archive`) e envia para uma URL assinada. |
| **Backup por snapshot** | Snapshots nativos de discos EBS (AWS, multi-volume consistente) e Persistent Disk (GCP) — não precisa de acesso ao sistema operacional. |
| **Seleção de máquinas** | O cliente escolhe algumas máquinas, várias pela busca/filtros ou **todas** (inclui as que forem adicionadas no futuro). |
| **Agendador** | Todos os dias, 1x por semana, 2x por semana, dias úteis ou qualquer combinação de dias + vários horários por dia, no fuso configurado. Pré-visualização das próximas execuções. |
| **Retenção** | Mantém as N cópias mais recentes por máquina/política (arquivos e snapshots). |
| **Restauração** | Restaura um backup de arquivos no mesmo servidor ou em outro, no diretório escolhido. Download do backup pelo navegador. |
| **Destinos** | Amazon S3 (com classe de armazenamento e SSE-S3/KMS), qualquer S3 compatível (MinIO, Wasabi, Ceph...), Google Cloud Storage e disco local/NAS. |
| **Operação** | Painel com cobertura de backup, histórico de 14 dias, logs detalhados por execução, SHA-256 dos arquivos, webhook (Slack/Teams/Discord) em falhas. |
| **Segurança** | Login com perfis (Administrador, Operador, Somente leitura), credenciais criptografadas (Fernet/AES), proteção CSRF, senhas com hash. |

## Arquitetura

```
                        ┌──────────────────────────────────────────────┐
  Navegador ──HTTPS──▶  │ BackupHub (Python / Flask, 1 processo)       │
                        │  • API REST + interface web (SPA)            │
                        │  • Agendador  • Fila de jobs (threads)       │
                        │  • SQLite (inventário, políticas, histórico) │
                        └───────┬───────────────┬──────────────┬───────┘
                     SSH (22)   │   WinRM (5985/6)│     APIs AWS / GCP
                ┌───────────────▼─┐   ┌──────────▼───────┐  ┌──▼───────────────────┐
                │ Servidores Linux│   │Servidores Windows│  │ EC2 / Compute Engine │
                │ tar | gzip ─────┼─┐ │ zip ──PUT URL ───┼┐ │ snapshots de disco   │
                └─────────────────┘ │ └──────────────────┘│ └──────────────────────┘
                                    ▼                      ▼
                         ┌──────────────────────────────────────────┐
                         │ Amazon S3 / S3 compatível / GCS / NAS     │
                         └──────────────────────────────────────────┘
```

**Por que Python e sem Ansible no núcleo?** O BackupHub fala SSH (paramiko) e WinRM (pywinrm) diretamente, como o Ansible faz por baixo, mas com controle fino de streaming, progresso, erros e retenção — e sem exigir Ansible instalado no cliente. O Ansible continua útil para **preparar** dezenas de servidores de uma vez: veja `deploy/ansible/`.

Estrutura do código:

```
backuphub/
  app.py             API REST e rotas da interface
  scheduler.py       agendador (dias da semana × horários, fuso configurável)
  jobs.py            fila e execução de backups/restaurações, webhook
  storage.py         destinos: S3, GCS, local (+ tokens de transferência)
  backup/            linux.py (SSH+tar), windows.py (WinRM+zip), snapshots.py (EBS/GCE)
  inventory/         linux.py, windows.py, aws.py, gcp.py, network.py (descoberta)
  remote/            clientes SSH e WinRM
  security.py        criptografia de credenciais, usuários
  static/            interface web (HTML/CSS/JS, sem dependências externas)
deploy/              systemd, permissões AWS/GCP, playbook Ansible
scripts/             preparação de servidores Linux e Windows
tests/               testes automatizados (pytest)
```

## Instalação

O BackupHub roda em **qualquer distribuição Linux** (x86_64 e ARM64). O instalador traz um **Python próprio** (portátil), então não depende da versão do Python do sistema, e detecta automaticamente o gerenciador de pacotes (`apt`, `dnf`, `yum`, `zypper`, `apk`, `pacman`) e o sistema de inicialização (`systemd`, `OpenRC`, `SysV`).

### Distribuições testadas automaticamente (a cada alteração, via GitHub Actions)

| Família | Versões |
|---|---|
| Ubuntu | 18.04, 20.04, 22.04, 24.04 (x86_64 e ARM64) |
| Debian | 10, 11, 12 |
| Red Hat e derivados | CentOS 7, Rocky 8 e 9 (x86_64 e ARM64), AlmaLinux 9, Oracle Linux 8 e 9, Fedora |
| Amazon Linux | 2 e 2023 (x86_64 e ARM64/Graviton) |
| Outras | openSUSE Leap 15, Arch Linux, Alpine |

Requisitos mínimos: 2 vCPU, 2 GB de RAM, 20 GB de disco, glibc 2.17+ (qualquer distribuição de 2014 em diante) ou Alpine.

### Instalação online (uma linha)

```bash
curl -fsSL https://raw.githubusercontent.com/saulosilva85/software-backup/main/install.sh | sudo sh
```

Sem `curl`: `wget -qO- https://raw.githubusercontent.com/saulosilva85/software-backup/main/install.sh | sudo sh`

Ao final, o instalador mostra o endereço do painel e a **senha inicial do admin** (gerada aleatoriamente). Opções úteis:

```bash
curl -fsSL https://raw.githubusercontent.com/saulosilva85/software-backup/main/install.sh | sudo sh -s -- \
  --admin-password 'MinhaSenhaForte' --timezone America/Sao_Paulo --open-firewall
```

| Opção | Descrição |
|---|---|
| `--admin-password` | Senha inicial do admin (padrão: aleatória, exibida no final) |
| `--timezone` | Fuso dos agendamentos (padrão: o do servidor) |
| `--public-url` | URL que os servidores Windows usam para alcançar o BackupHub |
| `--port` | Porta do painel (padrão 8080) |
| `--open-firewall` | Libera a porta no firewalld/ufw |
| `--system-python` | Usa o Python do sistema (>= 3.9) em vez do portátil |
| `--uninstall [--purge]` | Remove (com `--purge`, apaga também dados e configuração) |

### Instalação offline (servidor sem internet)

Baixe o pacote completo na página [Releases](https://github.com/saulosilva85/software-backup/releases) (`backuphub-<versão>-linux-x86_64.tar.gz` ou `-aarch64`), copie para o servidor e:

```bash
tar xzf backuphub-*-linux-x86_64.tar.gz
cd backuphub-*-linux-x86_64
sudo sh install.sh
```

O pacote inclui Python, todas as dependências e o código — não acessa a internet.

### Onde os arquivos ficam

| Caminho | Conteúdo |
|---|---|
| `/opt/backuphub` | Programa (Python portátil, dependências, código) |
| `/etc/backuphub.env` | Configuração (porta, fuso, URL pública, webhook) |
| `/var/lib/backuphub` | Banco de dados, chaves de criptografia e `backups/` (destino local) |
| `/var/log/backuphub` | Logs (em sistemas sem systemd) |

Serviço: `systemctl status|restart backuphub` e logs com `journalctl -u backuphub -f` (em OpenRC/SysV o instalador mostra os comandos equivalentes). **Atualizar** = executar o instalador novamente (dados e configuração são preservados).

### Docker (alternativa)

```bash
git clone https://github.com/saulosilva85/software-backup.git && cd software-backup
mkdir -p backups && sudo chown 10001:10001 backups
BACKUPHUB_ADMIN_PASSWORD='troque-esta-senha' docker compose up -d --build
```

> Em produção, coloque um proxy reverso com HTTPS (Nginx, Traefik, ALB) na frente e defina `BACKUPHUB_COOKIE_SECURE='1'` em `/etc/backuphub.env`.
> A ferramenta usa **1 processo** (o agendador e a fila de backup rodam dentro dele).

### Onde instalar no cliente

O BackupHub se adapta à infraestrutura de cada cliente:

- **Só on-premise**: uma VM Linux na rede do cliente, destino S3/GCS (ou NAS local).
- **AWS**: uma instância EC2 pequena (t3.small) com **IAM Role** — não é preciso cadastrar access keys; para outras contas use *AssumeRole*.
- **GCP**: uma VM e2-small com service account, ou o JSON da service account.
- **Híbrido**: uma única instalação alcançando a rede local (VPN/Direct Connect/Interconnect) e as contas de nuvem.

## Primeiros passos

1. **Credenciais** → cadastre o acesso SSH (Linux), WinRM (Windows) e as contas AWS/GCP. Use **Testar** para validar.
2. **Destinos** → cadastre o bucket S3 ou GCS e clique em **Testar conexão** (faz uma gravação de teste).
3. **Inventário** → *Descobrir na rede* (ex.: `192.168.0.0/24`), *Adicionar servidor* ou *Sincronizar nuvem*. Selecione as máquinas e clique em *Coletar inventário*.
4. **Agendamentos** → *Nova política*: escolha frequência (todos os dias / 1x / 2x por semana / personalizado), horários, máquinas (algumas ou todas), destino, caminhos e retenção.
5. **Execuções** → acompanhe logs em tempo real, baixe ou **restaure** backups.

Para um backup pontual: selecione máquinas no Inventário → **Backup agora**.

### Tipos de backup

| Modo | Quando usar | Para onde vai |
|---|---|---|
| **Automático** (padrão) | VMs de nuvem **sem** credencial de SO → snapshot; demais → arquivos | — |
| **Arquivos** | Servidores on-premise; VMs de nuvem quando o cliente quer os dados no bucket | Bucket S3 / GCS / NAS |
| **Snapshot** | VMs AWS/GCP inteiras (restauração de disco completo) | Snapshots EBS / GCE na própria conta |

## Preparando os servidores do cliente

**Linux** — usuário dedicado com chave SSH e sudo para leitura completa:
```bash
sudo ./scripts/prepare-linux.sh "ssh-ed25519 AAAA... backuphub"
```
Na credencial SSH, marque *Executar backup com sudo*. O BackupHub detecta se o sudo exige senha ou não.

**Windows** — habilita o WinRM e libera o firewall apenas para o IP do BackupHub:
```powershell
.\scripts\prepare-windows.ps1 -BackupHubIP 10.0.0.5 -CreateUser
```
Em domínio, prefira uma conta de serviço (`EMPRESA\svc-backup`) com GPO habilitando WinRM. Os servidores Windows precisam alcançar o destino (S3/GCS via HTTPS) — ou o BackupHub (`BACKUPHUB_PUBLIC_URL`) quando o destino é local.

**Em massa com Ansible:**
```bash
cd deploy/ansible
ansible-playbook -i inventory.ini prepare-servers.yml -e backuphub_ip=10.0.0.5 \
  -e "backuphub_pubkey='ssh-ed25519 AAAA... backuphub'"
```

### Permissões na nuvem

- **AWS**: política mínima em `deploy/cloud/aws-iam-policy.json` (inventário, snapshots, exclusão restrita a snapshots com a tag `backuphub:run`, e acesso ao bucket). Troque `NOME-DO-BUCKET`.
- **GCP**: `deploy/cloud/gcp-setup.sh <PROJETO> <BUCKET>` cria a service account com `compute.viewer`, `compute.storageAdmin` e `storage.objectAdmin` no bucket.

## Configuração (variáveis de ambiente)

| Variável | Padrão | Descrição |
|---|---|---|
| `BACKUPHUB_DATA_DIR` | `./data` | Banco SQLite e chaves geradas |
| `BACKUPHUB_ADMIN_USER` / `BACKUPHUB_ADMIN_PASSWORD` | `admin` / `admin123` | Usuário criado na primeira execução |
| `BACKUPHUB_TIMEZONE` | `America/Sao_Paulo` | Fuso dos agendamentos |
| `BACKUPHUB_MAX_PARALLEL_JOBS` | `4` | Backups simultâneos |
| `BACKUPHUB_PUBLIC_URL` | `http://localhost:8080` | URL que os servidores Windows usam para enviar ao destino local |
| `BACKUPHUB_WEBHOOK_URL` | — | Webhook chamado quando um job falha ou termina com avisos |
| `BACKUPHUB_SNAPSHOT_WAIT_TIMEOUT` | `3600` | Segundos aguardando snapshots concluírem (0 = não aguarda) |
| `BACKUPHUB_PRESIGNED_EXPIRES` | `21600` | Validade das URLs assinadas (s) |
| `BACKUPHUB_SECRET_KEY` / `BACKUPHUB_ENCRYPTION_KEY` | gerados | Chave de sessão e chave Fernet das credenciais |
| `BACKUPHUB_COOKIE_SECURE` | `0` | `1` quando servido via HTTPS |
| `BACKUPHUB_SCHEDULER` | `1` | `0` desativa o agendador |
| `BACKUPHUB_HOST` / `BACKUPHUB_PORT` | `0.0.0.0` / `8080` | Endereço do servidor de desenvolvimento |

> **Guarde a `BACKUPHUB_ENCRYPTION_KEY`** (arquivo `.backuphub_encryption_key` no diretório de dados). Sem ela as credenciais salvas não podem ser lidas.

## Segurança

- Credenciais (senhas, chaves SSH, secret keys, JSON de service account) são criptografadas com Fernet e nunca retornam para a interface.
- Perfis: **Administrador** (tudo), **Operador** (inventário, políticas, backup e restauração), **Somente leitura**.
- Requisições que alteram dados exigem o cabeçalho `X-Requested-With` (proteção CSRF) e o cookie de sessão é `HttpOnly`/`SameSite=Lax`.
- Nos destinos S3, a criptografia SSE-S3 (AES256) vem ativada por padrão.
- Troque a senha padrão do `admin` (a interface avisa enquanto ela estiver em uso).

## API

Toda a interface usa a API REST em `/api` (JSON, autenticação por sessão). Principais rotas:

```
POST /api/auth/login                 GET  /api/dashboard
GET  /api/machines                   POST /api/machines/inventory   {ids}
POST /api/discovery/scan  {target}   POST /api/discovery/import
POST /api/cloud/sync  {credential_id}
GET|POST|PUT|DELETE /api/credentials, /api/destinations, /api/policies, /api/users
POST /api/backups/run  {machine_ids|all, destination_id, mode, paths_linux, paths_windows}
POST /api/policies/<id>/run          POST /api/schedule/preview {days, times}
GET  /api/jobs  /api/jobs/<id>       GET  /api/jobs/<id>/download
POST /api/jobs/<id>/restore {machine_id, target_path}
```

## Testes

```bash
pip install -r requirements-dev.txt
pytest -q
```

Os testes cobrem agendador (diário, semanal, 2x/semana, fuso e não duplicação), parsers de inventário, API (permissões, validação, criptografia de credenciais) e o **fluxo completo de backup Linux** — tar real → destino → retenção → download → restauração — simulando o SSH localmente.

## Limitações conhecidas do MVP

- **Backups completos** a cada execução (sem incremental/deduplicação).
- **Windows → S3**: o envio usa uma URL assinada de PUT único, limitada a **5 GB** por arquivo. Para volumes maiores use GCS (até 5 TB), destino local, ou divida os caminhos em políticas diferentes. Arquivos abertos/bloqueados (ex.: bancos em uso) são ignorados com aviso (ainda sem VSS).
- Bancos de dados devem ser copiados a partir de dumps (ex.: agende `pg_dump`/`mysqldump`/backup do SQL Server para uma pasta incluída no backup).
- Restauração automática apenas de backups de **arquivos**; snapshots são restaurados criando volume/disco no console da nuvem.
- Chaves de host SSH são aceitas na primeira conexão (TOFU).
- SQLite e processo único: adequado para centenas de servidores por instalação.

## Roadmap

1. Upload multipart assinado para Windows (> 5 GB) e uso de VSS (arquivos abertos).
2. Backup incremental com deduplicação e criptografia no cliente (ex.: restic/kopia como motor).
3. Multi-tenant (vários clientes em uma instalação, para operação como MSP) e PostgreSQL.
4. Azure (VMs e Blob Storage), backup de bancos de dados (dumps gerenciados) e Object Lock (imutabilidade contra ransomware).
5. Relatórios por e-mail, SSO (Entra ID / Google), auditoria e API tokens.
