/* BackupHub — interface web (SPA sem dependências externas) */
"use strict";

// ------------------------------------------------------------------ Utilidades
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  server: '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  activity: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
  key: '<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  alert: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
  cloud: '<path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>',
  radar: '<circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  restore: '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  hdd: '<line x1="22" y1="12" x2="2" y2="12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><line x1="6" y1="16" x2="6.01" y2="16"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
  zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
};
const icon = (name, cls = "i") => `<svg class="${cls}" viewBox="0 0 24 24">${ICONS[name] || ""}</svg>`;

const DAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const DAYS_FULL = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"];
const STATUS = {
  success: ["Sucesso", "b-success"], warning: ["Com avisos", "b-warning"], failed: ["Falhou", "b-danger"],
  running: ["Executando", "b-running"], queued: ["Na fila", "b-muted"], ok: ["OK", "b-success"],
  error: ["Erro", "b-danger"], pending: ["Pendente", "b-muted"], online: ["Online", "b-success"],
  unreachable: ["Inacessível", "b-danger"], unknown: ["Desconhecido", "b-muted"],
  stopped: ["Parada", "b-muted"], terminated: ["Removida", "b-muted"], terminating: ["Removendo", "b-warning"],
  stopping: ["Parando", "b-warning"],
};
const MACHINE_STATE = {
  running: ["Ligada", "b-success"], online: ["Online", "b-success"], stopped: ["Desligada", "b-muted"],
  stopping: ["Desligando", "b-warning"], pending: ["Iniciando", "b-info"], terminated: ["Removida", "b-muted"],
  unreachable: ["Offline", "b-danger"], offline: ["Offline", "b-danger"], unknown: ["Verificando", "b-muted"], suspended: ["Suspensa", "b-muted"],
};
const machineBadge = (st) => { const [l, c] = MACHINE_STATE[st] || [st || "—", "b-muted"]; return `<span class="badge ${c}">${esc(l)}</span>`; };
const diskTotals = (disks) => {
  const t = { size: 0, used: 0, free: 0, known: false };
  for (const d of disks || []) {
    t.size += Number(d.size_gb) || 0;
    if (d.used_gb != null) { t.used += Number(d.used_gb) || 0; t.known = true; }
    if (d.free_gb != null) t.free += Number(d.free_gb) || 0;
    else if (d.size_gb != null && d.used_gb != null) t.free += (Number(d.size_gb) - Number(d.used_gb));
  }
  return t;
};
const gb = (v) => (v == null ? "—" : `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} GB`);
const EXTRA_LABELS = { kernel: "Kernel", uptime_s: null, cpu_model: null, hardware: null, version: "Versão / build",
  domain: "Domínio", workgroup: "Grupo de trabalho", last_boot: null, dns_name: "Nome DNS", ssh_banner: "Identificação SSH",
  instance_type: "Tipo de instância", vpc_id: "VPC", image_id: "Imagem (AMI)", machine_type: "Tipo de máquina",
  project: "Projeto", zone: "Zona", az: "Zona de disponibilidade", platform_details: "Plataforma" };
const fmtUptime = (sec) => { const s = Number(sec); if (!s) return null; const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600); return d ? `${d} dia(s) e ${h}h` : `${h}h ${Math.floor((s % 3600) / 60)}min`; };

const MODES = { auto: "Automático", files: "Arquivos", snapshot: "Snapshot" };
const CRED_TYPES = {
  ssh: { label: "SSH (Linux)", desc: "Usuário + senha ou chave privada" },
  winrm: { label: "WinRM (Windows)", desc: "Usuário local ou de domínio" },
  aws: { label: "Amazon Web Services", desc: "Access key ou IAM Role" },
  gcp: { label: "Google Cloud", desc: "JSON da service account" },
};
const DEST_TYPES = {
  s3: { label: "Amazon S3", desc: "S3 ou compatível (MinIO, Wasabi...)" },
  gcs: { label: "Google Cloud Storage", desc: "Bucket GCS" },
  local: { label: "Disco local / NAS", desc: "Diretório no servidor BackupHub" },
};

const fmtBytes = (b) => {
  if (b == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB", "PB"]; let i = 0; let n = Number(b);
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
};
const toDate = (s) => (s ? new Date(s) : null);
const fmtDateTime = (s) => (s ? toDate(s).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
const fmtRelative = (s) => {
  if (!s) return "—";
  const diff = (toDate(s) - Date.now()) / 1000; const a = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });
  if (a < 60) return rtf.format(Math.round(diff), "second");
  if (a < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (a < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
};
const duration = (a, b) => {
  if (!a) return "—";
  const s = Math.max(0, Math.round(((b ? toDate(b) : new Date()) - toDate(a)) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}min ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}min`;
};
const badge = (status) => { const [l, c] = STATUS[status] || [status || "—", "b-muted"]; return `<span class="badge ${c}">${esc(l)}</span>`; };
const provBadge = (p) => {
  const map = { aws: ["AWS", "aws"], gcp: ["GCP", "gcp"], onprem: ["On-prem", "onprem"] };
  const [l, c] = map[p] || [p, "onprem"];
  return `<span class="prov ${c}"><i>${c === "onprem" ? "DC" : l}</i>${l}</span>`;
};
const platformLabel = (p) => (p === "windows" ? "Windows" : p === "linux" ? "Linux" : p || "—");
const describeSchedule = (days, times) => {
  if (!days?.length || !times?.length) return "Sem agendamento";
  const d = [...days].sort();
  let when;
  if (d.length === 7) when = "Todos os dias";
  else if (d.join() === "0,1,2,3,4") when = "Dias úteis";
  else if (d.length === 1) when = `Toda ${DAYS_FULL[d[0]]}`;
  else when = d.map((x) => DAYS[x]).join(", ");
  return `${when} às ${times.join(", ")}`;
};

// ------------------------------------------------------------------ API
async function api(path, { method = "GET", body } = {}) {
  const opts = { method, headers: { "X-Requested-With": "BackupHub" }, credentials: "same-origin" };
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch { /* sem corpo */ }
  if (res.status === 401 && !path.startsWith("/api/auth/login")) { state.user = null; renderLogin(); throw new Error("Sessão expirada"); }
  if (!res.ok) throw new Error(data?.error || `Erro ${res.status}`);
  return data;
}

function toast(msg, type = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `${icon(type === "err" ? "alert" : "check")}<div>${esc(msg)}</div>`;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), type === "err" ? 7000 : 3800);
}

async function withBusy(btn, fn) {
  const html = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spin"></span>${btn.textContent.trim()}`;
  try { return await fn(); } finally { btn.disabled = false; btn.innerHTML = html; }
}

function readForm(root) {
  const out = {};
  $$("[name]", root).forEach((el) => {
    if (el.type === "checkbox") out[el.name] = el.checked;
    else if (el.type === "number") out[el.name] = el.value === "" ? null : Number(el.value);
    else out[el.name] = el.value;
  });
  return out;
}

// ------------------------------------------------------------------ Modais
function openModal({ title, subtitle = "", body = "", wide = false, actions = [], onMount, drawer = false }) {
  const overlay = document.createElement("div");
  overlay.className = `overlay ${drawer ? "drawer-overlay" : ""}`;
  overlay.innerHTML = `
    <div class="${drawer ? "drawer" : `modal ${wide ? "wide" : ""}`}" role="dialog">
      <div class="modal-head"><div><h2>${esc(title)}</h2>${subtitle ? `<p>${subtitle}</p>` : ""}</div>
        <button class="btn btn-ghost btn-icon" data-close>${icon("x")}</button></div>
      <div class="modal-body">${body}</div>
      ${actions.length ? `<div class="modal-foot">${actions.map((a, i) => `<button class="btn ${a.primary ? "btn-primary" : ""} ${a.danger ? "btn-danger" : ""}" data-action="${i}">${a.icon ? icon(a.icon) : ""}${esc(a.label)}</button>`).join("")}</div>` : ""}
    </div>`;
  const ctx = { el: overlay, close: () => { overlay.remove(); ctx.onClose?.(); } };
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) ctx.close(); });
  $("[data-close]", overlay).onclick = ctx.close;
  $$("[data-action]", overlay).forEach((b) => {
    const a = actions[Number(b.dataset.action)];
    b.onclick = async () => {
      if (!a.onClick) return ctx.close();
      try { await withBusy(b, () => a.onClick(ctx, b)); } catch (err) { toast(err.message, "err"); }
    };
  });
  const onKey = (e) => { if (e.key === "Escape" && overlay === $$(".overlay").pop()) ctx.close(); };
  document.addEventListener("keydown", onKey);
  const baseClose = ctx.close;
  ctx.close = () => { document.removeEventListener("keydown", onKey); baseClose(); };
  $("[data-close]", overlay).onclick = ctx.close;
  document.body.appendChild(overlay);
  onMount?.(ctx);
  $("input, select, textarea", overlay)?.focus();
  return ctx;
}

function confirmDialog(message, { title = "Confirmar", danger = true, label = "Confirmar" } = {}) {
  return new Promise((resolve) => {
    const m = openModal({
      title, body: `<p style="margin:0">${message}</p>`,
      actions: [{ label: "Cancelar", onClick: (c) => { resolve(false); c.close(); } },
        { label, primary: !danger, danger, onClick: (c) => { resolve(true); c.close(); } }],
    });
    m.onClose = () => resolve(false);
  });
}

// ------------------------------------------------------------------ Estado / roteamento
const state = { user: null, poll: null, defaultPassword: false };
const can = (role) => ({ viewer: 0, operator: 1, admin: 2 })[state.user?.role] >= ({ viewer: 0, operator: 1, admin: 2 })[role];

const ROUTES = {
  dashboard: { label: "Visão geral", icon: "dashboard", render: pageDashboard },
  inventory: { label: "Inventário", icon: "server", render: pageInventory },
  policies: { label: "Agendamentos", icon: "calendar", render: pagePolicies },
  jobs: { label: "Execuções", icon: "activity", render: pageJobs },
  destinations: { label: "Destinos", icon: "database", render: pageDestinations, section: "Configuração" },
  credentials: { label: "Credenciais", icon: "key", render: pageCredentials, role: "operator" },
  users: { label: "Usuários", icon: "users", render: pageUsers, role: "admin" },
};

async function loadSettings() { try { state.settings = await api("/api/settings"); } catch { state.settings = {}; } }
const syncLabel = () => (state.settings?.cloud_sync_minutes > 0 ? `a cada ${state.settings.cloud_sync_minutes} min` : "desativada no servidor");

function setPoll(fn, ms = 5000) { clearInterval(state.poll); state.poll = fn ? setInterval(fn, ms) : null; }

