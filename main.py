from __future__ import annotations

import argparse
from pathlib import Path

from config import settings
from core.loop import NexusLoop
from ui.display import NexusDisplay


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nexus Agent local orchestrator")
    parser.add_argument("task", nargs="*", help="High-level task for Nexus Agent")
    parser.add_argument(
        "--workspace",
        default=str(Path.cwd()),
        help="Workspace directory where the task will be executed",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=settings.max_iterations,
        help="Maximum loop iterations before the run stops",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task = " ".join(args.task).strip()

    if not task:
        task = input("Enter a task for Nexus Agent: ").strip()

    if not task:
        raise SystemExit("A task is required.")

    display = NexusDisplay()
    orchestrator = NexusLoop(display=display, workspace=Path(args.workspace))
    final_state = orchestrator.run(task=task, max_iterations=args.max_iterations)

    display.show_summary(final_state)


if __name__ == "__main__":
    main()
