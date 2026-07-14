// ── 1. Constants & State ───────────────────────────────────────────────────────
const API_BASE = "https://sgbau-results.onrender.com";

let currentWatcherId = null;   // UUID of the active watcher
let sseSource        = null;   // The active EventSource object
let probeCount       = 0;      // Probes shown in log counter
let resultCount      = 0;      // Student results received during batch fetch
let wAllRows         = [];     // All result rows (for filter rebuild)
let wPillFilter      = "all";  // Active pill filter value

// ── 2. Utility Helpers ────────────────────────────────────────────────────────
function wShow(id) { document.getElementById(id)?.classList.remove("hidden"); }
function wHide(id) { document.getElementById(id)?.classList.add("hidden"); }

// ── 3. PIN Verification ───────────────────────────────────────────────────────

async function verifyPin() {
  const input  = document.getElementById("pin-input");
  const btn    = document.getElementById("pin-submit-btn");
  const errEl  = document.getElementById("pin-error");
  const pin    = input.value.trim();

  if (!pin) {
    errEl.textContent = "Please enter a PIN.";
    wShow("pin-error");
    return;
  }

  btn.disabled  = true;
  btn.textContent = "Verifying…";
  wHide("pin-error");

  try {
    const res  = await fetch(`${API_BASE}/api/watch/verify-pin`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ pin }),
    });
    const data = await res.json();

    if (data.valid) {
      // Fade out overlay, reveal page
      const overlay = document.getElementById("pin-overlay");
      overlay.style.transition = "opacity 0.35s ease";
      overlay.style.opacity    = "0";
      setTimeout(() => overlay.classList.add("hidden"), 350);

      // Show all hidden page sections
      ["w-header", "w-main", "w-footer"].forEach(id => wShow(id));

      initPage();
    } else {
      errEl.textContent = "Incorrect PIN. Try again.";
      wShow("pin-error");
      input.value = "";
      input.focus();
      // Shake the modal
      const modal = document.querySelector(".pin-modal");
      modal.classList.add("shake");
      setTimeout(() => modal.classList.remove("shake"), 600);
      btn.disabled    = false;
      btn.textContent = "Unlock";
    }
  } catch (err) {
    errEl.textContent = "Connection error. Is the server awake?";
    wShow("pin-error");
    btn.disabled    = false;
    btn.textContent = "Unlock";
  }
}

// Enter key → verifyPin (declared inline in HTML too, but also here for safety)
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("pin-input")
    .addEventListener("keydown", e => { if (e.key === "Enter") verifyPin(); });
});

// ── 4. Page Init ──────────────────────────────────────────────────────────────

async function initPage() {
  // Read URL params and pre-fill roll fields
  const params    = new URLSearchParams(window.location.search);
  const startRoll = params.get("start") || "";
  const endRoll   = params.get("end")   || "";

  if (startRoll) document.getElementById("w-start-roll").value    = startRoll;
  if (endRoll)   document.getElementById("w-end-roll").value      = endRoll;
  if (startRoll) document.getElementById("w-sentinel-roll").value = startRoll;

  // Check if a watcher is already running on the server
  try {
    const res  = await fetch(`${API_BASE}/api/watch/current`);
    const data = await res.json();
    if (data.active) {
      resumeWatcherUI(data);
    }
  } catch (_) {
    // Server unreachable — user can still start a new watcher manually
  }
}

function resumeWatcherUI(data) {
  currentWatcherId = data.watcher_id;

  updateStatusBanner(data.status, `Next probe in ${data.interval_minutes} min`);
  wShow("watcher-status-banner");
  wShow("activity-log-card");

  addLogEntry("probe",
    `⟳ Reconnected to running watcher — ${data.dept_name || ""} | ` +
    `Probe count: ${data.probe_count ?? 0} | Status: ${data.status}`
  );

  wHide("w-start-btn");
  wShow("w-cancel-btn");

  connectSSE(data.watcher_id);
}

// ── 5. Start & Cancel ─────────────────────────────────────────────────────────

