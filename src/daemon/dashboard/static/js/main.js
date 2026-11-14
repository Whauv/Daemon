// Dashboard entry point: owns application state and wires data access to views.

import { api } from "./api.js";
import { renderSkeleton, withBusy } from "./dom.js";
import { isActive, isTerminal, pluralize } from "./format.js";
import { createPoller } from "./poller.js";
import { createStore, watch } from "./store.js";
import { createFeedback } from "./ui/feedback.js";
import { createTabs } from "./ui/tabs.js";
import { createComposer } from "./views/composer.js";
import { createEventsView } from "./views/events.js";
import { createHistoryView } from "./views/history.js";
import { createInspectorView } from "./views/inspector.js";
import { createLaunchesView } from "./views/launches.js";
import { createProjectsView } from "./views/projects.js";
import { createRunView } from "./views/run.js";

const HEALTH_INTERVAL_MS = 20_000;
const LAUNCHES_INTERVAL_MS = 8_000;
const RUN_POLL_INTERVAL_MS = 1_500;

const store = createStore({
  activeRunId: null,
  run: null,
  events: [],
  runs: null,
  runsError: null,
  projects: null,
  projectsError: null,
  launches: null,
  launchesError: null,
  workspace: "",
});

const feedback = createFeedback({
  region: document.getElementById("toast-region"),
  announcer: document.getElementById("announcer"),
});

const tabs = createTabs(document.getElementById("workbench-tabs"));

// --------------------------------------------------------------- health

const healthEl = document.getElementById("health");
const healthLabel = document.getElementById("health-label");

function setHealth(online, message) {
  healthEl.dataset.state = online ? "online" : "offline";
  healthLabel.textContent = message ?? (online ? "Backend online" : "Backend offline");
}

async function checkHealth() {
  try {
    await api.health();
    setHealth(true);
  } catch (error) {
    setHealth(false, "Backend offline");
    return error;
  }
  return null;
}

// ------------------------------------------------------------- loaders

async function loadRuns() {
  try {
    store.set({ runs: await api.listRuns(), runsError: null });
  } catch (error) {
    store.set({ runsError: error.message });
  }
}

async function loadProjects() {
  const workspace = composer.workspace;
  try {
    store.set({ projects: await api.listProjects(workspace), projectsError: null, workspace });
  } catch (error) {
    store.set({ projects: [], projectsError: error.message, workspace });
  }
}

async function loadLaunches() {
  try {
    store.set({ launches: await api.listLaunches(), launchesError: null });
  } catch (error) {
    store.set({ launchesError: error.message });
  }
}

// ----------------------------------------------------------------- runs

function upsertRun(runs, run) {
  if (!runs) return [run];
  const index = runs.findIndex((item) => item.id === run.id);
  if (index === -1) return [run, ...runs];
  const next = runs.slice();
  next[index] = run;
  return next;
}

const runPoller = createPoller(
  async () => {
    const runId = store.get().activeRunId;
    if (!runId) return false;
    const [run, events] = await Promise.all([api.getRun(runId), api.getRunEvents(runId)]);
    if (store.get().activeRunId !== runId) return true; // user switched runs mid-request
    store.set((state) => ({ run, events, runs: upsertRun(state.runs, run) }));

    if (isTerminal(run.status)) {
      // Announce outcomes for runs being watched live — not for finished runs opened from history.
      if (watchingOutcomeOf === run.id) {
        watchingOutcomeOf = null;
        announceOutcome(run);
      }
      loadProjects();
      return false;
    }
    return true;
  },
  {
    interval: RUN_POLL_INTERVAL_MS,
    onError: (error, failures) => {
      if (error.status === 404) {
        // The server restarted and forgot this run.
        runPoller.stop();
        feedback.error(new Error("This run is no longer known to the server (it may have restarted)."));
        return;
      }
      if (failures === 1) {
        setHealth(false, "Reconnecting…");
        feedback.error(new Error(`Lost contact with the backend: ${error.message} Retrying…`));
      }
    },
    onRecover: () => {
      setHealth(true);
      feedback.info("Reconnected to the backend.");
    },
  },
);