function renderLayout() {
  const route = location.hash.replace("#/", "") || "dashboard";
  let nav = "";
  for (const [key, r] of Object.entries(ROUTES)) {
    if (r.role && !can(r.role)) continue;
    if (r.section) nav += `<div class="nav-label">${r.section}</div>`;
    nav += `<a href="#/${key}" class="${key === route ? "active" : ""}">${icon(r.icon)}${r.label}</a>`;
  }
  const initials = (state.user.name || state.user.username).split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
  $("#app").innerHTML = `
    <div class="layout">
      <aside class="sidebar">
        <div class="brand"><div class="brand-logo">${icon("shield")}</div><div>BackupHub<small>Backup on-premise & cloud</small></div></div>
        <div class="nav-label">Operação</div>
        <nav class="nav" style="display:contents">${nav}</nav>
        <div class="sidebar-footer">
          <div class="user-chip"><div class="avatar">${esc(initials)}</div><div style="flex:1;min-width:0">
            <div class="ellipsis">${esc(state.user.name || state.user.username)}</div><small>${esc({ admin: "Administrador", operator: "Operador", viewer: "Leitura" }[state.user.role])}</small></div></div>
          <div class="nav">
            <a href="#" id="theme-toggle">${icon("moon")}Tema claro/escuro</a>
            <a href="#" id="pw-change">${icon("lock")}Alterar senha</a>
            <a href="#" id="logout">${icon("logout")}Sair</a>
          </div>
        </div>
      </aside>
      <main class="main" id="main"></main>
    </div>`;
  $("#logout").onclick = async (e) => { e.preventDefault(); await api("/api/auth/logout", { method: "POST" }); state.user = null; renderLogin(); };
  $("#theme-toggle").onclick = (e) => {
    e.preventDefault();
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next; try { localStorage.setItem("bh-theme", next); } catch { /* ignore */ }
  };
  $("#pw-change").onclick = (e) => { e.preventDefault(); changePasswordModal(); };
  const r = ROUTES[route] || ROUTES.dashboard;
  setPoll(null);
  const main = $("#main");
  if (state.defaultPassword) {
    main.insertAdjacentHTML("afterbegin", `<div class="alert tone-warning">${icon("alert")}<div><b>Senha padrão em uso.</b> Altere a senha do administrador antes de usar em produção. <a href="#" id="pw-now">Alterar agora</a></div></div>`);
    $("#pw-now").onclick = (e) => { e.preventDefault(); changePasswordModal(); };
  }
  const container = document.createElement("div");
  main.appendChild(container);
  r.render(container).catch((err) => { container.innerHTML = `<div class="alert tone-danger">${icon("alert")}${esc(err.message)}</div>`; });
}

function changePasswordModal() {
  openModal({
    title: "Alterar senha",
    body: `<div class="field"><label>Senha atual</label><input type="password" name="current_password"></div>
           <div class="field"><label>Nova senha</label><input type="password" name="new_password"><span class="hint">Mínimo de 8 caracteres</span></div>`,
    actions: [{ label: "Cancelar" }, { label: "Salvar", primary: true, onClick: async (m) => {
      await api("/api/auth/password", { method: "POST", body: readForm(m.el) });
      state.defaultPassword = false; toast("Senha alterada"); m.close(); renderLayout();
    } }],
  });
}

function renderLogin() {
  setPoll(null);
  $("#app").innerHTML = `
    <div class="login">
      <div class="login-art">
        <div class="brand" style="padding:0"><div class="brand-logo">${icon("shield")}</div><div>BackupHub</div></div>
        <div>
          <h1>Backup centralizado para servidores on-premise, AWS e GCP.</h1>
          <p>Inventário automático, políticas de backup agendadas e armazenamento em Amazon S3 ou Google Cloud Storage — tudo em um só painel.</p>
          <div class="feature"><span>${icon("radar")}</span>Descoberta de servidores Windows e Linux na rede</div>
          <div class="feature"><span>${icon("cloud")}</span>Inventário de instâncias EC2 e Compute Engine</div>
          <div class="feature"><span>${icon("calendar")}</span>Agendamento diário, semanal ou personalizado</div>
          <div class="feature"><span>${icon("database")}</span>Backups em S3, GCS ou NAS, com retenção automática</div>
        </div>
        <small style="color:#64748b">© BackupHub</small>
      </div>
      <div class="login-form">
        <form id="login-form">
          <h2>Entrar</h2><p class="muted" style="margin:0 0 24px">Acesse o painel de backup</p>
          <div class="field"><label>Usuário</label><input name="username" autocomplete="username" required></div>
          <div class="field"><label>Senha</label><input name="password" type="password" autocomplete="current-password" required></div>
          <button class="btn btn-primary" style="width:100%;justify-content:center;height:42px;margin-top:6px">Entrar</button>
        </form>
      </div>
    </div>`;
  $("#login-form").onsubmit = async (e) => {
    e.preventDefault();
    const btn = $("button", e.target);
    try {
      await withBusy(btn, async () => {
        const res = await api("/api/auth/login", { method: "POST", body: readForm(e.target) });
        state.user = res.user; state.defaultPassword = res.default_password; await loadSettings();
        if (!location.hash) location.hash = "#/dashboard";
        renderLayout();
      });
    } catch (err) { toast(err.message, "err"); }
  };
}

// ------------------------------------------------------------------ Página: visão geral
async function pageDashboard(el) {
  const load = async () => {
    const d = await api("/api/dashboard");
    const ok = (d.jobs_24h.success || 0) + (d.jobs_24h.warning || 0);
    const fail = d.jobs_24h.failed || 0;
    const rate = ok + fail ? Math.round((ok / (ok + fail)) * 100) : null;
    const max = Math.max(1, ...d.history.map((h) => h.success + h.failed));
    const prov = d.machines.by_provider;
    const coverage = d.machines.total ? Math.round((d.machines.protected_7d / d.machines.total) * 100) : 0;
    el.innerHTML = `
      <div class="page-head"><div><h1>Visão geral</h1><p>Saúde dos backups do seu parque de servidores</p></div>
        <div class="actions">${can("operator") ? `<a class="btn" href="#/inventory">${icon("server")}Inventário</a><a class="btn btn-primary" href="#/policies">${icon("plus")}Novo agendamento</a>` : ""}</div></div>
      <div class="grid kpis">
        ${kpi("server", "primary", "Máquinas no inventário", d.machines.total, `${prov.onprem || 0} on-prem · ${prov.aws || 0} AWS · ${prov.gcp || 0} GCP`)}
        ${kpi("shield", "success", "Protegidas (7 dias)", `${d.machines.protected_7d}`, `<div class="progress" style="margin-top:6px"><div style="width:${coverage}%"></div></div><span>${coverage}% de cobertura</span>`)}
        ${kpi("activity", fail ? "danger" : "info", "Execuções (24h)", ok + fail, rate == null ? "Nenhuma execução" : `${rate}% de sucesso · ${fail} falha(s)`)}
        ${kpi("database", "warning", "Dados armazenados", fmtBytes(d.stored_bytes), `${d.destinations} destino(s) · ${d.policies} política(s) ativas`)}
      </div>
      <div class="grid two" style="margin-bottom:16px">
        <div class="card">
          <div class="card-head"><h2>Backups nos últimos 14 dias</h2><div class="legend"><span>Sucesso</span><span class="f">Falha</span></div></div>
          <div class="card-pad"><div class="chart">${d.history.map((h) => `
            <div class="col" title="${esc(new Date(h.date + "T12:00").toLocaleDateString("pt-BR"))}: ${h.success} sucesso, ${h.failed} falha, ${fmtBytes(h.bytes)}">
              <div class="stack" style="height:${((h.success + h.failed) / max) * 100}%">
                <div class="seg-s" style="flex:${h.success}"></div><div class="seg-f" style="flex:${h.failed}"></div></div>
              <div class="lbl">${h.date.slice(8, 10)}/${h.date.slice(5, 7)}</div></div>`).join("")}</div></div>
        </div>
        <div class="card">
          <div class="card-head"><h2>Próximos agendamentos</h2>${d.running ? `<span class="badge b-running">${d.running} em execução</span>` : ""}</div>
          <div class="list">${d.upcoming.length ? d.upcoming.map((p) => `
            <div class="list-item"><div class="dot-icon tone-primary">${icon("clock")}</div>
              <div class="grow"><div class="ellipsis" style="font-weight:600">${esc(p.name)}</div><div class="muted">${fmtDateTime(p.next_run_at)}</div></div>
              <span class="muted">${fmtRelative(p.next_run_at)}</span></div>`).join("") : `<div class="empty">${icon("calendar")}<div>Nenhum backup agendado</div></div>`}
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Execuções recentes</h2><a href="#/jobs" class="btn btn-sm">Ver todas</a></div>
        ${jobsTable(d.recent, { compact: true })}
      </div>`;
    bindJobRows(el);
  };
  await load();
  setPoll(load, 10000);
}

function kpi(ic, tone, label, value, sub) {
  return `<div class="card kpi"><div class="kpi-icon tone-${tone}">${icon(ic)}</div>
    <div style="flex:1;min-width:0"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub}</div></div></div>`;
}

