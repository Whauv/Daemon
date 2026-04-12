from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"


def _bootstrap_src_path() -> None:
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))


def _runtime_defaults() -> tuple[int, str]:
    _bootstrap_src_path()
    from daemon.config import MAX_RETRIES, WORKSPACE_DIR

    return MAX_RETRIES, WORKSPACE_DIR


def _console():
    from rich.console import Console

    return Console()


def parse_args() -> argparse.Namespace:
    max_retries, workspace_dir = _runtime_defaults()
    parser = argparse.ArgumentParser(description="Daemon local orchestrator")
    parser.add_argument(
        "--task",
        help="Task description for Daemon",
    )
    parser.add_argument(
        "--workspace",
        default=workspace_dir,
        help="Workspace directory where the task will be executed",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=max_retries,
        help="Maximum retries before the run stops",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print the plan without executing any steps",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Launch the local web dashboard instead of the CLI run flow",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=8080,
        help="Port for the local dashboard server",
    )
    return parser.parse_args()


def main() -> None:
    _bootstrap_src_path()
    console = _console()
    args = parse_args()
    if args.dashboard:
        from daemon.dashboard.app import app as dashboard_app
        import uvicorn

        dashboard_url = f"http://127.0.0.1:{args.dashboard_port}"
        console.print(f"[green]Starting dashboard on {dashboard_url}[/green]")
        threading.Timer(1.2, lambda: webbrowser.open(dashboard_url)).start()
        uvicorn.run(dashboard_app, host="127.0.0.1", port=args.dashboard_port)
        return

    if not args.task:
        console.print("[red]Error:[/red] --task is required unless --dashboard is used.")
        raise SystemExit(1)

    task_text = args.task.strip()
    if len(task_text.split()) < 5:
        console.print("[yellow]Warning:[/yellow] Please provide a more specific task with at least 5 words.")
        raise SystemExit(1)

    workspace_dir = Path(args.workspace).resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    try:
        if args.dry_run:
            from daemon.agents.planner import Planner
            from daemon.ui.display import DaemonDisplay

            display = DaemonDisplay()
            planner = Planner(display=display)
            plan = planner.generate_plan(task=task_text, workspace_dir=str(workspace_dir))
            display.show_plan(plan, task_name=task_text)
            display.close()
            console.print("[green]Dry run complete. No steps were executed.[/green]")
            return

        from daemon.core.loop import run

        final_state = run(task=task_text, workspace_dir=str(workspace_dir), max_retries=args.max_retries)
    except KeyboardInterrupt:
        console.print("[yellow]Session interrupted[/yellow]")
        return

    session_log_path = (workspace_dir / "daemon_session_log.json").resolve()
    console.print(f"Session log: {session_log_path}")
    console.print(f"Final status: {final_state.status}")


if __name__ == "__main__":
    main()
