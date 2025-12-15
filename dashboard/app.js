// PredictiveOps Dashboard (Polling)
// - polls /api/risk-stream
// - renders: gauge + timeline + log table
// - can send a "test spike" to /api/risk-event

const els = {
  apiBase: document.getElementById("apiBase"),
  resourceSelect: document.getElementById("resourceSelect"),
  historySize: document.getElementById("historySize"),
  historyLabel: document.getElementById("historyLabel"),
  pollMs: document.getElementById("pollMs"),
  pollLabel: document.getElementById("pollLabel"),
  btnPause: document.getElementById("btnPause"),
  btnTestSpike: document.getElementById("btnTestSpike"),

  riskPill: document.getElementById("riskPill"),
  timelinePill: document.getElementById("timelinePill"),
  logPill: document.getElementById("logPill"),

  latencyVal: document.getElementById("latencyVal"),
  errorVal: document.getElementById("errorVal"),
  nxVal: document.getElementById("nxVal"),
  healVal: document.getElementById("healVal"),
  lastTsVal: document.getElementById("lastTsVal"),

  logBody: document.getElementById("logBody"),
};

const gaugeCanvas = document.getElementById("gauge");
const gaugeCtx = gaugeCanvas.getContext("2d");

const timelineCanvas = document.getElementById("timeline");
const timelineCtx = timelineCanvas.getContext("2d");

const state = {
  paused: false,
  timer: null,
  events: [], // normalized events
};

// --------- Config helpers ----------
function defaultApiBase() {
  // If served from http://localhost:7072, relative will work.
  // If opened as file://, we default to localhost.
  const isHttp = window.location.protocol.startsWith("http");
  if (isHttp) return ""; // same origin
  return "http://localhost:7072";
}

function getApiBase() {
  return (els.apiBase.value || "").trim().replace(/\/+$/, "");
}

function apiUrl(path) {
  const base = getApiBase();
  if (!base) return path;
  return `${base}${path}`;
}

// --------- Normalization ----------
function coerceNumber(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function toIso(ts) {
  if (!ts) return null;
  // Accept ISO or anything Date can parse
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

function normalizeEvent(raw) {
  // Expected keys (best case):
  // id, resourceId, latency, errorRate, nxdomainAnomaly, risk, timestamp,
  // autoHealTriggered, autoHealAction, webhookStatus
  const resourceId = raw.resourceId || raw.resource || raw.target || "unknown";
  const latency = coerceNumber(raw.latency, null);
  const errorRate = coerceNumber(raw.errorRate, null);
  const nxdomainAnomaly = !!raw.nxdomainAnomaly;
  const risk = coerceNumber(raw.risk, 0);
  const timestamp = toIso(raw.timestamp || raw.ts || raw.time) || new Date().toISOString();
  const id = raw.id || `${resourceId}-${timestamp}`;

  return {
    id: String(id),
    resourceId: String(resourceId),
    latency,
    errorRate,
    nxdomainAnomaly,
    risk,
    timestamp,
    autoHealTriggered: !!raw.autoHealTriggered,
    autoHealAction: raw.autoHealAction || raw.action || "",
    webhookStatus: raw.webhookStatus || "",
    notes: raw.notes || "",
  };
}

function unwrapStreamPayload(payload) {
  // We support:
  // 1) [ ...events ]
  // 2) { items: [ ...events ] }
  // 3) { events: [ ...events ] }
  if (Array.isArray(payload)) return payload;
  if (payload && Array.isArray(payload.items)) return payload.items;
  if (payload && Array.isArray(payload.events)) return payload.events;
  return [];
}

// --------- Polling ----------
async function fetchStream() {
  const limit = Number(els.historySize.value || 60);
  const resource = els.resourceSelect.value;

  const qs = new URLSearchParams();
  qs.set("limit", String(limit));
  if (resource && resource !== "__all__") qs.set("resourceId", resource);

  const url = apiUrl(`/api/risk-stream?${qs.toString()}`);

  const res = await fetch(url, {
    method: "GET",
    headers: { "Accept": "application/json" },
  });

  if (!res.ok) {
    throw new Error(`risk-stream HTTP ${res.status}`);
  }

  const payload = await res.json();
  const rawEvents = unwrapStreamPayload(payload);
  const normalized = rawEvents.map(normalizeEvent);

  // De-dupe by id, keep newest
  const map = new Map();
  for (const ev of normalized) map.set(ev.id, ev);

  // Merge with existing (so timeline doesn’t flicker)
  for (const ev of state.events) map.set(ev.id, ev);

  // Sort by timestamp
  const merged = Array.from(map.values()).sort((a, b) => {
    const ta = new Date(a.timestamp).getTime();
    const tb = new Date(b.timestamp).getTime();
    return ta - tb;
  });

  // Keep last N
  state.events = merged.slice(-limit);
}

function startPolling() {
  stopPolling();
  const ms = Number(els.pollMs.value || 1000);

  state.timer = setInterval(async () => {
    if (state.paused) return;
    try {
      await fetchStream();
      refreshUI();
    } catch (e) {
      // Light-touch error display
      els.riskPill.textContent = `Risk: -- (stream error)`;
    }
  }, ms);
}

function stopPolling() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
}

// --------- UI Rendering ----------
function riskBand(r) {
  if (r >= 0.85) return "bad";
  if (r >= 0.65) return "warn";
  return "good";
}

function formatTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso || "";
  }
}