async function startWatcher() {
  // Collect and validate fields
  const deptName    = document.getElementById("w-dept-name").value.trim();
  const startRoll   = document.getElementById("w-start-roll").value.trim();
  const endRoll     = document.getElementById("w-end-roll").value.trim();
  const sentinelRaw = document.getElementById("w-sentinel-roll").value.trim();
  const sentinel    = sentinelRaw || startRoll;  // defaults to startRoll
  const interval    = parseInt(document.getElementById("w-interval").value, 10);
  const session     = document.getElementById("w-session").value;
  const semCode     = document.getElementById("w-sem-code").value;
  const resultType  = document.getElementById("w-result-type").value;
  const courseCd    = document.getElementById("w-course-cd").value.trim();

  // Validation
  const required = [
    ["w-dept-name",  deptName,   "Department Name"],
    ["w-start-roll", startRoll,  "Start Roll Number"],
    ["w-end-roll",   endRoll,    "End Roll Number"],
    ["w-course-cd",  courseCd,   "Course Code"],
  ];
  for (const [id, val, label] of required) {
    if (!val) {
      const el = document.getElementById(id);
      el.style.borderColor = "var(--fail)";
      el.focus();
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => el.style.borderColor = "", 2000);
      alert(`Please fill in "${label}".`);
      return;
    }
  }
  if (isNaN(interval) || interval < 5 || interval > 1440) {
    alert("Check interval must be between 5 and 1440 minutes.");
    document.getElementById("w-interval").focus();
    return;
  }

  // Disable button and show spinner
  const startBtn  = document.getElementById("w-start-btn");
  const startText = document.getElementById("w-start-btn-text");
  startBtn.disabled  = true;
  startText.textContent = "Starting…";

  const body = {
    dept_name:        deptName,
    start_roll:       startRoll,
    end_roll:         endRoll,
    sentinel_roll:    sentinel,
    interval_minutes: interval,
    session,
    course_type:      "UG",
    result_type:      resultType,
    sem_code:         semCode,
    course_cd:        courseCd,
  };

  try {
    const res = await fetch(`${API_BASE}/api/watch/start`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });

    if (res.status === 202) {
      const data       = await res.json();
      currentWatcherId = data.watcher_id;

      updateStatusBanner("WAITING", `First probe in ${interval} minutes`);
      wShow("watcher-status-banner");
      wShow("activity-log-card");
      addLogEntry("probe",
        `▶ Watcher started. Sentinel: ${sentinel}. First probe in ${interval} minutes.`
      );

      wHide("w-start-btn");
      wShow("w-cancel-btn");

      connectSSE(currentWatcherId);

    } else if (res.status === 409) {
      alert("A watcher is already running. Refresh the page to reconnect to it.");
      startBtn.disabled   = false;
      startText.textContent = "Start Watching";

    } else {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
  } catch (err) {
    alert(`❌ Error starting watcher: ${err.message}`);
    startBtn.disabled   = false;
    startText.textContent = "Start Watching";
  }
}

async function cancelWatcher() {
  if (!currentWatcherId) return;

  const confirmed = window.confirm("Are you sure you want to stop the watcher?");
  if (!confirmed) return;

  const cancelBtn = document.getElementById("w-cancel-btn");
  cancelBtn.disabled = true;

  try {
    await fetch(`${API_BASE}/api/watch/cancel/${currentWatcherId}`, {
      method: "POST",
    });
    // The SSE stream will receive { type: "cancelled" } and call handleCancelled()
  } catch (err) {
    alert(`Could not send cancel signal: ${err.message}`);
    cancelBtn.disabled = false;
  }
}

// ── 6. SSE Consumer ───────────────────────────────────────────────────────────

function connectSSE(watcherId) {
  if (sseSource) {
    sseSource.close();
    sseSource = null;
  }

  sseSource           = new EventSource(`${API_BASE}/api/watch/status/${watcherId}`);
  sseSource.onmessage = handleWatcherEvent;
  sseSource.onerror   = handleSSEError;
}

function handleSSEError() {
  if (sseSource) { sseSource.close(); sseSource = null; }
  if (!currentWatcherId) return;

  addLogEntry("error", "⚠ Connection lost. Reconnecting in 5 seconds…");
  setTimeout(() => connectSSE(currentWatcherId), 5000);
}