// ------------------------------------------------------------------ Página: inventário
async function pageInventory(el) {
  const filters = { q: "", provider: "", platform: "", include_terminated: "" };
  const selected = new Set();
  let machines = [];

  el.innerHTML = `
    <div class="page-head"><div><h1>Inventário</h1><p>Servidores on-premise e máquinas virtuais na AWS e GCP · nuvem sincronizada automaticamente ${syncLabel()}</p></div>
      <div class="actions">${can("operator") ? `
        <button class="btn" id="btn-discover">${icon("radar")}Descobrir na rede</button>
        <button class="btn" id="btn-cloud">${icon("cloud")}Sincronizar nuvem</button>
        <button class="btn btn-primary" id="btn-add">${icon("plus")}Adicionar servidor</button>` : ""}</div></div>
    <div class="actions" style="margin-bottom:14px">
      <div class="search">${icon("search")}<input id="f-q" placeholder="Buscar por nome, IP, SO..."></div>
      <div class="segmented" id="f-provider">
        <button data-v="" class="on">Todos</button><button data-v="onprem">On-premise</button><button data-v="aws">AWS</button><button data-v="gcp">GCP</button></div>
      <div class="segmented" id="f-platform"><button data-v="" class="on">Todas</button><button data-v="linux">Linux</button><button data-v="windows">Windows</button></div>
      <label class="check" style="margin-left:auto"><input type="checkbox" id="f-removed"> Mostrar removidas da nuvem</label>
    </div>
    <div id="bulk"></div>
    <div class="card"><div class="table-wrap" id="machines"></div></div>`;

  const renderBulk = () => {
    $("#bulk", el).innerHTML = selected.size && can("operator") ? `
      <div class="bulkbar"><b>${selected.size} selecionada(s)</b><span style="flex:1"></span>
        <button class="btn btn-sm" id="b-inv">${icon("refresh")}Coletar inventário</button>
        <button class="btn btn-sm" id="b-backup">${icon("play")}Backup agora</button>
        <button class="btn btn-sm" id="b-del">${icon("trash")}Remover</button>
        <button class="btn btn-sm btn-icon" id="b-clear">${icon("x")}</button></div>` : "";
    if (!selected.size) return;
    $("#b-clear", el).onclick = () => { selected.clear(); renderTable(); };
    $("#b-inv", el).onclick = async () => {
      await api("/api/machines/inventory", { method: "POST", body: { ids: [...selected] } });
      toast(`Coleta de inventário iniciada para ${selected.size} máquina(s)`); load();
    };
    $("#b-backup", el).onclick = () => backupNowModal([...selected], machines);
    $("#b-del", el).onclick = async () => {
      if (!(await confirmDialog(`Remover ${selected.size} máquina(s) do inventário? Os backups já gravados não são apagados.`))) return;
      for (const id of selected) await api(`/api/machines/${id}`, { method: "DELETE" });
      selected.clear(); toast("Máquinas removidas"); load();
    };
  };

  const renderTable = () => {
    const box = $("#machines", el);
    if (!machines.length) {
      box.innerHTML = `<div class="empty">${icon("server")}<h3>Nenhuma máquina encontrada</h3>
        <div>Adicione servidores manualmente, descubra-os na rede ou sincronize uma conta AWS/GCP.</div></div>`;
      renderBulk(); return;
    }
    const allOn = machines.every((m) => selected.has(m.id));
    box.innerHTML = `<table><thead><tr>
        <th style="width:36px"><input type="checkbox" id="sel-all" ${allOn ? "checked" : ""}></th>
        <th>Máquina</th><th>Origem</th><th>Sistema</th><th>Recursos</th><th>Estado</th><th>Inventário</th><th>Último backup</th></tr></thead>
      <tbody>${machines.map((m) => {
        const dt = diskTotals(m.disks);
        const lb = m.last_backup;
        return `<tr class="clickable ${selected.has(m.id) ? "selected" : ""}" data-id="${m.id}">
          <td><input type="checkbox" class="sel" data-id="${m.id}" ${selected.has(m.id) ? "checked" : ""}></td>
          <td><div class="title">${esc(m.name)}</div><div class="sub mono">${esc(m.address || m.ip_private || "—")}${m.hostname && m.hostname !== m.name ? ` · ${esc(m.hostname)}` : ""}</div></td>
          <td>${provBadge(m.provider)}${m.region ? `<div class="sub">${esc(m.region)}</div>` : ""}</td>
          <td><div>${platformLabel(m.platform)}</div><div class="sub ellipsis" style="max-width:220px">${esc(m.os || "")}</div></td>
          <td class="muted nowrap">${m.cpu ? `${m.cpu} vCPU` : "—"} · ${m.memory_mb ? fmtBytes(m.memory_mb * 1048576) : "—"}<br>${dt.size ? `${gb(Math.round(dt.size))} disco${dt.known ? ` · ${gb(Math.round(dt.free))} livres` : ""}` : ""}</td>
          <td>${machineBadge(m.state || "unknown")}${m.state === "terminated" && m.terminated_at ? `<div class="sub">${fmtDateTime(m.terminated_at)}</div>`
            : ["offline", "unreachable"].includes(m.state) ? `<div class="sub">${m.last_seen_at ? `visto ${fmtRelative(m.last_seen_at)}` : "nunca respondeu"}</div>` : ""}</td>
          <td>${m.inventory_status === "running" ? '<span class="badge b-running">Coletando</span>' : badge(m.inventory_status || "pending")}
            ${m.inventory_status === "error" ? `<div class="sub ellipsis" style="max-width:200px" title="${esc(m.inventory_message)}">${esc(m.inventory_message)}</div>` : `<div class="sub">${fmtRelative(m.last_inventory_at)}</div>`}</td>
          <td>${lb ? `${badge(lb.status)}<div class="sub">${fmtRelative(lb.finished_at)}</div>` : '<span class="muted">Nunca</span>'}</td></tr>`;
      }).join("")}</tbody></table>`;
    $("#sel-all", box).onclick = (e) => { machines.forEach((m) => (e.target.checked ? selected.add(m.id) : selected.delete(m.id))); renderTable(); };
    $$(".sel", box).forEach((cb) => (cb.onclick = (e) => {
      e.stopPropagation(); const id = Number(cb.dataset.id);
      cb.checked ? selected.add(id) : selected.delete(id); cb.closest("tr").classList.toggle("selected", cb.checked); renderBulk();
    }));
    $$("tr.clickable", box).forEach((tr) => (tr.onclick = () => machineDrawer(Number(tr.dataset.id), load)));
    renderBulk();
  };

  const load = async () => {
    const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString();
    machines = await api(`/api/machines${qs ? `?${qs}` : ""}`);
    const ids = new Set(machines.map((m) => m.id));
    [...selected].forEach((id) => { if (!ids.has(id)) selected.delete(id); });
    renderTable();
    setPoll(machines.some((m) => m.inventory_status === "running") ? load : null, 3000);
  };

  let t;
  $("#f-q", el).oninput = (e) => { clearTimeout(t); t = setTimeout(() => { filters.q = e.target.value; load(); }, 250); };
  for (const key of ["provider", "platform"]) {
    $$(`#f-${key} button`, el).forEach((b) => (b.onclick = () => {
      $$(`#f-${key} button`, el).forEach((x) => x.classList.remove("on")); b.classList.add("on");
      filters[key] = b.dataset.v; load();
    }));
  }
  $("#f-removed", el).onchange = (e) => { filters.include_terminated = e.target.checked ? "1" : ""; load(); };
  if (can("operator")) {
    $("#btn-add", el).onclick = () => machineModal(null, load);
    $("#btn-discover", el).onclick = () => discoverModal(load);
    $("#btn-cloud", el).onclick = () => cloudSyncModal(load);
  }
  await load();
}

async function credentialOptions(types, selected, emptyLabel = "— Nenhuma —") {
  const creds = can("operator") ? await api("/api/credentials") : [];
  return `<option value="">${emptyLabel}</option>` + creds.filter((c) => types.includes(c.type))
    .map((c) => `<option value="${c.id}" ${String(c.id) === String(selected) ? "selected" : ""}>${esc(c.name)} (${c.type.toUpperCase()})</option>`).join("");
}

async function machineModal(machine, onDone) {
  const m = machine || { platform: "linux" };
  const credOpts = await credentialOptions(["ssh", "winrm"], m.credential_id);
  openModal({
    title: machine ? "Editar servidor" : "Adicionar servidor on-premise",
    subtitle: "O BackupHub conecta via SSH (Linux) ou WinRM (Windows) — nenhum agente é instalado.",
    body: `
      <div class="row"><div class="field"><label>Nome</label><input name="name" value="${esc(m.name)}" placeholder="srv-arquivos-01"></div>
        <div class="field"><label>Endereço IP ou hostname</label><input name="address" value="${esc(m.address)}" placeholder="10.0.0.15"></div></div>
      <div class="row"><div class="field"><label>Sistema operacional</label><select name="platform">
          <option value="linux" ${m.platform === "linux" ? "selected" : ""}>Linux</option><option value="windows" ${m.platform === "windows" ? "selected" : ""}>Windows</option></select></div>
        <div class="field"><label>Credencial de acesso</label><select name="credential_id">${credOpts}</select></div></div>
      ${machine ? "" : '<label class="check"><input type="checkbox" name="collect" checked> Coletar inventário após salvar</label>'}`,
    actions: [{ label: "Cancelar" }, { label: "Salvar", primary: true, onClick: async (ctx) => {
      const data = readForm(ctx.el); data.credential_id = data.credential_id ? Number(data.credential_id) : null;
      if (machine) await api(`/api/machines/${machine.id}`, { method: "PUT", body: data });
      else await api("/api/machines", { method: "POST", body: data });
      toast("Servidor salvo"); ctx.close(); onDone?.();
    } }],
  });
}

async function machineDrawer(id, onChange) {
  const m = await api(`/api/machines/${id}`);
  const credOpts = can("operator") ? await credentialOptions(m.platform === "windows" ? ["winrm"] : ["ssh"], m.credential_id) : "";
  const tags = Object.entries(m.tags || {});
  const ex = m.extra || {};
  const extra = Object.entries(ex).filter(([k, v]) => v != null && v !== "" && EXTRA_LABELS[k] !== null)
    .map(([k, v]) => [EXTRA_LABELS[k] || k, v]);
  const dt = diskTotals(m.disks);
  const notCollected = m.provider === "onprem" && m.inventory_status !== "ok";
  const credKind = m.platform === "windows" ? "WinRM (Windows)" : "SSH (Linux)";
  const ctx = openModal({
    drawer: true, title: m.name, subtitle: `${provBadge(m.provider)} &nbsp; ${platformLabel(m.platform)} &nbsp; ${machineBadge(m.state || "unknown")}`,
    body: `
      ${can("operator") ? `<div class="actions" style="margin-bottom:18px">
        <button class="btn btn-sm" id="d-inv">${icon("refresh")}Coletar inventário</button>
        <button class="btn btn-sm btn-primary" id="d-backup">${icon("play")}Backup agora</button>
        ${m.provider === "onprem" ? `<button class="btn btn-sm" id="d-edit">${icon("edit")}Editar</button>` : ""}
        <button class="btn btn-sm btn-danger" id="d-del">${icon("trash")}Remover</button></div>` : ""}
      ${m.state === "terminated" ? `<div class="alert tone-warning">${icon("alert")}<div><b>Máquina removida da nuvem${m.terminated_at ? ` em ${fmtDateTime(m.terminated_at)}` : ""}.</b> Ela não entra mais nos backups, mas o histórico e os backups já feitos continuam disponíveis para restauração em outro servidor.</div></div>` : ""}
      ${m.inventory_status === "error" ? `<div class="alert tone-danger">${icon("alert")}<div><b>Falha na coleta do inventário:</b> ${esc(m.inventory_message)}</div></div>` : ""}
      ${notCollected && !m.credential_id ? `<div class="alert tone-info">${icon("key")}<div><b>Inventário ainda não coletado.</b> Escolha uma credencial ${credKind} em <i>Acesso ao sistema operacional</i>, logo abaixo, e clique em <b>Salvar</b>: o sistema, CPU, memória e discos são coletados automaticamente.</div></div>` : ""}
      ${m.inventory_status === "running" ? `<div class="alert tone-info">${icon("refresh")}<div>Coletando o inventário...</div></div>` : ""}
      <dl class="kv">
        <dt>Hostname</dt><dd>${esc(m.hostname || "—")}</dd>
        <dt>Endereço</dt><dd class="mono">${esc(m.address || "—")}</dd>
        <dt>IP privado / público</dt><dd class="mono">${esc(m.ip_private || "—")} / ${esc(m.ip_public || "—")}</dd>
        <dt>Sistema</dt><dd>${esc(m.os || "—")}</dd>
        <dt>CPU</dt><dd>${m.cpu ? `${m.cpu} vCPU` : "—"}${ex.cpu_model ? `<div class="muted">${esc(ex.cpu_model)}</div>` : ""}</dd>
        <dt>Memória</dt><dd>${m.memory_mb ? fmtBytes(m.memory_mb * 1048576) : "—"}</dd>
        <dt>Disco (total)</dt><dd>${dt.size ? `${gb(dt.size)}${dt.known ? ` · ${gb(dt.used)} usados · <b>${gb(dt.free)} livres</b>` : ""}` : "—"}</dd>
        ${ex.hardware ? `<dt>Hardware</dt><dd>${esc(ex.hardware)}</dd>` : ""}
        ${ex.uptime_s && fmtUptime(ex.uptime_s) ? `<dt>Ligado há</dt><dd>${fmtUptime(ex.uptime_s)}</dd>` : ""}
        ${ex.last_boot ? `<dt>Último boot</dt><dd>${fmtDateTime(ex.last_boot)}</dd>` : ""}
        ${m.provider === "onprem" ? `<dt>Último contato</dt><dd>${m.last_seen_at ? `${fmtDateTime(m.last_seen_at)} (${fmtRelative(m.last_seen_at)})` : "—"}</dd>` : ""}
        ${m.instance_id ? `<dt>ID da instância</dt><dd class="mono">${esc(m.instance_id)}</dd>` : ""}
        ${m.region ? `<dt>Região / zona</dt><dd>${esc(m.region)}</dd>` : ""}
        ${extra.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}
        <dt>Último inventário</dt><dd>${fmtDateTime(m.last_inventory_at)}</dd>
      </dl>
      ${can("operator") ? `<div class="section-title">Acesso ao sistema operacional</div>
        <div class="actions"><select id="d-cred" style="flex:1">${credOpts}</select><button class="btn" id="d-cred-save">Salvar</button></div>
        <div class="hint muted" style="margin-top:6px">${m.provider !== "onprem" ? "Sem credencial, VMs de nuvem usam backup por snapshot de disco. Com credencial, é possível o backup de arquivos para o bucket." : "Obrigatória para inventário e backup."}</div>` : ""}
      <div class="section-title">Discos</div>
      ${(m.disks || []).length ? `<div class="card"><table><thead><tr><th>Disco</th><th>Tamanho</th><th>Usado</th><th>Livre</th><th>Uso</th></tr></thead><tbody>
        ${m.disks.map((d) => {
          const free = d.free_gb != null ? d.free_gb : (d.size_gb != null && d.used_gb != null ? d.size_gb - d.used_gb : null);
          const pct = d.used_gb != null && d.size_gb ? Math.min(100, Math.round((d.used_gb / d.size_gb) * 100)) : null;
          return `<tr><td><div class="mono">${esc(d.mount || d.device)}</div><div class="sub">${esc([d.label, d.mount && d.device !== d.mount ? d.device : null, d.volume_id, d.type].filter(Boolean).join(" · "))}</div></td>
          <td class="nowrap">${gb(d.size_gb)}</td><td class="nowrap">${gb(d.used_gb)}</td><td class="nowrap"><b>${gb(free)}</b></td>
          <td>${pct != null ? `<div style="display:flex;align-items:center;gap:8px"><div class="progress" style="width:70px"><div style="width:${pct}%;${pct >= 90 ? "background:#ef4444" : ""}"></div></div><span class="muted">${pct}%</span></div>` : "—"}</td></tr>`;
        }).join("")}
      </tbody></table></div>` : `<div class="muted">${notCollected ? "Disponível após a coleta do inventário" : "Sem informações de disco"}</div>`}
      ${tags.length ? `<div class="section-title">Tags / labels</div><div class="chips">${tags.map(([k, v]) => `<span class="chip" style="padding-right:10px">${esc(k)}: ${esc(v)}</span>`).join("")}</div>` : ""}
      <div class="section-title">Histórico de backups</div>
      <div class="card">${jobsTable(m.jobs, { compact: true, hideMachine: true })}</div>`,
  });
  bindJobRows(ctx.el);
  if (!can("operator")) return;
  $("#d-inv", ctx.el).onclick = async () => { await api("/api/machines/inventory", { method: "POST", body: { ids: [id] } }); toast("Coleta iniciada"); ctx.close(); onChange?.(); };
  $("#d-backup", ctx.el).onclick = () => { ctx.close(); backupNowModal([id], [m]); };
  $("#d-del", ctx.el).onclick = async () => {
    if (!(await confirmDialog(`Remover <b>${esc(m.name)}</b> do inventário?`))) return;
    await api(`/api/machines/${id}`, { method: "DELETE" }); toast("Máquina removida"); ctx.close(); onChange?.();
  };
  if ($("#d-edit", ctx.el)) $("#d-edit", ctx.el).onclick = () => { ctx.close(); machineModal(m, onChange); };
  $("#d-cred-save", ctx.el).onclick = async () => {
    const v = $("#d-cred", ctx.el).value;
    await api(`/api/machines/${id}`, { method: "PUT", body: { credential_id: v ? Number(v) : null } });
    toast(v ? "Credencial associada — coletando o inventário..." : "Credencial removida"); ctx.close(); onChange?.();
  };
}

