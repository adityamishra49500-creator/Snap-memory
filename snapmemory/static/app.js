const API = "/api";

// ---------------------------------------------------------------- helpers

function toast(message, type = "") {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const data = await res.json(); msg = data.error || msg; } catch (e) {}
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res;
}

function fmtDate(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString();
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s || "";
  return div.innerHTML;
}

// ---------------------------------------------------------------- routing

const views = document.querySelectorAll(".view");
const navItems = document.querySelectorAll(".nav-item");

function showView(name) {
  views.forEach(v => v.classList.toggle("active", v.id === `view-${name}`));
  navItems.forEach(n => n.classList.toggle("active", n.dataset.view === name));
  loadView(name);
}

navItems.forEach(btn => btn.addEventListener("click", () => showView(btn.dataset.view)));

function loadView(name) {
  const loaders = {
    dashboard: loadDashboard,
    memories: loadMemories,
    meetings: loadMeetings,
    documents: loadDocuments,
    images: loadImages,
    timeline: loadTimeline,
    privacy: loadPrivacy,
    performance: loadPerformance,
    settings: loadSettings,
  };
  if (loaders[name]) loaders[name]();
}

// --------------------------------------------------------------- dashboard

async function loadDashboard() {
  try {
    const d = await api("/dashboard");
    const grid = document.getElementById("stat-grid");
    grid.innerHTML = `
      ${statCard("Memories", d.total_memories)}
      ${statCard("Documents", d.documents)}
      ${statCard("Meetings", d.meetings)}
      ${statCard("Images", d.images)}
      ${statCard("Cloud requests", d.cloud_requests, d.cloud_requests === 0 ? "ok" : "warn")}
      ${statCard("Internet required", d.internet_required ? "YES" : "NO", d.internet_required ? "warn" : "ok")}
      ${statCard("AI Mode", d.ai_mode, "ok")}
    `;
    const recentMem = document.getElementById("recent-memories");
    recentMem.innerHTML = d.recent_memories.length
      ? d.recent_memories.map(m => `<div class="list-item"><div>${escapeHtml(m.snippet)}</div><div class="meta">${m.source_type} · ${fmtDate(m.created_at)}</div></div>`).join("")
      : `<div class="empty-state">No memories yet. Import a document, meeting, or image to get started.</div>`;
    const recentQ = document.getElementById("recent-questions");
    recentQ.innerHTML = d.recent_questions.length
      ? d.recent_questions.map(q => `<div class="list-item"><div><strong>${escapeHtml(q.question)}</strong></div><div class="meta">${fmtDate(q.created_at)}</div></div>`).join("")
      : `<div class="empty-state">No questions asked yet. Try the Ask SnapMemory tab.</div>`;
  } catch (e) { toast(e.message, "error"); }
}

function statCard(label, value, cls = "") {
  return `<div class="stat-card"><div class="stat-label">${label}</div><div class="stat-value ${cls}">${value}</div></div>`;
}

// -------------------------------------------------------------------- ask

document.getElementById("ask-btn").addEventListener("click", askQuestion);
document.getElementById("ask-input").addEventListener("keydown", e => { if (e.key === "Enter") askQuestion(); });

async function askQuestion() {
  const input = document.getElementById("ask-input");
  const question = input.value.trim();
  if (!question) return;
  const resultBox = document.getElementById("ask-result");
  resultBox.classList.remove("hidden");
  resultBox.innerHTML = `<div class="empty-state">Thinking locally…</div>`;
  try {
    const res = await api("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const citationsHtml = res.citations.length
      ? res.citations.map(c => `
          <div class="citation">
            <div class="cite-label">${escapeHtml(c.label)} · relevance ${c.relevance}</div>
            <div class="cite-excerpt">${escapeHtml(c.excerpt)}</div>
          </div>`).join("")
      : `<div class="empty-state">No sources retrieved.</div>`;
    resultBox.innerHTML = `
      <div class="answer-text">${escapeHtml(res.answer)}</div>
      <div class="answer-meta">
        <span>Model: ${escapeHtml(res.model_used)}</span>
        <span>Execution: ${escapeHtml(res.execution_provider)}</span>
        <span>${res.latency_ms} ms</span>
        <span>${res.chunks_retrieved} chunks retrieved</span>
      </div>
      <h4 style="margin-bottom:8px;color:var(--accent-strong);font-size:13px;">Sources</h4>
      ${citationsHtml}
    `;
  } catch (e) {
    resultBox.innerHTML = `<div class="empty-state">Error: ${escapeHtml(e.message)}</div>`;
  }
}

// --------------------------------------------------------------- memories

let currentMemoryFilter = "all";
document.querySelectorAll("#memory-filters .chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll("#memory-filters .chip").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    currentMemoryFilter = chip.dataset.type;
    loadMemories();
  });
});

