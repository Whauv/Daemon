from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from core.state import AgentState, ExecutionResult, PlanStep


class NexusDisplay:
    def __init__(self) -> None:
        self.console = Console()

    def show_banner(self) -> None:
        self.console.print(Panel("[bold cyan]Nexus Agent[/bold cyan]", border_style="cyan"))

    def show_status(self, message: str) -> None:
        self.console.print(f"[bold blue]{message}[/bold blue]")

    def show_plan(self, steps: list[PlanStep | dict[str, Any]], title: str = "Execution Plan") -> None:
        tree = Tree(f"[bold cyan]{title}[/bold cyan]")
        for step in steps:
            normalized = step if isinstance(step, dict) else step.model_dump()
            tree.add(
                f"[green]{normalized['id']}[/green] {normalized['title']} ({normalized['type']})"
            )
        self.console.print(tree)

    def show_step_start(self, step: PlanStep | dict[str, Any]) -> None:
        normalized = step if isinstance(step, dict) else step.model_dump()
        self.console.print(
            Panel(
                f"[bold]{normalized['title']}[/bold]\n{normalized['description']}",
                title=f"Running {normalized['id']}",
                border_style="blue",
            )
        )

    def show_step_done(self, step: PlanStep | dict[str, Any]) -> None:
        normalized = step if isinstance(step, dict) else step.model_dump()
        self.console.print(
            Panel(normalized.get("output", "Completed."), title=f"{normalized['id']} DONE", border_style="green")
        )

    def show_step_failed(self, step: PlanStep | dict[str, Any]) -> None:
        normalized = step if isinstance(step, dict) else step.model_dump()
        self.console.print(
            Panel(normalized.get("output", "Failed."), title=f"{normalized['id']} FAILED", border_style="red")
        )

    def show_success(self, summary: str) -> None:
        self.console.print(Panel(summary, title="Success", border_style="green"))

    def show_issues(self, issues: list[str]) -> None:
        issue_text = "\n".join(f"- {issue}" for issue in issues) if issues else "No issues reported."
        self.console.print(Panel(issue_text, title="Issues", border_style="yellow"))

    def show_fatal_error(self, message: str) -> None:
        self.console.print(Panel(message, title="Fatal Error", border_style="red"))

    def log(self, message: str) -> None:
        self.console.print(f"[yellow]LOG:[/yellow] {message}")

    def show_summary(self, state: AgentState) -> None:
        table = Table(title="Nexus Agent Summary")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Task", state.task)
        table.add_row("Workspace", state.workspace_dir)
        table.add_row("Status", state.status)
        table.add_row("Completed steps", str(len(state.completed_steps)))
        table.add_row("Failed steps", str(len(state.failed_steps)))
        table.add_row("Retries", str(state.retries))
        self.console.print(table)
