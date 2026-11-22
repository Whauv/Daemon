// Run lifecycle: polling the active run, opening/starting/cancelling runs, and
// announcing outcomes. Owns the run poller and the "watch this run's outcome" flag.

import { isActive, isTerminal } from "../format.js";
import { createPoller } from "../poller.js";

const RUN_POLL_INTERVAL_MS = 1_500;

/** Insert or replace a run in the cached list, keeping newest-first order. */
export function upsertRun(runs, run) {
  if (!runs) return [run];
  const index = runs.findIndex((item) => item.id === run.id);
  if (index === -1) return [run, ...runs];
  const next = runs.slice();
  next[index] = run;
  return next;
}

export function createRunsController({ store, api, feedback, tabs, composer, loadProjects, setHealth }) {
  // Id of the run whose completion should raise a toast. Set when a run is started
  // here or re-attached while still active; a fast run may already be terminal in
  // the start response, so this cannot be inferred from status transitions alone.
  let watchingOutcomeOf = null;

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

  return { openRun, startRun, cancelActiveRun };
}
