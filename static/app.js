"use strict";

const form = document.querySelector("#scan-form");
const fileInput = document.querySelector("#torrent-file");
const fileLabel = document.querySelector("#file-label");
const fileSubtitle = document.querySelector("#file-subtitle");
const scanButton = document.querySelector("#scan-button");
const statusMessage = document.querySelector("#status-message");
const reportSection = document.querySelector("#report-section");
const historyTable = document.querySelector("#history-table");
const dropZone = document.querySelector(".drop-zone");
const riskMeter = document.querySelector("#risk-meter");

fileInput.addEventListener("change", () => {
  const file = fileInput.files && fileInput.files[0];
  dropZone.classList.toggle("has-file", Boolean(file));
  if (file) {
    fileLabel.textContent = file.name;
    fileSubtitle.textContent = "Ready to analyze (" + formatBytes(file.size) + ")";
  } else {
    fileLabel.textContent = "Choose a torrent file";
    fileSubtitle.textContent = "Click to browse or drop a file here";
  }
});

// Drag and drop onto the scan area (UI only: it fills the same file input).
["dragenter", "dragover"].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragover");
  });
});
["dragleave", "dragend"].forEach((name) => {
  dropZone.addEventListener(name, () => dropZone.classList.remove("is-dragover"));
});
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("is-dragover");
  const dropped = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
  if (!dropped) return;
  const transfer = new DataTransfer();
  transfer.items.add(dropped);
  fileInput.files = transfer.files;
  fileInput.dispatchEvent(new Event("change"));
});
// Keep the browser from opening a file that is dropped outside the scan area.
["dragover", "drop"].forEach((name) => {
  window.addEventListener(name, (event) => {
    if (!dropZone.contains(event.target)) event.preventDefault();
  });
});

function scrollBehavior() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    showStatus("Choose a .torrent file first.", "error");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".torrent")) {
    showStatus("Only .torrent files are accepted.", "error");
    return;
  }

  const body = new FormData(form);
  scanButton.disabled = true;
  scanButton.textContent = "Analyzing…";
  form.classList.add("is-scanning");
  showStatus("Reading torrent metadata. No content files are downloaded or executed.", "info");

  try {
    const response = await fetch("/api/scan", { method: "POST", body });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Analysis failed.");
    renderReport(result);
    showStatus("Analysis complete. Review the report below.", "success");
    await loadHistory();
    reportSection.scrollIntoView({ behavior: scrollBehavior(), block: "start" });
  } catch (error) {
    showStatus(error.message || "Unable to analyze the file.", "error");
  } finally {
    form.classList.remove("is-scanning");
    scanButton.disabled = false;
    scanButton.textContent = "Analyze torrent";
  }
});

document.querySelector("#refresh-history").addEventListener("click", loadHistory);

function showStatus(message, type) {
  statusMessage.textContent = message;
  statusMessage.className = "status-message " + type;
  statusMessage.hidden = false;
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 ** 2) return (bytes / 1024).toFixed(1) + " KB";
  if (bytes < 1024 ** 3) return (bytes / (1024 ** 2)).toFixed(2) + " MB";
  return (bytes / (1024 ** 3)).toFixed(2) + " GB";
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function riskClass(level) {
  return String(level || "low").toLowerCase();
}