function discoverModal(onDone) {
  let hosts = [];
  let nets = { local: [], inventory: [], max_hosts: 1024 };
  const ctx = openModal({
    title: "Descobrir servidores na rede", wide: true,
    subtitle: "Procura servidores Linux (SSH 22) e Windows (SMB 445, RDP 3389, WinRM 5985/5986) nas redes deste servidor.",
    body: `<div id="scan-nets"><div class="muted"><span class="spin" style="display:inline-block;width:12px;height:12px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:spin .7s linear infinite;margin-right:8px"></span>Detectando as redes deste servidor...</div></div>
      <div class="field" style="margin-top:14px"><label>Outras faixas (opcional)</label>
        <div class="actions"><input id="scan-extra" style="flex:1" placeholder="Ex.: 10.20.0.0/24, 172.16.5.10-50, srv01.empresa.local">
        <button class="btn btn-primary" id="scan-go">${icon("radar")}Varrer</button></div>
        <span class="hint">Faixas de outras VLANs, filiais ou datacenters alcançáveis por este servidor (máximo de 1.024 endereços por varredura).</span></div>
      <div id="scan-res"></div>`,
  });
  const box = $("#scan-res", ctx.el);
  const netBox = $("#scan-nets", ctx.el);

  const selectedTargets = () => [
    ...$$(".net-sel:checked", ctx.el).map((c) => c.value),
    ...$("#scan-extra", ctx.el).value.split(",").map((x) => x.trim()).filter(Boolean),
  ];

  const renderNets = () => {
    const row = (n, checked, extra) => `<label class="check" style="padding:8px 12px;border:1px solid var(--border);border-radius:10px;font-weight:500">
      <input type="checkbox" class="net-sel" value="${esc(n.network)}" ${checked ? "checked" : ""}>
      <span><b class="mono">${esc(n.network)}</b> <span class="muted">${extra}</span>${n.note ? `<br><span class="hint">${esc(n.note)}</span>` : ""}</span></label>`;
    netBox.innerHTML = `
      <div class="section-title" style="margin-top:0">Redes deste servidor</div>
      ${nets.local.length ? `<div class="chips" style="gap:8px">${nets.local.map((n) => row(n, true, `· interface ${esc(n.interface)} · IP ${esc(n.address)} · ${n.hosts} endereços`)).join("")}</div>`
        : '<div class="muted">Nenhuma rede detectada automaticamente. Informe a faixa abaixo.</div>'}
      ${nets.inventory.length ? `<div class="section-title">Outras redes onde já há servidores no inventário</div>
        <div class="chips" style="gap:8px">${nets.inventory.map((n) => row(n, false, `· ${n.machines} servidor(es) no inventário`)).join("")}</div>` : ""}`;
  };

  const runScan = async (btn) => {
    const targets = selectedTargets();
    if (!targets.length) { toast("Selecione uma rede ou informe uma faixa", "err"); return; }
    const started = Date.now();
    box.innerHTML = `<div class="alert tone-info">${icon("radar")}<div><b>Varrendo ${esc(targets.join(", "))}</b><br><span id="scan-time">Isso costuma levar de 10 a 40 segundos...</span></div></div>`;
    const timer = setInterval(() => { const t = $("#scan-time", box); if (t) t.textContent = `Varrendo... ${Math.round((Date.now() - started) / 1000)}s`; }, 1000);
    try {
      hosts = await api("/api/discovery/scan", { method: "POST", body: { target: targets.join(", ") } });
    } catch (err) { clearInterval(timer); box.innerHTML = ""; toast(err.message, "err"); return; }
    clearInterval(timer);
    if (!hosts.length) { box.innerHTML = `<div class="empty">${icon("radar")}<div>Nenhum servidor respondeu nas portas verificadas.<br>Verifique se há firewall entre este servidor e a rede varrida.</div></div>`; return; }
    const [linOpts, winOpts] = await Promise.all([credentialOptions(["ssh"], null, "— Sem credencial —"), credentialOptions(["winrm"], null, "— Sem credencial —")]);
    const fresh = hosts.filter((h) => !h.known).length;
    box.innerHTML = `
      <div class="alert tone-success">${icon("check")}<div><b>${hosts.length} servidor(es) encontrado(s)</b> em ${Math.round((Date.now() - started) / 1000)}s — ${fresh} novo(s), ${hosts.length - fresh} já no inventário.</div></div>
      <div class="card" style="margin-bottom:16px"><table><thead><tr><th style="width:36px"><input type="checkbox" id="h-all" checked></th><th>IP</th><th>Nome</th><th>Sistema (estimado)</th><th>Serviços</th><th>Plataforma</th></tr></thead><tbody>
        ${hosts.map((h, i) => `<tr><td><input type="checkbox" class="h-sel" data-i="${i}" ${h.known ? "disabled" : "checked"}></td>
          <td class="mono">${esc(h.ip)}</td><td>${esc(h.hostname || "—")}${h.workgroup ? `<div class="sub">${esc(h.workgroup)}</div>` : ""}${h.known ? ' <span class="badge b-muted plain">já no inventário</span>' : ""}</td>
          <td class="muted">${esc(h.os_hint || (h.platform === "windows" ? "Windows" : "—"))}</td>
          <td>${h.services.map((sv) => `<span class="badge b-info plain">${sv}</span>`).join(" ")}</td>
          <td><select class="h-plat" data-i="${i}" style="width:120px"><option value="linux" ${h.platform === "linux" ? "selected" : ""}>Linux</option><option value="windows" ${h.platform === "windows" ? "selected" : ""}>Windows</option></select></td></tr>`).join("")}
      </tbody></table></div>
      <div class="row"><div class="field"><label>Credencial para os Linux</label><select id="c-lin">${linOpts}</select></div>
        <div class="field"><label>Credencial para os Windows</label><select id="c-win">${winOpts}</select></div></div>
      <div class="actions" style="justify-content:flex-end"><button class="btn btn-primary" id="h-import">${icon("plus")}Importar selecionados</button></div>`;
    $("#h-all", box).onclick = (ev) => $$(".h-sel:not(:disabled)", box).forEach((c) => (c.checked = ev.target.checked));
    $("#h-import", box).onclick = (ev) => withBusy(ev.currentTarget, async () => {
      const chosen = $$(".h-sel", box).filter((c) => c.checked).map((c) => ({ ...hosts[c.dataset.i], platform: $(`.h-plat[data-i="${c.dataset.i}"]`, box).value }));
      if (!chosen.length) return toast("Selecione ao menos um servidor", "err");
      const r = await api("/api/discovery/import", { method: "POST", body: {
        hosts: chosen, credential_linux: Number($("#c-lin", box).value) || null, credential_windows: Number($("#c-win", box).value) || null } });
      toast(`${r.created} servidor(es) importado(s)${r.inventory_queued ? ", inventário em andamento" : ""}`); ctx.close(); onDone?.();
    });
  };

  $("#scan-go", ctx.el).onclick = (e) => withBusy(e.currentTarget, () => runScan());
  $("#scan-extra", ctx.el).onkeydown = (e) => { if (e.key === "Enter") $("#scan-go", ctx.el).click(); };

  (async () => {
    try { nets = await api("/api/discovery/networks"); } catch { /* segue com o campo manual */ }
    renderNets();
    // Varre automaticamente as redes do próprio servidor ao abrir
    if (nets.local.length) $("#scan-go", ctx.el).click();
  })();
}

