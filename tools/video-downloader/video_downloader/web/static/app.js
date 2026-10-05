// Video Downloader 前端。
// 左邊：貼網址（或拖曳、剪貼簿、書籤小工具）→「解析」看標題與畫質，或「直接下載」。
// 右邊：每 0.8 秒輪詢 /api/downloads 顯示進度；「紀錄」分頁看下載過的檔案。

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const state = { app: null, sig: "", probes: [] };

const STATUS = { queued: "排隊中", downloading: "下載中", processing: "處理中", done: "完成", failed: "失敗", cancelled: "已取消" };

async function api(path, options = {}) {
  // 自訂 header：伺服器只接受帶這個 header 的寫入請求，擋其他網站跨站呼叫本機 API
  const headers = { "X-Video-Downloader": "1" };
  if (options.body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch { /* 不是 JSON */ }
    throw new Error(msg);
  }
  return res.json();
}
const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data) });

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtBytes(n) {
  if (!n) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
}
function fmtDuration(s) {
  if (!s) return "";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}
let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3000);
}

function urlsFromBox() {
  return $("#urls").value.split(/\s+/).map(s => s.trim()).filter(s => /^https?:\/\//i.test(s));
}
function addUrls(text) {
  const found = (text.match(/https?:\/\/[^\s"'<>]+/gi) || []);
  if (!found.length) { toast("沒有找到網址"); return 0; }
  const box = $("#urls");
  const existing = new Set(urlsFromBox());
  const fresh = found.filter(u => !existing.has(u));
  box.value = [...urlsFromBox(), ...fresh].join("\n");
  return fresh.length;
}
function headersFromBox() {
  const headers = {};
  $("#headers").value.split("\n").forEach(line => {
    const i = line.indexOf(":");
    if (i > 0 && line.slice(i + 1).trim()) headers[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  });
  return headers;
}
function presetOptions(selected) {
  return state.app.presets.map(p =>
    `<option value="${p.id}" title="${esc(p.description)}"${p.id === selected ? " selected" : ""}>${esc(p.name)}</option>`).join("");
}

// ---------------------------------------------------------------- 初始化
async function init() {
  state.app = await api("/api/state");
  $("#version").textContent = `v${state.app.version}`;
  $("#preset").innerHTML = presetOptions(state.app.settings.preset);
  renderEnv();
  bindEvents();
  const add = new URLSearchParams(location.search).get("add");   // 書籤小工具帶來的網址
  if (add) {
    history.replaceState(null, "", "/");
    addUrls(add);
    probeAll();
  }
  await pollQueue();
  setInterval(pollQueue, 800);
}

function renderEnv() {
  const { env, output_root } = state.app;
  $("#env-chips").innerHTML = [
    `<span class="chip">yt-dlp ${esc(env.yt_dlp)}</span>`,
    `<span class="chip ${env.ffmpeg ? "ok" : "bad"}" title="${esc(env.ffmpeg || "找不到 ffmpeg：無法合併影像與聲音")}">ffmpeg ${env.ffmpeg ? "✓" : "✗"}</span>`,
    `<span class="chip ${env.js_runtimes.length ? "ok" : "bad"}" title="YouTube 需要 JavaScript 執行環境">JS ${env.js_runtimes.length ? "✓ " + esc(env.js_runtimes[0]) : "✗"}</span>`,
  ].join("");
  $("#out-hint").textContent = `存到：${output_root}`;
  $("#custom-format-label").hidden = $("#preset").value !== "custom";
}

// ---------------------------------------------------------------- 解析
async function probeAll() {
  const urls = urlsFromBox();
  if (!urls.length) { toast("請先貼上網址"); return; }
  const box = $("#probe-results");
  box.innerHTML = `<div class="card muted">解析 ${urls.length} 個網址中…</div>`;
  $("#btn-probe").disabled = true;
  try {
    state.probes = await post("/api/probe", { urls, headers: headersFromBox() });
    renderProbes();
  } catch (e) {
    box.innerHTML = `<div class="card error">${esc(e.message)}</div>`;
  } finally {
    $("#btn-probe").disabled = false;
  }
}

function renderProbes() {
  const preset = $("#preset").value;
  $("#probe-results").innerHTML = state.probes.map((p, i) => {
    if (p.error) {
      return `<div class="card"><div class="title">${esc(p.url)}</div><div class="error">${esc(p.error)}</div></div>`;
    }
    if (p.type === "playlist") {
      const rows = p.entries.map(e => `<label class="check"><input type="checkbox" data-entry="${e.index}" checked>
        <span>${e.index}. ${esc(e.title)}</span><span class="dur">${fmtDuration(e.duration)}</span></label>`).join("");
      return `<div class="card" data-probe="${i}">
        <div class="title">📃 ${esc(p.title)}</div>
        <div class="meta">${esc(p.uploader)}${p.uploader ? " · " : ""}${p.count} 支 · 存到子資料夾「${esc(p.title)}」</div>
        <div class="entries">${rows}</div>
        <div class="controls">
          <button class="ghost small" data-act="all">全選</button><button class="ghost small" data-act="none">全不選</button>
          <select data-role="preset">${presetOptions(preset)}</select>
          <button class="primary" data-act="download">⬇ 下載選取的</button>
        </div></div>`;
    }
    const best = p.heights.length ? `最高 ${p.heights[0]}p` : (p.audio_only ? "只有聲音" : "");
    const subs = p.subtitles.length ? ` · 字幕：${esc(p.subtitles.slice(0, 6).join("、"))}` : "";
    return `<div class="card probe${p.thumbnail ? "" : " no-thumb"}" data-probe="${i}">
      ${p.thumbnail ? `<img src="${esc(p.thumbnail)}" alt="" referrerpolicy="no-referrer" loading="lazy">` : ""}
      <div>
        <div class="title">${esc(p.title)}</div>
        <div class="meta">${[esc(p.extractor), esc(p.uploader), fmtDuration(p.duration), best].filter(Boolean).join(" · ")}${subs}${p.is_live ? " · 🔴 直播中" : ""}</div>
        <div class="controls">
          <select data-role="preset">${presetOptions(preset)}</select>
          <button class="primary" data-act="download">⬇ 下載</button>
        </div>
      </div></div>`;
  }).join("");
}

async function onProbeClick(ev) {
  const btn = ev.target.closest("[data-act]");
  const card = ev.target.closest("[data-probe]");
  if (!btn || !card) return;
  const p = state.probes[+card.dataset.probe];
  const act = btn.dataset.act;
  if (act === "all" || act === "none") {
    $$("input[data-entry]", card).forEach(c => { c.checked = act === "all"; });
    return;
  }
  const preset = $("select[data-role=preset]", card).value;
  let items;
  if (p.type === "playlist") {
    const picked = new Set($$("input[data-entry]:checked", card).map(c => +c.dataset.entry));
    items = p.entries.filter(e => picked.has(e.index)).map(e => ({
      url: e.url || p.url, playlist_items: e.url ? "" : String(e.index),
      title: e.title, preset, subfolder: p.title,
    }));
    if (!items.length) { toast("沒有勾選任何影片"); return; }
  } else {
    items = [{ url: p.url, title: p.title, preset, filename: state.probes.length === 1 ? $("#filename").value.trim() : "" }];
  }
  await submit(items);
}

// ---------------------------------------------------------------- 下載
async function submit(items) {
  const custom = $("#custom-format").value.trim();
  items.forEach(it => { if (it.preset === "custom") it.custom_format = custom; });
  try {
    const jobs = await post("/api/downloads", { items, headers: headersFromBox() });
    toast(`已加入 ${jobs.length} 個下載`);
    switchTab("queue");
    pollQueue();
  } catch (e) {
    toast(`無法開始：${e.message}`);
  }
}

function quickDownload() {
  const urls = urlsFromBox();
  if (!urls.length) { toast("請先貼上網址"); return; }
  const preset = $("#preset").value;
  const filename = urls.length === 1 ? $("#filename").value.trim() : "";
  submit(urls.map(url => ({ url, preset, filename })));
  $("#urls").value = "";
}

async function pollQueue() {
  let jobs;
  try { jobs = await api("/api/downloads"); } catch { return; }
  const sig = JSON.stringify(jobs);
  if (sig === state.sig) return;
  const finished = state.jobs?.some(o => !["done", "failed", "cancelled"].includes(o.status)
    && jobs.find(j => j.id === o.id && ["done", "failed"].includes(j.status)));
  state.sig = sig;
  state.jobs = jobs;
  renderQueue();
  if (finished && !$("#history").hidden) loadHistory();
}

function renderQueue() {
  const jobs = state.jobs || [];
  const active = jobs.filter(j => ["queued", "downloading", "processing"].includes(j.status)).length;
  $("#queue-count").textContent = active ? `(${active})` : "";
  if (!jobs.length) {
    $("#queue").innerHTML = '<div class="empty-list">還沒有下載。貼上網址按「直接下載」，或先「解析」選畫質。</div>';
    return;
  }
  $("#queue").innerHTML = jobs.map(j => {
    const live = j.status === "downloading" || j.status === "processing";
    const pct = Math.round(j.progress * 100);
    const detail = live ? [
      j.stage,
      j.total ? `${fmtBytes(j.downloaded)} / ${fmtBytes(j.total)}` : fmtBytes(j.downloaded),
      j.speed ? `${fmtBytes(j.speed)}/s` : "",
      j.eta ? `剩 ${fmtDuration(j.eta)}` : "",
    ].filter(Boolean).map(t => `<span>${esc(t)}</span>`).join("") : (j.status === "cancelled" ? `<span>${esc(j.stage)}</span>` : "");
    const bar = live ? `<div class="bar${j.status === "processing" || !j.progress ? " indeterminate" : ""}"><div style="width:${pct}%"></div></div>` : "";
    const actions = live || j.status === "queued"
      ? '<button class="small" data-act="cancel">取消</button>'
      : `${j.status !== "done" ? '<button class="small" data-act="retry">重試</button>' : ""}`
        + (j.filepath ? '<button class="small" data-act="reveal">開啟位置</button>' : (j.folder ? '<button class="small" data-act="folder">資料夾</button>' : ""))
        + '<button class="small ghost" data-act="remove">移出清單</button>';
    return `<div class="job" data-id="${j.id}">
      <div class="top"><span class="title" title="${esc(j.url)}">${esc(j.title)}</span>
        <span class="badge ${j.status}">${STATUS[j.status]}${live && j.progress ? ` ${pct}%` : ""}</span></div>
      ${bar}
      ${detail ? `<div class="detail">${detail}</div>` : ""}
      ${j.error ? `<div class="error">${esc(j.error)}</div>` : ""}
      ${j.status === "done" && j.filepath ? `<div class="path">${esc(j.filepath)}</div>` : ""}
      <div class="actions">${actions}</div>
    </div>`;
  }).join("");
}

async function onQueueClick(ev) {
  const btn = ev.target.closest("[data-act]");
  const card = ev.target.closest(".job");
  if (!btn || !card) return;
  const id = card.dataset.id;
  const job = (state.jobs || []).find(j => j.id === id);
  try {
    switch (btn.dataset.act) {
      case "cancel": await post(`/api/downloads/${id}/cancel`, {}); break;
      case "retry": await post(`/api/downloads/${id}/retry`, {}); toast("重新開始（會從已下載的部分接著下載）"); break;
      case "remove": await api(`/api/downloads/${id}`, { method: "DELETE" }); break;
      case "reveal": await post("/api/open", { path: job.filepath, reveal: true }); break;
      case "folder": await post("/api/open", { path: job.folder }); break;
    }
  } catch (e) { toast(e.message); }
  pollQueue();
}

// ---------------------------------------------------------------- 紀錄
async function loadHistory() {
  let items;
  try { items = await api("/api/history"); } catch { return; }
  state.history = items;
  if (!items.length) { $("#history").innerHTML = '<div class="empty-list">還沒有下載紀錄。</div>'; return; }
  $("#history").innerHTML = `<div class="history-tools"><button class="small ghost" data-act="clear">清除紀錄（不會刪檔案）</button></div>`
    + items.map((h, i) => `<div class="job" data-index="${i}">
      <div class="top"><span class="title" title="${esc(h.url)}">${esc(h.title)}</span>
        <span class="badge ${h.status}">${STATUS[h.status] || h.status}</span></div>
      <div class="detail"><span>${esc(h.finished.replace("T", " "))}</span><span>${fmtBytes(h.size)}</span><span>${esc(h.preset)}</span></div>
      ${h.error ? `<div class="error">${esc(h.error)}</div>` : ""}
      ${h.path ? `<div class="path">${esc(h.path)}</div>` : ""}
      <div class="actions">
        ${h.path ? '<button class="small" data-act="reveal">開啟位置</button>' : ""}
        <button class="small ghost" data-act="again">再下載一次</button>
      </div></div>`).join("");
}

async function onHistoryClick(ev) {
  const btn = ev.target.closest("[data-act]");
  if (!btn) return;
  if (btn.dataset.act === "clear") {
    if (confirm("清除下載紀錄？（只清紀錄，不會刪除任何檔案）")) { await api("/api/history", { method: "DELETE" }); loadHistory(); }
    return;
  }
  const h = state.history[+btn.closest(".job").dataset.index];
  try {
    if (btn.dataset.act === "reveal") await post("/api/open", { path: h.path, reveal: true });
    if (btn.dataset.act === "again") {
      const r = h.request || { url: h.url };
      await post("/api/downloads", { items: [{ url: r.url, preset: r.preset, custom_format: r.custom_format || "",
        filename: r.filename || "", subfolder: r.subfolder || "", playlist_items: r.playlist_items || "", title: h.title }],
        headers: r.headers || {} });
      toast("已加入下載");
      switchTab("queue");
    }
  } catch (e) { toast(e.message); }
}

// ---------------------------------------------------------------- 設定
function openSettings() {
  const s = state.app.settings;
  $("#s-output").value = s.output_dir;
  $("#s-output").placeholder = state.app.output_root;
  $("#s-template").value = s.filename_template;
  $("#s-preset").innerHTML = presetOptions(s.preset);
  $("#s-concurrent").value = s.concurrent_downloads;
  $("#s-fragments").value = s.concurrent_fragments;
  $("#s-rate").value = s.rate_limit;
  $("#s-proxy").value = s.proxy;
  $("#s-cookies").value = s.cookies_from_browser;
  $("#s-subs").checked = s.subtitles;
  $("#s-sublangs").value = s.sub_langs;
  $("#s-autosubs").checked = s.auto_subtitles;
  $("#s-embedsubs").checked = s.embed_subs;
  $("#s-metadata").checked = s.embed_metadata;
  $("#s-thumbnail").checked = s.embed_thumbnail;
  $("#s-ffmpeg").value = s.ffmpeg_path;
  $("#bookmarklet").href = `javascript:(()=>{window.open('${location.origin}/?add='+encodeURIComponent(location.href),'_blank')})()`;
  const dlg = $("#dlg-settings");
  dlg.returnValue = "";
  dlg.onclose = () => { if (dlg.returnValue === "ok") saveSettings(); };
  dlg.showModal();
}

async function saveSettings() {
  const before = state.app.settings.concurrent_downloads;
  const data = {
    output_dir: $("#s-output").value.trim(),
    filename_template: $("#s-template").value.trim() || "%(title).150B [%(id)s].%(ext)s",
    preset: $("#s-preset").value,
    concurrent_downloads: Math.max(1, parseInt($("#s-concurrent").value, 10) || 2),
    concurrent_fragments: Math.max(1, parseInt($("#s-fragments").value, 10) || 4),
    rate_limit: $("#s-rate").value.trim(),
    proxy: $("#s-proxy").value.trim(),
    cookies_from_browser: $("#s-cookies").value,
    subtitles: $("#s-subs").checked,
    sub_langs: $("#s-sublangs").value.trim(),
    auto_subtitles: $("#s-autosubs").checked,
    embed_subs: $("#s-embedsubs").checked,
    embed_metadata: $("#s-metadata").checked,
    embed_thumbnail: $("#s-thumbnail").checked,
    ffmpeg_path: $("#s-ffmpeg").value.trim(),
  };
  try {
    state.app = await api("/api/settings", { method: "PUT", body: JSON.stringify(data) });
    $("#preset").innerHTML = presetOptions(state.app.settings.preset);
    renderEnv();
    toast(data.concurrent_downloads !== before ? "已儲存（同時下載數重新開啟後生效）" : "已儲存");
  } catch (e) { toast(`儲存失敗：${e.message}`); }
}

// ---------------------------------------------------------------- 事件
function switchTab(tab) {
  $$("#tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  $("#queue").hidden = tab !== "queue";
  $("#history").hidden = tab !== "history";
  if (tab === "history") loadHistory();
}

function bindEvents() {
  $("#btn-probe").onclick = probeAll;
  $("#btn-quick").onclick = quickDownload;
  $("#btn-paste").onclick = async () => {
    try { const n = addUrls(await navigator.clipboard.readText()); if (n) toast(`加入 ${n} 個網址`); }
    catch { toast("瀏覽器不允許讀剪貼簿，請直接 Ctrl+V 貼上"); }
  };
  $("#urls").addEventListener("keydown", e => { if (e.key === "Enter" && e.ctrlKey) probeAll(); });
  $("#preset").onchange = () => { $("#custom-format-label").hidden = $("#preset").value !== "custom"; };
  const zone = $("#drop-zone");
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("dragging"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("dragging");
    const text = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
    const n = addUrls(text);
    if (n) toast(`加入 ${n} 個網址`);
  });
  $("#probe-results").onclick = onProbeClick;
  $("#queue").onclick = onQueueClick;
  $("#history").onclick = onHistoryClick;
  $("#tabs").onclick = e => { const b = e.target.closest("button"); if (b) switchTab(b.dataset.tab); };
  $("#btn-settings").onclick = openSettings;
}

init().catch(err => {
  document.body.innerHTML = `<div class="empty-list">無法連到 Video Downloader：${esc(err.message)}<br>請確認程式還開著，然後重新整理。</div>`;
});
