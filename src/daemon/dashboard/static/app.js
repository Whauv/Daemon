const state = {
  activeRunId: null,
  pollingHandle: null,
  selectedProject: null,
  selectedFilePath: null,
  workspaceDir: "",
  eventFilter: "",
  lastEvents: [],
  lastRuns: [],
  lastLaunches: [],
  currentFileTruncated: false,
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
  refreshHistoryButton: document.getElementById("refresh-history-button"),
  refreshLaunchesButton: document.getElementById("refresh-launches-button"),
  copyEventsButton: document.getElementById("copy-events-button"),
  eventFilterInput: document.getElementById("event-filter-input"),
  loadFullFileButton: document.getElementById("load-full-file-button"),
  runMessage: document.getElementById("run-message"),
  runStatusBadge: document.getElementById("run-status-badge"),
  runTaskLabel: document.getElementById("run-task-label"),
  runMeta: document.getElementById("run-meta"),
  progressLabel: document.getElementById("progress-label"),
  progressFill: document.getElementById("progress-fill"),
  planList: document.getElementById("plan-list"),
  eventsList: document.getElementById("events-list"),
  historyList: document.getElementById("history-list"),
  projectsList: document.getElementById("projects-list"),
  launchesList: document.getElementById("launches-list"),
  inspectorProjectLabel: document.getElementById("inspector-project-label"),
  filesList: document.getElementById("files-list"),
  fileMeta: document.getElementById("file-meta"),
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
    let message = `Request failed: ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch {
      const text = await response.text();
      message = text || message;
    }
    throw new Error(message);
  }
  return response.json();
}

function create(tag, className, text) {
  const element = document.createElement(tag);
  if (className) {
    element.className = className;
  }
  if (text !== undefined) {
    element.textContent = text;
  }
  return element;
}

function clearElement(element) {
  while (element.firstChild) {
    element.removeChild(element.firstChild);
  }
}

function renderEmptyState(container, message) {
  clearElement(container);
  container.append(create("div", "empty-state", message));
}

function setStatusMessage(message, kind = "info") {
  els.runMessage.textContent = message;
  els.runMessage.dataset.kind = kind;
}

function setBadge(status) {
  els.runStatusBadge.textContent = status;
  els.runStatusBadge.className = `badge ${
    status === "running" || status === "cancelling"
      ? "running"
      : status === "done"
        ? "done"
        : status === "failed" || status === "cancelled"
          ? "failed"
          : "neutral"
  }`;
}

function getWorkspaceQuery() {
  const workspace = els.workspaceInput.value.trim();
  return workspace ? `?workspace_dir=${encodeURIComponent(workspace)}` : "";
}

function formatTimestamp(isoString) {
  if (!isoString) {
    return "Unknown time";
  }
  return new Date(isoString).toLocaleString();
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
    renderEmptyState(els.planList, "No plan available yet.");
    return;
  }

  clearElement(els.planList);
  plan.forEach((step, index) => {
    const card = create("article", "step-card");
    const head = create("div", "step-head");
    const left = create("div");
    left.append(create("strong", "", `#${step.id} ${step.title}`));
    left.append(create("div", "step-type", step.type));
    const status = create("div", "step-status", step.status || (index === currentIndex ? "running" : "pending"));
    head.append(left, status);
    card.append(head, create("div", "step-output", step.output || step.description || ""));
    els.planList.append(card);
  });
}

function renderEvents(events) {
  state.lastEvents = events;
  const filter = state.eventFilter.trim().toLowerCase();
  const filtered = filter
    ? events.filter((event) => JSON.stringify(event).toLowerCase().includes(filter))
    : events;

  if (!filtered.length) {
    renderEmptyState(els.eventsList, filter ? "No logs match the current filter." : "No live events yet.");
    return;
  }

  clearElement(els.eventsList);
  filtered.slice().reverse().forEach((event) => {
    const card = create("article", `event-card ${event.type || ""}`.trim());
    card.append(create("strong", "", event.type || "event"));
    const meta = create("div", "event-meta");
    meta.textContent = event.message || event.result?.summary || event.step?.title || "";
    if (event.step?.output) {
      meta.append("\n\n", event.step.output);
    }
    card.append(meta);
    if (event.step?.output || event.result || event.path) {
      const details = create("details", "event-details");
      const summary = create("summary", "", "More details");
      const pre = create("pre", "event-output", JSON.stringify(event, null, 2));
      details.append(summary, pre);
      card.append(details);
    }
    card.append(create("div", "muted", formatTimestamp(event.timestamp)));
    els.eventsList.append(card);
  });
}

