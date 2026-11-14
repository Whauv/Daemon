// "Current run" panel: summary, progress, and the plan timeline.

import { h, reconcile, renderEmpty, setData, setText } from "../dom.js";
import { animateDisclosure, highlight } from "../motion.js";
import { basename, formatDateTime, isActive, shortId, statusTone } from "../format.js";

export function createRunView() {
  const badge = document.getElementById("run-status");
  const taskLabel = document.getElementById("run-task");
  const metaRun = document.getElementById("meta-run-id");
  const metaMode = document.getElementById("meta-mode");
  const metaWorkspace = document.getElementById("meta-workspace");
  const metaRetries = document.getElementById("meta-retries");
  const metaStarted = document.getElementById("meta-started");
  const progress = document.querySelector(".progress");
  const progressTrack = document.getElementById("progress-track");
  const progressFill = document.getElementById("progress-fill");
  const progressLabel = document.getElementById("progress-label");
  const errorBox = document.getElementById("run-error");
  const planList = document.getElementById("plan-list");

  renderEmpty(planList, "Start a run or open one from history to see its plan.");

  function setBadge(status) {
    const changed = badge.textContent !== status;
    setText(badge, status);
    setData(badge, "tone", statusTone(status));
    badge.dataset.status = status;
    if (changed && status !== "idle") highlight(badge);
  }

  function createStep() {
    const marker = h("span", { class: "step-marker", "aria-hidden": "true" });
    const title = h("p", { class: "step-title" });
    const type = h("span", { class: "step-type" });
    const description = h("p", { class: "step-desc" });
    const outputPre = h("pre", { class: "output" });
    const outputSummary = h("summary");
    const output = h("details", { class: "step-output" }, outputSummary, outputPre);
    animateDisclosure(output);
    const status = h("span", { class: "sr-only" });
    const node = h(
      "li",
      { class: "step" },
      marker,
      h("div", { class: "step-main" }, h("div", { class: "step-head" }, title, type), description, output, status),
    );
    node._parts = { marker, title, type, description, output, outputPre, outputSummary, status };
    return node;
  }

  function updateStep(node, { step, displayStatus, isCurrent }) {
    const parts = node._parts;
    setData(node, "status", displayStatus);
    setData(node, "current", isCurrent ? "true" : undefined);
    if (isCurrent) node.setAttribute("aria-current", "step");
    else node.removeAttribute("aria-current");
    setText(parts.marker, displayStatus === "done" ? "✓" : displayStatus === "failed" ? "!" : String(step.id));
    setText(parts.title, step.title || `Step ${step.id}`);
    setText(parts.type, (step.type || "").replace("_", " "));
    setText(parts.description, step.description || "");
    parts.description.hidden = !step.description || step.description === step.title;
    setText(parts.status, `Status: ${displayStatus}`);
    const output = step.output || "";
    parts.output.hidden = !output;
    setText(parts.outputSummary, displayStatus === "failed" ? "Error output" : "Output");
    setText(parts.outputPre, output);
  }

  function renderPlan(run) {
    const plan = run?.plan ?? [];
    if (!plan.length) {
      renderEmpty(
        planList,
        run ? (isActive(run.status) ? "Waiting for the planner…" : "This run has no plan.") : "Start a run or open one from history to see its plan.",
      );
      return;
    }
    const currentIndex = run.state?.current_step_index ?? 0;
    const active = isActive(run.status);
    const rows = plan.map((step, index) => {
      const isCurrent = active && index === currentIndex;
      const displayStatus = isCurrent && (step.status === "pending" || !step.status) ? "running" : step.status || "pending";
      return { step, displayStatus, isCurrent };
    });
    reconcile(planList, rows, { key: (row) => row.step.id, create: createStep, update: updateStep });
  }

  function renderProgress(run) {
    const plan = run?.plan ?? [];
    const done = plan.filter((step) => step.status === "done").length;
    const total = plan.length;
    const ratio = total ? done / total : 0;
    progressFill.style.transform = `scaleX(${ratio})`;
    setText(progressLabel, `${done} / ${total}`);
    progressTrack.setAttribute("aria-valuemax", String(total));
    progressTrack.setAttribute("aria-valuenow", String(done));
    progressTrack.setAttribute("aria-valuetext", total ? `${done} of ${total} steps done` : "No steps yet");
    const tone = statusTone(run?.status);
    setData(progress, "tone", tone === "danger" || tone === "warning" ? tone : undefined);
  }

  return {
    render(run) {
      if (!run) {
        setBadge("idle");
        setText(taskLabel, "No run selected");
        taskLabel.dataset.empty = "true";
        for (const field of [metaRun, metaMode, metaWorkspace, metaRetries, metaStarted]) setText(field, "—");
        errorBox.hidden = true;
        renderProgress(null);
        renderPlan(null);
        return;
      }
      setBadge(run.status);
      setText(taskLabel, run.task);
      taskLabel.dataset.empty = "false";
      setText(metaRun, shortId(run.id));
      metaRun.title = run.id;
      setText(metaMode, run.dry_run ? "Dry run" : "Full run");
      setText(metaWorkspace, basename(run.workspace_dir));
      metaWorkspace.title = run.workspace_dir;
      setText(metaRetries, `${run.state?.retries ?? 0} / ${run.max_retries}`);
      setText(metaStarted, formatDateTime(run.created_at));
      errorBox.hidden = !run.error;
      setText(errorBox, run.error ? `Run error: ${run.error}` : "");
      renderProgress(run);
      renderPlan(run);
    },
  };
}
