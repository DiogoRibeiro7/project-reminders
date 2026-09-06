"""Command-line interface for project-reminders."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from project_reminders.application.assessment import AssessmentService
from project_reminders.application.dashboard import build_dashboard
from project_reminders.application.github_import import GitHubImportService, ImportPlan
from project_reminders.application.operational import OperationalRefreshService
from project_reminders.bootstrap import build_service
from project_reminders.domain.enums import HealthDimension, HealthState, Priority, ProjectStatus
from project_reminders.domain.models import Project
from project_reminders.infrastructure.github import GitHubOperationalState, GitHubRepositoryDiscovery, GitHubRepositoryEvidence


def _print_project(project: Project) -> None:
    print(f"{project.name} [{project.status.value}] ({project.priority.value})")
    print(f"  repository: {project.repository}")
    print(f"  next: {project.next_action.description if project.next_action else '—'}")
    print(f"  blocker: {project.blocker or '—'}")
    print(f"  ci: {project.operational.ci_state.value}")
    print(f"  open PRs: {len(project.operational.open_pull_requests)}")
    health = " ".join(f"{dimension.value}={project.health.state_for(dimension).value}" for dimension in HealthDimension)
    print(f"  health: {health}")


def _github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("PROJECT_SCAN_TOKEN")
    if token is None:
        raise ValueError("set GITHUB_TOKEN or PROJECT_SCAN_TOKEN for GitHub access")
    return token


def _github_importer(root: Path) -> GitHubImportService:
    return GitHubImportService(build_service(root), GitHubRepositoryDiscovery(_github_token()))


def _print_plan(plan: ImportPlan) -> None:
    print(f"Candidates: {len(plan.candidates)}")
    for repository in plan.candidates:
        visibility = "private" if repository.private else "public"
        print(f"  + {repository.full_name} [{visibility}]")
    print(f"Already tracked: {len(plan.skipped_existing)}")
    print(f"Forks skipped: {len(plan.skipped_forks)}")
    print(f"Archived skipped: {len(plan.skipped_archived)}")


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
    discover = subparsers.add_parser("discover")
    discover.add_argument("--include-forks", action="store_true")
    discover.add_argument("--include-archived", action="store_true")
    discover.add_argument("--json", action="store_true")
    import_github = subparsers.add_parser("import-github")
    import_github.add_argument("--include-forks", action="store_true")
    import_github.add_argument("--include-archived", action="store_true")
    import_github.add_argument("--dry-run", action="store_true")
    assess = subparsers.add_parser("assess")
    assess.add_argument("identifier", nargs="?")
    assess.add_argument("--write", action="store_true")
    observe = subparsers.add_parser("observe")
    observe.add_argument("identifier", nargs="?")
    observe.add_argument("--write", action="store_true")
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
                print(f"{card.project.name:36} {card.project.status.value:20} {card.project.priority.value:8} CI={card.project.operational.ci_state.value:9} PRs={len(card.project.operational.open_pull_requests):2} next: {next_text}")
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
            project = service.add_project(name=args.name, repository=args.repo, status=ProjectStatus(args.status), priority=Priority(args.priority), next_action=args.next_action, summary=args.summary)
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
            _print_project(service.set_health(args.identifier, HealthDimension(args.dimension), HealthState(args.state)))
            return 0
        if args.command in {"discover", "import-github"}:
            importer = _github_importer(root)
            plan = importer.plan(include_forks=args.include_forks, include_archived=args.include_archived)
            if args.command == "discover":
                if args.json:
                    print(json.dumps(asdict(plan), default=str, indent=2))
                else:
                    _print_plan(plan)
                return 0
            if args.dry_run:
                _print_plan(plan)
                return 0
            imported = importer.import_repositories(include_forks=args.include_forks, include_archived=args.include_archived)
            print(f"Imported {len(imported)} repositories")
            for project in imported:
                print(f"  + {project.repository}")
            return 0
        if args.command == "assess":
            assessor = AssessmentService(GitHubRepositoryEvidence(_github_token()))
            projects = (service.find(args.identifier),) if args.identifier else service.load().projects
            assessments = assessor.assess_many(tuple(project.repository for project in projects))
            for project in projects:
                health_value = assessments[project.repository]
                print(project.repository)
                for dimension in HealthDimension:
                    print(f"  {dimension.value:16} {health_value.state_for(dimension).value}")
            if args.write:
                service.apply_health_many(assessments)
                print(f"Updated {len(assessments)} project assessments")
            return 0
        if args.command == "observe":
            refresher = OperationalRefreshService(service, GitHubOperationalState(_github_token()))
            result = refresher.refresh(args.identifier, write=args.write)
            for repository, snapshot in result.snapshots:
                print(f"{repository}: CI={snapshot.ci_state.value}, PRs={len(snapshot.open_pull_requests)}, release={snapshot.latest_release or '—'}, tag={snapshot.latest_tag or '—'}")
            for repository, error in result.failed:
                print(f"{repository}: ERROR {error}")
            if args.write:
                print(f"Updated {len(result.updated)} operational snapshots")
            return 2 if result.failed and not result.updated else 0
        if args.command == "serve":
            import uvicorn
            from project_reminders.web import create_app
            uvicorn.run(create_app(root), host=args.host, port=args.port)
            return 0
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}")
        return 2
    raise AssertionError(f"unhandled command: {args.command}")