async function loadMemories(query = "") {
  try {
    const params = new URLSearchParams({ type: currentMemoryFilter, q: query });
    const rows = await api(`/memories?${params.toString()}`);
    const list = document.getElementById("memory-list");
    list.innerHTML = rows.length
      ? rows.map(r => `<div class="list-item"><div>${escapeHtml(r.snippet)}</div><div class="meta">${escapeHtml(r.label)} · ${fmtDate(r.created_at)}</div></div>`).join("")
      : `<div class="empty-state">No memories match this filter.</div>`;
  } catch (e) { toast(e.message, "error"); }
}

document.getElementById("global-search").addEventListener("input", (e) => {
  const activeView = document.querySelector(".view.active").id;
  if (activeView === "view-memories") loadMemories(e.target.value);
});

// ---------------------------------------------------------------- uploads

function setupDropzone(selector, inputId, uploadFn) {
  const zone = document.querySelector(selector);
  const input = document.getElementById(inputId);
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("dragover");
    if (e.dataTransfer.files.length) uploadFn(e.dataTransfer.files[0]);
  });
  input.addEventListener("change", () => {
    if (input.files.length) uploadFn(input.files[0]);
    input.value = "";
  });
}

async function uploadFile(endpoint, file, onDone) {
  const formData = new FormData();
  formData.append("file", file);
  toast(`Uploading ${file.name}…`);
  try {
    const res = await api(endpoint, { method: "POST", body: formData });
    if (res.status === "duplicate") {
      toast(res.message, "error");
    } else if (res.status === "transcription_unavailable") {
      toast(res.message, "error");
    } else {
      toast(`Indexed ${file.name}`, "success");
    }
    if (onDone) onDone(res);
  } catch (e) {
    toast(e.message, "error");
  }
}

setupDropzone('[data-upload-type="document"]', "document-file-input",
  (file) => uploadFile("/documents/upload", file, loadDocuments));
setupDropzone('[data-upload-type="meeting"]', "meeting-file-input",
  (file) => uploadFile("/meetings/upload", file, loadMeetings));
setupDropzone('[data-upload-type="image"]', "image-file-input",
  (file) => uploadFile("/images/upload", file, loadImages));

// --------------------------------------------------------------- documents

async function loadDocuments() {
  try {
    const rows = await api("/documents");
    const list = document.getElementById("document-list");
    list.innerHTML = rows.length
      ? rows.map(d => `
        <div class="card">
          <button class="card-delete" onclick="deleteDocument(${d.id}, event)">✕</button>
          <div class="card-title">${escapeHtml(d.filename)}</div>
          <div class="card-meta">${d.source_type.toUpperCase()} · ${d.chunk_count} chunks${d.page_count ? ` · ${d.page_count} pages/slides` : ""}</div>
          <div class="card-meta">${fmtDate(d.imported_at)}</div>
          <span class="card-status ok">Indexed ✓</span>
        </div>`).join("")
      : `<div class="empty-state">No documents yet.</div>`;
  } catch (e) { toast(e.message, "error"); }
}

async function deleteDocument(id, event) {
  event.stopPropagation();
  if (!confirm("Delete this document and its memories?")) return;
  await api(`/documents/${id}`, { method: "DELETE" });
  loadDocuments();
  toast("Deleted.", "success");
}

// ------------------------------------------------------------------ images

async function loadImages() {
  try {
    const rows = await api("/images");
    const list = document.getElementById("image-list");
    list.innerHTML = rows.length
      ? rows.map(i => `
        <div class="card">
          <button class="card-delete" onclick="deleteImage(${i.id}, event)">✕</button>
          <div class="card-title">${escapeHtml(i.filename)}</div>
          <div class="card-meta">${escapeHtml(i.description || "")}</div>
          <div class="card-meta">${escapeHtml(i.ocr_text || "(no text detected)")}</div>
          <div class="card-meta">${fmtDate(i.imported_at)}</div>
        </div>`).join("")
      : `<div class="empty-state">No images yet.</div>`;
  } catch (e) { toast(e.message, "error"); }
}

