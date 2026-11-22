// Launched project servers: start, stop, restart, and view server logs.

import { withBusy } from "../dom.js";

export function createLaunchesController({ store, api, feedback, loadLaunches, inspection, getWorkspace }) {
  async function launchProject(name, button) {
    try {
      const launch = await withBusy(button, "Launching…", () => api.launchProject(name, getWorkspace()));
      feedback.success(`Launched ${name} on port ${launch.port}.`, {
        action: { label: "Open API docs", href: launch.docs_url },
      });
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
      const launch = await withBusy(button, "Restarting…", () => api.restartProject(name, getWorkspace()));
      feedback.success(`Restarted ${name} on port ${launch.port}.`, {
        action: { label: "Open API docs", href: launch.docs_url },
      });
    } catch (error) {
      feedback.error(error);
    }
    await loadLaunches();
  }

  async function viewLaunchLog(name, button) {
    try {
      const log = await withBusy(button, "Loading…", () => api.launchLog(name));
      inspection.showText(
        `${name} server log${log.truncated ? " (last 20 KB)" : ""} — ${log.path}`,
        log.content || "The server has not written any output yet.",
      );
    } catch (error) {
      feedback.error(error);
    }
  }

  return { launchProject, stopProject, restartProject, viewLaunchLog };
}