function getFilteredEvents() {
  const resource = els.resourceSelect.value;
  if (!resource || resource === "__all__") return state.events;
  return state.events.filter(e => e.resourceId === resource);
}

function lastEventForResource() {
  const evs = getFilteredEvents();
  return evs.length ? evs[evs.length - 1] : null;
}

function renderGauge(risk) {
  // 0..1 gauge
  const w = gaugeCanvas.width;
  const h = gaugeCanvas.height;
  const cx = w / 2;
  const cy = h * 0.92;
  const radius = Math.min(w * 0.42, h * 0.82);

  gaugeCtx.clearRect(0, 0, w, h);

  // track
  gaugeCtx.lineWidth = 18;
  gaugeCtx.lineCap = "round";

  const start = Math.PI * 1.08;
  const end = Math.PI * 1.92;

  // Base arc
  gaugeCtx.strokeStyle = "rgba(255,255,255,0.08)";
  gaugeCtx.beginPath();
  gaugeCtx.arc(cx, cy, radius, start, end);
  gaugeCtx.stroke();

  // Value arc
  const clamped = Math.max(0, Math.min(1, risk || 0));
  const valueEnd = start + (end - start) * clamped;

  const band = riskBand(clamped);
  let stroke = "rgba(108,242,184,0.85)";
  if (band === "warn") stroke = "rgba(255,202,92,0.9)";
  if (band === "bad") stroke = "rgba(255,79,123,0.9)";

  gaugeCtx.strokeStyle = stroke;
  gaugeCtx.beginPath();
  gaugeCtx.arc(cx, cy, radius, start, valueEnd);
  gaugeCtx.stroke();

  // Needle
  const angle = valueEnd;
  const nx = cx + Math.cos(angle) * (radius - 6);
  const ny = cy + Math.sin(angle) * (radius - 6);

  gaugeCtx.lineWidth = 3;
  gaugeCtx.strokeStyle = "rgba(245,247,255,0.9)";
  gaugeCtx.beginPath();
  gaugeCtx.moveTo(cx, cy);
  gaugeCtx.lineTo(nx, ny);
  gaugeCtx.stroke();

  // Center dot
  gaugeCtx.fillStyle = "rgba(245,247,255,0.95)";
  gaugeCtx.beginPath();
  gaugeCtx.arc(cx, cy, 5, 0, Math.PI * 2);
  gaugeCtx.fill();

  // Text
  gaugeCtx.fillStyle = "rgba(245,247,255,0.95)";
  gaugeCtx.font = "700 30px system-ui, -apple-system, Segoe UI, sans-serif";
  gaugeCtx.textAlign = "center";
  gaugeCtx.fillText((clamped * 100).toFixed(0) + "%", cx, h * 0.58);

  gaugeCtx.fillStyle = "rgba(167,175,199,0.95)";
  gaugeCtx.font = "600 12px system-ui, -apple-system, Segoe UI, sans-serif";
  gaugeCtx.fillText("Risk Score", cx, h * 0.70);
}

