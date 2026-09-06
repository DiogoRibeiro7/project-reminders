"""Command-line interface for project-reminders."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from project_reminders.application.dashboard import build_dashboard
from project_reminders.bootstrap import build_service
from project_reminders.domain.enums import HealthDimension, HealthState, Priority, ProjectStatus
from project_reminders.domain.models import Project


def _print_project(project: Project) -> None:
    print(f"{project.name} [{project.status.value}] ({project.priority.value})")
    print(f"  repository: {project.repository}")
    print(f"  next: {project.next_action.description if project.next_action else '—'}")
    print(f"  blocker: {project.blocker or '—'}")
    health = " ".join(
        f"{dimension.value}={project.health.state_for(dimension).value}"
        for dimension in HealthDimension
    )
    print(f"  health: {health}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-reminders")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("dashboard")
    subparsers.add_parser("list")

    show = subparsers.add_parser("show")
    show.add_argument("identifier")

    add = subparsers.add_parser("add")
    add.add_argument("name")
    add.add_argument("--repo", required=True)
    add.add_argument("--status", choices=[item.value for item in ProjectStatus], default="idea")
    add.add_argument("--priority", choices=[item.value for item in Priority], default="medium")
    add.add_argument("--next-action")
    add.add_argument("--summary", default="")

    status = subparsers.add_parser("status")
    status.add_argument("identifier")
    status.add_argument("status", choices=[item.value for item in ProjectStatus])

    next_action = subparsers.add_parser("next-action")
    next_action.add_argument("identifier")
    next_action.add_argument("description", nargs="?")
    next_action.add_argument("--clear", action="store_true")

    health = subparsers.add_parser("health")
    health.add_argument("identifier")
    health.add_argument("dimension", choices=[item.value for item in HealthDimension])
    health.add_argument("state", choices=[item.value for item in HealthState])

    serve = subparsers.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""

    args = _parser().parse_args(argv)
    root: Path = args.root
    service = build_service(root)

    try:
        if args.command == "dashboard":
            dashboard = build_dashboard(service.load())
            print(f"Active: {dashboard.active_count} | Needs attention: {dashboard.attention_count}")
            for card in dashboard.cards:
                next_text = card.project.next_action.description if card.project.next_action else "—"
                print(
                    f"{card.project.name:36} {card.project.status.value:20} "
                    f"{card.project.priority.value:8} next: {next_text}"
                )
                for reason in card.reasons:
                    print(f"  ! {reason}")
            return 0

        if args.command == "list":
            for project in service.load().projects:
                _print_project(project)
            return 0

        if args.command == "show":
            _print_project(service.find(args.identifier))
            return 0

        if args.command == "add":
            project = service.add_project(
                name=args.name,
                repository=args.repo,
                status=ProjectStatus(args.status),
                priority=Priority(args.priority),
                next_action=args.next_action,
                summary=args.summary,
            )
            _print_project(project)
            return 0

        if args.command == "status":
            _print_project(service.set_status(args.identifier, ProjectStatus(args.status)))
            return 0

        if args.command == "next-action":
            if args.clear and args.description is not None:
                raise ValueError("provide a description or --clear, not both")
            if not args.clear and args.description is None:
                raise ValueError("next-action requires a description or --clear")
            _print_project(service.set_next_action(args.identifier, None if args.clear else args.description))
            return 0

        if args.command == "health":
            _print_project(
                service.set_health(
                    args.identifier,
                    HealthDimension(args.dimension),
                    HealthState(args.state),
                )
            )
            return 0

        if args.command == "serve":
            import uvicorn

            from project_reminders.web import create_app

            uvicorn.run(create_app(root), host=args.host, port=args.port)
            return 0
    except (KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}")
        return 2

    raise AssertionError(f"unhandled command: {args.command}")
