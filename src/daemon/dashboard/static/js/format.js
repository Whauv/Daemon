// Pure presentation helpers shared by the views.

export const ACTIVE_STATUSES = new Set(["queued", "running", "planning", "executing", "verifying", "cancelling"]);
export const TERMINAL_STATUSES = new Set(["done", "failed", "cancelled"]);
export const MIN_TASK_WORDS = 5;
export const MAX_RETRIES = 10;

export function isActive(status) {
  return ACTIVE_STATUSES.has(status);
}

export function isTerminal(status) {
  return TERMINAL_STATUSES.has(status);
}

/** Map a run/step status to a visual tone used by badges, events, and progress. */
export function statusTone(status) {
  if (status === "done") return "success";
  if (status === "failed") return "danger";
  if (status === "cancelled" || status === "cancelling") return "warning";
  if (ACTIVE_STATUSES.has(status)) return "active";
  return "idle";
}

const EVENT_META = {
  status: { label: "Status", tone: "active" },
  plan: { label: "Plan ready", tone: "active" },
  step_start: { label: "Step started", tone: "active" },
  step_done: { label: "Step done", tone: "success" },
  step_failed: { label: "Step failed", tone: "danger" },
  step_replanned: { label: "Replanned", tone: "warning" },
  issues: { label: "Issues found", tone: "warning" },
  patch_plan: { label: "Patch plan", tone: "active" },
  success: { label: "Success", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  fatal: { label: "Fatal", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "warning" },
  session_saved: { label: "Session saved", tone: "success" },
};

export function eventMeta(type) {
  return EVENT_META[type] ?? { label: type || "Event", tone: "idle" };
}

export function eventMessage(event) {
  const step = event.step;
  switch (event.type) {
    case "plan":
    case "patch_plan":
      return `${event.plan?.length ?? 0} steps in plan.`;
    case "step_start":
    case "step_done":
      return step ? `#${step.id} ${step.title}` : "";
    case "step_failed":
      return step ? `#${step.id} ${step.title} — attempt ${event.retries ?? "?"}` : "";
    case "step_replanned":
      return step ? `#${step.id} replaced with “${step.title}”` : "";
    case "issues":
    case "failed": {
      const issues = event.result?.issues ?? [];
      const summary = event.result?.summary ?? event.message ?? "";
      return issues.length ? `${summary} ${issues.join(" · ")}`.trim() : summary;
    }
    case "session_saved":
      return event.path ?? "";
    default:
      return event.message ?? event.result?.summary ?? step?.title ?? "";
  }
}

export function formatTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDateTime(iso) {
  if (!iso) return "Unknown time";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function formatBytes(size) {
  if (!Number.isFinite(size)) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function shortId(id) {
  return id ? id.slice(0, 8) : "—";
}

export function basename(path) {
  if (!path) return "";
  const parts = String(path).split(/[\\/]/).filter(Boolean);
  return parts.at(-1) ?? path;
}

export function wordCount(text) {
  return String(text ?? "").trim().split(/\s+/).filter(Boolean).length;
}

export function pluralize(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}