function renderTimeline(events) {
  const w = timelineCanvas.width;
  const h = timelineCanvas.height;
  timelineCtx.clearRect(0, 0, w, h);

  // padding
  const padL = 46;
  const padR = 18;
  const padT = 14;
  const padB = 28;

  // grid bg
  timelineCtx.fillStyle = "rgba(255,255,255,0.02)";
  timelineCtx.fillRect(0, 0, w, h);

  // axes
  timelineCtx.strokeStyle = "rgba(255,255,255,0.10)";
  timelineCtx.lineWidth = 1;
  timelineCtx.beginPath();
  timelineCtx.moveTo(padL, padT);
  timelineCtx.lineTo(padL, h - padB);
  timelineCtx.lineTo(w - padR, h - padB);
  timelineCtx.stroke();

  // y labels (0, .5, 1.0)
  timelineCtx.fillStyle = "rgba(167,175,199,0.9)";
  timelineCtx.font = "600 11px system-ui, -apple-system, Segoe UI, sans-serif";
  timelineCtx.textAlign = "right";
  const yFor = (v) => {
    const innerH = (h - padB) - padT;
    return (h - padB) - (innerH * v);
  };
  [1.0, 0.5, 0.0].forEach(v => {
    const y = yFor(v);
    timelineCtx.fillText(v.toFixed(1), padL - 8, y + 4);
    timelineCtx.strokeStyle = "rgba(255,255,255,0.06)";
    timelineCtx.beginPath();
    timelineCtx.moveTo(padL, y);
    timelineCtx.lineTo(w - padR, y);
    timelineCtx.stroke();
  });

  if (!events.length) {
    timelineCtx.fillStyle = "rgba(167,175,199,0.9)";
    timelineCtx.textAlign = "left";
    timelineCtx.fillText("No events yet. Hit 'Send Test Spike' or POST to /api/risk-event.", padL + 10, padT + 18);
    return;
  }

  const innerW = (w - padR) - padL;
  const xs = events.map((_, i) => padL + (innerW * (i / Math.max(1, events.length - 1))));
  const ys = events.map(e => yFor(Math.max(0, Math.min(1, e.risk))));

  // line
  timelineCtx.strokeStyle = "rgba(79,156,255,0.9)";
  timelineCtx.lineWidth = 2;
  timelineCtx.beginPath();
  timelineCtx.moveTo(xs[0], ys[0]);
  for (let i = 1; i < xs.length; i++) timelineCtx.lineTo(xs[i], ys[i]);
  timelineCtx.stroke();

  // points
  for (let i = 0; i < events.length; i++) {
    const r = events[i].risk;
    const band = riskBand(r);
    let fill = "rgba(108,242,184,0.95)";
    if (band === "warn") fill = "rgba(255,202,92,0.95)";
    if (band === "bad") fill = "rgba(255,79,123,0.95)";
    timelineCtx.fillStyle = fill;
    timelineCtx.beginPath();
    timelineCtx.arc(xs[i], ys[i], 3.2, 0, Math.PI * 2);
    timelineCtx.fill();
  }

  // x labels (first and last time)
  timelineCtx.fillStyle = "rgba(167,175,199,0.9)";
  timelineCtx.textAlign = "left";
  timelineCtx.fillText(new Date(events[0].timestamp).toLocaleTimeString(), padL, h - 10);
  timelineCtx.textAlign = "right";
  timelineCtx.fillText(new Date(events[events.length - 1].timestamp).toLocaleTimeString(), w - padR, h - 10);
}