async function deleteImage(id, event) {
  event.stopPropagation();
  if (!confirm("Delete this image and its memories?")) return;
  await api(`/images/${id}`, { method: "DELETE" });
  loadImages();
  toast("Deleted.", "success");
}

// ---------------------------------------------------------------- meetings

async function loadMeetings() {
  try {
    const rows = await api("/meetings");
    const list = document.getElementById("meeting-list");
    list.innerHTML = rows.length
      ? rows.map(m => `
        <div class="card" onclick="openMeeting(${m.id})">
          <button class="card-delete" onclick="deleteMeeting(${m.id}, event)">✕</button>
          <div class="card-title">${escapeHtml(m.filename)}</div>
          <div class="card-meta">${escapeHtml(m.provider || "")}</div>
          <div class="card-meta">${fmtDate(m.imported_at)}</div>
          <span class="card-status ${m.status === 'indexed' ? 'ok' : 'warn'}">${escapeHtml(m.status)}</span>
        </div>`).join("")
      : `<div class="empty-state">No meetings yet. Upload an audio recording above.</div>`;
  } catch (e) { toast(e.message, "error"); }
}

async function deleteMeeting(id, event) {
  event.stopPropagation();
  if (!confirm("Delete this meeting and its memories?")) return;
  await api(`/meetings/${id}`, { method: "DELETE" });
  loadMeetings();
  document.getElementById("meeting-detail").classList.add("hidden");
  toast("Deleted.", "success");
}

async function openMeeting(id) {
  try {
    const m = await api(`/meetings/${id}`);
    const panel = document.getElementById("meeting-detail");
    panel.classList.remove("hidden");
    const tags = (arr) => (arr && arr.length ? arr.map(t => `<span class="tag">${escapeHtml(String(t))}</span>`).join("") : `<span class="muted">Not found in the available meeting information.</span>`);
    const actionItemsHtml = (m.action_items && m.action_items.length)
      ? m.action_items.map(a => `<div class="list-item"><div>${escapeHtml(a.task)}</div><div class="meta">Person: ${escapeHtml(a.person || "unknown")} · Deadline: ${escapeHtml(a.deadline || "unknown")}</div></div>`).join("")
      : `<div class="empty-state">Not found in the available meeting information.</div>`;
    panel.innerHTML = `
      <h3>${escapeHtml(m.filename)}</h3>
      <div class="muted">Transcription: ${escapeHtml(m.provider || "unknown")}</div>
      <h4>Summary</h4>
      <p>${escapeHtml(m.summary)}</p>
      <h4>Decisions</h4>
      ${m.decisions.length ? m.decisions.map(d => `<div class="list-item">${escapeHtml(d)}</div>`).join("") : `<div class="empty-state">Not found in the available meeting information.</div>`}
      <h4>Action Items</h4>
      ${actionItemsHtml}
      <h4>Open Questions</h4>
      ${tags(m.open_questions)}
      <h4>Important Dates</h4>
      ${tags(m.important_dates)}
      <h4>Topics</h4>
      ${tags(m.topics)}
      <h4>People Mentioned</h4>
      ${tags(m.people)}
      <h4>Full Transcript</h4>
      <div class="list-item mono" style="white-space:pre-wrap;">${escapeHtml(m.transcript || "Not available.")}</div>
    `;
  } catch (e) { toast(e.message, "error"); }
}

// ---------------------------------------------------------------- timeline

async function loadTimeline() {
  try {
    const rows = await api("/timeline");
    const list = document.getElementById("timeline-list");
    list.innerHTML = rows.length
      ? rows.map(r => `
        <div class="timeline-item">
          <div class="timeline-date">${fmtDate(r.imported_at)}</div>
          <div class="timeline-title">${escapeHtml(r.filename)}</div>
          <div class="timeline-type">${r.type}</div>
        </div>`).join("")
      : `<div class="empty-state">Nothing imported yet.</div>`;
  } catch (e) { toast(e.message, "error"); }
}

