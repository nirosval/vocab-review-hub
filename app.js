// ---------- State ----------
let manifestItems = [];      // from data/manifest_vocab.json
let statusData = { history: [], latest: {} };
let currentFilter = "all";
let currentSearch = "";
let selectedKey = null;      // "<course>::<lecture>"

const COMPONENTS = ["video", "audio", "script"];

// ---------- Boot ----------
init();

async function init() {
  restoreCheckerName();
  wireGlobalControls();
  try {
    const [manifestRes, statusRes] = await Promise.all([
      fetch("data/manifest_vocab.json").then((r) => r.json()),
      fetch("/api/status").then((r) => (r.ok ? r.json() : { history: [], latest: {} })),
    ]);
    manifestItems = manifestRes.items || [];
    statusData = statusRes;
    renderQueue();
  } catch (e) {
    document.getElementById("queueList").innerHTML =
      `<div class="queue-empty">Couldn't load the queue. ${escapeHtml(String(e))}</div>`;
  }
}

function restoreCheckerName() {
  const saved = localStorage.getItem("checkerName");
  if (saved) document.getElementById("checkerName").value = saved;
  document.getElementById("checkerName").addEventListener("input", (e) => {
    localStorage.setItem("checkerName", e.target.value.trim());
  });
}

function wireGlobalControls() {
  document.getElementById("searchBox").addEventListener("input", (e) => {
    currentSearch = e.target.value.trim().toLowerCase();
    renderQueue();
  });
  document.getElementById("filterChips").addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    currentFilter = btn.dataset.filter;
    renderQueue();
  });
}

// ---------- Status helpers ----------

function lectureKey(item) {
  return `${item.course}::${item.lecture}`;
}

function overallStatus(item) {
  // "Needs revision" wins if any component needs it; "Passed" only if every
  // component that has ever been checked is Passed; otherwise Not started.
  let anyChecked = false;
  let anyRevision = false;
  let allPassed = true;
  for (const comp of COMPONENTS) {
    const entry = statusData.latest[`${item.course}::${item.lecture}::${comp}`];
    if (!entry) { allPassed = false; continue; }
    anyChecked = true;
    if (entry.status === "Needs Revision") anyRevision = true;
    if (entry.status !== "Passed") allPassed = false;
  }
  if (anyRevision) return "needs-revision";
  if (anyChecked && allPassed) return "passed";
  return "not-started";
}

function statusLabel(key) {
  return { "not-started": "Not started", "needs-revision": "Needs revision", passed: "Passed" }[key];
}

// ---------- Queue rendering ----------

function renderQueue() {
  const list = document.getElementById("queueList");
  const filtered = manifestItems.filter((item) => {
    const st = overallStatus(item);
    if (currentFilter !== "all" && st !== currentFilter) return false;
    if (currentSearch) {
      const hay = `${item.course} ${item.lecture} ${item.month || ""}`.toLowerCase();
      if (!hay.includes(currentSearch)) return false;
    }
    return true;
  });

  document.getElementById("queueCount").textContent =
    `${filtered.length} lecture${filtered.length === 1 ? "" : "s"}`;

  if (!filtered.length) {
    list.innerHTML = `<div class="queue-empty">No lectures match this view.</div>`;
    return;
  }

  list.innerHTML = filtered
    .map((item) => {
      const key = lectureKey(item);
      const st = overallStatus(item);
      const selected = key === selectedKey ? "selected" : "";
      return `
        <button class="queue-item ${selected}" data-key="${escapeHtml(key)}">
          <div class="queue-item-top">
            <span class="queue-item-lecture">${escapeHtml(item.lecture || item.title || "")}</span>
            <span class="badge ${st}">${statusLabel(st)}</span>
          </div>
          <div class="queue-item-course">${escapeHtml(item.course)}</div>
        </button>`;
    })
    .join("");

  list.querySelectorAll(".queue-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedKey = btn.dataset.key;
      renderQueue();
      openReview(selectedKey);
    });
  });
}

// ---------- Review panel ----------

