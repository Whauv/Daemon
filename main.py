from __future__ import annotations

import argparse
from pathlib import Path

from config import MAX_RETRIES, WORKSPACE_DIR
from rich.console import Console


console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nexus Agent local orchestrator")
    parser.add_argument(
        "--task",
        required=True,
        help="Task description for Nexus Agent",
    )
    parser.add_argument(
        "--workspace",
        default=WORKSPACE_DIR,
        help="Workspace directory where the task will be executed",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=MAX_RETRIES,
        help="Maximum retries before the run stops",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print the plan without executing any steps",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_text = args.task.strip()
    if len(task_text.split()) < 5:
        console.print("[yellow]Warning:[/yellow] Please provide a more specific task with at least 5 words.")
        raise SystemExit(1)

    workspace_dir = Path(args.workspace).resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    try:
        if args.dry_run:
            from agents.planner import Planner
            from ui.display import NexusDisplay

            display = NexusDisplay()
            planner = Planner(display=display)
            plan = planner.generate_plan(task=task_text, workspace_dir=str(workspace_dir))
            display.show_plan(plan, task_name=task_text)
            display.close()
            console.print("[green]Dry run complete. No steps were executed.[/green]")
            return

        from core.loop import run

        final_state = run(task=task_text, workspace_dir=str(workspace_dir), max_retries=args.max_retries)
    except KeyboardInterrupt:
        console.print("[yellow]Session interrupted[/yellow]")
        return

    session_log_path = (workspace_dir / "nexus_session_log.json").resolve()
    console.print(f"Session log: {session_log_path}")
    console.print(f"Final status: {final_state.status}")


if __name__ == "__main__":
    main()
