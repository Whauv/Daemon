from __future__ import annotations

from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from core.state import AgentState, PlanStep


class DaemonDisplay:
    def __init__(self) -> None:
        self.console = Console()
        self.banner_panel: Panel | None = None
        self.status_message = "Idle"
        self.plan_steps: list[dict[str, Any]] = []
        self.task_name = "Daemon Task"
        self.event_panels: list[Panel] = []
        self.progress = Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=self.console,
            expand=True,
        )
        self.progress_task_id = self.progress.add_task("Steps", total=0, completed=0)
        self.live = Live(self._build_renderable(), console=self.console, refresh_per_second=8, auto_refresh=False)
        self.live.start()

    def show_banner(self) -> None:
        self.banner_panel = Panel(
            Text("DAEMON", style="bold white", justify="center"),
            border_style="cyan",
        )
        self._refresh()

    def show_status(self, msg: str) -> None:
        self.status_message = msg
        self._refresh()

    def show_plan(
        self,
        plan: list[PlanStep | dict[str, Any]],
        title: str = "Execution Plan",
        task_name: str | None = None,
    ) -> None:
        self.plan_steps = [step if isinstance(step, dict) else step.model_dump() for step in plan]
        self.task_name = task_name or self.task_name or title
        self._update_progress()
        self._refresh()

    def show_step_start(self, step: PlanStep | dict[str, Any]) -> None:
        normalized = step if isinstance(step, dict) else step.model_dump()
        self.status_message = f"Running step {normalized['id']}: {normalized['title']}"
        self._push_event(
            Panel(
                f"[yellow][RUNNING][/yellow] Step {normalized['id']}: {normalized['title']}",
                border_style="yellow",
            )
        )

    def show_step_done(self, step: PlanStep | dict[str, Any]) -> None:
        normalized = step if isinstance(step, dict) else step.model_dump()
        preview = str(normalized.get("output", ""))[:100] or "No output."
        self.status_message = f"Completed step {normalized['id']}: {normalized['title']}"
        self._push_event(
            Panel(
                f"[green][DONE][/green] Step {normalized['id']}: {normalized['title']}\n{preview}",
                border_style="green",
            )
        )
        self._replace_plan_step(normalized)

    def show_step_failed(self, step: PlanStep | dict[str, Any]) -> None:
        normalized = step if isinstance(step, dict) else step.model_dump()
        full_error = str(normalized.get("output", "")) or "Unknown error."
        self.status_message = f"Failed step {normalized['id']}: {normalized['title']}"
        self._push_event(
            Panel(
                f"[red][FAILED][/red] Step {normalized['id']}: {normalized['title']}\n{full_error}",
                border_style="red",
            )
        )
        self._replace_plan_step(normalized)

    def show_fatal_error(self, msg: str) -> None:
        self.status_message = msg
        self._push_event(Panel(msg, title="Fatal Error", border_style="red"))

    def show_success(self, summary: str) -> None:
        self.status_message = "Task complete"
        self._push_event(Panel(f"TASK COMPLETE\n\n{summary}", border_style="green"))

    def show_issues(self, issues: list[str]) -> None:
        issue_text = "\n".join(f"- {issue}" for issue in issues) if issues else "No issues reported."
        self.status_message = "Issues found during verification"
        self._push_event(Panel(issue_text, title="Issues", border_style="yellow"))

    def log(self, message: str) -> None:
        self._push_event(Panel(message, title="Log", border_style="blue"))

    def show_summary(self, state: AgentState) -> None:
        self.close()
        table = Table(title="Daemon Summary")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Task", state.task)
        table.add_row("Workspace", state.workspace_dir)
        table.add_row("Status", state.status)
        table.add_row("Completed steps", str(len(state.completed_steps)))
        table.add_row("Failed steps", str(len(state.failed_steps)))
        table.add_row("Retries", str(state.retries))
        self.console.print(table)

    def close(self) -> None:
        if getattr(self.live, "is_started", False):
            self.live.stop()

    def _push_event(self, panel: Panel) -> None:
        self.event_panels.append(panel)
        self.event_panels = self.event_panels[-6:]
        self._refresh()

    def _replace_plan_step(self, updated_step: dict[str, Any]) -> None:
        for index, step in enumerate(self.plan_steps):
            if step["id"] == updated_step["id"]:
                self.plan_steps[index] = updated_step
                break
        self._update_progress()
        self._refresh()

    def _update_progress(self) -> None:
        total_steps = max(len(self.plan_steps), 1)
        steps_done = sum(1 for step in self.plan_steps if step.get("status") == "done")
        self.progress.update(self.progress_task_id, total=total_steps, completed=steps_done)

    def _build_status_renderable(self) -> Panel:
        spinner_progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold blue]{task.description}"),
            console=self.console,
            expand=True,
        )
        spinner_progress.add_task(self.status_message)
        return Panel(spinner_progress, border_style="blue")

    def _build_plan_tree(self) -> Panel:
        root = Tree(f"[bold cyan]{self.task_name}[/bold cyan]")
        for step in self.plan_steps:
            badge = self._type_badge(step.get("type", "unknown"))
            root.add(f"[green]#{step['id']}[/green] {badge} {step['title']}")
        return Panel(root, title="Plan", border_style="cyan")

    @staticmethod
    def _type_badge(step_type: str) -> str:
        colors = {
            "write_file": "magenta",
            "run_command": "blue",
            "create_dir": "cyan",
            "verify": "green",
        }
        color = colors.get(step_type, "white")
        return f"[{color}][{step_type.upper()}][/{color}]"

    def _build_renderable(self) -> Group:
        components: list[Any] = []
        if self.banner_panel is not None:
            components.append(self.banner_panel)
        components.append(self._build_status_renderable())
        if self.plan_steps:
            components.append(self._build_plan_tree())
        if self.event_panels:
            components.extend(self.event_panels)
        components.append(Panel(self.progress, title="Progress", border_style="white"))
        return Group(*components)

    def _refresh(self) -> None:
        self.live.update(self._build_renderable(), refresh=True)
