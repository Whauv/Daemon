// Run history: every run this dashboard session has started.

import { h, reconcile, renderEmpty, setData, setText } from "../dom.js";
import { basename, formatDateTime, shortId, statusTone } from "../format.js";

export function createHistoryView({ onOpen, onClone, onSessionLog }) {
  const list = document.getElementById("history-list");

  function createItem() {
    const task = h("p", { class: "history-task" });
    const badge = h("span", { class: "badge" });
    const meta = h("p", { class: "history-meta" });
    const open = h("button", { class: "btn btn-small", type: "button", text: "Open" });
    const clone = h("button", { class: "btn btn-small", type: "button", text: "Run again" });
    const log = h("button", { class: "btn btn-small", type: "button", text: "Session log" });
    const node = h(
      "li",
      { class: "history-item" },
      h("div", { class: "history-top" }, task, badge),
      meta,
      h("div", { class: "history-actions" }, open, clone, log),
    );
    open.addEventListener("click", () => onOpen(node._run));
    clone.addEventListener("click", (event) => onClone(node._run, event.currentTarget));
    log.addEventListener("click", (event) => onSessionLog(node._run, event.currentTarget));
    node._parts = { task, badge, meta, open, clone, log };
    return node;
  }

  function updateItem(node, { run, active }) {
    node._run = run;
    const parts = node._parts;
    setText(parts.task, run.task);
    parts.task.title = run.task;
    setText(parts.badge, run.status);
    setData(parts.badge, "tone", statusTone(run.status));
    const workspace = basename(run.workspace_dir);
    setText(parts.meta, `${shortId(run.id)} · ${formatDateTime(run.created_at)} · ${workspace}${run.dry_run ? " · dry run" : ""}`);
    setData(node, "active", active ? "true" : undefined);
    const label = run.task.length > 60 ? `${run.task.slice(0, 57)}…` : run.task;
    parts.open.setAttribute("aria-label", `Open run: ${label}`);
    parts.open.disabled = active;
    parts.clone.setAttribute("aria-label", `Run again: ${label}`);
    parts.log.setAttribute("aria-label", `Session log for: ${label}`);
    parts.log.disabled = !run.session_log_path;
  }

  return {
    render(runs, { activeRunId, error }) {
      if (error) {
        renderEmpty(list, "Run history could not be loaded.", { tone: "danger" });
        return;
      }
      if (!runs) return; // still loading — keep the skeleton
      if (!runs.length) {
        renderEmpty(list, "No runs yet. Runs you start appear here until the server restarts.");
        return;
      }
      reconcile(
        list,
        runs.map((run) => ({ run, active: run.id === activeRunId })),
        { key: (row) => row.run.id, create: createItem, update: updateItem },
      );
    },
  };
}
