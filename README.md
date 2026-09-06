# project-reminders

A local-first control panel for the lifecycle and engineering health of code projects.

The repository answers three questions:

1. **Where is each project?** Lifecycle state from idea to maintenance or archive.
2. **How healthy is it?** Tests, typing, linting, CI, documentation, packaging, security, reproducibility, release and demo readiness.
3. **What should happen next?** Every active project can carry one concrete next action and an optional blocker.

GitHub will be used as evidence, not as the source of truth. The portfolio stays in a plain JSON file committed to this repository.

## Lifecycle

```text
idea → prototype → active_development → hardening → portfolio_ready → maintenance

paused | archived | abandoned
```

Lifecycle and engineering health are intentionally separate. A repository can be in active development with excellent CI, or portfolio-ready while still missing a formal release.

## Engineering health

Each dimension is one of `unknown`, `missing`, `partial`, `complete`, or `not_applicable`:

- tests
- typing
- lint
- ci
- documentation
- packaging
- security
- reproducibility
- release
- demo

`unknown` is important: an uninspected repository is not automatically unhealthy.

## Architecture

```text
src/project_reminders/
├── domain/          model and rules; no infrastructure imports
├── application/     portfolio mutations and dashboard read models
├── infrastructure/  JSON persistence
├── cli.py            command-line interface
└── web.py            FastAPI + Jinja2 local dashboard
```

Dependencies point inward. The JSON file is authoritative; future GitHub scanning will populate observed evidence without silently changing declared lifecycle state.

## Data

```text
data/projects.json
```

The file is deliberately readable without this application. Writes are atomic and projects are stored in stable name order.

## Installation

Python 3.13 or newer is required.

```bash
poetry install
poetry run project-reminders --help
```

## First project

```bash
poetry run project-reminders add "project-reminders" \
  --repo DiogoRibeiro7/project-reminders \
  --status active_development \
  --priority high \
  --next-action "Add GitHub repository assessment"
```

Then inspect the portfolio:

```bash
poetry run project-reminders dashboard
poetry run project-reminders list
poetry run project-reminders show project-reminders
```

Update state and health explicitly:

```bash
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

The baseline intentionally does not guess repository health. The next implementation slices are:

1. GitHub repository discovery and observed activity.
2. Deterministic engineering-health assessment from repository evidence.
3. Open PR / failed CI / release state integration.
4. Scheduled refresh and attention reminders.
5. Portfolio import for existing repositories.