// ----------------------------------------------------------------- privacy

async function loadPrivacy() {
  try {
    const d = await api("/privacy");
    const s = d.summary;
    const grid = document.getElementById("privacy-grid");
    grid.innerHTML = `
      ${statCard("Cloud API calls", s.cloud_api_calls, s.cloud_api_calls === 0 ? "ok" : "warn")}
      ${statCard("External uploads", s.external_uploads, "ok")}
      ${statCard("Local files processed", s.local_files_processed)}
      ${statCard("Internet required", s.internet_required ? "YES" : "NO", s.internet_required ? "warn" : "ok")}
      ${statCard("Local AI", s.local_ai ? "✓" : "✕", s.local_ai ? "ok" : "warn")}
      ${statCard("Local database", s.local_database ? "✓" : "✕", "ok")}
      ${statCard("Queries executed", s.queries_executed)}
      ${statCard("Deletions", s.deletions)}
    `;
    const log = document.getElementById("audit-log");
    log.innerHTML = d.audit_log.length
      ? d.audit_log.map(e => `<div class="list-item">[${fmtDate(e.ts)}] ${e.event_type} — ${escapeHtml(JSON.stringify(e.detail))}</div>`).join("")
      : `<div class="empty-state">No activity logged yet.</div>`;
  } catch (e) { toast(e.message, "error"); }
}

document.getElementById("export-btn").addEventListener("click", () => {
  window.location.href = `${API}/data/export`;
});
document.getElementById("import-file-input").addEventListener("change", async (e) => {
  if (!e.target.files.length) return;
  const formData = new FormData();
  formData.append("file", e.target.files[0]);
  try {
    await api("/data/import", { method: "POST", body: formData });
    toast("Backup restored.", "success");
    loadDashboard();
  } catch (err) { toast(err.message, "error"); }
});
document.getElementById("delete-all-btn").addEventListener("click", async () => {
  if (!confirm("This will permanently delete ALL memories, documents, meetings, and images. Continue?")) return;
  await api("/data/delete_all", { method: "POST" });
  toast("All memories deleted.", "success");
  loadDashboard();
});

// ------------------------------------------------------------- performance

async function loadPerformance() {
  try {
    const d = await api("/models");
    const list = document.getElementById("model-status-list");
    const dev = d.device;
    let html = `<div class="list-item">
      <strong>Device:</strong> ${escapeHtml(dev.cpu)} · ${escapeHtml(dev.os_name)}<br>
      <strong>ONNX Runtime:</strong> ${dev.onnxruntime_installed ? "installed" : "not installed"}<br>
      <strong>NPU (Qualcomm) detected:</strong> ${dev.npu_provider_detected ? escapeHtml(dev.npu_provider_detected) : "Not detected on this machine"}
    </div>`;
    html += d.statuses.map(s => `
      <div class="list-item">
        <strong>${s.capability.toUpperCase()}</strong> — ${escapeHtml(s.model_name)}<br>
        Runtime: ${escapeHtml(s.runtime)} · Execution: ${escapeHtml(s.execution_provider)} · Installed: ${s.installed ? "yes" : "no"}
        ${s.notes ? `<div class="meta">${escapeHtml(s.notes)}</div>` : ""}
      </div>`).join("");
    list.innerHTML = html;
  } catch (e) { toast(e.message, "error"); }

  try {
    const hist = await api("/benchmark/history");
    renderBenchmarkResults(hist.length ? { history: hist } : null);
  } catch (e) { /* ignore, no history yet */ }
}

document.getElementById("run-benchmark-btn").addEventListener("click", async () => {
  const box = document.getElementById("benchmark-results");
  box.innerHTML = `<div class="empty-state">Running benchmark on this device…</div>`;
  try {
    const res = await api("/benchmark/run", { method: "POST" });
    renderBenchmarkResults(res);
  } catch (e) { toast(e.message, "error"); }
});

document.getElementById("export-benchmark-btn").addEventListener("click", () => {
  window.location.href = `${API}/benchmark/export?format=json`;
});