async function cloudSyncModal(onDone) {
  const opts = await credentialOptions(["aws", "gcp"], null, "Selecione a conta...");
  openModal({
    title: "Sincronizar inventário de nuvem",
    subtitle: "Lista instâncias EC2 (todas as regiões) ou VMs do Compute Engine e atualiza o inventário.",
    body: `<div class="field"><label>Conta AWS / GCP</label><select name="credential_id">${opts}</select>
      <span class="hint">Não tem uma conta cadastrada? Crie em <a href="#/credentials">Credenciais</a>.</span></div><div id="sync-res"></div>`,
    actions: [{ label: "Fechar" }, { label: "Sincronizar", primary: true, icon: "refresh", onClick: async (ctx) => {
      const id = Number(readForm(ctx.el).credential_id);
      if (!id) throw new Error("Selecione uma conta");
      const r = await api("/api/cloud/sync", { method: "POST", body: { credential_id: id } });
      $("#sync-res", ctx.el).innerHTML = `<div class="alert ${r.errors.length ? "tone-warning" : "tone-success"}">${icon(r.errors.length ? "alert" : "check")}<div>
        <b>${r.total} instância(s) encontrada(s)</b> — ${r.created} nova(s), ${r.updated} atualizada(s), ${r.removed} removida(s)${r.removed_names?.length ? `: ${r.removed_names.map(esc).join(", ")}` : ""}.
        ${r.errors.length ? `<div style="margin-top:6px">${r.errors.map(esc).join("<br>")}</div>` : ""}</div></div>`;
      onDone?.();
    } }],
  });
}

async function backupNowModal(ids, machines) {
  const dests = await api("/api/destinations");
  const sel = machines.filter((m) => ids.includes(m.id));
  const hasWin = sel.some((m) => m.platform === "windows");
  const hasLin = sel.some((m) => m.platform !== "windows");
  openModal({
    title: "Executar backup agora", subtitle: `${ids.length} máquina(s): ${sel.slice(0, 4).map((m) => esc(m.name)).join(", ")}${sel.length > 4 ? "..." : ""}`,
    body: `
      <div class="field"><label>Tipo de backup</label>${modeSelector("auto")}</div>
      <div class="field"><label>Destino</label><select name="destination_id">${dests.map((d) => `<option value="${d.id}">${esc(d.name)} — ${DEST_TYPES[d.type].label}</option>`).join("")}</select>
        ${dests.length ? "" : '<span class="hint">Cadastre um destino em <a href="#/destinations">Destinos</a>.</span>'}</div>
      ${hasLin ? `<div class="field"><label>Caminhos Linux</label><textarea name="paths_linux">/etc\n/home\n/var/www</textarea><span class="hint">Um por linha</span></div>` : ""}
      ${hasWin ? `<div class="field"><label>Caminhos Windows</label><textarea name="paths_windows">C:\\Users\nC:\\inetpub</textarea></div>` : ""}`,
    onMount: (ctx) => bindSegmented(ctx.el),
    actions: [{ label: "Cancelar" }, { label: "Iniciar backup", primary: true, icon: "play", onClick: async (ctx) => {
      const data = readForm(ctx.el);
      data.mode = $(".segmented [data-mode].on", ctx.el).dataset.mode;
      data.destination_id = Number(data.destination_id) || null;
      await api("/api/backups/run", { method: "POST", body: { ...data, machine_ids: ids } });
      toast("Backup enfileirado — acompanhe em Execuções"); ctx.close(); location.hash = "#/jobs";
    } }],
  });
}

function modeSelector(current) {
  return `<div class="segmented">${Object.entries(MODES).map(([k, v]) => `<button type="button" data-mode="${k}" class="${k === current ? "on" : ""}">${v}</button>`).join("")}</div>
    <span class="hint" style="margin-top:6px">Automático: VMs de nuvem sem credencial de SO usam snapshot de disco; as demais, cópia de arquivos para o bucket.</span>`;
}
function bindSegmented(root) {
  $$(".segmented", root).forEach((seg) => $$("button", seg).forEach((b) => b.addEventListener("click", () => {
    $$("button", seg).forEach((x) => x.classList.remove("on")); b.classList.add("on");
  })));
}

// ------------------------------------------------------------------ Página: agendamentos
async function pagePolicies(el) {
  const load = async () => {
    const [policies, dests] = await Promise.all([api("/api/policies"), api("/api/destinations")]);
    const destName = Object.fromEntries(dests.map((d) => [d.id, d.name]));
    el.innerHTML = `
      <div class="page-head"><div><h1>Agendamentos</h1><p>Políticas de backup: quais máquinas, quando, para onde e por quanto tempo</p></div>
        <div class="actions">${can("operator") ? `<button class="btn btn-primary" id="p-new">${icon("plus")}Nova política</button>` : ""}</div></div>
      ${policies.length ? `<div class="grid cards">${policies.map((p) => `
        <div class="card pcard">
          <div class="pcard-top"><div style="min-width:0"><h2 class="ellipsis">${esc(p.name)}</h2>
            <div class="muted" style="margin-top:2px">${icon("clock", "i")} ${esc(describeSchedule(p.days, p.times))}</div></div>
            ${can("operator") ? `<label class="switch" title="Ativar/desativar"><input type="checkbox" data-toggle="${p.id}" ${p.enabled ? "checked" : ""}><span></span></label>` : ""}</div>
          <div class="days">${DAYS.map((d, i) => `<button disabled class="${p.days.includes(i) ? "on" : ""}" style="width:34px;height:28px;font-size:11.5px;cursor:default">${d}</button>`).join("")}</div>
          <div class="meta">
            <div><small>Máquinas</small><b>${p.all_machines ? `Todas (${p.machine_count})` : p.machine_count}</b></div>
            <div><small>Tipo</small><b>${MODES[p.mode]}</b></div>
            <div><small>Destino</small><b class="ellipsis" style="display:block">${esc(destName[p.destination_id] || (p.mode === "snapshot" ? "Snapshot nativo" : "—"))}</b></div>
            <div><small>Retenção</small><b>${p.retention_count ? `${p.retention_count} cópias` : "Ilimitada"}</b></div>
          </div>
          <div class="muted">${p.enabled && p.next_run_at ? `Próxima execução: <b style="color:var(--text)">${fmtDateTime(p.next_run_at)}</b> (${fmtRelative(p.next_run_at)})` : "Política desativada"}
            ${p.last_status ? ` · última: ${badge(p.last_status)}` : ""}</div>
          ${can("operator") ? `<div class="actions">
            <button class="btn btn-sm" data-run="${p.id}">${icon("play")}Executar agora</button>
            <button class="btn btn-sm" data-edit="${p.id}">${icon("edit")}Editar</button>
            <span style="flex:1"></span><button class="btn btn-sm btn-ghost btn-danger btn-icon" data-del="${p.id}">${icon("trash")}</button></div>` : ""}
        </div>`).join("")}</div>`
      : `<div class="card"><div class="empty">${icon("calendar")}<h3>Nenhuma política de backup</h3><div>Crie uma política para agendar backups diários, semanais ou personalizados.</div></div></div>`}`;
    if (!can("operator")) return;
    $("#p-new", el).onclick = () => policyModal(null, load);
    $$("[data-edit]", el).forEach((b) => (b.onclick = () => policyModal(policies.find((p) => p.id === Number(b.dataset.edit)), load)));
    $$("[data-run]", el).forEach((b) => (b.onclick = () => withBusy(b, async () => {
      try { const r = await api(`/api/policies/${b.dataset.run}/run`, { method: "POST" }); toast(`${r.job_ids.length} backup(s) enfileirado(s)`); }
      catch (err) { toast(err.message, "err"); }
    })));
    $$("[data-del]", el).forEach((b) => (b.onclick = async () => {
      if (!(await confirmDialog("Excluir esta política? O histórico e os backups já gravados são mantidos."))) return;
      await api(`/api/policies/${b.dataset.del}`, { method: "DELETE" }); toast("Política excluída"); load();
    }));
    $$("[data-toggle]", el).forEach((cb) => (cb.onchange = async () => {
      const p = policies.find((x) => x.id === Number(cb.dataset.toggle));
      try { await api(`/api/policies/${p.id}`, { method: "PUT", body: { ...p, enabled: cb.checked } }); toast(cb.checked ? "Política ativada" : "Política desativada"); load(); }
      catch (err) { cb.checked = !cb.checked; toast(err.message, "err"); }
    }));
  };
  await load();
}