function announceOutcome(run) {
  const summary = run.dry_run ? "Dry run complete — the plan is ready." : `Run finished: ${run.status}.`;
  if (run.status === "done") feedback.success(summary);
  else if (run.status === "failed") feedback.error(new Error(run.error ? `Run failed: ${run.error}` : "Run failed."));
  else feedback.info(summary);
}

// Id of the run whose completion should raise a toast. Set when a run is started
// here or re-attached while still active; a fast run may already be terminal in
// the start response, so this cannot be inferred from status transitions alone.
let watchingOutcomeOf = null;

function openRun(run, { adoptWorkspace = false, announceOutcome: announce = false } = {}) {
  watchingOutcomeOf = announce || isActive(run.status) ? run.id : null;
  store.set({ activeRunId: run.id, run, events: [] });
  if (adoptWorkspace && composer.adoptWorkspace(run.workspace_dir)) loadProjects();
  runPoller.start();
}

async function startRun(payload) {
  try {
    const run = await api.startRun(payload);
    store.set((state) => ({ runs: upsertRun(state.runs, run) }));
    openRun(run, { announceOutcome: true });
    tabs.select("tab-log");
    feedback.info(payload.dry_run ? "Dry run started — generating a plan." : "Run started.");
    document.getElementById("run-panel").focus({ preventScroll: window.innerWidth >= 1280 });
  } catch (error) {
    feedback.error(error);
  }
}

async function cancelActiveRun() {
  const { activeRunId } = store.get();
  if (!activeRunId) return;
  try {
    const run = await api.cancelRun(activeRunId);
    store.set((state) => ({ run, runs: upsertRun(state.runs, run) }));
    feedback.info("Cancellation requested. The run stops after the current step.");
    runPoller.now();
  } catch (error) {
    feedback.error(error);
  }
}

// ------------------------------------------------------- inspector state

let inspected = { project: null, path: null };

async function inspectProject(projectName) {
  inspected = { project: projectName, path: null };
  tabs.select("tab-inspector");
  inspector.showLoading(projectName);
  try {
    const files = await api.projectFiles(projectName, composer.workspace);
    if (inspected.project !== projectName) return;
    inspector.showFiles(projectName, files);
    feedback.announce(`Loaded ${pluralize(files.length, "file")} from ${projectName}.`);
    if (files.length) await loadFile(files[0].path);
  } catch (error) {
    inspector.showFilesError(projectName, error.message);
  }
}

async function loadFile(path, full = false) {
  const project = inspected.project;
  if (!project) return;
  inspected.path = path;
  try {
    const file = await api.projectFile(project, path, composer.workspace, full);
    if (inspected.project === project && inspected.path === path) inspector.showFile(file);
  } catch (error) {
    feedback.error(error);
  }
}

// ------------------------------------------------------------ launches

async function launchProject(name, button) {
  try {
    const launch = await withBusy(button, "Launching…", () => api.launchProject(name, composer.workspace));
    feedback.success(`Launched ${name} on port ${launch.port}.`, { action: { label: "Open API docs", href: launch.docs_url } });
    await loadLaunches();
    // uvicorn fails fast on import errors; surface that instead of a silent dead server.
    window.setTimeout(async () => {
      await loadLaunches();
      const current = store.get().launches?.find((item) => item.project_name === name);
      if (current && !current.running && current.status !== "stopped") {
        feedback.error(new Error(`${name} exited right after starting. Open Launches → View log for details.`));
      }
    }, 2000);
  } catch (error) {
    feedback.error(error);
  }
}

async function stopProject(name, button) {
  try {
    await withBusy(button, "Stopping…", () => api.stopProject(name));
    feedback.success(`Stopped ${name}.`);
  } catch (error) {
    feedback.error(error);
  }
  await loadLaunches();
}

async function restartProject(name, button) {
  try {
    const launch = await withBusy(button, "Restarting…", () => api.restartProject(name, composer.workspace));
    feedback.success(`Restarted ${name} on port ${launch.port}.`, { action: { label: "Open API docs", href: launch.docs_url } });
  } catch (error) {
    feedback.error(error);
  }
  await loadLaunches();
}

