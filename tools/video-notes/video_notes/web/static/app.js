// Video Notes 前端。
// 左邊：表單 → /api/check（處理過的先問要不要重做）→ /api/jobs；每秒輪詢 /api/jobs 更新清單。
// 右邊：檢視筆記（渲染後 / Markdown 原文 / 逐字稿）、複製到 Notion、用 Better Prompt 的模式二次加工。

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const STAGES = [["info", "資訊"], ["download", "下載"], ["audio", "音訊"], ["transcribe", "轉錄"], ["notes", "筆記"]];
const STAGE_TITLE = { running: "進行中", waiting: "排隊中", done: "完成", reused: "沿用既有檔案", failed: "失敗" };
const STATUS_TEXT = { queued: "排隊中", running: "處理中", done: "完成", failed: "失敗", cancelled: "已取消" };

const state = {
  app: null,          // /api/state
  jobs: [],
  jobsSig: "",
  library: [],
  modifiers: new Set(),
  selected: null,     // {type: "job", id} | {type: "lib", folder}
  view: "rendered",
  current: null,      // 右側正在看的東西 {title, meta, url, folder, notes[], slug, text, live}
};

// ---------------------------------------------------------------- helpers
async function api(path, options = {}) {
  // 自訂 header：伺服器只接受帶這個 header 的寫入請求（擋別的網站跨站呼叫本機 API）
  const headers = { "X-Video-Notes": "1" };
  if (options.body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch { /* 不是 JSON */ }
    throw new Error(msg);
  }
  return (res.headers.get("content-type") || "").includes("json") ? res.json() : res.text();
}
const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data) });

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

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
  fillForm();
  fillRefine();
  bindEvents();
  await pollJobs();
  setInterval(pollJobs, 1000);
  loadLibrary();
}

function renderEnv() {
  const { env, settings, providers } = state.app;
  const chips = [];
  chips.push(`<span class="chip ${env.gpu ? "ok" : ""}" title="${esc(env.gpu_text)}">${env.gpu ? "GPU" : "CPU"} 語音辨識</span>`);
  chips.push(`<span class="chip ${env.ffmpeg ? "ok" : "bad"}" title="${esc(env.ffmpeg || "找不到 ffmpeg")}">ffmpeg ${env.ffmpeg ? "✓" : "✗"}</span>`);
  chips.push(`<span class="chip ${env.js_runtimes.length ? "ok" : "bad"}" title="yt-dlp ${esc(env.yt_dlp)}">YouTube JS ${env.js_runtimes.length ? "✓ " + env.js_runtimes[0] : "✗"}</span>`);
  const ready = env.keys[settings.provider];   // 有金鑰；Claude 訂閱則是找得到 Claude Code
  const keyless = env.keyless.includes(settings.provider);
  const model = settings.model || state.app.default_models[settings.provider];
  const missing = keyless ? "（找不到 Claude Code）" : "（未設定金鑰）";
  chips.push(`<span class="chip ${ready ? "ok" : "bad"}" title="${esc(keyless ? env.claude_code : "")}">AI：${esc(providers[settings.provider])} ${esc(model)} ${ready ? "✓" : missing}</span>`);
  $("#env-chips").innerHTML = chips.join("");
  $("#out-hint").textContent = `輸出到：${state.app.output_root}`;
}

function fillForm() {
  const { profiles, modifiers, presets, settings } = state.app;
  $("#profile").innerHTML = `<option value="auto">🤖 自動判斷</option>`
    + profiles.map(p => `<option value="${esc(p.id)}" title="${esc(p.description)}">${esc(p.icon)} ${esc(p.name)}</option>`).join("");
  $("#profile").value = settings.profile in Object.fromEntries(profiles.map(p => [p.id, 1])) ? settings.profile : "auto";
  $("#preset").innerHTML = `<option value="">（不使用）</option>`
    + presets.map(p => `<option value="${esc(p.id)}" title="${esc(p.description)}">${esc(p.name)}</option>`).join("");
  state.modifiers = new Set(settings.modifiers || []);
  $("#modifiers").innerHTML = modifiers.map(m =>
    `<button type="button" class="toggle" data-mod="${esc(m.id)}" title="${esc(m.description)}">${esc(m.icon)} ${esc(m.name)}</button>`).join("");
  renderToggles();
  $("#opt-keep-video").checked = !!settings.keep_video;
}

