// Video Notes 前端。
// 左邊：新增影片（模式、輸出形式、語音辨識）→ /api/check（處理過的先問要不要重做或直接補輸出）→ /api/jobs；每秒輪詢 /api/jobs。
// 筆記庫：影片與「合併」分開，可多選 → 產生其他輸出（不花 token）／重新分析／合併成一份。
// 右邊：檢視筆記（渲染後 / Markdown 原文 / 逐字稿）、開啟各種輸出、複製到 Notion、二次加工。
//
// 安全：來自資料（影片標題、筆記、錯誤訊息…）的文字一律用 textContent（h() 的字串子節點與 text 屬性）。
// 唯一用 innerHTML 的是 renderMarkdown()：它先把全部內容跳脫，連結只放行 http(s)。

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const enc = encodeURIComponent;

const STAGES_VIDEO = [["info", "資訊"], ["download", "下載"], ["audio", "音訊"], ["transcribe", "轉錄"], ["notes", "筆記"], ["outputs", "輸出"]];
const STAGES_TASK = [["notes", "分析"], ["outputs", "輸出"]];
const STAGE_TITLE = { running: "進行中", waiting: "排隊中", done: "完成", reused: "沿用既有檔案", failed: "失敗" };
const STATUS_TEXT = { queued: "排隊中", running: "處理中", done: "完成", failed: "失敗", cancelled: "已取消" };
const TYPE_TEXT = { reanalyze: "重新分析", combine: "合併" };
const GROUP_TITLE = { notes: "筆記", tree: "樹狀圖", html: "網頁" };
const COMPAT = "openai-compat";

const state = {
  app: null,          // /api/state
  jobs: [],
  jobsSig: "",
  library: { videos: [], collections: [] },
  checked: new Set(), // 筆記庫勾選的資料夾
  modifiers: new Set(),
  preset: "",
  outPicker: null,    // 新增影片表單的輸出多選
  selected: null,     // {type: "job", id} | {type: "lib", folder}
  view: "rendered",
  current: null,      // 右側正在看的東西
  curSig: "",
};

// ---------------------------------------------------------------- helpers
class ApiError extends Error {
  constructor(message, extra = {}) { super(message); Object.assign(this, extra); }
}

// 錯誤合約：reason 一句人話；remedy.action 是「怎麼辦」
function errText(e) {
  if (!e) return "";
  const how = e.remedy && e.remedy.action ? `（怎麼辦：${e.remedy.action}）` : "";
  return `${e.reason || "發生錯誤"}${how}`;
}

async function api(path, options = {}) {
  // 自訂 header：伺服器只接受帶這個 header 的寫入請求（擋別的網站跨站呼叫本機 API）
  const headers = { "X-Video-Notes": "1" };
  if (options.body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    let body = {};
    try { body = await res.json(); } catch { /* 不是 JSON */ }
    if (body.error) throw new ApiError(errText(body.error), { info: body.error, estimate: body.estimate, status: res.status });
    const detail = typeof body.detail === "string" ? body.detail : (body.detail ? "資料格式不正確" : res.statusText);
    throw new ApiError(detail, { status: res.status });
  }
  return (res.headers.get("content-type") || "").includes("json") ? res.json() : res.text();
}
const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data) });

// 建 DOM：字串子節點一律是文字（不會被當 HTML）
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k in el && k !== "list") el[k] = v;
    else el.setAttribute(k, v);
  }
  el.append(...kids.flat().filter(c => c != null && c !== false));
  return el;
}
const labelled = (text, control) => h("label", {}, text, control);