function renderHistory(runs) {
  state.lastRuns = runs;
  if (!runs.length) {
    renderEmptyState(els.historyList, "No run history yet.");
    return;
  }

  clearElement(els.historyList);
  runs.forEach((run) => {
    const card = create("article", "history-card");
    const top = create("div", "history-top");
    top.append(create("strong", "", run.task));
    top.append(create("span", `badge ${run.status === "done" ? "done" : run.status === "failed" ? "failed" : run.status === "running" ? "running" : "neutral"}`, run.status));
    card.append(top);
    card.append(create("div", "muted", `${run.workspace_dir} | ${formatTimestamp(run.created_at)}`));
    const actions = create("div", "project-actions");

    const reopen = create("button", "secondary", "Reopen");
    reopen.type = "button";
    reopen.addEventListener("click", async () => {
      state.activeRunId = run.id;
      await refreshRun();
      setStatusMessage(`Opened history for run ${run.id.slice(0, 8)}.`, "info");
    });

    const clone = create("button", "secondary", "Clone Run");
    clone.type = "button";
    clone.addEventListener("click", async () => {
      try {
        const newRun = await api(`/api/runs/${run.id}/clone`, { method: "POST" });
        state.activeRunId = newRun.id;
        setBadge(newRun.status);
        setStatusMessage("Cloned run started.", "success");
        startPolling();
        await Promise.all([refreshRun(), loadHistory()]);
      } catch (error) {
        setStatusMessage(error.message, "error");
      }
    });

    const log = create("button", "secondary", "Session Log");
    log.type = "button";
    log.disabled = !run.session_log_path;
    log.addEventListener("click", async () => {
      try {
        const payload = await api(`/api/runs/${run.id}/session-log`);
        els.fileMeta.textContent = payload.path;
        els.fileContent.textContent = payload.content;
        els.loadFullFileButton.hidden = true;
        setStatusMessage("Loaded session log into the inspector.", "info");
      } catch (error) {
        setStatusMessage(error.message, "error");
      }
    });

    actions.append(reopen, clone, log);
    card.append(actions);
    els.historyList.append(card);
  });
}

function renderProjects(projects) {
  if (!projects.length) {
    renderEmptyState(els.projectsList, "No generated projects found yet.");
    return;
  }

  clearElement(els.projectsList);
  projects.forEach((project) => {
    const card = create("article", "project-card");
    const head = create("div", "project-head");
    const left = create("div");
    left.append(create("strong", "", project.name));
    left.append(create("div", "muted", project.path));
    head.append(left);
    card.append(head);

    const actions = create("div", "project-actions");
    [
      ["Inspect", () => inspectProject(project.name)],
      ["Launch App", () => launchProject(project.name)],
      ["Open Docs", () => openDocs(project.name)],
    ].forEach(([label, handler]) => {
      const button = create("button", "secondary", label);
      button.type = "button";
      button.addEventListener("click", () => handler().catch((error) => setStatusMessage(error.message, "error")));
      actions.append(button);
    });

    card.append(actions);
    els.projectsList.append(card);
  });
}

function renderLaunches(launches) {
  state.lastLaunches = launches;
  if (!launches.length) {
    renderEmptyState(els.launchesList, "No launched apps yet.");
    return;
  }

  clearElement(els.launchesList);
  launches.forEach((launch) => {
    const card = create("article", "launch-card");
    const head = create("div", "history-top");
    head.append(create("strong", "", launch.project_name));
    head.append(create("span", `badge ${launch.running ? "running" : "neutral"}`, launch.running ? "running" : "stopped"));
    card.append(head);
    card.append(create("div", "muted", `${launch.url} | Port ${launch.port}`));
    const actions = create("div", "project-actions");
    const docs = create("button", "secondary", "Open Docs");
    docs.type = "button";
    docs.addEventListener("click", () => window.open(launch.docs_url, "_blank", "noopener,noreferrer"));
    const restart = create("button", "secondary", "Restart");
    restart.type = "button";
    restart.addEventListener("click", async () => {
      try {
        await api(`/api/projects/${encodeURIComponent(launch.project_name)}/restart${getWorkspaceQuery()}`, { method: "POST" });
        setStatusMessage(`Restarted ${launch.project_name}.`, "success");
        await loadLaunches();
      } catch (error) {
        setStatusMessage(error.message, "error");
      }
    });
    const stop = create("button", "secondary", "Stop");
    stop.type = "button";
    stop.disabled = !launch.running;
    stop.addEventListener("click", async () => {
      try {
        await api(`/api/projects/${encodeURIComponent(launch.project_name)}/stop`, { method: "POST" });
        setStatusMessage(`Stopped ${launch.project_name}.`, "success");
        await loadLaunches();
      } catch (error) {
        setStatusMessage(error.message, "error");
      }
    });
    actions.append(docs, restart, stop);
    card.append(actions);
    els.launchesList.append(card);
  });
}

