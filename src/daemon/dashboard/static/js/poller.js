// Polling loop with exponential back-off on failure. It pauses while the tab is
// hidden and resumes immediately when it becomes visible again.
//
// `task` returns `false` to stop polling (e.g. the run reached a final state).

export function createPoller(task, { interval = 1500, maxInterval = 12000, onError, onRecover } = {}) {
  let timer = null;
  let running = false;
  let inFlight = false;
  let failures = 0;

  function schedule(delay) {
    clearTimeout(timer);
    if (running) timer = setTimeout(tick, delay);
  }

  async function tick() {
    timer = null;
    if (!running || inFlight) return;
    if (document.hidden) return; // resumed by visibilitychange
    inFlight = true;
    try {
      const keepGoing = await task();
      if (failures > 0) onRecover?.();
      failures = 0;
      if (keepGoing === false) running = false;
    } catch (error) {
      if (error?.name !== "AbortError") {
        failures += 1;
        onError?.(error, failures);
      }
    } finally {
      inFlight = false;
    }
    schedule(Math.min(interval * 2 ** failures, maxInterval));
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && running && !inFlight) schedule(0);
  });

  return {
    start() {
      running = true;
      failures = 0;
      schedule(0);
    },
    stop() {
      running = false;
      clearTimeout(timer);
      timer = null;
    },
    /** Poll right now (e.g. after the user cancels a run). */
    now() {
      if (running && !inFlight) schedule(0);
    },
    get running() {
      return running;
    },
  };
}