function renderLog(events) {
  const rows = events.slice().reverse().slice(0, 35); // newest first

  els.logBody.innerHTML = rows.map(ev => {
    const band = riskBand(ev.risk);
    const cls = band === "bad" ? "rowBad" : band === "warn" ? "rowWarn" : "rowGood";

    const riskBadge = band === "bad"
      ? `<span class="badge bad">${ev.risk.toFixed(2)}</span>`
      : band === "warn"
        ? `<span class="badge warn">${ev.risk.toFixed(2)}</span>`
        : `<span class="badge good">${ev.risk.toFixed(2)}</span>`;

    const healBadge = ev.autoHealTriggered
      ? `<span class="badge bad">true</span>`
      : `<span class="badge">false</span>`;

    const nx = ev.nxdomainAnomaly ? "true" : "false";
    const notes = [
      ev.autoHealAction ? `action=${ev.autoHealAction}` : "",
      ev.webhookStatus ? `webhook=${ev.webhookStatus}` : "",
      ev.notes ? ev.notes : "",
    ].filter(Boolean).join(" • ");

    return `
      <tr class="${cls}">
        <td>${formatTime(ev.timestamp)}</td>
        <td>${escapeHtml(ev.resourceId)}</td>
        <td>${riskBadge}</td>
        <td>${ev.latency ?? "--"}</td>
        <td>${ev.errorRate ?? "--"}</td>
        <td>${nx}</td>
        <td>${healBadge}</td>
        <td>${escapeHtml(notes)}</td>
      </tr>
    `;
  }).join("");
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function refreshResourceSelect() {
  const current = els.resourceSelect.value;

  const resources = Array.from(new Set(state.events.map(e => e.resourceId))).sort();
  const options = [`<option value="__all__">All</option>`].concat(
    resources.map(r => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`)
  ).join("");

  els.resourceSelect.innerHTML = options;

  // restore selection if still present
  const exists = resources.includes(current);
  els.resourceSelect.value = exists ? current : "__all__";
}

function refreshUI() {
  refreshResourceSelect();

  const evs = getFilteredEvents();
  const last = lastEventForResource();

  els.timelinePill.textContent = `${evs.length} pts`;
  els.logPill.textContent = `${evs.length} events`;

  if (!last) {
    els.riskPill.textContent = "Risk: --";
    els.latencyVal.textContent = "--";
    els.errorVal.textContent = "--";
    els.nxVal.textContent = "--";
    els.healVal.textContent = "--";
    els.lastTsVal.textContent = "--";
    renderGauge(0);
    renderTimeline([]);
    renderLog([]);
    return;
  }

  const band = riskBand(last.risk);
  const bandText = band === "bad" ? "CRITICAL" : band === "warn" ? "ELEVATED" : "NORMAL";
  els.riskPill.textContent = `Risk: ${(last.risk * 100).toFixed(0)}% (${bandText})`;

  els.latencyVal.textContent = (last.latency ?? "--") + (last.latency != null ? " ms" : "");
  els.errorVal.textContent = (last.errorRate ?? "--") + (last.errorRate != null ? "%" : "");
  els.nxVal.textContent = last.nxdomainAnomaly ? "true" : "false";
  els.healVal.textContent = last.autoHealTriggered ? "true" : "false";
  els.lastTsVal.textContent = formatTime(last.timestamp);

  renderGauge(last.risk);
  renderTimeline(evs);
  renderLog(evs);
}

// --------- Actions ----------
async function sendTestSpike() {
  // This hits your existing RiskEngine: POST /api/risk-event
  const resource = els.resourceSelect.value !== "__all__"
    ? els.resourceSelect.value
    : "azure-webapp/prod-api";

  const payload = {
    resourceId: resource,
    latency: 650,
    errorRate: 3.2,
    nxdomainAnomaly: false
  };

  const url = apiUrl("/api/risk-event");
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`risk-event HTTP ${res.status} ${t}`);
  }

  // Pull response (not required, but useful)
  return await res.json().catch(() => ({}));
}

// --------- Wire up ----------
function init() {
  els.apiBase.value = defaultApiBase();

  els.historyLabel.textContent = els.historySize.value;
  els.pollLabel.textContent = els.pollMs.value;

  els.historySize.addEventListener("input", () => {
    els.historyLabel.textContent = els.historySize.value;
  });
  els.pollMs.addEventListener("input", () => {
    els.pollLabel.textContent = els.pollMs.value;
  });

  els.historySize.addEventListener("change", async () => {
    try {
      await fetchStream();
      refreshUI();
    } catch {}
  });

  els.pollMs.addEventListener("change", () => startPolling());
  els.resourceSelect.addEventListener("change", () => refreshUI());

  els.btnPause.addEventListener("click", () => {
    state.paused = !state.paused;
    els.btnPause.textContent = state.paused ? "Resume" : "Pause";
  });

  els.btnTestSpike.addEventListener("click", async () => {
    els.btnTestSpike.disabled = true;
    els.btnTestSpike.textContent = "Sending…";
    try {
      await sendTestSpike();
      // fetch immediately instead of waiting for next tick
      await fetchStream();
      refreshUI();
    } catch (e) {
      alert(`Test spike failed: ${e.message}`);
    } finally {
      els.btnTestSpike.disabled = false;
      els.btnTestSpike.textContent = "Send Test Spike";
    }
  });

  document.getElementById("year").textContent = String(new Date().getFullYear());

  // initial draw
  renderGauge(0);
  renderTimeline([]);
  renderLog([]);
  startPolling();
}

init();