function handleWatcherEvent(event) {
  let data;
  try { data = JSON.parse(event.data); } catch { return; }

  switch (data.type) {
    case "probe":
      if (data.found) {
        addLogEntry("found", `🎉 ${data.message}`);
        updateStatusBanner("FETCHING", "Fetching all results now…");
      } else {
        probeCount++;
        addLogEntry("probe", data.message);
        updateProbeCounter(probeCount);
        updateStatusBanner("WAITING",
          data.next_probe_in_minutes
            ? `Next probe in ${data.next_probe_in_minutes} min`
            : "Waiting…"
        );
      }
      break;

    case "probe_error":
      addLogEntry("error", data.message);
      break;

    case "fetching":
      addLogEntry("fetching", data.message);
      wShow("w-progress-card");
      document.getElementById("w-progress-label").textContent = data.message;
      break;

    case "result":
      resultCount++;
      wAppendResultRow(data);
      wUpdateProgress(resultCount);
      wShow("w-results-card");
      break;

    case "emailed":
      addLogEntry("emailed", `📬 ${data.message}`);
      break;

    case "done":
      handleDone(data);
      break;

    case "cancelled":
      handleCancelled();
      break;

    case "error":
      addLogEntry("error", `⚠ ${data.message}`);
      break;

    case "timeout":
      // Browser SSE auto-reconnects — nothing to do
      break;

    default:
      break;
  }
}

// ── 7. Log Panel ──────────────────────────────────────────────────────────────

