// Inspector pane: browsing a project's files, loading a single file (optionally
// in full), and showing arbitrary text (session logs, server logs). Owns the
// "what is currently inspected" state.

import { withBusy } from "../dom.js";
import { pluralize } from "../format.js";

export function createInspectionController({ api, feedback, tabs, inspector, getWorkspace }) {
  let inspected = { project: null, path: null };

  async function inspectProject(projectName) {
    inspected = { project: projectName, path: null };
    tabs.select("tab-inspector");
    inspector.showLoading(projectName);
    try {
      const files = await api.projectFiles(projectName, getWorkspace());
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
      const file = await api.projectFile(project, path, getWorkspace(), full);
      if (inspected.project === project && inspected.path === path) inspector.showFile(file);
    } catch (error) {
      feedback.error(error);
    }
  }

  function loadFull(button) {
    if (inspected.project && inspected.path) {
      withBusy(button, "Loading…", () => loadFile(inspected.path, true));
    }
  }

  /** Show free-form text (a session log or server log) in the inspector pane. */
  function showText(title, content) {
    inspected = { project: null, path: null };
    tabs.select("tab-inspector");
    inspector.showText(title, content);
  }

  return { inspectProject, loadFile, loadFull, showText };
}