async function policyModal(policy, onDone) {
  const [machines, dests] = await Promise.all([api("/api/machines"), api("/api/destinations")]);
  const p = policy ? { ...policy } : {
    name: "", enabled: true, mode: "auto", days: [0, 1, 2, 3, 4, 5, 6], times: ["02:00"], all_machines: false, machine_ids: [],
    destination_id: dests[0]?.id || null, paths_linux: ["/etc", "/home", "/var/www", "/opt"], paths_windows: ["C:\\Users", "C:\\inetpub"],
    excludes: ["*.tmp", "*/cache/*"], retention_count: 7,
  };
  const chosen = new Set(p.machine_ids);
  const presetOf = (days) => { const d = [...days].sort().join(); return d === "0,1,2,3,4,5,6" ? "daily" : days.length === 1 ? "weekly" : days.length === 2 ? "twice" : "custom"; };

  const ctx = openModal({
    title: policy ? "Editar política" : "Nova política de backup", wide: true,
    body: `
      <div class="row"><div class="field"><label>Nome da política</label><input name="name" value="${esc(p.name)}" placeholder="Servidores de produção — diário"></div>
        <div class="field"><label>Destino dos backups</label><select name="destination_id"><option value="">— Somente snapshot —</option>
          ${dests.map((d) => `<option value="${d.id}" ${d.id === p.destination_id ? "selected" : ""}>${esc(d.name)} — ${DEST_TYPES[d.type].label}</option>`).join("")}</select></div></div>
      <div class="section-title" style="margin-top:4px">Frequência</div>
      <div class="segmented" id="preset" style="margin-bottom:12px">
        <button type="button" data-p="daily">Todos os dias</button><button type="button" data-p="weekly">1x por semana</button>
        <button type="button" data-p="twice">2x por semana</button><button type="button" data-p="custom">Personalizado</button></div>
      <div class="field"><label>Dias da semana</label><div class="days" id="days">${DAYS.map((d, i) => `<button type="button" data-d="${i}">${d}</button>`).join("")}</div></div>
      <div class="field"><label>Horários</label><div class="chips" id="times"></div>
        <div class="actions" style="margin-top:6px"><input type="time" id="time-new" value="02:00" style="width:140px"><button type="button" class="btn btn-sm" id="time-add">${icon("plus")}Adicionar horário</button></div></div>
      <div class="alert tone-info" id="preview">${icon("clock")}<div></div></div>
      <div class="section-title">Máquinas</div>
      <label class="check" style="margin-bottom:10px"><input type="checkbox" name="all_machines" ${p.all_machines ? "checked" : ""}> Todas as máquinas do inventário (inclui as adicionadas no futuro)</label>
      <div id="picker"><div class="search" style="margin-bottom:8px">${icon("search")}<input id="pick-q" placeholder="Filtrar máquinas..." style="width:100%"></div>
        <div class="pick-list" id="pick-list"></div><div class="muted" id="pick-count" style="margin-top:6px"></div></div>
      <div class="section-title">Conteúdo</div>
      <div class="field"><label>Tipo de backup</label>${modeSelector(p.mode)}</div>
      <div class="row"><div class="field"><label>Caminhos Linux</label><textarea name="paths_linux">${esc((p.paths_linux || []).join("\n"))}</textarea></div>
        <div class="field"><label>Caminhos Windows</label><textarea name="paths_windows">${esc((p.paths_windows || []).join("\n"))}</textarea></div></div>
      <div class="row"><div class="field"><label>Exclusões (padrões)</label><textarea name="excludes" style="min-height:60px">${esc((p.excludes || []).join("\n"))}</textarea><span class="hint">Ex.: *.tmp, */node_modules/*</span></div>
        <div class="field"><label>Retenção (cópias por máquina)</label><input type="number" min="0" name="retention_count" value="${p.retention_count}"><span class="hint">Backups mais antigos são apagados automaticamente. 0 = manter todos.</span></div></div>`,
    actions: [{ label: "Cancelar" }, { label: "Salvar política", primary: true, onClick: async (c) => {
      const f = readForm(c.el);
      const body = { ...f, enabled: p.enabled, days: p.days, times: p.times, machine_ids: [...chosen],
        mode: $(".segmented [data-mode].on", c.el).dataset.mode, destination_id: Number(f.destination_id) || null };
      if (policy) await api(`/api/policies/${policy.id}`, { method: "PUT", body });
      else await api("/api/policies", { method: "POST", body });
      toast("Política salva"); c.close(); onDone?.();
    } }],
  });
  const root = ctx.el;
  bindSegmented(root);

  const renderSchedule = async () => {
    $$("#days button", root).forEach((b) => b.classList.toggle("on", p.days.includes(Number(b.dataset.d))));
    $$("#preset button", root).forEach((b) => b.classList.toggle("on", b.dataset.p === presetOf(p.days)));
    $("#times", root).innerHTML = p.times.length ? p.times.map((t) => `<span class="chip">${t}<button type="button" data-t="${t}">×</button></span>`).join("") : '<span class="muted">Nenhum horário</span>';
    $$("#times [data-t]", root).forEach((b) => (b.onclick = () => { p.times = p.times.filter((x) => x !== b.dataset.t); renderSchedule(); }));
    const prev = $("#preview div", root);
    prev.innerHTML = `<b>${esc(describeSchedule(p.days, p.times))}</b>`;
    try {
      const next = await api("/api/schedule/preview", { method: "POST", body: { days: p.days, times: p.times } });
      if (next.length) prev.innerHTML += `<br>Próximas execuções: ${next.slice(0, 4).map(fmtDateTime).join(" · ")}`;
    } catch { /* ignore */ }
  };
  $$("#days button", root).forEach((b) => (b.onclick = () => {
    const d = Number(b.dataset.d); p.days = p.days.includes(d) ? p.days.filter((x) => x !== d) : [...p.days, d].sort(); renderSchedule();
  }));
  $$("#preset button", root).forEach((b) => (b.onclick = () => {
    p.days = { daily: [0, 1, 2, 3, 4, 5, 6], weekly: [6], twice: [1, 4], custom: p.days }[b.dataset.p]; renderSchedule();
  }));
  $("#time-add", root).onclick = () => { const v = $("#time-new", root).value; if (v && !p.times.includes(v)) { p.times = [...p.times, v].sort(); renderSchedule(); } };

  const renderPicker = () => {
    const all = $('[name="all_machines"]', root).checked;
    $("#picker", root).style.display = all ? "none" : "";
    const q = $("#pick-q", root).value.toLowerCase();
    const list = machines.filter((m) => !q || `${m.name} ${m.address} ${m.os}`.toLowerCase().includes(q));
    $("#pick-list", root).innerHTML = list.length ? list.map((m) => `<label><input type="checkbox" data-m="${m.id}" ${chosen.has(m.id) ? "checked" : ""}>
      <div style="flex:1"><b>${esc(m.name)}</b> <span class="muted mono">${esc(m.address || "")}</span></div>${provBadge(m.provider)}<span class="muted" style="width:70px">${platformLabel(m.platform)}</span></label>`).join("")
      : '<div class="empty" style="padding:20px">Nenhuma máquina no inventário</div>';
    $$("[data-m]", root).forEach((cb) => (cb.onchange = () => { const id = Number(cb.dataset.m); cb.checked ? chosen.add(id) : chosen.delete(id); $("#pick-count", root).textContent = `${chosen.size} selecionada(s)`; }));
    $("#pick-count", root).textContent = `${chosen.size} selecionada(s)`;
  };
  $('[name="all_machines"]', root).onchange = renderPicker;
  $("#pick-q", root).oninput = renderPicker;
  renderSchedule(); renderPicker();
}

// ------------------------------------------------------------------ Página: execuções
function jobsTable(items, { compact = false, hideMachine = false } = {}) {
  if (!items?.length) return `<div class="empty">${icon("activity")}<div>Nenhuma execução ainda</div></div>`;
  return `<div class="table-wrap"><table><thead><tr><th>#</th>${hideMachine ? "" : "<th>Máquina</th>"}<th>Tipo</th><th>Status</th><th>Tamanho</th><th>Início</th>${compact ? "" : "<th>Duração</th><th>Mensagem</th>"}</tr></thead><tbody>
    ${items.map((j) => `<tr class="clickable" data-job="${j.id}"><td class="muted">${j.id}</td>
      ${hideMachine ? "" : `<td><div class="title">${esc(j.machine_name)}</div><div class="sub">${esc(j.policy_name || (j.trigger === "schedule" ? "Agendado" : "Manual"))}</div></td>`}
      <td>${j.kind === "restore" ? '<span class="badge b-info plain">Restauração</span>' : `<span class="muted">${MODES[j.mode] || j.mode || "—"}</span>`}</td>
      <td>${badge(j.status)}</td><td>${fmtBytes(j.size_bytes)}</td><td title="${fmtDateTime(j.created_at)}">${fmtRelative(j.started_at || j.created_at)}</td>
      ${compact ? "" : `<td class="muted">${duration(j.started_at, j.finished_at)}</td><td class="muted ellipsis" style="max-width:280px" title="${esc(j.message)}">${esc(j.message || "")}</td>`}</tr>`).join("")}
  </tbody></table></div>`;
}
function bindJobRows(root, onChange) { $$("[data-job]", root).forEach((tr) => (tr.onclick = () => jobModal(Number(tr.dataset.job), onChange))); }

async function pageJobs(el) {
  const filters = { status: "", kind: "" };
  el.innerHTML = `
    <div class="page-head"><div><h1>Execuções</h1><p>Histórico de backups e restaurações, com logs detalhados</p></div>
      <div class="actions"><button class="btn" id="j-refresh">${icon("refresh")}Atualizar</button></div></div>
    <div class="actions" style="margin-bottom:14px">
      <div class="segmented" id="f-status"><button data-v="" class="on">Todos</button><button data-v="running">Executando</button><button data-v="success">Sucesso</button><button data-v="warning">Com avisos</button><button data-v="failed">Falhas</button></div>
      <div class="segmented" id="f-kind"><button data-v="" class="on">Backup e restauração</button><button data-v="backup">Backups</button><button data-v="restore">Restaurações</button></div>
    </div>
    <div class="card" id="jobs"></div>`;
  const load = async () => {
    const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString();
    const data = await api(`/api/jobs?limit=200${qs ? `&${qs}` : ""}`);
    $("#jobs", el).innerHTML = jobsTable(data.items) + (data.total > data.items.length ? `<div class="muted" style="padding:12px 16px">Exibindo ${data.items.length} de ${data.total}</div>` : "");
    bindJobRows(el, load);
    setPoll(data.items.some((j) => ["queued", "running"].includes(j.status)) ? load : null, 4000);
  };
  for (const key of ["status", "kind"]) {
    $$(`#f-${key} button`, el).forEach((b) => (b.onclick = () => {
      $$(`#f-${key} button`, el).forEach((x) => x.classList.remove("on")); b.classList.add("on"); filters[key] = b.dataset.v; load();
    }));
  }
  $("#j-refresh", el).onclick = load;
  await load();
}

async function jobModal(id, onChange) {
  let j = await api(`/api/jobs/${id}`);
  let timer = null;
  const body = () => `
    <dl class="kv">
      <dt>Status</dt><dd>${badge(j.status)}</dd>
      <dt>Máquina</dt><dd>${esc(j.machine_name)}</dd>
      <dt>Operação</dt><dd>${j.kind === "restore" ? "Restauração" : `Backup · ${MODES[j.mode] || j.mode}`} · ${j.trigger === "schedule" ? "agendado" : "manual"}${j.policy_name ? ` · ${esc(j.policy_name)}` : ""}</dd>
      <dt>Início / fim</dt><dd>${fmtDateTime(j.started_at)} → ${fmtDateTime(j.finished_at)} (${duration(j.started_at, j.finished_at)})</dd>
      <dt>Tamanho</dt><dd>${fmtBytes(j.size_bytes)}</dd>
      ${j.artifact ? `<dt>${j.mode === "snapshot" ? "Snapshots" : "Arquivo"}</dt><dd class="mono">${esc(j.artifact)}</dd>` : ""}
      ${j.sha256 ? `<dt>SHA-256</dt><dd class="mono" style="font-size:11px">${esc(j.sha256)}</dd>` : ""}
      ${j.message ? `<dt>Mensagem</dt><dd>${esc(j.message)}</dd>` : ""}
    </dl>
    <div class="section-title">Log</div><div class="log" id="job-log">${esc(j.log || "Aguardando início...")}</div>`;
  const okFiles = j.kind === "backup" && j.mode === "files" && ["success", "warning"].includes(j.status) && can("operator");
  const ctx = openModal({
    title: `Execução #${j.id}`, subtitle: esc(j.machine_name), wide: true, body: body(),
    actions: okFiles ? [
      { label: "Baixar backup", icon: "download", onClick: () => { window.location.href = `/api/jobs/${j.id}/download`; } },
      { label: "Restaurar", icon: "restore", primary: true, onClick: (c) => { c.close(); restoreModal(j); } },
    ] : [],
  });
  const refresh = async () => {
    j = await api(`/api/jobs/${id}`);
    $(".modal-body", ctx.el).innerHTML = body();
    const log = $("#job-log", ctx.el); log.scrollTop = log.scrollHeight;
    if (!["queued", "running"].includes(j.status)) { clearInterval(timer); onChange?.(); }
  };
  if (["queued", "running"].includes(j.status)) timer = setInterval(refresh, 2500);
  ctx.onClose = () => clearInterval(timer);
  const log = $("#job-log", ctx.el); log.scrollTop = log.scrollHeight;
}