function renderReport(report) {
  reportSection.hidden = false;
  document.querySelector("#report-filename").textContent = report.filename || "";
  document.querySelector("#risk-badge").textContent = (report.risk_level || "Unknown") + " risk";
  document.querySelector("#risk-badge").className = "risk-badge risk-" + riskClass(report.risk_level);
  reportSection.dataset.risk = riskClass(report.risk_level);
  document.querySelector("#metric-score").textContent = report.risk_score ?? 0;
  showRiskOnMeter(report.risk_score ?? 0);
  document.querySelector("#metric-files").textContent = Number(report.file_count || 0).toLocaleString();
  document.querySelector("#metric-size").textContent = formatBytes(report.total_size);
  document.querySelector("#torrent-name").textContent = report.torrent_name || "—";
  document.querySelector("#torrent-hash").textContent = report.sha256 || "—";
  document.querySelector("#scanned-at").textContent = formatDate(report.scanned_at);
  document.querySelector("#scope-note").textContent = report.scope_note || "";

  const flags = document.querySelector("#flags-list");
  flags.replaceChildren();
  (report.flags || []).forEach((item) => {
    const card = document.createElement("article");
    card.className = "flag " + (item.level || "info");
    const head = document.createElement("div");
    head.className = "flag-head";
    const level = document.createElement("span");
    level.className = "flag-level";
    level.textContent = item.level || "info";
    const title = document.createElement("strong");
    title.textContent = item.title || "Observation";
    head.append(level, title);
    const detail = document.createElement("p");
    detail.textContent = item.detail || "";
    card.append(head, detail);
    flags.append(card);
  });

  const tbody = document.querySelector("#files-table");
  tbody.replaceChildren();
  (report.files || []).forEach((item) => {
    const row = document.createElement("tr");
    const pathCell = document.createElement("td");
    pathCell.textContent = item.path || "(unnamed file)";
    const sizeCell = document.createElement("td");
    sizeCell.className = "number-cell";
    sizeCell.textContent = formatBytes(item.size);
    row.append(pathCell, sizeCell);
    tbody.append(row);
  });
  document.querySelector("#file-list-note").textContent = report.files_truncated
    ? "Showing the first 1,000 entries. The torrent lists more files."
    : (report.file_count || 0) + " file entr" + ((report.file_count || 0) === 1 ? "y" : "ies") + " listed.";
}

// Moves the marker on the risk ruler. Display only: the score comes from the server.
function showRiskOnMeter(score) {
  const value = Math.max(0, Math.min(100, Number(score) || 0));
  riskMeter.setAttribute("aria-label", "Risk score " + value + " out of 100");
  riskMeter.style.setProperty("--score", 0);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => riskMeter.style.setProperty("--score", value));
  });
}

async function loadHistory() {
  historyTable.replaceChildren();
  try {
    const response = await fetch("/api/history");
    if (!response.ok) throw new Error("History could not be loaded.");
    const rows = await response.json();
    if (!rows.length) {
      addEmptyHistory("No scans yet. Upload a .torrent file to begin.");
      return;
    }
    rows.forEach((item) => {
      const row = document.createElement("tr");
      const filename = document.createElement("td");
      filename.textContent = item.filename;
      const risk = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = "table-risk " + riskClass(item.risk_level);
      badge.textContent = item.risk_level;
      risk.append(badge);
      const score = document.createElement("td");
      score.textContent = item.risk_score + "/100";
      const date = document.createElement("td");
      date.textContent = formatDate(item.scanned_at);
      const action = document.createElement("td");
      const button = document.createElement("button");
      button.className = "link-button";
      button.type = "button";
      button.textContent = "View";
      button.addEventListener("click", () => loadReport(item.id));
      action.append(button);
      row.append(filename, risk, score, date, action);
      historyTable.append(row);
    });
  } catch (error) {
    addEmptyHistory(error.message || "Unable to load history.");
  }
}

function addEmptyHistory(message) {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 5;
  cell.className = "empty-cell";
  cell.textContent = message;
  row.append(cell);
  historyTable.append(row);
}

async function loadReport(id) {
  try {
    const response = await fetch("/api/report/" + encodeURIComponent(id));
    const report = await response.json();
    if (!response.ok) throw new Error(report.error || "Could not load report.");
    renderReport(report);
    reportSection.scrollIntoView({ behavior: scrollBehavior(), block: "start" });
  } catch (error) {
    showStatus(error.message || "Could not load report.", "error");
  }
}

loadHistory();