async function viewLaunchLog(name, button) {
  try {
    const log = await withBusy(button, "Loading…", () => api.launchLog(name));
    inspected = { project: null, path: null };
    tabs.select("tab-inspector");
    inspector.showText(
      `${name} server log${log.truncated ? " (last 20 KB)" : ""} — ${log.path}`,
      log.content || "The server has not written any output yet.",
    );
  } catch (error) {
    feedback.error(error);
  }
}

// ---------------------------------------------------------------- views

const composer = createComposer({
  onSubmit: startRun,
  onCancel: cancelActiveRun,
  onWorkspaceChange: () => loadProjects(),
});

const runView = createRunView();
const eventsView = createEventsView({ feedback });

const historyView = createHistoryView({
  onOpen: (run) => {
    openRun(run, { adoptWorkspace: true });
    feedback.announce(`Opened run ${run.task}`);
  },
  onClone: async (run, button) => {
    try {
      const clone = await withBusy(button, "Starting…", () => api.cloneRun(run.id));
      store.set((state) => ({ runs: upsertRun(state.runs, clone) }));
      openRun(clone, { announceOutcome: true });
      feedback.info("Started a new run with the same settings.");
    } catch (error) {
      feedback.error(error);
    }
  },
  onSessionLog: async (run, button) => {
    try {
      const log = await withBusy(button, "Loading…", () => api.sessionLog(run.id));
      inspected = { project: null, path: null };
      tabs.select("tab-inspector");
      inspector.showText(`Session log — ${log.path}`, log.content);
    } catch (error) {
      feedback.error(error);
    }
  },
});

const projectsView = createProjectsView({
  onInspect: inspectProject,
  onLaunch: launchProject,
  onStop: stopProject,
});

const launchesView = createLaunchesView({
  onStop: stopProject,
  onRestart: restartProject,
  onViewLog: viewLaunchLog,
});

const inspector = createInspectorView({
  onSelectFile: (path) => loadFile(path),
  onLoadFull: (button) => {
    if (inspected.project && inspected.path) withBusy(button, "Loading…", () => loadFile(inspected.path, true));
  },
});

// ------------------------------------------------------------- bindings

watch(store, (state) => state.run, (run) => {
  runView.render(run);
  composer.setCancelable(Boolean(run && isActive(run.status) && run.status !== "cancelling"));
});
watch(store, (state) => state.events, (events, state) => eventsView.render(events, { runSelected: Boolean(state.activeRunId) }));
store.subscribe((state, previous) => {
  if (state.runs !== previous.runs || state.activeRunId !== previous.activeRunId || state.runsError !== previous.runsError) {
    historyView.render(state.runs, { activeRunId: state.activeRunId, error: state.runsError });
  }
  if (
    state.projects !== previous.projects ||
    state.launches !== previous.launches ||
    state.projectsError !== previous.projectsError
  ) {
    projectsView.render(state.projects, {
      launches: state.launches,
      workspace: state.workspace,
      error: state.projectsError,
    });
  }
  if (state.launches !== previous.launches || state.launchesError !== previous.launchesError) {
    launchesView.render(state.launches, { error: state.launchesError });
  }
});

document.getElementById("refresh-history-button").addEventListener("click", loadRuns);
document.getElementById("refresh-projects-button").addEventListener("click", (event) =>
  withBusy(event.currentTarget, "Refreshing…", loadProjects),
);
document.getElementById("refresh-launches-button").addEventListener("click", (event) =>
  withBusy(event.currentTarget, "Refreshing…", loadLaunches),
);

// ----------------------------------------------------------------- boot

async function boot() {
  renderSkeleton(document.getElementById("history-list"), 2);
  renderSkeleton(document.getElementById("projects-list"), 3);
  renderSkeleton(document.getElementById("launches-list"), 1);

  const healthError = await checkHealth();
  if (healthError) feedback.error(healthError);

  await Promise.all([loadRuns(), loadProjects(), loadLaunches()]);

  // Re-attach to a run that is still in progress (e.g. after a page reload).
  const activeRun = store.get().runs?.find((run) => isActive(run.status));
  if (activeRun) openRun(activeRun, { adoptWorkspace: true });

  window.setInterval(checkHealth, HEALTH_INTERVAL_MS);
  window.setInterval(() => {
    if (!document.hidden) loadLaunches();
  }, LAUNCHES_INTERVAL_MS);
}

boot();