function renderToggles() {
  $$("#modifiers .toggle").forEach(b => b.classList.toggle("on", state.modifiers.has(b.dataset.mod)));
}

function fillRefine() {
  const modes = state.app.text_modes;
  $("#r-mode").innerHTML = Object.keys(modes).map(m => `<option>${esc(m)}</option>`).join("");
  const fillSubs = () => { $("#r-sub").innerHTML = modes[$("#r-mode").value].map(s => `<option>${esc(s)}</option>`).join(""); };
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
    if (existing.length) {
      redo = await askRedo(existing);
      if (redo === null) return;
    }
    const jobs = await post("/api/jobs", {
      urls,
      profile: $("#profile").value,
      modifiers: [...state.modifiers],
      focus: $("#focus").value.trim(),
      notes: !$("#opt-transcript-only").checked,
      keep_video: $("#opt-keep-video").checked,
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

function askRedo(items) {
  return new Promise(resolve => {
    const box = $("#redo-rows");
    box.innerHTML = items.map(it => {
      const s = it.status;
      return `<div class="redo-row" data-url="${esc(it.url)}">
        <div class="t">${esc(it.title || it.url)}</div>
        <div class="muted small">已有：影音 ${s.media ? "✓" : "✗"}　逐字稿 ${s.transcript ? "✓" : "✗"}　筆記 ${s.notes.length ? esc(s.notes.join("、")) : "無"}</div>
        <div class="opts">
          ${s.media ? '<label class="check"><input type="checkbox" value="download"> 重新下載</label>' : ""}
          ${s.transcript ? '<label class="check"><input type="checkbox" value="transcribe"> 重新轉錄</label>' : ""}
          ${s.notes.length ? '<label class="check"><input type="checkbox" value="notes"> 重新整理筆記（同方案會覆蓋）</label>' : ""}
        </div>
      </div>`;
    }).join("");
    const dlg = $("#dlg-redo");
    dlg.returnValue = "";
    dlg.onclose = () => {
      if (dlg.returnValue !== "ok") { resolve(null); return; }
      const redo = {};
      $$(".redo-row", box).forEach(row => {
        const stages = $$("input:checked", row).map(i => i.value);
        if (stages.length) redo[row.dataset.url] = stages;
      });
      resolve(redo);
    };
    dlg.showModal();
  });
}

// ---------------------------------------------------------------- 工作清單
async function pollJobs() {
  let jobs;
  try { jobs = await api("/api/jobs"); } catch { return; }
  const sig = JSON.stringify(jobs);
  const finishedNow = state.jobs.some(old => old.status === "running" && jobs.find(j => j.id === old.id && j.status !== "running"));
  state.jobs = jobs;
  if (sig !== state.jobsSig) { state.jobsSig = sig; renderJobs(); }
  if (finishedNow) loadLibrary();
  if (state.selected?.type === "job") refreshSelectedJob();
}

function renderJobs() {
  const box = $("#jobs");
  const active = state.jobs.filter(j => j.status === "queued" || j.status === "running").length;
  $("#job-count").textContent = active ? `(${active})` : "";
  if (!state.jobs.length) {
    box.innerHTML = '<div class="empty-list">還沒有工作。貼上網址按「開始處理」。</div>';
    return;
  }
  box.innerHTML = state.jobs.map(j => {
    const sel = state.selected?.type === "job" && state.selected.id === j.id ? " selected" : "";
    const live = j.status === "running";
    const stages = STAGES.map(([k, name]) =>
      `<span class="stage ${j.stages[k] || ""}" title="${STAGE_TITLE[j.stages[k]] || "尚未開始"}">${name}</span>`).join("");
    const kind = j.kind ? `<span class="badge">${j.kind === "short" ? "短影音" : "影片"}</span>` : "";
    return `<div class="job status-${j.status}${sel}" data-id="${j.id}">
      <div class="top"><span class="title">${esc(j.title || j.url)}</span>${kind}<span class="badge">${STATUS_TEXT[j.status]}</span></div>
      <div class="stages">${stages}</div>
      ${live ? `<div class="bar"><div style="width:${Math.round((j.progress || 0) * 100)}%"></div></div>` : ""}
      ${live && j.detail ? `<div class="detail">${esc(j.detail)}</div>` : ""}
      ${j.error ? `<div class="error">${esc(j.error)}</div>` : ""}
      <div class="row-actions">
        ${live || j.status === "queued" ? '<button data-act="cancel">取消</button>' : '<button data-act="remove">移出清單</button>'}
        ${j.folder ? '<button data-act="open">資料夾</button>' : ""}
      </div>
    </div>`;
  }).join("");
}

async function onJobClick(ev) {
  const card = ev.target.closest(".job");
  if (!card) return;
  const id = card.dataset.id;
  const act = ev.target.closest("[data-act]")?.dataset.act;
  const job = state.jobs.find(j => j.id === id);
  if (act === "cancel") { await post(`/api/jobs/${id}/cancel`, {}); toast("已取消（已產生的檔案會保留）"); return pollJobs(); }
  if (act === "remove") {
    await api(`/api/jobs/${id}`, { method: "DELETE" });
    if (state.selected?.id === id) clearViewer();
    return pollJobs();
  }
  if (act === "open" && job?.folder) { await post("/api/open", { path: job.folder }); return; }
  select({ type: "job", id });
}

// ---------------------------------------------------------------- 筆記庫
async function loadLibrary() {
  try { state.library = await api("/api/library"); } catch { return; }
  const box = $("#library");
  if (!state.library.length) {
    box.innerHTML = `<div class="empty-list">輸出資料夾裡還沒有處理過的影片。<br>${esc(state.app.output_root)}</div>`;
    return;
  }
  box.innerHTML = state.library.map(it => {
    const sel = state.selected?.type === "lib" && state.selected.folder === it.folder ? " selected" : "";
    const notes = it.notes.length ? it.notes.map(n => `<span class="badge">${esc(n)}</span>`).join(" ") : '<span class="badge">只有逐字稿</span>';
    return `<div class="job${sel}" data-folder="${esc(it.folder)}">
      <div class="top"><span class="title">${esc(it.title)}</span><span class="badge">${it.kind === "short" ? "短影音" : "影片"}</span></div>
      <div class="detail">${notes}　<span class="muted">${fmtTime(it.updated)}</span></div>
    </div>`;
  }).join("");
}

function onLibraryClick(ev) {
  const card = ev.target.closest(".job");
  if (card) select({ type: "lib", folder: card.dataset.folder });
}

// ---------------------------------------------------------------- 右側檢視
function select(sel) {
  state.selected = sel;
  state.view = state.view || "rendered";
  $$(".job").forEach(el => el.classList.toggle("selected",
    (sel.type === "job" && el.dataset.id === sel.id) || (sel.type === "lib" && el.dataset.folder === sel.folder)));
  $("#r-out").textContent = "";
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
  const live = j.status === "running" && j.stages.notes !== "reused";
  const slug = j.notes_file ? j.notes_file.split(/[\\/]/).pop().replace(/^notes\./, "").replace(/\.md$/, "") : "";
  const prev = state.current;
  const notes = prev?.folder === j.folder && prev.notes?.length ? prev.notes : (slug ? [slug] : []);
  const text = j.notes || (j.status === "running" ? "（還在處理中，筆記產生時會即時顯示在這裡）"
    : j.error ? `處理失敗：${j.error}` : j.stages.notes ? "" : "（這個工作沒有產生筆記：只做了逐字稿）");
  showCurrent({ title: j.title || j.url, url: j.url, folder: j.folder, meta: metaFor(j), notes, slug, text, live });
  if ((first || j.status !== "running") && j.folder && !prev?.notesLoaded) refreshNoteList();
}

function metaFor(j) {
  const plan = j.plan || {};
  const parts = [STATUS_TEXT[j.status]];
  if (j.kind) parts.push(j.kind === "short" ? "短影音" : "影片");
  if (plan.profile) parts.push(`方案：${plan.profile}${plan.modifiers?.length ? " + " + plan.modifiers.join(" + ") : ""}`);
  if (plan.focus) parts.push(`關注：${plan.focus}`);
  return parts.join(" · ");
}

async function refreshNoteList() {
  const cur = state.current;
  if (!cur?.url) return;
  try {
    const [info] = await post("/api/check", { urls: [cur.url] });
    if (state.current !== cur || !info?.status) return;
    cur.notes = info.status.notes;
    cur.notesLoaded = true;
    renderNoteSelect();
  } catch { /* 清單只是附加資訊 */ }
}

async function openLibraryItem(folder) {
  const it = state.library.find(x => x.folder === folder);
  if (!it) return;
  const slug = it.notes[0] || "";
  let text = "（這支影片還沒有筆記，可以按「換方案重做」產生）";
  if (slug) {
    try { text = await api(`/api/note?folder=${encodeURIComponent(folder)}&slug=${encodeURIComponent(slug)}`); } catch (e) { text = e.message; }
  }
  showCurrent({ title: it.title, url: it.url, folder, meta: `${it.kind === "short" ? "短影音" : "影片"} · ${fmtTime(it.updated)}`,
    notes: it.notes, slug, text, live: false, notesLoaded: true });
}

function showCurrent(cur) {
  state.current = cur;
  $("#viewer-empty").hidden = true;
  $("#viewer-body").hidden = false;
  $("#v-title").textContent = cur.title;
  $("#v-meta").textContent = cur.meta;
  renderNoteSelect();
  renderView();
}

function renderNoteSelect() {
  const cur = state.current;
  const sel = $("#v-note-select");
  sel.hidden = !cur.notes || cur.notes.length < 2;
  sel.innerHTML = (cur.notes || []).map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  if (cur.slug) sel.value = cur.slug;
}

async function renderView() {
  const cur = state.current;
  const box = $("#v-content");
  $$("#view-tabs button").forEach(b => b.classList.toggle("active", b.dataset.view === state.view));
  if (state.view === "transcript") {
    box.className = "";
    box.innerHTML = '<pre class="plain">讀取中…</pre>';
    try {
      const text = await api(`/api/transcript?folder=${encodeURIComponent(cur.folder)}`);
      if (state.current === cur && state.view === "transcript") box.innerHTML = `<pre class="plain">${esc(text)}</pre>`;
    } catch (e) {
      box.innerHTML = `<pre class="plain">${esc(e.message)}</pre>`;
    }
    return;
  }
  if (state.view === "markdown") {
    box.className = "";
    box.innerHTML = `<pre class="plain${cur.live ? " streaming" : ""}">${esc(cur.text)}</pre>`;
    return;
  }
  box.className = "markdown" + (cur.live ? " streaming" : "");
  box.innerHTML = renderMarkdown(cur.text || "");
}

async function onNoteSelect() {
  const cur = state.current;
  const slug = $("#v-note-select").value;
  try {
    cur.text = await api(`/api/note?folder=${encodeURIComponent(cur.folder)}&slug=${encodeURIComponent(slug)}`);
    cur.slug = slug;
    cur.live = false;
    if (state.selected?.type === "job") state.selected = { type: "lib", folder: cur.folder };  // 停止被輪詢覆蓋
    renderView();
  } catch (e) { toast(e.message); }
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
function openSettings() {
  const { settings, output_choices, providers, whisper_models, env } = state.app;
  $$('input[name="output"]').forEach(r => { r.checked = r.value === settings.output; });
  $("#out-downloads").textContent = output_choices.downloads;
  $("#out-data").textContent = output_choices.data;
  $("#s-output-custom").value = settings.output_custom || "";
  $("#s-keep-video").checked = !!settings.keep_video;
  $("#s-provider").innerHTML = Object.entries(providers).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  $("#s-provider").value = settings.provider;
  $("#s-model").value = settings.model || "";
  updateModelHints();
  $("#s-whisper").innerHTML = whisper_models.map(m => `<option>${m}</option>`).join("");
  $("#s-whisper").value = settings.whisper_model;
  $("#s-device").value = settings.whisper_device;
  $("#s-language").value = settings.language;
  $("#s-traditional").checked = !!settings.traditional;
  $("#s-parallel").value = settings.parallel_jobs;
  $("#s-long").value = settings.long_transcript_chars;
  $("#s-cookies").value = settings.cookies_from_browser || "";
  $("#s-notify").value = settings.notify_url || "";
  $("#s-prompts-dir").textContent = env.user_prompts;
  $("#s-key").value = "";
  updateKeyStatus();
  const dlg = $("#dlg-settings");
  dlg.returnValue = "";
  dlg.onclose = () => { if (dlg.returnValue === "ok") saveSettings(); };
  dlg.showModal();
}

function updateModelHints() {
  const p = $("#s-provider").value;
  const hints = { "claude-sub": ["sonnet", "haiku", "opus"],
    openai: ["gpt-5.1", "gpt-4.1", "gpt-4.1-mini"], gemini: ["gemini-2.5-flash", "gemini-2.5-pro"],
    anthropic: ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"] }[p] || [];
  $("#model-hints").innerHTML = hints.map(h => `<option value="${h}">`).join("");
  $("#s-model").placeholder = `空白 = ${state.app.default_models[p]}`;
}

function updateKeyStatus() {
  const p = $("#s-provider").value;
  const { env, providers } = state.app;
  const keyless = env.keyless.includes(p);
  $(".key-row").style.display = keyless ? "none" : "";   // Claude 訂閱用 Claude Code 登入的帳號，沒有金鑰可貼
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
  const data = {
    output: $('input[name="output"]:checked')?.value || "downloads",
    output_custom: $("#s-output-custom").value.trim(),
    keep_video: $("#s-keep-video").checked,
    provider: $("#s-provider").value,
    model: $("#s-model").value.trim(),
    whisper_model: $("#s-whisper").value,
    whisper_device: $("#s-device").value,
    language: $("#s-language").value.trim() || "auto",
    traditional: $("#s-traditional").checked,
    parallel_jobs: Math.max(1, parseInt($("#s-parallel").value, 10) || 3),
    long_transcript_chars: Math.max(5000, parseInt($("#s-long").value, 10) || 60000),
    cookies_from_browser: $("#s-cookies").value,
    notify_url: $("#s-notify").value.trim(),
  };
  if (data.output === "custom" && !data.output_custom) { toast("選了「自選」就要填資料夾路徑"); return; }
  const parallelChanged = data.parallel_jobs !== state.app.settings.parallel_jobs;
  try {
    state.app = await api("/api/settings", { method: "PUT", body: JSON.stringify(data) });
    renderEnv();
    loadLibrary();
    toast(parallelChanged ? "已儲存（同時處理數量重新開啟後生效）" : "已儲存");
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
  $("#preset").onchange = () => {
    const p = state.app.presets.find(x => x.id === $("#preset").value);
    if (!p) return;
    $("#profile").value = p.profile;
    state.modifiers = new Set(p.modifiers);
    if (p.focus) $("#focus").value = p.focus;
    renderToggles();
    toast(`已套用「${p.name}」`);
  };
  $("#left-tabs").onclick = e => { const b = e.target.closest("button"); if (b) switchTab(b.dataset.tab); };
  $("#jobs").onclick = onJobClick;
  $("#library").onclick = onLibraryClick;
  $("#view-tabs").onclick = e => { const b = e.target.closest("button"); if (b) { state.view = b.dataset.view; renderView(); } };
  $("#v-note-select").onchange = onNoteSelect;
  $("#v-copy").onclick = () => copyText(state.current?.live ? "" : state.current?.text, " Markdown，可以直接貼進 Notion");
  $("#v-open").onclick = () => state.current?.folder && post("/api/open", { path: state.current.folder }).catch(e => toast(e.message));
  $("#v-redo").onclick = () => state.current?.url && start([state.current.url]);
  $("#r-run").onclick = runRefine;
  $("#r-copy").onclick = () => copyText($("#r-out").textContent, "加工結果");
  $("#btn-settings").onclick = openSettings;
  $("#s-provider").onchange = () => { updateModelHints(); updateKeyStatus(); };
  $("#s-key-save").onclick = saveKey;
}

init().catch(err => {
  document.body.innerHTML = `<div class="empty">無法連到 Video Notes 伺服器：${esc(err.message)}<br>請確認程式還開著，然後重新整理。</div>`;
});
