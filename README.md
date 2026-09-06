# project-reminders

A local-first control panel for the lifecycle and engineering health of code projects.

The repository answers three questions:

1. **Where is each project?** Lifecycle state from idea to maintenance or archive.
2. **How healthy is it?** Tests, typing, linting, CI, documentation, packaging, security, reproducibility, release and demo readiness.
3. **What should happen next?** Every active project can carry one concrete next action and an optional blocker.

GitHub is evidence, not the source of truth. The portfolio stays in a plain JSON file committed to this repository.

## Lifecycle

```text
idea → prototype → active_development → hardening → portfolio_ready → maintenance

paused | archived | abandoned
```

Lifecycle and engineering health are intentionally separate. A repository can be in active development with excellent CI, or portfolio-ready while still missing a formal release.

## Engineering health

Each dimension is one of `unknown`, `missing`, `partial`, `complete`, or `not_applicable`: tests, typing, lint, CI, documentation, packaging, security, reproducibility, release and demo.

`unknown` is important: an uninspected repository is not automatically unhealthy.

## Architecture

```text
src/project_reminders/
├── domain/          model and rules; no infrastructure imports
├── application/     portfolio mutations, discovery/import, dashboard read models
├── infrastructure/  JSON persistence and GitHub adapters
├── cli.py            command-line interface
└── web.py            FastAPI + Jinja2 local dashboard
```

## Installation

Python 3.13 or newer is required.

```bash
poetry install
poetry run project-reminders --help
```

## GitHub discovery and import

Repository discovery uses a read token from `PROJECT_SCAN_TOKEN` or `GITHUB_TOKEN`. For a portfolio containing private repositories, the token must be able to read those repositories.

Start with a dry run:

```bash
export PROJECT_SCAN_TOKEN=...
poetry run project-reminders discover
poetry run project-reminders import-github --dry-run
```

By default forks and archived repositories are skipped. They can be included explicitly:

```bash
poetry run project-reminders discover --include-forks --include-archived
```

A real import is intentionally conservative:

```bash
poetry run project-reminders import-github
```

Every imported repository starts as:

```text
status   = idea
priority = medium
health   = unknown for every dimension
```

That is not a claim that the repository is immature. It means the tracker has observed that the repository exists but has not yet classified it. Repository descriptions are copied as summaries; existing tracked repositories are never overwritten.

## Manual project management

```bash
poetry run project-reminders add "project-reminders" \
  --repo DiogoRibeiro7/project-reminders \
  --status active_development \
  --priority high \
  --next-action "Add deterministic repository assessment"

poetry run project-reminders dashboard
poetry run project-reminders status project-reminders hardening
poetry run project-reminders health project-reminders tests complete
poetry run project-reminders next-action project-reminders "Import the first portfolio repositories"
```

## Web dashboard

```bash
poetry run project-reminders serve
```

Open `http://127.0.0.1:8000`. The server binds to localhost by default and has no authentication; it is intended as a local control panel.

## Development

```bash
poetry install
poetry run ruff check .
poetry run mypy .
poetry run pytest
```

CI runs all three gates on Python 3.13.

## Next slices

1. Deterministic engineering-health assessment from repository evidence.
2. Open PR / failed CI / release observation.
3. Scheduled refresh and attention reminders.
4. Bulk classification of imported repositories.