function addLogEntry(type, message) {
  const log  = document.getElementById("activity-log");
  const time = new Date().toLocaleTimeString("en-IN", {
    hour: "2-digit", minute: "2-digit",
  });

  const entry = document.createElement("div");
  entry.className = `log-entry log-${type}`;
  entry.innerHTML = `
    <span class="log-time">${time}</span>
    <span class="log-msg">${escapeHtml(message)}</span>
  `;
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function updateProbeCounter(count) {
  const el = document.getElementById("probe-counter");
  if (el) el.textContent = `${count} probe${count !== 1 ? "s" : ""} completed`;
}

// ── 8. Status Banner ──────────────────────────────────────────────────────────

function updateStatusBanner(status, detail) {
  const dot    = document.getElementById("status-dot");
  const text   = document.getElementById("status-text");
  const detEl  = document.getElementById("status-detail");

  if (dot) {
    dot.dataset.status = status;
  }
  if (text)  text.textContent  = status;
  if (detEl) detEl.textContent = detail || "";
}

// ── 9. Done & Cancelled Handlers ──────────────────────────────────────────────

function handleDone(data) {
  if (sseSource) { sseSource.close(); sseSource = null; }

  updateStatusBanner("DONE", "All results fetched and sent!");
  addLogEntry("done", "✅ Done! Results sent via Telegram. Download CSV below.");

  wShow("w-download-btn");
  wHide("w-cancel-btn");

  // Re-show start button so admin can start a new watch
  const startBtn  = document.getElementById("w-start-btn");
  const startText = document.getElementById("w-start-btn-text");
  startBtn.disabled   = false;
  startText.textContent = "Start New Watch";
  wShow("w-start-btn");

  // Populate summary card
  if (data.summary && data.summary.length) {
    wRenderSummary(data.summary);
    wShow("w-summary-card");
  }
}

function handleCancelled() {
  if (sseSource) { sseSource.close(); sseSource = null; }

  updateStatusBanner("CANCELLED", "Watcher stopped by admin.");
  addLogEntry("cancelled", "🛑 Watcher cancelled.");

  wHide("w-cancel-btn");

  const startBtn  = document.getElementById("w-start-btn");
  const startText = document.getElementById("w-start-btn-text");
  startBtn.disabled   = false;
  startText.textContent = "Start New Watch";
  wShow("w-start-btn");

  // Show download button if any results were fetched before cancel
  if (resultCount > 0) {
    wShow("w-download-btn");
  }
}

// ── 10. Results Table ─────────────────────────────────────────────────────────

function wAppendResultRow(msg) {
  const resultText = (msg.result || "").toUpperCase();
  const badgeClass =
    resultText === "PASS" ? "pass" :
    resultText === "FAIL" ? "fail" :
    resultText === "ATKT" ? "atkt" : "other";

  const rowData = {
    roll: msg.roll || "", name: msg.name || "—",
    result: msg.result || "—", sgpa: msg.sgpa || "—",
    status: msg.status || "", badgeClass, resultText,
  };
  wAllRows.push(rowData);

  document.getElementById("w-results-count-badge").textContent = wAllRows.length;
  if (wRowMatchesFilter(rowData)) wRenderRow(rowData);
}

function wRenderRow(d) {
  const tbody = document.getElementById("w-results-body");
  const tr    = document.createElement("tr");
  tr.dataset.result = d.resultText;
  tr.dataset.name   = d.name.toLowerCase();
  tr.dataset.roll   = d.roll.toLowerCase();
  tr.innerHTML = `
    <td><code style="font-size:12px;color:var(--indigo-400)">${d.roll}</code></td>
    <td>${d.name}</td>
    <td><span class="badge ${d.badgeClass}">${d.result}</span></td>
    <td>${d.sgpa}</td>
    <td><span style="font-size:12px;color:var(--text-muted)">${d.status}</span></td>
  `;
  tbody.appendChild(tr);
}

function wRowMatchesFilter(d) {
  const q      = (document.getElementById("w-filter-input")?.value || "").toLowerCase();
  const textOk = !q || d.name.toLowerCase().includes(q) || d.roll.toLowerCase().includes(q);
  const pillOk = wPillFilter === "all" || d.resultText.toLowerCase() === wPillFilter;
  return textOk && pillOk;
}

function filterWatcherTable() { wRebuildTable(); }

function setWatcherPill(val, el) {
  wPillFilter = val;
  document.querySelectorAll("#w-filter-pills .pill").forEach(p => p.classList.remove("active"));
  el.classList.add("active");
  wRebuildTable();
}

function wRebuildTable() {
  document.getElementById("w-results-body").innerHTML = "";
  wAllRows.filter(wRowMatchesFilter).forEach(wRenderRow);
}

// ── 11. Progress Bar ──────────────────────────────────────────────────────────

function wUpdateProgress(count) {
  document.getElementById("w-progress-count").textContent = count;
  // Indeterminate progress during batch fetch (we don't know total upfront in all cases)
  const fill = document.getElementById("w-progress-fill");
  if (fill) {
    // Animate toward 95% asymptotically — will jump to 100% on done
    const pct = Math.min(95, Math.round((count / Math.max(count, 10)) * 100));
    fill.style.width = `${pct}%`;
  }
  document.getElementById("w-progress-label").textContent =
    `Fetching results… ${count} received`;
}

// ── 12. Summary Card ──────────────────────────────────────────────────────────

function wRenderSummary(summaries) {
  const el = document.getElementById("w-summary-body");
  if (!summaries || !summaries.length) { el.textContent = "No summary."; return; }

  el.innerHTML = summaries.map(s => {
    const pct    = s.total > 0 ? Math.round((s.passed / s.total) * 100) : 0;
    const failed = s.total - s.passed;
    return `
      <div class="summary-item">
        <div class="summary-dept">${s.name}</div>
        <div class="summary-stat">📚 ${s.total} students &nbsp;·&nbsp; ${s.range || ""}</div>
        <div class="summary-stat" style="color:var(--pass);margin-top:6px">✓ ${s.passed} passed (${pct}%)</div>
        <div class="summary-stat" style="color:var(--fail)">✗ ${failed} failed</div>
        <div class="summary-bar-track">
          <div class="summary-bar-fill" style="width:${pct}%"></div>
        </div>
      </div>`;
  }).join("");
}

// ── 13. CSV Download ──────────────────────────────────────────────────────────

function downloadWatcherCSV() {
  if (!currentWatcherId) return;
  // Reuses the existing /api/download/{id} endpoint — JOBS dict was populated
  // by run_batch_fetch() (Phase 8 Option A)
  window.open(`${API_BASE}/api/download/${currentWatcherId}`, "_blank");
}