async function restoreModal(job) {
  const machines = await api("/api/machines");
  const src = machines.find((m) => m.id === job.machine_id);
  const isWin = job.artifact.endsWith(".zip");
  const targets = machines.filter((m) => (m.platform === "windows") === isWin);
  openModal({
    title: "Restaurar backup", subtitle: `Backup #${job.id} de ${esc(job.machine_name)} — ${fmtDateTime(job.finished_at)}`,
    body: `
      <div class="alert tone-warning">${icon("alert")}<div>Os arquivos serão extraídos no diretório indicado. Arquivos existentes com o mesmo nome serão sobrescritos.</div></div>
      <div class="field"><label>Servidor de destino</label><select name="machine_id">${targets.map((m) => `<option value="${m.id}" ${m.id === src?.id ? "selected" : ""}>${esc(m.name)} (${esc(m.address || "")})</option>`).join("")}</select></div>
      <div class="field"><label>Diretório de restauração</label><input name="target_path" value="${isWin ? "C:\\BackupHub-Restore" : "/tmp/backuphub-restore"}">
        <span class="hint">${isWin ? "" : "Use / para restaurar nos caminhos originais."}</span></div>`,
    actions: [{ label: "Cancelar" }, { label: "Restaurar", primary: true, icon: "restore", onClick: async (c) => {
      const f = readForm(c.el);
      const r = await api(`/api/jobs/${job.id}/restore`, { method: "POST", body: { machine_id: Number(f.machine_id), target_path: f.target_path } });
      toast("Restauração iniciada"); c.close(); jobModal(r.job_id);
    } }],
  });
}

