// "New run" form: validation, payload building, and submit/cancel button states.

import { animateDisclosure } from "../motion.js";
import { MAX_RETRIES, MIN_TASK_WORDS, pluralize, wordCount } from "../format.js";
import { h } from "../dom.js";

export function createComposer({ onSubmit, onCancel, onWorkspaceChange }) {
  const form = document.getElementById("run-form");
  const task = document.getElementById("task-input");
  const count = document.getElementById("task-count");
  const error = document.getElementById("task-error");
  const workspace = document.getElementById("workspace-input");
  const retries = document.getElementById("retries-input");
  const dryRun = document.getElementById("dry-run-input");
  const runButton = document.getElementById("run-button");
  const cancelButton = document.getElementById("cancel-button");
  const advanced = document.getElementById("advanced-options");

  animateDisclosure(advanced);
  let submitting = false;
  let canCancel = false;

  function updateCount() {
    const words = wordCount(task.value);
    count.textContent = pluralize(words, "word");
    count.dataset.ready = String(words >= MIN_TASK_WORDS);
    if (task.getAttribute("aria-invalid") === "true" && words >= MIN_TASK_WORDS) setError("");
  }

  function setError(message) {
    error.textContent = message;
    task.setAttribute("aria-invalid", message ? "true" : "false");
  }

  function validate() {
    if (wordCount(task.value) < MIN_TASK_WORDS) {
      setError(`Please describe the task in at least ${MIN_TASK_WORDS} words.`);
      task.focus();
      return null;
    }
    const retryValue = Number(retries.value || 3);
    if (!Number.isInteger(retryValue) || retryValue < 1 || retryValue > MAX_RETRIES) {
      advanced.open = true;
      retries.setAttribute("aria-invalid", "true");
      setError(`Max retries must be a whole number from 1 to ${MAX_RETRIES}.`);
      retries.focus();
      return null;
    }
    retries.setAttribute("aria-invalid", "false");
    setError("");
    return {
      task: task.value.trim(),
      workspace_dir: workspace.value.trim() || undefined,
      max_retries: retryValue,
      dry_run: dryRun.checked,
    };
  }

  function renderButtons() {
    runButton.disabled = submitting;
    runButton.setAttribute("aria-busy", String(submitting));
    runButton.replaceChildren(
      ...(submitting ? [h("span", { class: "spinner", "aria-hidden": "true" }), "Starting…"] : ["Run task"]),
    );
    cancelButton.disabled = !canCancel;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitting) return;
    const payload = validate();
    if (!payload) return;
    submitting = true;
    renderButtons();
    try {
      await onSubmit(payload);
    } finally {
      submitting = false;
      renderButtons();
    }
  });

  // Ctrl/Cmd + Enter submits from the textarea.
  task.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  task.addEventListener("input", updateCount);
  retries.addEventListener("input", () => retries.setAttribute("aria-invalid", "false"));
  cancelButton.addEventListener("click", () => onCancel());
  workspace.addEventListener("change", () => onWorkspaceChange(workspace.value.trim()));

  updateCount();
  renderButtons();

  return {
    get workspace() {
      return workspace.value.trim();
    },
    /** Adopt a run's workspace, unless the user is currently editing the field. */
    adoptWorkspace(value) {
      if (document.activeElement === workspace || workspace.value === value) return false;
      workspace.value = value;
      return true;
    },
    setCancelable(value) {
      canCancel = value;
      renderButtons();
    },
  };
}