async function refreshRun() {
  if (!state.activeRunId) {
    return;
  }

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

    if (run.status === "done" || run.status === "failed" || run.status === "cancelled") {
      stopPolling();
      setStatusMessage(
        run.session_log_path ? `Session log: ${run.session_log_path}` : run.error || `Run finished with status: ${run.status}`,
        run.status === "done" ? "success" : run.status === "failed" ? "error" : "info",
      );
      await Promise.all([loadProjects(), loadHistory()]);
    }
  } catch (error) {
    stopPolling();
    setStatusMessage(error.message, "error");
  }
}

function startPolling() {
  stopPolling();
  state.pollingHandle = window.setInterval(() => {
    refreshRun().catch((error) => setStatusMessage(error.message, "error"));
  }, 1500);
}

function stopPolling() {
  if (state.pollingHandle) {
    clearInterval(state.pollingHandle);
    state.pollingHandle = null;
  }
}

async function startRun() {
  const task = els.taskInput.value.trim();
  if (task.split(/\s+/).filter(Boolean).length < 5) {
    setStatusMessage("Please provide a more specific task with at least 5 words.", "error");
    return;
  }

  const payload = {
    task,
    workspace_dir: els.workspaceInput.value.trim() || undefined,
    max_retries: Number(els.retriesInput.value || 3),
    dry_run: els.dryRunInput.checked,
  };

  setStatusMessage("Starting run...", "info");
  const run = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) });
  state.activeRunId = run.id;
  setBadge(run.status);
  startPolling();
  await Promise.all([refreshRun(), loadHistory()]);
}

async function cancelRun() {
  if (!state.activeRunId) {
    setStatusMessage("No active run to cancel.", "error");
    return;
  }
  await api(`/api/runs/${state.activeRunId}/cancel`, { method: "POST" });
  setStatusMessage("Cancellation requested...", "info");
  await refreshRun();
}

async function loadProjects() {
  try {
    const projects = await api(`/api/projects${getWorkspaceQuery()}`);
    renderProjects(projects);
  } catch (error) {
    renderEmptyState(els.projectsList, "Projects could not be loaded.");
    setStatusMessage(error.message, "error");
  }
}

async function loadHistory() {
  try {
    const runs = await api("/api/runs");
    renderHistory(runs);
  } catch (error) {
    renderEmptyState(els.historyList, "Run history could not be loaded.");
    setStatusMessage(error.message, "error");
  }
}

async function loadLaunches() {
  try {
    const launches = await api("/api/launches");
    renderLaunches(launches);
  } catch (error) {
    renderEmptyState(els.launchesList, "Launch data could not be loaded.");
    setStatusMessage(error.message, "error");
  }
}

async function inspectProject(projectName) {
  state.selectedProject = projectName;
  state.selectedFilePath = null;
  state.currentFileTruncated = false;
  els.inspectorProjectLabel.textContent = projectName;
  try {
    const files = await api(`/api/projects/${encodeURIComponent(projectName)}/files${getWorkspaceQuery()}`);
    if (!files.length) {
      renderEmptyState(els.filesList, "No files available.");
      els.fileMeta.textContent = "No files available.";
      els.fileContent.textContent = "No files available.";
      els.loadFullFileButton.hidden = true;
      return;
    }

    clearElement(els.filesList);
    files.forEach((file) => {
      const row = create("button", "file-row", `${file.path} (${file.size} bytes)`);
      row.type = "button";
      row.addEventListener("click", () => loadFile(projectName, file.path).catch((error) => setStatusMessage(error.message, "error")));
      els.filesList.append(row);
    });
    await loadFile(projectName, files[0].path);
  } catch (error) {
    renderEmptyState(els.filesList, "Files could not be loaded.");
    setStatusMessage(error.message, "error");
  }
}