async function openReview(key) {
  const item = manifestItems.find((it) => lectureKey(it) === key);
  const pane = document.getElementById("reviewPane");
  if (!item) return;

  pane.innerHTML = `
    <div class="review-header">
      <p class="review-eyebrow">${escapeHtml(item.month || "")}</p>
      <h2 class="review-title">${escapeHtml(item.lecture || item.title || "")} — ${escapeHtml(item.course)}</h2>
    </div>

    <div class="review-grid">
      <div class="panel">
        <h3>Video</h3>
        <video id="videoPlayer" controls></video>
        <p class="media-status" id="videoStatus">Loading link…</p>
      </div>
      <div class="panel">
        <h3>Audio</h3>
        <audio id="audioPlayer" controls></audio>
        <p class="media-status" id="audioStatus">Loading link…</p>
      </div>
    </div>

    <div class="panel" style="margin-bottom:20px;">
      <h3>Script (List intro)</h3>
      <div class="script-text">${
        item.script_intro
          ? escapeHtml(item.script_intro)
          : `<span class="script-empty">No script intro attached to this lecture yet.</span>`
      }</div>
    </div>

    <div class="check-form">
      <h3 style="margin-bottom:14px;">Log a check</h3>
      <div class="check-row">
        <div class="field">
          <label for="componentSelect">Component</label>
          <select id="componentSelect">
            <option value="video">Video</option>
            <option value="audio">Audio</option>
            <option value="script">Script</option>
          </select>
        </div>
        <div class="field">
          <label for="statusSelect">Status</label>
          <select id="statusSelect">
            <option value="Passed">Passed</option>
            <option value="Needs Revision">Needs Revision</option>
          </select>
        </div>
      </div>
      <div class="field" style="margin-bottom:12px;">
        <label for="notesInput">Notes</label>
        <textarea id="notesInput" placeholder="e.g. Bad audio sync at 0:27"></textarea>
      </div>
      <div class="submit-row">
        <button class="submit-btn" id="submitCheck">Save check</button>
        <span class="form-note" id="formNote"></span>
      </div>
    </div>

    <div class="history-panel">
      <h3>History</h3>
      <div class="history-list" id="historyList"></div>
    </div>
  `;

  renderHistory(item);
  wireCheckForm(item);
  loadMedia(item);
}

function renderHistory(item) {
  const rows = statusData.history
    .filter((h) => h.course === item.course && h.lecture === item.lecture)
    .slice()
    .reverse();
  const box = document.getElementById("historyList");
  if (!rows.length) {
    box.innerHTML = `<div class="script-empty" style="font-size:13px;">No checks logged yet.</div>`;
    return;
  }
  box.innerHTML = rows
    .map(
      (r) => `
      <div class="history-row">
        <span class="hist-time">${escapeHtml(formatTime(r.timestamp))}</span>
        <span>${escapeHtml(r.component)}</span>
        <span class="badge ${r.status === "Passed" ? "passed" : "needs-revision"}">${escapeHtml(r.status)}</span>
        <span class="hist-notes">${escapeHtml(r.notes || "—")}</span>
        <span>${escapeHtml(r.checker)}</span>
      </div>`
    )
    .join("");
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

async function loadMedia(item) {
  mintLink(item.code, item.video_fileid, "videoPlayer", "videoStatus");
  if (item.audio_fileid) {
    mintLink(item.code, item.audio_fileid, "audioPlayer", "audioStatus");
  } else {
    document.getElementById("audioStatus").textContent = "No audio file found for this lecture.";
  }
}

async function mintLink(code, fileid, playerId, statusId) {
  const statusEl = document.getElementById(statusId);
  const playerEl = document.getElementById(playerId);
  if (!fileid) {
    statusEl.textContent = "No file id in manifest.";
    return;
  }
  try {
    const r = await fetch("/api/getlink", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, fileid }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "link mint failed");
    playerEl.src = data.url;
    statusEl.textContent = "";
  } catch (e) {
    statusEl.textContent = `Couldn't load: ${e.message}`;
  }
}

function wireCheckForm(item) {
  document.getElementById("submitCheck").addEventListener("click", async () => {
    const checker = document.getElementById("checkerName").value.trim();
    const component = document.getElementById("componentSelect").value;
    const status = document.getElementById("statusSelect").value;
    const notes = document.getElementById("notesInput").value.trim();
    const note = document.getElementById("formNote");
    const btn = document.getElementById("submitCheck");

    if (!checker) {
      note.textContent = "Enter your name at the top first.";
      note.className = "form-note error";
      return;
    }

    btn.disabled = true;
    note.textContent = "Saving…";
    note.className = "form-note";

    try {
      const r = await fetch("/api/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          month: item.month,
          course: item.course,
          lecture: item.lecture,
          checker,
          component,
          status,
          notes,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error ? JSON.stringify(data.error) : "save failed");

      // reflect locally without a full refetch
      const entry = { timestamp: new Date().toISOString(), month: item.month, course: item.course, lecture: item.lecture, checker, component, status, notes };
      statusData.history.push(entry);
      statusData.latest[`${item.course}::${item.lecture}::${component}`] = entry;

      note.textContent = "Saved.";
      note.className = "form-note success";
      document.getElementById("notesInput").value = "";
      renderHistory(item);
      renderQueue();
    } catch (e) {
      note.textContent = `Couldn't save: ${e.message}`;
      note.className = "form-note error";
    } finally {
      btn.disabled = false;
    }
  });
}

// ---------- Utils ----------

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