function renderBenchmarkResults(res) {
  const box = document.getElementById("benchmark-results");
  if (!res) {
    box.innerHTML = `<div class="empty-state">No benchmark run yet. Click "Start Benchmark".</div>`;
    return;
  }
  if (res.history) {
    box.innerHTML = res.history.map(h => `<div class="list-item">${h.name}: ${h.value} ${h.unit || ""} <span class="meta">${fmtDate(h.created_at)}</span></div>`).join("");
    return;
  }
  const rows = Object.entries(res).filter(([k, v]) => typeof v === "object" && v !== null && "value" in v);
  box.innerHTML = rows.map(([k, v]) => `<div class="list-item"><strong>${k}</strong>: ${v.value} ${v.unit || v.metric || ""}</div>`).join("")
    + `<div class="list-item">Execution provider: ${escapeHtml(res.end_to_end_query_latency ? res.end_to_end_query_latency.execution_provider : "unknown")}</div>`;
}

// ---------------------------------------------------------------- settings

async function loadSettings() {
  try {
    const d = await api("/dashboard");
    document.getElementById("settings-db-path").textContent = d.db_path;
  } catch (e) {}
}

// ------------------------------------------------------------ demo mode

document.getElementById("demo-mode-btn").addEventListener("click", async () => {
  toast("Loading synthetic demo data…");
  try {
    const res = await api("/demo/seed", { method: "POST" });
    toast(`Demo data loaded: ${res.documents.length} documents, ${res.meetings.length} meetings, ${res.images.length} images.`, "success");
    loadDashboard();
  } catch (e) { toast(e.message, "error"); }
});

// ------------------------------------------------------------- command palette

const COMMANDS = [
  { label: "Ask SnapMemory", action: () => showView("ask") },
  { label: "Import document", action: () => showView("documents") },
  { label: "Import meeting", action: () => showView("meetings") },
  { label: "Import image", action: () => showView("images") },
  { label: "Search memories", action: () => showView("memories") },
  { label: "Open Privacy Center", action: () => showView("privacy") },
  { label: "Run benchmark", action: () => showView("performance") },
  { label: "Settings", action: () => showView("settings") },
  { label: "Load demo data", action: () => document.getElementById("demo-mode-btn").click() },
];

const overlay = document.getElementById("command-palette-overlay");
const cmdkInput = document.getElementById("cmdk-input");
const cmdkList = document.getElementById("cmdk-list");
let cmdkActiveIndex = 0;

function openPalette() {
  overlay.classList.remove("hidden");
  cmdkInput.value = "";
  cmdkActiveIndex = 0;
  renderPalette("");
  setTimeout(() => cmdkInput.focus(), 10);
}
function closePalette() { overlay.classList.add("hidden"); }

function renderPalette(query) {
  const filtered = COMMANDS.filter(c => c.label.toLowerCase().includes(query.toLowerCase()));
  cmdkList.innerHTML = filtered.map((c, i) =>
    `<div class="cmdk-item ${i === cmdkActiveIndex ? 'active' : ''}" data-index="${i}">${c.label}</div>`
  ).join("") || `<div class="cmdk-item">No matching commands</div>`;
  cmdkList.querySelectorAll(".cmdk-item").forEach(el => {
    el.addEventListener("click", () => {
      filtered[Number(el.dataset.index)].action();
      closePalette();
    });
  });
  cmdkList._filtered = filtered;
}

cmdkInput.addEventListener("input", () => { cmdkActiveIndex = 0; renderPalette(cmdkInput.value); });
cmdkInput.addEventListener("keydown", (e) => {
  const filtered = cmdkList._filtered || [];
  if (e.key === "ArrowDown") { cmdkActiveIndex = Math.min(cmdkActiveIndex + 1, filtered.length - 1); renderPalette(cmdkInput.value); }
  else if (e.key === "ArrowUp") { cmdkActiveIndex = Math.max(cmdkActiveIndex - 1, 0); renderPalette(cmdkInput.value); }
  else if (e.key === "Enter") { if (filtered[cmdkActiveIndex]) { filtered[cmdkActiveIndex].action(); closePalette(); } }
  else if (e.key === "Escape") { closePalette(); }
});

document.getElementById("cmdk-trigger").addEventListener("click", openPalette);
overlay.addEventListener("click", (e) => { if (e.target === overlay) closePalette(); });

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    overlay.classList.contains("hidden") ? openPalette() : closePalette();
  }
});

// ---------------------------------------------------------------------- init

loadDashboard();