async function loadFile(projectName, path, full = false) {
  state.selectedProject = projectName;
  state.selectedFilePath = path;
  const workspace = els.workspaceInput.value.trim();
  const params = new URLSearchParams({ path });
  if (workspace) {
    params.set("workspace_dir", workspace);
  }
  if (full) {
    params.set("full", "true");
  }

  const file = await api(`/api/projects/${encodeURIComponent(projectName)}/file?${params.toString()}`);
  els.fileMeta.textContent = `${file.path} | ${file.size} bytes${file.binary ? " | binary" : file.truncated ? " | preview truncated" : ""}`;
  els.fileContent.textContent = file.binary
    ? file.message
    : `${file.content}${file.message ? `\n\n${file.message}` : ""}`;
  state.currentFileTruncated = Boolean(file.truncated);
  els.loadFullFileButton.hidden = !file.truncated;
}

async function launchProject(projectName) {
  const launch = await api(`/api/projects/${encodeURIComponent(projectName)}/launch${getWorkspaceQuery()}`, { method: "POST" });
  setStatusMessage(`Launched ${projectName} on ${launch.docs_url}`, "success");
  await loadLaunches();
}

async function openDocs(projectName) {
  try {
    const launch = await api(`/api/projects/${encodeURIComponent(projectName)}/launch`);
    window.open(launch.docs_url, "_blank", "noopener,noreferrer");
  } catch {
    const launch = await api(`/api/projects/${encodeURIComponent(projectName)}/launch${getWorkspaceQuery()}`, { method: "POST" });
    window.open(launch.docs_url, "_blank", "noopener,noreferrer");
  }
}

async function copyEvents() {
  if (!state.lastEvents.length) {
    setStatusMessage("No logs available to copy.", "error");
    return;
  }
  const lines = state.lastEvents.map((event) => JSON.stringify(event)).join("\n");
  await navigator.clipboard.writeText(lines);
  setStatusMessage("Copied current logs to clipboard.", "success");
}

function applyEventFilter() {
  state.eventFilter = els.eventFilterInput.value;
  renderEvents(state.lastEvents);
}

function bindEvents() {
  els.runButton.addEventListener("click", () => startRun().catch((error) => setStatusMessage(error.message, "error")));
  els.cancelButton.addEventListener("click", () => cancelRun().catch((error) => setStatusMessage(error.message, "error")));
  els.refreshProjectsButton.addEventListener("click", () => loadProjects().catch((error) => setStatusMessage(error.message, "error")));
  els.refreshHistoryButton.addEventListener("click", () => loadHistory().catch((error) => setStatusMessage(error.message, "error")));
  els.refreshLaunchesButton.addEventListener("click", () => loadLaunches().catch((error) => setStatusMessage(error.message, "error")));
  els.copyEventsButton.addEventListener("click", () => copyEvents().catch((error) => setStatusMessage(error.message, "error")));
  els.eventFilterInput.addEventListener("input", applyEventFilter);
  els.introEnterButton.addEventListener("click", () => {
    els.introOverlay.classList.add("hidden");
  });
  els.loadFullFileButton.addEventListener("click", () => {
    if (!state.selectedProject || !state.selectedFilePath) {
      return;
    }
    loadFile(state.selectedProject, state.selectedFilePath, true).catch((error) => setStatusMessage(error.message, "error"));
  });
}

async function init() {
  try {
    await api("/api/health");
    els.healthLabel.textContent = "Backend online";
  } catch (error) {
    els.healthLabel.textContent = `Backend offline: ${error.message}`;
    setStatusMessage(error.message, "error");
  }

  bindEvents();
  renderEmptyState(els.historyList, "Loading run history...");
  renderEmptyState(els.projectsList, "Loading generated projects...");
  renderEmptyState(els.launchesList, "Loading launched apps...");
  await Promise.all([loadProjects(), loadHistory(), loadLaunches()]);
}

init().catch((error) => {
  setStatusMessage(error.message, "error");
});
