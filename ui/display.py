from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from core.state import AgentState, ExecutionResult, PlanStep


class NexusDisplay:
    def __init__(self) -> None:
        self.console = Console()

    def show_plan(self, steps: list[PlanStep], title: str = "Execution Plan") -> None:
        tree = Tree(f"[bold cyan]{title}[/bold cyan]")
        for step in steps:
            tree.add(f"[green]{step.id}[/green] {step.title} ({step.action})")
        self.console.print(tree)

    def show_step_start(self, step: PlanStep, iteration: int, max_iterations: int) -> None:
        self.console.print(
            Panel(
                f"[bold]{step.title}[/bold]\n{step.description}\nIteration {iteration}/{max_iterations}",
                title=f"Running {step.id}",
                border_style="blue",
            )
        )

    def show_step_result(self, step: PlanStep, result: ExecutionResult) -> None:
        status = "[green]SUCCESS[/green]" if result.success else "[red]FAILED[/red]"
        body = result.output or result.error or "No output."
        self.console.print(
            Panel(body, title=f"{step.id} {status}", border_style="green" if result.success else "red")
        )

    def log(self, message: str) -> None:
        self.console.print(f"[yellow]LOG:[/yellow] {message}")

    def show_summary(self, state: AgentState) -> None:
        table = Table(title="Nexus Agent Summary")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Task", state.original_task)
        table.add_row("Workspace", state.workspace)
        table.add_row("Status", state.status)
        table.add_row("Iterations", str(state.iteration))
        table.add_row("Completed steps", str(len(state.completed_steps)))
        table.add_row("Failed steps", str(len(state.failed_steps)))
        table.add_row("Last verification", state.last_verification or "n/a")
        self.console.print(table)
