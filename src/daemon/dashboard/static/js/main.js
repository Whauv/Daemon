// Dashboard composition root: creates the store and views, wires controllers to
// them, binds store slices to view renders, and boots the initial data load.

import { api } from "./api.js";
import { createInspectionController } from "./controllers/inspection.js";
import { createLaunchesController } from "./controllers/launches.js";
import { createRunsController, upsertRun } from "./controllers/runs.js";
import { renderSkeleton, withBusy } from "./dom.js";
import { isActive } from "./format.js";
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

// ---------------------------------------------------------------- views

const composer = createComposer({
  onSubmit: (payload) => runs.startRun(payload),
  onCancel: () => runs.cancelActiveRun(),
  onWorkspaceChange: () => loadProjects(),
});

const runView = createRunView();
const eventsView = createEventsView({ feedback });

const historyView = createHistoryView({
  onOpen: (run) => {
    runs.openRun(run, { adoptWorkspace: true });
    feedback.announce(`Opened run ${run.task}`);
  },
  onClone: async (run, button) => {
    try {
      const clone = await withBusy(button, "Starting…", () => api.cloneRun(run.id));
      store.set((state) => ({ runs: upsertRun(state.runs, clone) }));
      runs.openRun(clone, { announceOutcome: true });
      feedback.info("Started a new run with the same settings.");
    } catch (error) {
      feedback.error(error);
    }
  },
  onSessionLog: async (run, button) => {
    try {
      const log = await withBusy(button, "Loading…", () => api.sessionLog(run.id));
      inspection.showText(`Session log — ${log.path}`, log.content);
    } catch (error) {
      feedback.error(error);
    }
  },
});

const projectsView = createProjectsView({
  onInspect: (name) => inspection.inspectProject(name),
  onLaunch: (name, button) => launches.launchProject(name, button),
  onStop: (name, button) => launches.stopProject(name, button),
});

const launchesView = createLaunchesView({
  onStop: (name, button) => launches.stopProject(name, button),
  onRestart: (name, button) => launches.restartProject(name, button),
  onViewLog: (name, button) => launches.viewLaunchLog(name, button),
});

const inspector = createInspectorView({
  onSelectFile: (path) => inspection.loadFile(path),
  onLoadFull: (button) => inspection.loadFull(button),
});

// ------------------------------------------------------------ controllers

const inspection = createInspectionController({
  api,
  feedback,
  tabs,
  inspector,
  getWorkspace: () => composer.workspace,
});

const runs = createRunsController({
  store,
  api,
  feedback,
  tabs,
  composer,
  loadProjects,
  setHealth,
});

const launches = createLaunchesController({
  store,
  api,
  feedback,
  loadLaunches,
  inspection,
  getWorkspace: () => composer.workspace,
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
  if (activeRun) runs.openRun(activeRun, { adoptWorkspace: true });

  window.setInterval(checkHealth, HEALTH_INTERVAL_MS);
  window.setInterval(() => {
    if (!document.hidden) loadLaunches();
  }, LAUNCHES_INTERVAL_MS);
}

boot();