// ------------------------------------------------------------------ Página: destinos
async function pageDestinations(el) {
  const load = async () => {
    const dests = await api("/api/destinations");
    el.innerHTML = `
      <div class="page-head"><div><h1>Destinos de backup</h1><p>Buckets Amazon S3, Google Cloud Storage ou armazenamento local/NAS</p></div>
        <div class="actions">${can("admin") ? `<button class="btn btn-primary" id="d-new">${icon("plus")}Novo destino</button>` : ""}</div></div>
      ${dests.length ? `<div class="grid cards">${dests.map((d) => `
        <div class="card pcard">
          <div class="pcard-top"><div style="display:flex;gap:12px;align-items:center;min-width:0">
            <div class="kpi-icon ${d.type === "s3" ? "tone-warning" : d.type === "gcs" ? "tone-info" : "tone-primary"}">${icon(d.type === "local" ? "hdd" : "database")}</div>
            <div style="min-width:0"><h2 class="ellipsis">${esc(d.name)}</h2><div class="muted">${DEST_TYPES[d.type].label}</div></div></div></div>
          <div class="mono muted ellipsis">${esc(d.type === "local" ? d.config.path : `${d.type === "s3" ? "s3" : "gs"}://${d.config.bucket}`)}${d.config.prefix ? `/${esc(d.config.prefix)}` : ""}</div>
          <div class="meta"><div><small>Armazenado</small><b>${fmtBytes(d.stored_bytes)}</b></div><div><small>Políticas</small><b>${d.policies}</b></div></div>
          <div class="actions"><button class="btn btn-sm" data-test="${d.id}">${icon("zap")}Testar conexão</button>
            ${can("admin") ? `<button class="btn btn-sm" data-edit="${d.id}">${icon("edit")}Editar</button><span style="flex:1"></span>
            <button class="btn btn-sm btn-ghost btn-danger btn-icon" data-del="${d.id}">${icon("trash")}</button>` : ""}</div>
        </div>`).join("")}</div>`
      : `<div class="card"><div class="empty">${icon("database")}<h3>Nenhum destino configurado</h3><div>Cadastre um bucket S3 (AWS) ou GCS (Google Cloud) para receber os backups.</div></div></div>`}`;
    if ($("#d-new", el)) $("#d-new", el).onclick = () => destinationModal(null, load);
    $$("[data-edit]", el).forEach((b) => (b.onclick = () => destinationModal(dests.find((d) => d.id === Number(b.dataset.edit)), load)));
    $$("[data-test]", el).forEach((b) => (b.onclick = () => withBusy(b, async () => {
      const r = await api(`/api/destinations/${b.dataset.test}/test`, { method: "POST" }); toast(r.message, r.ok ? "ok" : "err");
    })));
    $$("[data-del]", el).forEach((b) => (b.onclick = async () => {
      if (!(await confirmDialog("Excluir este destino? Os arquivos no bucket não são apagados."))) return;
      await api(`/api/destinations/${b.dataset.del}`, { method: "DELETE" }); toast("Destino excluído"); load();
    }));
  };
  await load();
}

async function destinationModal(dest, onDone) {
  const d = dest ? { ...dest, config: { ...dest.config } } : { type: "s3", config: {} };
  const creds = await api("/api/credentials");
  const fields = (type) => {
    const c = d.config; const v = (k, def = "") => esc(c[k] ?? def);
    const credSel = (t, optional) => `<div class="field"><label>Credencial ${t.toUpperCase()}</label><select name="credential_id">
      ${optional ? '<option value="">Usar IAM Role / variáveis de ambiente do servidor</option>' : '<option value="">Selecione...</option>'}
      ${creds.filter((x) => x.type === t).map((x) => `<option value="${x.id}" ${x.id === d.credential_id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div>`;
    if (type === "s3") return `
      <div class="row"><div class="field"><label>Bucket</label><input name="bucket" value="${v("bucket")}" placeholder="empresa-backups"></div>
        <div class="field"><label>Região</label><input name="region" value="${v("region", "us-east-1")}"></div></div>
      <div class="row"><div class="field"><label>Prefixo (pasta)</label><input name="prefix" value="${v("prefix", "backuphub")}"></div>
        <div class="field"><label>Classe de armazenamento</label><select name="storage_class">${["", "STANDARD_IA", "INTELLIGENT_TIERING", "GLACIER_IR", "ONEZONE_IA"].map((s) => `<option value="${s}" ${c.storage_class === s ? "selected" : ""}>${s || "STANDARD"}</option>`).join("")}</select></div></div>
      <div class="row"><div class="field"><label>Criptografia no servidor</label><select name="sse"><option value="AES256" ${c.sse !== "" && c.sse !== "aws:kms" ? "selected" : ""}>SSE-S3 (AES256)</option><option value="aws:kms" ${c.sse === "aws:kms" ? "selected" : ""}>SSE-KMS</option><option value="" ${c.sse === "" ? "selected" : ""}>Padrão do bucket</option></select></div>
        <div class="field"><label>Endpoint (opcional)</label><input name="endpoint_url" value="${v("endpoint_url")}" placeholder="https://minio.empresa.local:9000"><span class="hint">Para MinIO, Wasabi, Ceph e outros compatíveis com S3</span></div></div>
      ${credSel("aws", true)}`;
    if (type === "gcs") return `
      <div class="row"><div class="field"><label>Bucket</label><input name="bucket" value="${v("bucket")}" placeholder="empresa-backups"></div>
        <div class="field"><label>Prefixo (pasta)</label><input name="prefix" value="${v("prefix", "backuphub")}"></div></div>
      <div class="field"><label>Classe de armazenamento</label><select name="storage_class">${["", "NEARLINE", "COLDLINE", "ARCHIVE"].map((s) => `<option value="${s}" ${c.storage_class === s ? "selected" : ""}>${s || "Padrão do bucket"}</option>`).join("")}</select></div>
      ${credSel("gcp", false)}`;
    return `<div class="field"><label>Diretório no servidor BackupHub</label><input name="path" value="${v("path", "/data/backups")}"><span class="hint">Pode ser um compartilhamento NFS/SMB montado</span></div>
      <div class="field"><label>Prefixo (subpasta)</label><input name="prefix" value="${v("prefix")}"></div>`;
  };
  const ctx = openModal({
    title: dest ? "Editar destino" : "Novo destino de backup",
    body: `<div class="type-cards">${Object.entries(DEST_TYPES).map(([k, t]) => `<button type="button" class="type-card ${k === d.type ? "on" : ""}" data-type="${k}" ${dest ? "disabled" : ""}><b>${t.label}</b><span>${t.desc}</span></button>`).join("")}</div>
      <div class="field"><label>Nome</label><input name="name" value="${esc(d.name)}" placeholder="Bucket principal"></div><div id="dest-fields">${fields(d.type)}</div>`,
    actions: [{ label: "Cancelar" }, { label: "Salvar", primary: true, onClick: async (c) => {
      const f = readForm(c.el);
      const { name, credential_id: cred, ...config } = f;
      const bodyData = { name, type: d.type, config, credential_id: Number(cred) || null };
      if (dest) await api(`/api/destinations/${dest.id}`, { method: "PUT", body: bodyData });
      else await api("/api/destinations", { method: "POST", body: bodyData });
      toast("Destino salvo"); c.close(); onDone?.();
    } }],
  });
  $$(".type-card", ctx.el).forEach((b) => (b.onclick = () => {
    d.type = b.dataset.type; $$(".type-card", ctx.el).forEach((x) => x.classList.toggle("on", x === b)); $("#dest-fields", ctx.el).innerHTML = fields(d.type);
  }));
}

// ------------------------------------------------------------------ Página: credenciais
async function pageCredentials(el) {
  const load = async () => {
    const creds = await api("/api/credentials");
    el.innerHTML = `
      <div class="page-head"><div><h1>Credenciais</h1><p>Acesso aos servidores e às contas de nuvem — armazenadas criptografadas (AES/Fernet)</p></div>
        <div class="actions">${can("admin") ? `<button class="btn btn-primary" id="c-new">${icon("plus")}Nova credencial</button>` : ""}</div></div>
      <div class="card">${creds.length ? `<div class="table-wrap"><table><thead><tr><th>Nome</th><th>Tipo</th><th>Identificação</th><th>Em uso</th><th>Sincronização da nuvem</th><th></th></tr></thead><tbody>
        ${creds.map((c) => `<tr><td><div class="title">${esc(c.name)}</div><div class="sub">${esc(c.description || "")}</div></td>
          <td><span class="badge b-info plain">${CRED_TYPES[c.type].label}</span></td>
          <td class="mono muted">${esc(c.data.username || c.data.access_key_id || c.data.role_arn || c.data.projects || (c.type === "gcp" ? "service account" : "—"))}</td>
          <td>${c.usage} máquina(s)</td>
          <td>${["aws", "gcp"].includes(c.type) ? `<div>${c.sync_enabled ? `<span class="badge b-info plain">Automática</span> <span class="muted">${syncLabel()}</span>` : '<span class="badge b-muted plain">Manual</span>'}</div>
            <div class="sub" title="${esc(c.last_sync_message || "")}">${c.last_sync_at ? `${badge(c.last_sync_status === "warning" ? "warning" : c.last_sync_status === "error" ? "failed" : "success")} ${fmtRelative(c.last_sync_at)}` : (c.sync_enabled ? "Aguardando primeira sincronização" : "Nunca sincronizada")}</div>` : '<span class="muted">—</span>'}</td>
          <td style="text-align:right;white-space:nowrap">${["aws", "gcp"].includes(c.type) ? `<button class="btn btn-sm" data-sync="${c.id}">${icon("refresh")}Sincronizar</button>` : ""}<button class="btn btn-sm" data-test="${c.id}">${icon("zap")}Testar</button>
            ${can("admin") ? `<button class="btn btn-sm" data-edit="${c.id}">${icon("edit")}</button><button class="btn btn-sm btn-danger" data-del="${c.id}">${icon("trash")}</button>` : ""}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">${icon("key")}<h3>Nenhuma credencial</h3><div>Cadastre acessos SSH/WinRM para os servidores e chaves das contas AWS/GCP.</div></div>`}</div>`;
    if ($("#c-new", el)) $("#c-new", el).onclick = () => credentialModal(null, load);
    $$("[data-edit]", el).forEach((b) => (b.onclick = () => credentialModal(creds.find((c) => c.id === Number(b.dataset.edit)), load)));
    $$("[data-sync]", el).forEach((b) => (b.onclick = () => withBusy(b, async () => {
      try {
        const r = await api("/api/cloud/sync", { method: "POST", body: { credential_id: Number(b.dataset.sync) } });
        toast(`${r.total} instância(s): ${r.created} nova(s), ${r.updated} atualizada(s), ${r.removed} removida(s)`, r.errors.length ? "err" : "ok");
      } catch (err) { toast(err.message, "err"); }
      load();
    })));
    $$("[data-del]", el).forEach((b) => (b.onclick = async () => {
      if (!(await confirmDialog("Excluir esta credencial? As máquinas que a utilizam ficarão sem acesso."))) return;
      await api(`/api/credentials/${b.dataset.del}`, { method: "DELETE" }); toast("Credencial excluída"); load();
    }));
    $$("[data-test]", el).forEach((b) => (b.onclick = () => {
      const c = creds.find((x) => x.id === Number(b.dataset.test));
      const run = async (host) => { const r = await api(`/api/credentials/${c.id}/test`, { method: "POST", body: { host } }); toast(r.message, r.ok ? "ok" : "err"); return r; };
      if (["ssh", "winrm"].includes(c.type)) {
        openModal({ title: `Testar ${c.name}`, body: '<div class="field"><label>Servidor para teste</label><input name="host" placeholder="10.0.0.15"></div>',
          actions: [{ label: "Fechar" }, { label: "Testar", primary: true, onClick: async (m) => { const r = await run(readForm(m.el).host); if (r.ok) m.close(); } }] });
      } else withBusy(b, () => run(null));
    }));
  };
  await load();
}

function credentialModal(cred, onDone) {
  let type = cred?.type || "ssh";
  const data = cred?.data || {};
  const kept = cred ? "•••••• (mantida — preencha para trocar)" : "";
  const val = (k, def = "") => esc(data[k] ?? def);
  const fields = (t) => ({
    ssh: `<div class="row"><div class="field"><label>Usuário</label><input name="username" value="${val("username")}" placeholder="backup"></div>
          <div class="field"><label>Porta</label><input type="number" name="port" value="${val("port", 22)}"></div></div>
        <div class="field"><label>Senha</label><input type="password" name="password" placeholder="${kept}"></div>
        <div class="field"><label>Chave privada (opcional)</label><textarea name="private_key" placeholder="${cred ? kept : "-----BEGIN OPENSSH PRIVATE KEY-----"}"></textarea></div>
        <div class="field"><label>Passphrase da chave</label><input type="password" name="passphrase" placeholder="${kept}"></div>
        <label class="check"><input type="checkbox" name="use_sudo" ${data.use_sudo ? "checked" : ""}> Executar backup com sudo (necessário para ler /etc, /root etc. com usuário não-root)</label>`,
    winrm: `<div class="row"><div class="field"><label>Usuário</label><input name="username" value="${val("username")}" placeholder="EMPRESA\\svc-backup"></div>
          <div class="field"><label>Senha</label><input type="password" name="password" placeholder="${kept}"></div></div>
        <div class="row3"><div class="field"><label>Autenticação</label><select name="transport">${["ntlm", "kerberos", "credssp", "basic"].map((x) => `<option ${data.transport === x ? "selected" : ""}>${x}</option>`).join("")}</select></div>
          <div class="field"><label>Porta</label><input type="number" name="port" value="${val("port")}" placeholder="5985 / 5986"></div>
          <div class="field"><label>&nbsp;</label><label class="check"><input type="checkbox" name="use_https" ${data.use_https ? "checked" : ""}> HTTPS (5986)</label></div></div>
        <label class="check"><input type="checkbox" name="ignore_cert" ${data.ignore_cert !== false ? "checked" : ""}> Aceitar certificado autoassinado</label>`,
    aws: `<div class="row"><div class="field"><label>Access Key ID</label><input name="access_key_id" value="${val("access_key_id")}" placeholder="AKIA..."></div>
          <div class="field"><label>Secret Access Key</label><input type="password" name="secret_access_key" placeholder="${kept}"></div></div>
        <div class="field"><label>IAM Role ARN (opcional)</label><input name="role_arn" value="${val("role_arn")}" placeholder="arn:aws:iam::123456789012:role/BackupHub"><span class="hint">Para acessar a conta do cliente via AssumeRole (recomendado). Sem access key, usa a role da instância onde o BackupHub roda.</span></div>
        <div class="row"><div class="field"><label>Região padrão</label><input name="default_region" value="${val("default_region", "us-east-1")}"></div>
          <div class="field"><label>Regiões para inventário</label><input name="regions" value="${val("regions")}" placeholder="vazio = todas"></div></div>
        <label class="check"><input type="checkbox" name="sync_enabled" ${cred ? (cred.sync_enabled ? "checked" : "") : "checked"}> Sincronizar o inventário desta conta automaticamente (${syncLabel()})</label>`,
    gcp: `<div class="field"><label>JSON da service account</label><textarea name="service_account_json" style="min-height:140px" placeholder="${cred ? kept : '{"type": "service_account", "project_id": ...}'}"></textarea>
          <span class="hint">Papéis sugeridos: Compute Viewer, Compute Storage Admin (snapshots) e Storage Object Admin no bucket.</span></div>
        <div class="field"><label>Projetos para inventário</label><input name="projects" value="${val("projects")}" placeholder="vazio = projeto da service account"></div>
        <label class="check"><input type="checkbox" name="sync_enabled" ${cred ? (cred.sync_enabled ? "checked" : "") : "checked"}> Sincronizar o inventário desta conta automaticamente (${syncLabel()})</label>`,
  })[t];
  const ctx = openModal({
    title: cred ? "Editar credencial" : "Nova credencial",
    body: `<div class="type-cards">${Object.entries(CRED_TYPES).map(([k, t]) => `<button type="button" class="type-card ${k === type ? "on" : ""}" data-type="${k}" ${cred ? "disabled" : ""}><b>${t.label}</b><span>${t.desc}</span></button>`).join("")}</div>
      <div class="row"><div class="field"><label>Nome</label><input name="name" value="${esc(cred?.name)}" placeholder="Servidores Linux produção"></div>
        <div class="field"><label>Descrição</label><input name="description" value="${esc(cred?.description)}"></div></div>
      <div id="cred-fields">${fields(type)}</div>`,
    actions: [{ label: "Cancelar" }, { label: "Salvar", primary: true, onClick: async (c) => {
      const { name, description, sync_enabled: syncEnabled, ...secret } = readForm($(".modal-body", c.el));
      const extra = syncEnabled === undefined ? {} : { sync_enabled: syncEnabled };
      if (cred) await api(`/api/credentials/${cred.id}`, { method: "PUT", body: { name, description, data: secret, ...extra } });
      else await api("/api/credentials", { method: "POST", body: { name, description, type, data: secret, ...extra } });
      toast("Credencial salva"); c.close(); onDone?.();
    } }],
  });
  $$(".type-card", ctx.el).forEach((b) => (b.onclick = () => {
    type = b.dataset.type; $$(".type-card", ctx.el).forEach((x) => x.classList.toggle("on", x === b)); $("#cred-fields", ctx.el).innerHTML = fields(type);
  }));
}

// ------------------------------------------------------------------ Página: usuários
async function pageUsers(el) {
  const ROLE_LABEL = { admin: "Administrador", operator: "Operador", viewer: "Somente leitura" };
  const load = async () => {
    const users = await api("/api/users");
    el.innerHTML = `
      <div class="page-head"><div><h1>Usuários</h1><p>Quem acessa o painel e o que pode fazer</p></div>
        <div class="actions"><button class="btn btn-primary" id="u-new">${icon("plus")}Novo usuário</button></div></div>
      <div class="alert tone-info">${icon("shield")}<div><b>Administrador:</b> tudo, inclusive credenciais e destinos. <b>Operador:</b> inventário, políticas, backups e restaurações. <b>Somente leitura:</b> consulta.</div></div>
      <div class="card"><table><thead><tr><th>Usuário</th><th>Perfil</th><th>Criado em</th><th></th></tr></thead><tbody>
        ${users.map((u) => `<tr><td><div class="title">${esc(u.name || u.username)}</div><div class="sub">${esc(u.username)}</div></td>
          <td><span class="badge b-info plain">${ROLE_LABEL[u.role]}</span></td><td class="muted">${fmtDateTime(u.created_at)}</td>
          <td style="text-align:right"><button class="btn btn-sm" data-edit="${u.id}">${icon("edit")}</button>
            ${u.id !== state.user.id ? `<button class="btn btn-sm btn-danger" data-del="${u.id}">${icon("trash")}</button>` : ""}</td></tr>`).join("")}
      </tbody></table></div>`;
    const form = (u) => `
      <div class="row"><div class="field"><label>Usuário (login)</label><input name="username" value="${esc(u?.username)}" ${u ? "disabled" : ""}></div>
        <div class="field"><label>Nome</label><input name="name" value="${esc(u?.name)}"></div></div>
      <div class="row"><div class="field"><label>Perfil</label><select name="role">${Object.entries(ROLE_LABEL).map(([k, v]) => `<option value="${k}" ${u?.role === k ? "selected" : ""}>${v}</option>`).join("")}</select></div>
        <div class="field"><label>${u ? "Nova senha (opcional)" : "Senha"}</label><input type="password" name="password"></div></div>`;
    $("#u-new", el).onclick = () => openModal({ title: "Novo usuário", body: form(null), actions: [{ label: "Cancelar" }, { label: "Criar", primary: true, onClick: async (c) => {
      await api("/api/users", { method: "POST", body: readForm(c.el) }); toast("Usuário criado"); c.close(); load(); } }] });
    $$("[data-edit]", el).forEach((b) => (b.onclick = () => {
      const u = users.find((x) => x.id === Number(b.dataset.edit));
      openModal({ title: `Editar ${u.username}`, body: form(u), actions: [{ label: "Cancelar" }, { label: "Salvar", primary: true, onClick: async (c) => {
        const { username, ...rest } = readForm(c.el);
        await api(`/api/users/${u.id}`, { method: "PUT", body: rest }); toast("Usuário atualizado"); c.close(); load(); } }] });
    }));
    $$("[data-del]", el).forEach((b) => (b.onclick = async () => {
      if (!(await confirmDialog("Remover este usuário?"))) return;
      await api(`/api/users/${b.dataset.del}`, { method: "DELETE" }); toast("Usuário removido"); load();
    }));
  };
  await load();
}

// ------------------------------------------------------------------ Inicialização
(async function boot() {
  try { const t = localStorage.getItem("bh-theme"); if (t) document.documentElement.dataset.theme = t; } catch { /* ignore */ }
  window.addEventListener("hashchange", () => { if (state.user) { $$(".overlay").forEach((o) => o.remove()); renderLayout(); } });
  try {
    const res = await api("/api/auth/me");
    state.user = res.user; await loadSettings(); renderLayout();
  } catch { renderLogin(); }
})();
