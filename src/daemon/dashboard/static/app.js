const state = {
  activeRunId: null,
  pollingHandle: null,
  selectedProject: null,
  workspaceDir: "",
};

const els = {
  healthLabel: document.getElementById("health-label"),
  taskInput: document.getElementById("task-input"),
  workspaceInput: document.getElementById("workspace-input"),
  retriesInput: document.getElementById("retries-input"),
  dryRunInput: document.getElementById("dry-run-input"),
  runButton: document.getElementById("run-button"),
  cancelButton: document.getElementById("cancel-button"),
  refreshProjectsButton: document.getElementById("refresh-projects-button"),
  runMessage: document.getElementById("run-message"),
  runStatusBadge: document.getElementById("run-status-badge"),
  runTaskLabel: document.getElementById("run-task-label"),
  runMeta: document.getElementById("run-meta"),
  progressLabel: document.getElementById("progress-label"),
  progressFill: document.getElementById("progress-fill"),
  planList: document.getElementById("plan-list"),
  eventsList: document.getElementById("events-list"),
  projectsList: document.getElementById("projects-list"),
  inspectorProjectLabel: document.getElementById("inspector-project-label"),
  filesList: document.getElementById("files-list"),
  fileContent: document.getElementById("file-content"),
  introOverlay: document.getElementById("intro-overlay"),
  introEnterButton: document.getElementById("intro-enter-button"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setRunMessageWithLink(projectName, docsUrl) {
  els.runMessage.textContent = "";
  const prefix = document.createTextNode(`Launched ${projectName} on `);
  const link = document.createElement("a");
  link.href = docsUrl;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = docsUrl;
  els.runMessage.append(prefix, link);
}

function setBadge(status) {
  els.runStatusBadge.textContent = status;
  els.runStatusBadge.className = `badge ${status === "running" || status === "cancelling" ? "running" : status === "done" ? "done" : status === "failed" || status === "cancelled" ? "failed" : "neutral"}`;
}

function renderPlan(run) {
  const plan = run?.plan || [];
  const stateDump = run?.state || {};
  const currentIndex = stateDump.current_step_index || 0;
  const total = plan.length;
  const done = plan.filter((step) => step.status === "done").length;
  els.progressLabel.textContent = `${done} / ${total}`;
  els.progressFill.style.width = total ? `${(done / total) * 100}%` : "0%";
  const retries = stateDump.retries ?? 0;
  const currentStep = plan[currentIndex];
  els.runMeta.textContent = currentStep
    ? `Current step: #${currentStep.id} ${currentStep.title} | Retries: ${retries}`
    : `Waiting for the next update | Retries: ${retries}`;

  if (!plan.length) {
    els.planList.innerHTML = `<div class="step-card">No plan available yet.</div>`;
    return;
  }

  els.planList.innerHTML = plan.map((step, index) => `
    <div class="step-card">
      <div class="step-head">
        <div>
          <strong>#${escapeHtml(step.id)} ${escapeHtml(step.title)}</strong>
          <div class="step-type">${escapeHtml(step.type)}</div>
        </div>
        <div class="step-status">${escapeHtml(step.status || (index === currentIndex ? "running" : "pending"))}</div>
      </div>
      <div class="step-output">${escapeHtml(step.output || step.description || "")}</div>
    </div>
  `).join("");
}

function renderEvents(events) {
  if (!events.length) {
    els.eventsList.innerHTML = `<div class="event-card">No live events yet.</div>`;
    return;
  }
  els.eventsList.innerHTML = events.slice().reverse().map((event) => `
    <div class="event-card ${event.type || ""}">
      <strong>${escapeHtml(event.type || "event")}</strong>
      <div class="event-meta">${escapeHtml(event.message || event.result?.summary || event.step?.title || "")}${event.step?.output ? `\n\n${escapeHtml(event.step.output)}` : ""}</div>
      <div class="muted">${new Date(event.timestamp).toLocaleTimeString()}</div>
    </div>
  `).join("");
}

async function refreshRun() {
  if (!state.activeRunId) return;
  try {
    const [run, events] = await Promise.all([
      api(`/api/runs/${state.activeRunId}`),
      api(`/api/runs/${state.activeRunId}/events`),
    ]);
    state.workspaceDir = run.workspace_dir;
    els.workspaceInput.value = run.workspace_dir;
    els.runTaskLabel.textContent = run.task;
    setBadge(run.status);
    renderPlan(run);
    renderEvents(events);
    if (events.length) {
      const latest = events[events.length - 1];
      if (latest.message) {
        els.runMessage.textContent = latest.message;
      } else if (latest.step?.output) {
        els.runMessage.textContent = latest.step.output;
      }
    }
    if (run.status === "done" || run.status === "failed") {
      clearInterval(state.pollingHandle);
      state.pollingHandle = null;
      els.runMessage.textContent = run.session_log_path
        ? `Session log: ${run.session_log_path}`
        : run.error || `Run finished with status: ${run.status}`;
      await loadProjects();
    }
    if (run.status === "cancelled") {
      clearInterval(state.pollingHandle);
      state.pollingHandle = null;
      els.runMessage.textContent = "Run cancelled.";
    }
  } catch (error) {
    els.runMessage.textContent = error.message;
  }
}

async function startRun() {
  const task = els.taskInput.value.trim();
  if (task.split(/\s+/).filter(Boolean).length < 5) {
    els.runMessage.textContent = "Please provide a more specific task with at least 5 words.";
    return;
  }

  const payload = {
    task,
    workspace_dir: els.workspaceInput.value.trim() || undefined,
    max_retries: Number(els.retriesInput.value || 3),
    dry_run: els.dryRunInput.checked,
  };

  els.runMessage.textContent = "Starting run...";
  const run = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) });
  state.activeRunId = run.id;
  setBadge(run.status);
  if (state.pollingHandle) clearInterval(state.pollingHandle);
  state.pollingHandle = setInterval(refreshRun, 1200);
  await refreshRun();
}