function esc(s) {   // 只給 renderMarkdown 用
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

// ---------------------------------------------------------------- 中文標籤
const profileName = id => { const p = state.app.profiles.find(x => x.id === id); return p ? `${p.icon} ${p.name}` : id; };
const modName = id => { const m = state.app.modifiers.find(x => x.id === id); return m ? `${m.icon} ${m.name}` : id; };
// 分析方案代碼（news+brief、finance+focus-ab12cd）→ 人看得懂的名稱
const slugLabel = slug => String(slug).split("+").map((part, i) =>
  part.startsWith("focus-") ? "指定關注" : (i === 0 ? profileName(part) : modName(part))).join(" ＋ ");
const rendererByName = n => state.app.renderers.find(r => r.name === n);
const rendererLabel = n => rendererByName(n)?.label || n;
// outputs/<slug>.<renderer>.<副檔名> → 輸出格式的中文名稱
function outputInfo(file) {
  const list = [...state.app.renderers].sort((a, b) => b.name.length - a.name.length);
  for (const r of list) {
    const i = file.indexOf(`.${r.name}.`);
    if (i > 0) return { renderer: r.name, slug: file.slice(0, i), label: r.label };
  }
  return { renderer: "", slug: "", label: file };
}
const baseName = p => String(p).split(/[\\/]/).pop();

// ---------------------------------------------------------------- markdown（Notion 會用到的子集）
function inline(text) {
  let s = esc(text);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
  s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/(^|[\s(（])(https?:\/\/[^\s<)）]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  return s;
}

function renderTable(rows) {
  const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
  const body = rows.filter(r => !/^\|\s*:?-{2,}/.test(r));
  if (!body.length) return "";
  const [head, ...rest] = body;
  return `<table><thead><tr>${cells(head).map(c => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>`
    + rest.map(r => `<tr>${cells(r).map(c => `<td>${inline(c)}</td>`).join("")}</tr>`).join("") + "</tbody></table>";
}

function renderMarkdown(md) {
  const lines = md.replace(/\r/g, "").split("\n");
  let html = "", list = null, para = [];
  const flush = () => { if (para.length) { html += `<p>${inline(para.join(" "))}</p>`; para = []; } };
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let m;
    if (!line.trim()) { flush(); close(); continue; }
    if ((m = line.match(/^(#{1,4})\s+(.*)$/))) {
      flush(); close();
      html += `<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`;
      continue;
    }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { flush(); close(); html += "<hr>"; continue; }
    if (/^>/.test(line)) {
      flush(); close();
      const quote = [line.replace(/^>\s?/, "")];
      while (i + 1 < lines.length && /^>/.test(lines[i + 1])) quote.push(lines[++i].replace(/^>\s?/, ""));
      html += `<blockquote>${quote.map(inline).join("<br>")}</blockquote>`;
      continue;
    }
    if (/^\|.*\|\s*$/.test(line)) {
      flush(); close();
      const rows = [line];
      while (i + 1 < lines.length && /^\|.*\|\s*$/.test(lines[i + 1])) rows.push(lines[++i]);
      html += renderTable(rows);
      continue;
    }
    if ((m = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/))) {
      flush();
      const type = /\d/.test(m[2]) ? "ol" : "ul";
      if (list !== type) { close(); html += `<${type}>`; list = type; }
      const indent = m[1].length >= 2 ? ' style="margin-left:1.4em"' : "";
      const task = m[3].match(/^\[( |x|X)\]\s+(.*)$/);
      html += task
        ? `<li class="task"${indent}>${task[1].trim() ? "☑" : "☐"} ${inline(task[2])}</li>`
        : `<li${indent}>${inline(m[3])}</li>`;
      continue;
    }
    close();
    para.push(line.trim());
  }
  flush(); close();
  return html;
}

// ---------------------------------------------------------------- 初始化
async function init() {
  state.app = await api("/api/state");
  $("#version").textContent = `v${state.app.version}`;
  renderEnv();
  renderAlerts();
  if ((state.app.deps_job || {}).state === "running") pollDeps();   // 重新整理頁面時下載還在跑
  fillForm();
  fillRefine();
  bindEvents();
  await pollJobs();
  setInterval(pollJobs, 1000);
  loadLibrary();
}

function chip(text, cls, title) { return h("span", { class: `chip ${cls || ""}`, title: title || "", text }); }

function renderEnv() {
  const { env, settings, providers, ytdlp } = state.app;
  const chips = [];
  chips.push(chip(`${env.gpu ? "GPU" : "CPU"} 語音辨識`, env.gpu ? "ok" : "", env.gpu_text));
  chips.push(chip(`ffmpeg ${env.ffmpeg ? "✓" : "✗"}`, env.ffmpeg ? "ok" : "bad", env.ffmpeg || "找不到 ffmpeg"));
  chips.push(chip(`YouTube JS ${env.js_runtimes.length ? "✓ " + env.js_runtimes[0] : "✗"}`, env.js_runtimes.length ? "ok" : "bad", ""));
  const days = ytdlp.days == null ? "" : `（${ytdlp.days} 天前）`;
  chips.push(chip(`yt-dlp ${ytdlp.version}${days}`, ytdlp.level === "ok" ? "ok" : ytdlp.level === "warn" ? "warn" : "bad",
    ytdlp.level === "ok" ? "下載套件夠新" : `已經很久沒更新，YouTube 可能抓不到。${ytdlp.action || ""}`));
  const ready = env.keys[settings.provider];   // 有金鑰；Claude 訂閱則是找得到 Claude Code
  const keyless = env.keyless.includes(settings.provider);
  const model = settings.model || state.app.default_models[settings.provider];
  const missing = settings.provider === COMPAT ? "（還沒填端點網址）" : keyless ? "（找不到 Claude Code）" : "（未設定金鑰）";
  chips.push(chip(`AI：${providers[settings.provider] || settings.provider} ${model || ""} ${ready ? "✓" : missing}`,
    ready ? "ok" : "bad", keyless ? env.claude_code : ""));
  $("#env-chips").replaceChildren(...chips);
  $("#out-hint").textContent = `輸出到：${state.app.output_root}`;
}

// 頂端警示條：缺少的外部程式（一鍵下載）＋被標成「壞掉」的依賴（中文原因＋怎麼辦）＋「重新檢查」
function renderAlerts() {
  const { degraded, ytdlp } = state.app;
  const job = state.app.deps_job || {};
  const depItems = (state.app.deps || []).filter(d => d.needed || (job.name === d.name && job.state !== "done"))
    .map(d => depAlert(d, job));
  const items = degraded.map(d => ({ title: `${d.label} 目前被標記為壞掉`, reason: d.reason, action: d.action }));
  if (ytdlp.level !== "ok" && !degraded.some(d => d.source === "yt-dlp")) {
    items.push({ title: `yt-dlp 已經 ${ytdlp.days} 天沒更新`, reason: "網站改版後可能抓不到影片。", action: ytdlp.action });
  }
  const bar = $("#alert-bar");
  bar.hidden = !items.length && !depItems.length;
  bar.replaceChildren(
    h("div", { class: "alert-list" }, depItems, items.map(it => h("div", { class: "alert-item" },
      h("strong", { text: it.title }), h("span", { text: `　${it.reason}` }),
      it.action ? h("div", { class: "small", text: `怎麼辦：${it.action}` }) : null))),
    items.length ? h("button", { type: "button", id: "btn-recheck", onclick: recheck, text: "重新檢查" }) : null);
}

// 缺少 ffmpeg／Deno：一鍵從官方下載（使用者按了才下載），或自己到官網／用 winget 裝
function depAlert(d, job) {
  const mine = job.name === d.name;
  const running = job.state === "running";
  let status = null;
  if (mine && job.state === "failed") status = h("div", { class: "small bad", text: `下載失敗：${errText(job.error)}` });
  else if (mine && running) status = h("div", { class: "small", text: `${job.detail || "下載中…"}` });
  return h("div", { class: "alert-item" },
    h("strong", { text: `缺少 ${d.label}` }), h("span", { text: `　${d.purpose}` }),
    h("div", { class: "dep-actions" },
      h("button", { type: "button", disabled: running, onclick: () => installDep(d.name),
        text: mine && running ? "下載中…" : `一鍵下載 ${d.label}（${d.size_hint}）` }),
      h("a", { href: d.homepage, target: "_blank", rel: "noopener noreferrer", text: "到官網自己下載" }),
      h("code", { text: d.winget, title: "也可以在終端機執行這一行" })),
    h("div", { class: "small", text: `從官方下載並核對 SHA-256，放在工具旁邊的 data\\bin\\，不會動到系統設定。授權：${d.license}` }),
    status);
}

async function installDep(name) {
  try {
    const r = await post("/api/deps/install", { name });
    state.app.deps_job = r.job;
    renderAlerts();
    pollDeps();
  } catch (e) {
    toast(`沒辦法開始下載：${e.message}`);
  }
}

async function pollDeps() {
  let r;
  try { r = await api("/api/deps"); } catch (e) { setTimeout(pollDeps, 2000); return; }
  state.app.deps = r.items;
  state.app.deps_job = r.job;
  renderAlerts();
  if (r.job.state === "running") { setTimeout(pollDeps, 1000); return; }
  if (r.job.state === "done") {
    toast(r.job.detail || "安裝完成");
    state.app = await api("/api/state");   // ffmpeg／JS 的狀態晶片一起更新
    renderEnv();
    renderAlerts();
  }
}

async function recheck() {
  const btn = $("#btn-recheck");
  btn.disabled = true;
  try {
    const r = await post("/api/health/recheck", {});
    state.app.degraded = r.degraded;
    state.app.ytdlp = r.ytdlp;
    renderAlerts();
    renderEnv();
    const bad = r.checks.filter(c => c.level === "error").length;
    toast(bad ? `重新檢查完成：還有 ${bad} 項有問題` : "重新檢查完成：都正常");
  } catch (e) {
    toast(`重新檢查失敗：${e.message}`);
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- 輸出形式／語音辨識／模式（共用元件）
// 輸出形式多選，依分組；不能用的灰掉，tooltip 寫原因與怎麼辦。skipAlways：不列出「一定會產生」的 Markdown。
function outputPicker({ checked = [], skipAlways = false, onchange } = {}) {
  const boxes = new Map();
  const root = h("div", { class: "out-groups" });
  for (const g of ["notes", "tree", "html"]) {
    const items = state.app.renderers.filter(r => r.group === g && !(skipAlways && r.always));
    if (!items.length) continue;
    const row = h("div", { class: "out-group" }, h("span", { class: "out-group-title", text: GROUP_TITLE[g] }));
    for (const r of items) {
      const cb = h("input", { type: "checkbox", checked: r.always || (checked.includes(r.name) && r.available),
                              disabled: r.always || !r.available, onchange });
      boxes.set(r.name, cb);
      const tip = r.always ? "一定會產生" : !r.available ? `不能用：${r.reason}${r.action ? "。怎麼辦：" + r.action : ""}` : "";
      row.append(h("label", { class: "check out-opt" + (r.available ? "" : " unavail"), title: tip }, cb, r.label));
    }
    root.append(row);
  }
  return {
    node: root,
    get: () => [...boxes].filter(([n, cb]) => cb.checked && !rendererByName(n).always).map(([n]) => n),
    set(list) { boxes.forEach((cb, n) => { const r = rendererByName(n); if (!r.always) cb.checked = list.includes(n) && r.available; }); },
  };
}

const sttLabel = x => x.label + (x.privacy === "cloud" ? "（雲端・會上傳音訊）" : "") + (x.available ? "" : `（不能用：${x.reason}）`);
function fillSttSelect(select, current) {
  select.replaceChildren(...state.app.stt_providers.map(x => h("option", {
    value: x.name, disabled: !x.available,
    title: x.available ? (x.cost_hint || "") : `${x.reason}${x.action ? "。怎麼辦：" + x.action : ""}`, text: sttLabel(x) })));
  const ok = state.app.stt_providers.find(x => x.name === current && x.available);
  select.value = ok ? current : "local";
}
function sttHintText(name) {
  const x = state.app.stt_providers.find(s => s.name === name);
  if (!x) return "";
  if (x.privacy !== "cloud") return "在這台電腦上辨識，音訊不會離開電腦。";
  const back = state.app.settings.stt_fallback_local ? "失敗時會退回本機辨識。" : "失敗時不會自動退回本機。";
  return `⚠ 音訊會上傳到雲端服務辨識。${back}`;
}

// 模式欄位（對話框用）：常用組合、整理方式、加料、關注重點、輸出形式
function modeFields({ outputs = [], onchange } = {}) {
  const { profiles, modifiers, presets } = state.app;
  const mods = new Set();
  const preset = h("select", {}, h("option", { value: "", text: "（不使用常用組合）" }),
    presets.map(p => h("option", { value: p.id, title: p.description, text: `${p.name}　${p.description}` })));
  const profile = h("select", {}, h("option", { value: "auto", text: "🤖 自動判斷" }),
    profiles.map(p => h("option", { value: p.id, title: p.description, text: `${p.icon} ${p.name}` })));
  const modBox = h("div", { class: "toggles" });
  const renderMods = () => modBox.replaceChildren(...modifiers.map(m => h("button", {
    type: "button", class: "toggle" + (mods.has(m.id) ? " on" : ""), title: m.description, text: `${m.icon} ${m.name}`,
    onclick: () => { mods.has(m.id) ? mods.delete(m.id) : mods.add(m.id); renderMods(); onchange?.(); } })));
  const focus = h("input", { placeholder: "例如：AI 伺服器、對台積電的看法", oninput: () => onchange?.() });
  const picker = outputPicker({ checked: outputs, skipAlways: true });
  preset.onchange = () => {
    const p = presets.find(x => x.id === preset.value);
    if (p) {
      profile.value = profiles.some(x => x.id === p.profile) ? p.profile : "auto";
      mods.clear(); p.modifiers.forEach(m => mods.add(m));
      focus.value = p.focus || "";
      if (p.outputs?.length) picker.set(p.outputs);
      renderMods();
    }
    onchange?.();
  };
  profile.onchange = () => onchange?.();
  renderMods();
  const node = h("div", { class: "mode-fields" },
    labelled("模式（常用組合）", preset), labelled("整理方式", profile),
    h("div", { class: "field" }, h("span", { class: "label", text: "加料（可以多選）" }), modBox),
    labelled("特別想知道（選填）", focus),
    h("div", { class: "field" }, h("span", { class: "label", text: "輸出形式（Markdown 筆記一定會產生）" }), picker.node));
  return { node, get: () => ({ profile: profile.value, modifiers: [...mods], focus: focus.value.trim(), preset: preset.value, outputs: picker.get() }) };
}

// ---------------------------------------------------------------- 新增影片表單
function fillForm() {
  const { profiles, modifiers, settings } = state.app;
  $("#profile").replaceChildren(h("option", { value: "auto", text: "🤖 自動判斷" }),
    ...profiles.map(p => h("option", { value: p.id, title: p.description, text: `${p.icon} ${p.name}` })));
  $("#profile").value = profiles.some(p => p.id === settings.profile) ? settings.profile : "auto";
  state.modifiers = new Set(settings.modifiers || []);
  $("#modifiers").replaceChildren(...modifiers.map(m => h("button", {
    type: "button", class: "toggle", dataset: { mod: m.id }, title: m.description, text: `${m.icon} ${m.name}` })));
  renderToggles();
  renderPresets();
  state.outPicker = outputPicker({ checked: settings.outputs || [] });
  $("#outputs").replaceChildren(state.outPicker.node);
  fillSttSelect($("#stt"), settings.stt_provider);
  $("#stt-hint").textContent = sttHintText($("#stt").value);
  $("#opt-keep-video").checked = !!settings.keep_video;
  $("#advanced").open = false;
}

function renderToggles() {
  $$("#modifiers .toggle").forEach(b => b.classList.toggle("on", state.modifiers.has(b.dataset.mod)));
}

function renderPresets() {
  const card = (id, name, desc) => h("button", {
    type: "button", class: "preset-card" + (state.preset === id ? " on" : ""), title: desc, onclick: () => choosePreset(id) },
    h("strong", { text: name }), h("span", { class: "muted small", text: desc }));
  $("#presets").replaceChildren(card("", "自己選", "不套用常用組合，自己決定整理方式與輸出"),
    ...state.app.presets.map(p => card(p.id, p.name, p.description)));
}

function choosePreset(id) {
  state.preset = id;
  const p = state.app.presets.find(x => x.id === id);
  if (p) {
    $("#profile").value = state.app.profiles.some(x => x.id === p.profile) ? p.profile : "auto";
    state.modifiers = new Set(p.modifiers);
    $("#focus").value = p.focus || "";
    if (p.outputs?.length) state.outPicker.set(p.outputs);     // 常用組合建議的輸出自動勾上
    toast(`已套用「${p.name}」`);
  } else {
    $("#advanced").open = true;
  }
  renderPresets();
  renderToggles();
}

function fillRefine() {
  const modes = state.app.text_modes;
  $("#r-mode").replaceChildren(...Object.keys(modes).map(m => h("option", { text: m })));
  const fillSubs = () => $("#r-sub").replaceChildren(...modes[$("#r-mode").value].map(s => h("option", { text: s })));
  $("#r-mode").onchange = fillSubs;
  $("#r-mode").value = Object.keys(modes).find(m => m.includes("摘要")) || Object.keys(modes)[0];
  fillSubs();
}

// ---------------------------------------------------------------- 送出工作
async function start(urlsOverride) {
  const urls = (urlsOverride || $("#urls").value.split("\n")).map(s => s.trim()).filter(Boolean);
  if (!urls.length) { toast("請先貼上影片網址"); return; }
  $("#btn-start").disabled = true;
  try {
    const checks = await post("/api/check", { urls });
    const existing = checks.filter(c => c.status);
    let redo = {};
    let sendUrls = urls;
    if (existing.length) {
      const answer = await askRedo(existing);
      if (answer === null) return;
      redo = answer.redo;
      if (answer.renderOnly.length) {
        const made = await renderOnly(answer.renderOnly, answer.outputs);
        sendUrls = urls.filter(u => !answer.renderOnly.some(r => r.url === u));
        if (made && !sendUrls.length) { if (!urlsOverride) $("#urls").value = ""; return; }
      }
    }
    const jobs = await post("/api/jobs", {
      urls: sendUrls,
      profile: $("#profile").value,
      modifiers: [...state.modifiers],
      focus: $("#focus").value.trim(),
      preset: state.preset,
      notes: !$("#opt-transcript-only").checked,
      keep_video: $("#opt-keep-video").checked,
      outputs: state.outPicker.get(),
      stt_provider: $("#stt").value,
      redo,
    });
    if (!urlsOverride) $("#urls").value = "";
    toast(`已加入 ${jobs.length} 支影片`);
    switchTab("jobs");
    if (jobs.length) select({ type: "job", id: jobs[0].id });
    pollJobs();
  } catch (err) {
    toast(`無法開始：${err.message}`);
  } finally {
    $("#btn-start").disabled = false;
  }
}

// 處理過的網址：直接用現有分析補產生其他輸出（不花 token）
async function renderOnly(list, outputs) {
  if (!outputs.length) { toast("沒有選輸出格式，「直接產生其他輸出」的影片先略過"); return false; }
  let made = 0;
  const problems = [];
  for (const r of list) {
    try {
      const res = await post("/api/render", { folder: r.folder, slug: r.slug, outputs });
      made += Object.keys(res.outputs).length;
      for (const [k, v] of Object.entries(res.errors)) problems.push(`${rendererLabel(k)}：${v}`);
    } catch (e) { problems.push(e.message); }
  }
  toast(problems.length ? `產生了 ${made} 個輸出，有問題：${problems.join("；")}` : `已產生 ${made} 個輸出（沒有花 token），到筆記庫就看得到`);
  loadLibrary();
  return made > 0;
}

function askRedo(items) {
  return new Promise(resolve => {
    const picker = outputPicker({ skipAlways: true, checked: state.outPicker.get() });
    $("#redo-outputs-box").replaceChildren(picker.node);
    const outBox = $("#redo-outputs");
    outBox.hidden = true;
    const rows = items.map(it => {
      const s = it.status;
      const analyses = it.analyses || [];
      const checks = [];
      const mk = (value, text) => h("label", { class: "check" }, h("input", { type: "checkbox", value, class: "redo-stage" }), text);
      if (s.media) checks.push(mk("download", "重新下載"));
      if (s.transcript) checks.push(mk("transcribe", "重新轉錄"));
      if (s.notes.length || analyses.length) checks.push(mk("notes", "重新分析（同方案會覆蓋）"));
      let reuse = null, reuseSel = null, reuseBox = null;
      if (analyses.length) {
        reuseBox = h("input", { type: "checkbox", class: "render-only" });
        reuseSel = h("select", { hidden: analyses.length < 2 },
          analyses.map(a => h("option", { value: a, text: slugLabel(a) })));
        reuseBox.onchange = () => {
          $$(".redo-stage", row).forEach(c => { c.disabled = reuseBox.checked; if (reuseBox.checked) c.checked = false; });
          outBox.hidden = !$$(".render-only", $("#redo-rows")).some(c => c.checked);
        };
        reuse = h("div", { class: "reuse-row" },
          h("label", { class: "check" }, reuseBox, "直接用現有分析產生其他輸出（不花 token）"), reuseSel);
      }
      const row = h("div", { class: "redo-row", dataset: { url: it.url, folder: it.folder } },
        h("div", { class: "t", text: it.title || it.url }),
        h("div", { class: "muted small", text: `已有：影音 ${s.media ? "✓" : "✗"}　逐字稿 ${s.transcript ? "✓" : "✗"}　筆記 ${s.notes.length ? s.notes.map(slugLabel).join("、") : "無"}` }),
        analyses.length ? h("div", { class: "muted small", text: `已有分析：${analyses.map(slugLabel).join("、")}` }) : null,
        h("div", { class: "opts" }, checks), reuse);
      row._reuse = { box: reuseBox, sel: reuseSel };
      return row;
    });
    $("#redo-rows").replaceChildren(...rows);
    const dlg = $("#dlg-redo");
    dlg.returnValue = "";
    dlg.onclose = () => {
      if (dlg.returnValue !== "ok") { resolve(null); return; }
      const redo = {}, renderOnlyList = [];
      rows.forEach(row => {
        if (row._reuse.box?.checked) {
          renderOnlyList.push({ url: row.dataset.url, folder: row.dataset.folder, slug: row._reuse.sel.value });
          return;
        }
        const stages = $$(".redo-stage:checked", row).map(i => i.value);
        if (stages.length) redo[row.dataset.url] = stages;
      });
      resolve({ redo, renderOnly: renderOnlyList, outputs: picker.get() });
    };
    dlg.showModal();
  });
}

// ---------------------------------------------------------------- 工作清單
async function pollJobs() {
  let jobs;
  try { jobs = await api("/api/jobs"); } catch { return; }
  const sig = JSON.stringify(jobs);
  const finishedNow = state.jobs.some(old => ["running", "queued"].includes(old.status) && jobs.find(j => j.id === old.id && !["running", "queued"].includes(j.status)));
  state.jobs = jobs;
  if (sig !== state.jobsSig) { state.jobsSig = sig; renderJobs(); }
  if (finishedNow) await loadLibrary();
  if (state.selected?.type === "job") refreshSelectedJob();
}

function jobError(j) {
  if (j.error_info) return errText(j.error_info);
  return j.error || "";
}

function jobRow(j) {
  const live = j.status === "running";
  const sel = state.selected?.type === "job" && state.selected.id === j.id ? " selected" : "";
  const stages = (j.type === "video" ? STAGES_VIDEO : STAGES_TASK).map(([k, name]) =>
    h("span", { class: `stage ${j.stages[k] || ""}`, title: STAGE_TITLE[j.stages[k]] || "尚未開始", text: name }));
  let badge = null;
  if (j.type !== "video") badge = h("span", { class: "badge", text: TYPE_TEXT[j.type] });
  else if (j.kind) badge = h("span", { class: "badge", text: j.kind === "short" ? "短影音" : "影片" });
  let detail = live ? j.detail : "";
  if (live && j.streamed_chars > 0 && ["running", "waiting"].includes(j.stages.notes)) {
    detail = `AI 分析中…（已收到 ${j.streamed_chars} 字）`;     // 串流的是 JSON 原文，人看不懂，只報字數
  }
  const outErrors = Object.entries(j.output_errors || {}).map(([k, v]) => `${rendererLabel(k)}：${v}`);
  return h("div", { class: `job status-${j.status}${sel}`, dataset: { id: j.id } },
    h("div", { class: "top" }, h("span", { class: "title", text: j.title || j.url }), badge,
      h("span", { class: "badge", text: STATUS_TEXT[j.status] })),
    h("div", { class: "stages" }, stages),
    live ? h("div", { class: "bar" }, h("div", { style: `width:${Math.round((j.progress || 0) * 100)}%` })) : null,
    detail ? h("div", { class: "detail", text: detail }) : null,
    jobError(j) ? h("div", { class: "error", text: jobError(j) }) : null,
    outErrors.length ? h("div", { class: "error", text: `這些輸出沒做成：${outErrors.join("；")}` }) : null,
    h("div", { class: "row-actions" },
      live || j.status === "queued" ? h("button", { dataset: { act: "cancel" }, text: "取消" }) : h("button", { dataset: { act: "remove" }, text: "移出清單" }),
      j.folder ? h("button", { dataset: { act: "open" }, text: "資料夾" }) : null));
}

function renderJobs() {
  const box = $("#jobs");
  const active = state.jobs.filter(j => j.status === "queued" || j.status === "running").length;
  $("#job-count").textContent = active ? `(${active})` : "";
  if (!state.jobs.length) {
    box.replaceChildren(h("div", { class: "empty-list", text: "還沒有工作。貼上網址按「開始處理」。" }));
    return;
  }
  box.replaceChildren(...state.jobs.map(jobRow));
}

async function onJobClick(ev) {
  const card = ev.target.closest(".job");
  if (!card) return;
  const id = card.dataset.id;
  const act = ev.target.closest("[data-act]")?.dataset.act;
  const job = state.jobs.find(j => j.id === id);
  try {
    if (act === "cancel") { await post(`/api/jobs/${id}/cancel`, {}); toast("已取消（已產生的檔案會保留）"); return pollJobs(); }
    if (act === "remove") {
      await api(`/api/jobs/${id}`, { method: "DELETE" });
      if (state.selected?.id === id) clearViewer();
      return pollJobs();
    }
    if (act === "open" && job?.folder) { await post("/api/open", { path: job.folder }); return; }
  } catch (e) { toast(e.message); return; }
  select({ type: "job", id });
}

// ---------------------------------------------------------------- 筆記庫
const allEntries = () => [...state.library.videos, ...state.library.collections];
const entryByFolder = folder => allEntries().find(x => x.folder === folder);

async function loadLibrary() {
  try {
    const lib = await api("/api/library");
    state.library = { videos: lib.videos || [], collections: lib.collections || [] };
  } catch { return; }
  const known = new Set(allEntries().map(x => x.folder));
  state.checked.forEach(f => { if (!known.has(f)) state.checked.delete(f); });
  renderLibrary();
  if (state.current) renderOutputsBar();
}

function emptyNote(text) { return h("div", { class: "empty-list", text }); }

function libRow(it) {
  const sel = state.selected?.type === "lib" && state.selected.folder === it.folder ? " selected" : "";
  const cb = h("input", { type: "checkbox", class: "pick", checked: state.checked.has(it.folder), title: "勾選（可以多選）",
    onclick: e => e.stopPropagation(),
    onchange: e => { e.target.checked ? state.checked.add(it.folder) : state.checked.delete(it.folder); renderLibActions(); } });
  const kind = it.type === "collection" ? `合併 ${it.members?.length || ""}`.trim() + (it.members?.length ? " 支" : "")
    : it.kind === "short" ? "短影音" : "影片";
  const analyses = it.analyses.length
    ? h("div", { class: "detail wrap" }, h("span", { class: "muted", text: "已有分析：" }),
      it.analyses.map(a => h("span", { class: "badge", title: a.summary || "", text: slugLabel(a.slug) })))
    : h("div", { class: "detail" }, h("span", { class: "badge", text: it.notes.length ? "只有 Markdown 筆記（舊版）" : "只有逐字稿" }));
  const outs = it.outputs.length
    ? h("div", { class: "detail wrap" }, h("span", { class: "muted", text: "輸出：" }),
      it.outputs.map(f => { const info = outputInfo(f); return h("button", {
        type: "button", class: "badge link", title: info.slug ? `${slugLabel(info.slug)}（點一下開啟）` : "點一下開啟", text: info.label,
        onclick: e => { e.stopPropagation(); openOutput(it.folder, f); } }); }))
    : null;
  return h("div", { class: `job lib-row${sel}`, dataset: { folder: it.folder } },
    h("div", { class: "top" }, cb, h("span", { class: "title", text: it.title }), h("span", { class: "badge", text: kind })),
    analyses, outs, h("div", { class: "detail muted", text: fmtTime(it.updated) }));
}

function renderLibrary() {
  const { videos, collections } = state.library;
  $("#lib-videos").replaceChildren(...(videos.length ? videos.map(libRow)
    : [emptyNote(`輸出資料夾裡還沒有處理過的影片。${state.app.output_root}`)]));
  $("#lib-collections").replaceChildren(...(collections.length ? collections.map(libRow)
    : [emptyNote("還沒有合併過。勾選兩支以上的影片，按「合併成一份」。")]));
  renderLibActions();
}

function renderLibActions() {
  const bar = $("#lib-actions");
  const sel = [...state.checked].map(entryByFolder).filter(Boolean);
  bar.hidden = !sel.length;
  if (!sel.length) return;
  const videos = sel.filter(x => x.type === "video");
  const cols = sel.filter(x => x.type === "collection");
  bar.replaceChildren(
    h("span", { class: "muted small", text: `已勾選 ${sel.length} 項` }),
    h("button", { type: "button", title: "用已經分析好的結果產生其他格式，不花 token", onclick: () => openRenderDialog(sel), text: "🧩 產生其他輸出" }),
    videos.length ? h("button", { type: "button", title: "沿用逐字稿，用新的模式重新分析（會花 token）", onclick: () => openReanalyzeDialog(videos), text: "🔁 重新分析" }) : null,
    h("button", { type: "button", disabled: videos.length < 2, title: videos.length < 2 ? "要勾選至少兩支影片" : "把這幾支影片整理成一份",
      onclick: () => openCombineDialog(videos), text: "🗂 合併成一份" }),
    sel.length === 1 && cols.length === 1 ? h("button", { type: "button", onclick: () => openRecombineDialog(cols[0]), text: "🔀 換模式再合併" }) : null,
    h("button", { type: "button", class: "ghost", onclick: () => { state.checked.clear(); renderLibrary(); }, text: "取消勾選" }));
}

function onLibraryClick(ev) {
  const card = ev.target.closest(".lib-row");
  if (card) select({ type: "lib", folder: card.dataset.folder });
}

// ---------------------------------------------------------------- 對話框（產生輸出／重新分析／合併）
function openAct({ title, body, okText = "確定", onOk }) {
  const dlg = $("#dlg-act");
  const ok = $("#act-ok"), msg = $("#act-msg");
  $("#act-title").textContent = title;
  $("#act-body").replaceChildren(body);
  const handle = {
    setOkText: t => { ok.textContent = t; },
    setMsg: (t, kind = "bad") => { msg.hidden = !t; msg.textContent = t; msg.className = `act-msg ${kind}`; },
  };
  handle.setOkText(okText);
  handle.setMsg("");
  ok.disabled = false;
  $("#act-form").onsubmit = async ev => {
    ev.preventDefault();
    ok.disabled = true;
    try { if ((await onOk(handle)) !== false) dlg.close(); }
    catch (e) { handle.setMsg(e.message); }
    finally { ok.disabled = false; }
  };
  $("#act-cancel").onclick = () => dlg.close();
  dlg.showModal();
  return handle;
}

function openRenderDialog(items, preferSlug = "") {
  const usable = items.filter(i => i.analyses.length);
  if (!usable.length) { toast("選的項目還沒有分析結果，請先「重新分析」"); return; }
  const picker = outputPicker({ skipAlways: true, checked: state.app.settings.outputs || [] });
  const rows = usable.map(it => {
    const sel = h("select", { hidden: it.analyses.length < 2 }, it.analyses.map(a => h("option", { value: a.slug, text: slugLabel(a.slug) })));
    sel.value = it.analyses.some(a => a.slug === preferSlug) ? preferSlug : it.analyses[it.analyses.length - 1].slug;
    return { it, sel, node: h("div", { class: "act-row" }, h("div", { class: "t", text: it.title }),
      it.analyses.length < 2 ? h("div", { class: "muted small", text: `分析：${slugLabel(it.analyses[0].slug)}` }) : sel) };
  });
  const body = h("div", {},
    h("p", { class: "muted small", text: "用已經分析好的結果直接產生，不會呼叫 AI，也不花 token。" }),
    rows.map(r => r.node),
    h("div", { class: "field" }, h("span", { class: "label", text: "要產生哪些輸出" }), picker.node));
  openAct({ title: "產生其他輸出", body, okText: "產生", onOk: async handle => {
    const outputs = picker.get();
    if (!outputs.length) { handle.setMsg("請至少選一種輸出格式"); return false; }
    let made = 0;
    const problems = [];
    for (const r of rows) {
      try {
        const res = await post("/api/render", { folder: r.it.folder, slug: r.sel.value, outputs });
        made += Object.keys(res.outputs).length;
        for (const [k, v] of Object.entries(res.errors)) problems.push(`${r.it.title} 的${rendererLabel(k)}：${v}`);
      } catch (e) { problems.push(`${r.it.title}：${e.message}`); }
    }
    await loadLibrary();
    if (problems.length && !made) { handle.setMsg(problems.join("\n")); return false; }
    toast(problems.length ? `產生了 ${made} 個輸出；有 ${problems.length} 個沒成功：${problems.join("；")}` : `已產生 ${made} 個輸出（沒有花 token）`);
    return true;
  } });
}

function openReanalyzeDialog(items) {
  const usable = items.filter(i => i.transcript);
  const skipped = items.length - usable.length;
  if (!usable.length) { toast("這些項目沒有逐字稿，沒辦法重新分析；請重新丟網址完整處理一次"); return; }
  const fields = modeFields({ outputs: state.app.settings.outputs || [] });
  const body = h("div", {},
    h("p", { class: "muted small", text: `沿用逐字稿，用新的模式重新分析 ${usable.length} 支影片（不重新下載、不重新辨識）。這會呼叫 AI，要花 token；每支各開一個工作。` }),
    skipped ? h("p", { class: "small", text: `有 ${skipped} 項沒有逐字稿，會略過。` }) : null,
    fields.node);
  openAct({ title: "換模式重新分析", body, okText: "開始重新分析", onOk: async handle => {
    const mode = fields.get();
    const problems = [];
    let first = null;
    for (const it of usable) {
      try {
        const job = await post("/api/reanalyze", { folder: it.folder, ...mode });
        first = first || job;
      } catch (e) { problems.push(`${it.title}：${e.message}`); }
    }
    if (problems.length && !first) { handle.setMsg(problems.join("\n")); return false; }
    if (problems.length) toast(`有 ${problems.length} 支沒能開始：${problems.join("；")}`);
    switchTab("jobs");
    pollJobs();
    if (first) select({ type: "job", id: first.id });
    return true;
  } });
}

function openRecombineDialog(col) {
  const fields = modeFields({ outputs: state.app.settings.outputs || [] });
  const body = h("div", {},
    h("p", { class: "muted small", text: `用原本的 ${col.members?.length || ""} 支影片，換一個模式再合併一次（會呼叫 AI）。` }), fields.node);
  openAct({ title: "換模式再合併", body, okText: "開始合併", onOk: async () => {
    const job = await post("/api/recombine", { folder: col.folder, ...fields.get() });
    switchTab("jobs");
    pollJobs();
    select({ type: "job", id: job.id });
    return true;
  } });
}

function openCombineDialog(items) {
  const title = h("input", { placeholder: "合併後的標題（選填）" });
  const box = h("div", { class: "estimate", text: "計算中…" });
  let lastEstimate = null, timer = 0, seq = 0;
  const folders = items.map(i => i.folder);
  let handle;
  const refresh = async () => {
    const mine = ++seq;
    box.className = "estimate";
    box.textContent = "計算中…";
    try {
      const est = await post("/api/combine/estimate", { folders, ...fields.get() });
      if (mine !== seq) return;
      lastEstimate = est;
      box.replaceChildren(h("div", { text: `${est.text}。` }),
        est.missing?.length ? h("div", { class: "small bad", text: `有 ${est.missing.length} 支讀不到分析結果，會略過：${est.missing.join("、")}` }) : null,
        est.needs_confirm ? h("div", { class: "small warn", text: "內容比較多，要花不少 token，開始前會再請你確認一次。" }) : null);
      handle?.setOkText(est.needs_confirm ? "確認並開始合併" : "開始合併");
    } catch (e) {
      if (mine !== seq) return;
      lastEstimate = null;
      box.textContent = `現在算不出預估：${e.message}`;
    }
  };
  const fields = modeFields({ outputs: state.app.settings.outputs || [], onchange: () => { clearTimeout(timer); timer = setTimeout(refresh, 400); } });
  const body = h("div", {},
    h("p", { class: "muted small", text: `把 ${items.length} 支影片已經分析好的結果整理成一份（不會重新讀逐字稿，比較省）。每支影片原本的筆記都會保留。` }),
    items.map(i => h("div", { class: "small", text: `・${i.title}` })),
    labelled("合併後的標題", title), fields.node,
    h("div", { class: "field" }, h("span", { class: "label", text: "預估" }), box));
  handle = openAct({ title: "合併成一份", body, okText: "開始合併", onOk: async hd => {
    try {
      const job = await post("/api/combine", { folders, title: title.value.trim(), ...fields.get(),
        confirmed: !!lastEstimate?.needs_confirm });     // 預估已經顯示在畫面上，按下去就是確認
      state.checked.clear();
      switchTab("jobs");
      pollJobs();
      select({ type: "job", id: job.id });
      return true;
    } catch (e) {
      if (e.status === 409 && e.info?.code === "needs_confirm") {
        lastEstimate = e.estimate;
        hd.setOkText("確認並開始合併");
        hd.setMsg(`${e.estimate?.text || "內容比較多"}。確定的話再按一次。`, "warn");
        return false;
      }
      throw e;
    }
  } });
  refresh();
}

// ---------------------------------------------------------------- 開啟輸出
async function openOutput(folder, name) {
  const url = `/api/output?folder=${enc(folder)}&name=${enc(name)}`;
  const ext = name.split(".").pop().toLowerCase();
  if (ext === "html" || ext === "htm") { window.open(url, "_blank", "noopener"); return; }
  if (["md", "mmd", "txt"].includes(ext)) {            // 文字類：顯示在右側，可以複製
    try {
      const text = await api(url);
      const info = outputInfo(name);
      const base = state.current?.folder === folder ? state.current : { title: entryByFolder(folder)?.title || name, folder, url: "" };
      state.selected = { type: "lib", folder };         // 停止被工作輪詢蓋掉
      state.view = ext === "md" ? "rendered" : "markdown";
      showCurrent({ ...base, meta: `輸出：${info.label}`, text, live: false, notes: base.notes || [], slug: "", shownOutput: name });
    } catch (e) { toast(e.message); }
    return;
  }
  const a = h("a", { href: url, download: name });      // 其他格式（XMind、OPML、FreeMind）：下載
  document.body.append(a);
  a.click();
  a.remove();
  toast("已開始下載，可以用 XMind 等軟體開啟");
}

function renderOutputsBar() {
  const cur = state.current;
  const bar = $("#v-outputs");
  const entry = cur && entryByFolder(cur.folder);
  const files = entry ? entry.outputs : [];
  bar.hidden = !files.length;
  bar.replaceChildren(h("span", { class: "muted small", text: "其他輸出：" }),
    ...files.map(f => { const info = outputInfo(f); return h("button", {
      type: "button", class: "badge link", title: info.slug ? slugLabel(info.slug) : "", text: info.label, onclick: () => openOutput(cur.folder, f) }); }));
}

// ---------------------------------------------------------------- 右側檢視
function select(sel) {
  state.selected = sel;
  $$(".job").forEach(el => el.classList.toggle("selected",
    (sel.type === "job" && el.dataset.id === sel.id) || (sel.type === "lib" && el.dataset.folder === sel.folder)));
  $("#r-out").textContent = "";
  state.curSig = "";
  if (sel.type === "job") refreshSelectedJob(true);
  else openLibraryItem(sel.folder);
}

function clearViewer() {
  state.selected = null;
  state.current = null;
  $("#viewer-body").hidden = true;
  $("#viewer-empty").hidden = false;
}

async function refreshSelectedJob(first = false) {
  const id = state.selected.id;
  let j;
  try { j = await api(`/api/jobs/${id}`); } catch { return; }
  if (state.selected?.type !== "job" || state.selected.id !== id) return;
  const live = j.status === "running";
  const slug = j.notes_file ? baseName(j.notes_file).replace(/^notes\./, "").replace(/\.md$/, "") : "";
  const entry = j.folder ? entryByFolder(j.folder) : null;
  const notes = entry?.notes?.length ? entry.notes : (slug ? [slug] : []);
  let text = j.notes;
  if (!text) {
    if (live) text = j.streamed_chars > 0 ? `AI 分析中…（已收到 ${j.streamed_chars} 字）` : "（還在處理中，AI 分析完成後筆記會顯示在這裡）";
    else if (jobError(j)) text = `處理失敗：${jobError(j)}`;
    else if (j.status === "cancelled") text = "（已取消）";
    else text = j.type === "video" ? "（這個工作沒有產生筆記：只做了逐字稿）" : "";
  }
  const sig = JSON.stringify([j.title, j.status, text, notes, entry?.outputs]);
  if (!first && sig === state.curSig) return;
  state.curSig = sig;
  showCurrent({ title: j.title || j.url, url: j.type === "video" ? j.url : "", folder: j.folder, meta: metaFor(j), notes, slug, text, live,
    type: j.type === "combine" ? "collection" : "video" });
}

function metaFor(j) {
  const plan = j.plan || {};
  const parts = [STATUS_TEXT[j.status]];
  if (j.type !== "video") parts.push(TYPE_TEXT[j.type]);
  else if (j.kind) parts.push(j.kind === "short" ? "短影音" : "影片");
  if (plan.profile) parts.push(`方案：${plan.profile === "auto" ? "自動判斷" : slugLabel([plan.profile, ...(plan.modifiers || [])].join("+"))}`);
  if (plan.focus) parts.push(`關注：${plan.focus}`);
  return parts.join(" · ");
}

async function openLibraryItem(folder) {
  const it = entryByFolder(folder);
  if (!it) return;
  const slug = it.notes[0] || "";
  let text = "（這裡還沒有筆記，可以按「換模式重新分析」產生）";
  if (slug) {
    try { text = await api(`/api/note?folder=${enc(folder)}&slug=${enc(slug)}`); } catch (e) { text = e.message; }
  }
  const kind = it.type === "collection" ? "合併" : (it.kind === "short" ? "短影音" : "影片");
  showCurrent({ title: it.title, url: it.url, folder, meta: `${kind} · ${fmtTime(it.updated)}`, notes: it.notes, slug, text, live: false, type: it.type });
}

function showCurrent(cur) {
  state.current = cur;
  $("#viewer-empty").hidden = true;
  $("#viewer-body").hidden = false;
  $("#v-title").textContent = cur.title;
  $("#v-meta").textContent = cur.meta;
  const isCol = cur.type === "collection";
  $("#v-redo").textContent = isCol ? "🔀 換模式再合併" : "🔁 換模式重新分析";
  $("#v-redo").title = isCol ? "用原本的影片換一個模式再合併一次（會花 token）" : "沿用逐字稿，換一個模式重新分析（會花 token）";
  $('#view-tabs [data-view="transcript"]').hidden = isCol;
  if (isCol && state.view === "transcript") state.view = "rendered";
  renderNoteSelect();
  renderOutputsBar();
  renderView();
}

function renderNoteSelect() {
  const cur = state.current;
  const sel = $("#v-note-select");
  sel.hidden = !cur.notes || cur.notes.length < 2;
  sel.replaceChildren(...(cur.notes || []).map(n => h("option", { value: n, text: slugLabel(n) })));
  if (cur.slug) sel.value = cur.slug;
}

async function renderView() {
  const cur = state.current;
  const box = $("#v-content");
  $$("#view-tabs button").forEach(b => b.classList.toggle("active", b.dataset.view === state.view));
  const plain = text => { box.className = ""; box.replaceChildren(h("pre", { class: "plain", text })); return box.firstChild; };
  if (state.view === "transcript") {
    plain("讀取中…");
    try {
      const text = await api(`/api/transcript?folder=${enc(cur.folder)}`);
      if (state.current === cur && state.view === "transcript") plain(text);
    } catch (e) { plain(e.message); }
    return;
  }
  if (state.view === "markdown") {
    plain(cur.text).classList.toggle("streaming", !!cur.live);
    return;
  }
  box.className = "markdown" + (cur.live ? " streaming" : "");
  box.innerHTML = renderMarkdown(cur.text || "");      // renderMarkdown 先跳脫全部內容
}

async function onNoteSelect() {
  const cur = state.current;
  const slug = $("#v-note-select").value;
  try {
    cur.text = await api(`/api/note?folder=${enc(cur.folder)}&slug=${enc(slug)}`);
    cur.slug = slug;
    cur.live = false;
    cur.shownOutput = "";
    if (state.selected?.type === "job") state.selected = { type: "lib", folder: cur.folder };  // 停止被輪詢覆蓋
    renderView();
  } catch (e) { toast(e.message); }
}

async function withEntry(fn) {
  const cur = state.current;
  if (!cur?.folder) return;
  let entry = entryByFolder(cur.folder);
  if (!entry) { await loadLibrary(); entry = entryByFolder(cur.folder); }
  if (!entry) { toast("筆記庫裡還找不到這個項目，等處理完再試"); return; }
  fn(entry);
}

async function copyText(text, what) {
  if (!text) { toast("沒有內容可以複製"); return; }
  try {
    await navigator.clipboard.writeText(text);
    toast(`已複製${what}`);
  } catch {
    toast("複製失敗：瀏覽器不允許存取剪貼簿");
  }
}

// ---------------------------------------------------------------- 二次加工（Better Prompt 的模式）
async function runRefine() {
  const text = state.current?.text;
  if (!text || state.current.live) { toast("等筆記完成後再加工"); return; }
  const out = $("#r-out");
  out.textContent = "";
  out.classList.add("streaming");
  $("#r-run").disabled = true;
  try {
    const res = await fetch("/api/refine", {
      method: "POST",
      headers: { "X-Video-Notes": "1", "Content-Type": "application/json" },
      body: JSON.stringify({ text, mode: $("#r-mode").value, submode: $("#r-sub").value }),
    });
    if (!res.ok) {
      let msg = res.statusText;
      try { msg = (await res.json()).detail || msg; } catch { /* 不是 JSON */ }
      out.textContent = `❌ ${msg}`;
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      out.textContent += decoder.decode(value, { stream: true });
    }
  } catch (err) {
    out.textContent += `\n\n❌ ${err.message}`;
  } finally {
    out.classList.remove("streaming");
    $("#r-run").disabled = false;
  }
}

// ---------------------------------------------------------------- 設定
let settingsOutputs = null;

function openSettings() {
  const { settings, output_choices, providers, whisper_models, env } = state.app;
  $$('input[name="output"]').forEach(r => { r.checked = r.value === settings.output; });
  $("#out-downloads").textContent = output_choices.downloads;
  $("#out-data").textContent = output_choices.data;
  $("#s-output-custom").value = settings.output_custom || "";
  $("#s-keep-video").checked = !!settings.keep_video;
  settingsOutputs = outputPicker({ checked: settings.outputs || [], skipAlways: true });
  $("#s-outputs").replaceChildren(settingsOutputs.node);
  $("#s-provider").replaceChildren(...Object.entries(providers).map(([k, v]) => h("option", { value: k, text: v })));
  $("#s-provider").value = settings.provider;
  $("#s-model").value = settings.model || "";
  $("#s-compat").value = settings.compat_base_url || "";
  updateProviderUi();
  fillSttSelect($("#s-stt"), settings.stt_provider);
  $("#s-stt-hint").textContent = sttHintText($("#s-stt").value);
  $("#s-stt-fallback").checked = !!settings.stt_fallback_local;
  $("#s-whisper").replaceChildren(...whisper_models.map(m => h("option", { text: m })));
  $("#s-whisper").value = settings.whisper_model;
  $("#s-device").value = settings.whisper_device;
  $("#s-language").value = settings.language;
  $("#s-traditional").checked = !!settings.traditional;
  $("#s-combine-tokens").value = settings.combine_confirm_tokens;
  $("#s-parallel").value = settings.parallel_jobs;
  $("#s-dl-parallel").value = settings.max_parallel_downloads;
  const gap = settings.sleep_between_videos || [5, 10];
  $("#s-sleep-min").value = gap[0];
  $("#s-sleep-max").value = gap[gap.length - 1];
  $("#s-long").value = settings.long_transcript_chars;
  $("#s-cookies").value = settings.cookies_from_browser || "";
  $("#s-notify").value = settings.notify_url || "";
  $("#s-prompts-dir").textContent = env.user_prompts;
  $("#s-key").value = "";
  const dlg = $("#dlg-settings");
  dlg.returnValue = "";
  dlg.onclose = () => { if (dlg.returnValue === "ok") saveSettings(); };
  dlg.showModal();
}

function updateProviderUi() {
  const p = $("#s-provider").value;
  const hints = { "claude-sub": ["sonnet", "haiku", "opus"],
    openai: ["gpt-5.1", "gpt-4.1", "gpt-4.1-mini"], gemini: ["gemini-2.5-flash", "gemini-2.5-pro"],
    anthropic: ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"] }[p] || [];
  $("#model-hints").replaceChildren(...hints.map(x => h("option", { value: x })));
  $("#s-model").placeholder = p === COMPAT ? "模型名稱，例如 llama3.1" : `空白 = ${state.app.default_models[p]}`;
  $("#s-compat-row").hidden = p !== COMPAT;                // 只有選相容端點才需要填網址
  updateKeyStatus();
}

function updateKeyStatus() {
  const p = $("#s-provider").value;
  const { env, providers } = state.app;
  const keyless = env.keyless.includes(p);
  $(".key-row").style.display = keyless ? "none" : "";   // Claude 訂閱／相容端點沒有金鑰可貼
  if (p === COMPAT) {
    $("#s-key-status").textContent = "如果這個服務需要金鑰，寫在專案 .env 的 OPENAI_COMPAT_API_KEY（本機的 Ollama 不用）。";
    return;
  }
  if (keyless) {
    $("#s-key-status").textContent = env.keys[p]
      ? "✓ 用電腦上 Claude Code 登入的帳號，不需要金鑰（會用掉訂閱額度）"
      : `找不到 Claude Code（${env.claude_code}）：先安裝，再開終端機執行一次 claude 登入`;
    return;
  }
  $("#s-key-status").textContent = env.keys[p] ? `✓ 已經有 ${providers[p]} 的金鑰（貼上新的會取代）` : `尚未設定 ${providers[p]} 的金鑰`;
}

async function saveKey() {
  const key = $("#s-key").value.trim();
  if (!key) { toast("請先貼上金鑰"); return; }
  try {
    const res = await post("/api/keys", { provider: $("#s-provider").value, key });
    state.app.env = res.env;
    $("#s-key").value = "";
    updateKeyStatus();
    renderEnv();
    toast("金鑰已存到共用金鑰檔（其他工具也會用到）");
  } catch (e) { toast(e.message); }
}

async function saveSettings() {
  const num = (sel, fallback) => { const v = parseFloat($(sel).value); return Number.isFinite(v) ? v : fallback; };
  const data = {
    output: $('input[name="output"]:checked')?.value || "downloads",
    output_custom: $("#s-output-custom").value.trim(),
    keep_video: $("#s-keep-video").checked,
    outputs: settingsOutputs.get(),
    provider: $("#s-provider").value,
    model: $("#s-model").value.trim(),
    compat_base_url: $("#s-compat").value.trim(),
    stt_provider: $("#s-stt").value,
    stt_fallback_local: $("#s-stt-fallback").checked,
    whisper_model: $("#s-whisper").value,
    whisper_device: $("#s-device").value,
    language: $("#s-language").value.trim() || "auto",
    traditional: $("#s-traditional").checked,
    combine_confirm_tokens: Math.max(1000, Math.round(num("#s-combine-tokens", 60000))),
    parallel_jobs: Math.max(1, Math.round(num("#s-parallel", 3))),
    max_parallel_downloads: Math.max(1, Math.round(num("#s-dl-parallel", 2))),
    sleep_between_videos: [Math.max(0, num("#s-sleep-min", 5)), Math.max(0, num("#s-sleep-max", 10))],
    long_transcript_chars: Math.max(5000, Math.round(num("#s-long", 60000))),
    cookies_from_browser: $("#s-cookies").value,
    notify_url: $("#s-notify").value.trim(),
  };
  if (data.output === "custom" && !data.output_custom) { toast("選了「自選」就要填資料夾路徑"); return; }
  if (data.provider === COMPAT && !data.compat_base_url) { toast("選了相容端點，就要填端點網址"); return; }
  const old = state.app.settings;
  const restart = data.parallel_jobs !== old.parallel_jobs || data.max_parallel_downloads !== old.max_parallel_downloads;
  try {
    const fresh = await api("/api/settings", { method: "PUT", body: JSON.stringify(data) });
    state.app = fresh;
    renderEnv();
    renderAlerts();
    fillSttSelect($("#stt"), fresh.settings.stt_provider);
    $("#stt-hint").textContent = sttHintText($("#stt").value);
    loadLibrary();
    toast(restart ? "已儲存（同時處理／下載的數量重新開啟後生效）" : "已儲存");
  } catch (e) { toast(`儲存失敗：${e.message}`); }
}

// ---------------------------------------------------------------- 事件
function switchTab(tab) {
  $$("#left-tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  $("#jobs").hidden = tab !== "jobs";
  $("#library").hidden = tab !== "library";
  if (tab === "library") loadLibrary();
}

function bindEvents() {
  $("#btn-start").onclick = () => start();
  $("#urls").addEventListener("keydown", e => { if (e.key === "Enter" && e.ctrlKey) start(); });
  $("#modifiers").onclick = e => {
    const b = e.target.closest(".toggle");
    if (!b) return;
    state.modifiers.has(b.dataset.mod) ? state.modifiers.delete(b.dataset.mod) : state.modifiers.add(b.dataset.mod);
    renderToggles();
  };
  $("#stt").onchange = () => { $("#stt-hint").textContent = sttHintText($("#stt").value); };
  $("#left-tabs").onclick = e => { const b = e.target.closest("button"); if (b) switchTab(b.dataset.tab); };
  $("#jobs").onclick = onJobClick;
  $("#library").onclick = onLibraryClick;
  $("#view-tabs").onclick = e => { const b = e.target.closest("button"); if (b) { state.view = b.dataset.view; renderView(); } };
  $("#v-note-select").onchange = onNoteSelect;
  $("#v-copy").onclick = () => copyText(state.current?.live ? "" : state.current?.text, " Markdown，可以直接貼進 Notion");
  $("#v-open").onclick = () => state.current?.folder && post("/api/open", { path: state.current.folder }).catch(e => toast(e.message));
  $("#v-render").onclick = () => withEntry(entry => openRenderDialog([entry], state.current.slug));
  $("#v-redo").onclick = () => withEntry(entry => entry.type === "collection" ? openRecombineDialog(entry) : openReanalyzeDialog([entry]));
  $("#r-run").onclick = runRefine;
  $("#r-copy").onclick = () => copyText($("#r-out").textContent, "加工結果");
  $("#btn-settings").onclick = openSettings;
  $("#s-provider").onchange = updateProviderUi;
  $("#s-stt").onchange = () => { $("#s-stt-hint").textContent = sttHintText($("#s-stt").value); };
  $("#s-key-save").onclick = saveKey;
}

init().catch(err => {
  document.body.replaceChildren(h("div", { class: "empty" }, `無法連到 Video Notes 伺服器：${err.message}`, h("br"), "請確認程式還開著，然後重新整理。"));
});