async function cancelRun() {
  if (!state.activeRunId) {
    els.runMessage.textContent = "No active run to cancel.";
    return;
  }
  await api(`/api/runs/${state.activeRunId}/cancel`, { method: "POST" });
  els.runMessage.textContent = "Cancellation requested...";
  await refreshRun();
}

async function loadProjects() {
  const workspaceQuery = els.workspaceInput.value.trim() ? `?workspace_dir=${encodeURIComponent(els.workspaceInput.value.trim())}` : "";
  const projects = await api(`/api/projects${workspaceQuery}`);
  if (!projects.length) {
    els.projectsList.innerHTML = `<div class="project-card">No generated projects found yet.</div>`;
    return;
  }
  els.projectsList.innerHTML = projects.map((project) => `
    <div class="project-card">
      <div class="project-head">
        <div>
          <strong>${escapeHtml(project.name)}</strong>
          <div class="muted">${escapeHtml(project.path)}</div>
        </div>
      </div>
      <div class="project-actions">
        <button class="secondary" data-action="inspect" data-project="${escapeHtml(project.name)}">Inspect</button>
        <button class="secondary" data-action="launch" data-project="${escapeHtml(project.name)}">Launch App</button>
        <button class="secondary" data-action="docs" data-project="${escapeHtml(project.name)}">Open Docs</button>
      </div>
    </div>
  `).join("");
}

async function inspectProject(projectName) {
  state.selectedProject = projectName;
  els.inspectorProjectLabel.textContent = projectName;
  const workspaceQuery = els.workspaceInput.value.trim() ? `&workspace_dir=${encodeURIComponent(els.workspaceInput.value.trim())}` : "";
  const files = await api(`/api/projects/${encodeURIComponent(projectName)}/files?${workspaceQuery.replace(/^&/, "")}`);
  if (!files.length) {
    els.filesList.innerHTML = `<div class="file-row">No files available.</div>`;
    els.fileContent.textContent = "No files available.";
    return;
  }
  els.filesList.innerHTML = files.map((file) => `
    <div class="file-row" data-file="${escapeHtml(file.path)}">${escapeHtml(file.path)}</div>
  `).join("");
  await loadFile(projectName, files[0].path);
}

async function loadFile(projectName, path) {
  const workspaceQuery = els.workspaceInput.value.trim() ? `&workspace_dir=${encodeURIComponent(els.workspaceInput.value.trim())}` : "";
  const file = await api(`/api/projects/${encodeURIComponent(projectName)}/file?path=${encodeURIComponent(path)}${workspaceQuery}`);
  els.fileContent.textContent = file.content;
}

async function launchProject(projectName) {
  const workspaceQuery = els.workspaceInput.value.trim() ? `?workspace_dir=${encodeURIComponent(els.workspaceInput.value.trim())}` : "";
  const launch = await api(`/api/projects/${encodeURIComponent(projectName)}/launch${workspaceQuery}`, { method: "POST" });
  setRunMessageWithLink(projectName, launch.docs_url);
  await loadProjects();
}

async function openDocs(projectName) {
  const workspaceQuery = els.workspaceInput.value.trim() ? `?workspace_dir=${encodeURIComponent(els.workspaceInput.value.trim())}` : "";
  try {
    const launch = await api(`/api/projects/${encodeURIComponent(projectName)}/launch${workspaceQuery}`);
    window.open(launch.docs_url, "_blank", "noopener,noreferrer");
  } catch {
    const launch = await api(`/api/projects/${encodeURIComponent(projectName)}/launch${workspaceQuery}`, { method: "POST" });
    window.open(launch.docs_url, "_blank", "noopener,noreferrer");
  }
}

function bindDynamicClicks() {
  els.projectsList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const project = button.dataset.project;
    const action = button.dataset.action;
    if (action === "inspect") await inspectProject(project);
    if (action === "launch") await launchProject(project);
    if (action === "docs") await openDocs(project);
  });

  els.filesList.addEventListener("click", async (event) => {
    const row = event.target.closest("[data-file]");
    if (!row || !state.selectedProject) return;
    await loadFile(state.selectedProject, row.dataset.file);
  });
}

async function init() {
  try {
    await api("/api/health");
    els.healthLabel.textContent = "Backend online";
  } catch (error) {
    els.healthLabel.textContent = `Backend offline: ${error.message}`;
  }

  bindDynamicClicks();
  els.runButton.addEventListener("click", () => startRun().catch((error) => {
    els.runMessage.textContent = error.message;
  }));
  els.cancelButton.addEventListener("click", () => cancelRun().catch((error) => {
    els.runMessage.textContent = error.message;
  }));
  els.refreshProjectsButton.addEventListener("click", () => loadProjects().catch((error) => {
    els.runMessage.textContent = error.message;
  }));
  els.introEnterButton.addEventListener("click", () => {
    els.introOverlay.classList.add("hidden");
  });

  await loadProjects();
}

init().catch((error) => {
  els.runMessage.textContent = error.message;
});
