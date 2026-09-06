# project-reminders

A local-first control panel for the lifecycle and engineering health of code projects.

The repository answers three questions:

1. **Where is each project?** Lifecycle state from idea to maintenance or archive.
2. **How healthy is it?** Tests, typing, lint, CI, documentation, packaging, security, reproducibility, release and demo readiness.
3. **What should happen next?** Every active project can carry one concrete next action and an optional blocker.

GitHub is evidence, not the source of truth. The portfolio stays in a plain JSON file committed to this repository.

## Lifecycle

```text
idea → prototype → active_development → hardening → portfolio_ready → maintenance

paused | archived | abandoned
```

Lifecycle and engineering health are intentionally separate.

## Engineering health

Each dimension is one of `unknown`, `missing`, `partial`, `complete`, or `not_applicable`: tests, typing, lint, CI, documentation, packaging, security, reproducibility, release and demo.

`unknown` is important: an uninspected repository is not automatically unhealthy. The deterministic rules are documented in [`docs/assessment-rules.md`](docs/assessment-rules.md).

## Installation

Python 3.13 or newer is required.

```bash
poetry install
poetry run project-reminders --help
```

## GitHub discovery and import

Repository discovery uses a read token from `PROJECT_SCAN_TOKEN` or `GITHUB_TOKEN`.

```bash
export PROJECT_SCAN_TOKEN=...
poetry run project-reminders discover
poetry run project-reminders import-github --dry-run
poetry run project-reminders import-github
```

Imports are conservative: new repositories start at `idea`, `medium`, with every health dimension `unknown`. Existing tracked repositories are never overwritten.

## Deterministic assessment

Preview one project without writing anything:

```bash
poetry run project-reminders assess project-reminders
```

Assess every tracked repository:

```bash
poetry run project-reminders assess
```

Persist those observed health states only when you choose to:

```bash
poetry run project-reminders assess --write
```

Assessment can change only engineering health. It never changes status, priority, next action, or blocker. A truncated GitHub tree cannot create a negative health claim: absent evidence remains `unknown`.

## Manual project management

```bash
poetry run project-reminders dashboard
poetry run project-reminders status project-reminders hardening
poetry run project-reminders health project-reminders tests complete
poetry run project-reminders next-action project-reminders "Import the first portfolio repositories"
```

## Web dashboard

```bash
poetry run project-reminders serve
```

Open `http://127.0.0.1:8000`.

## Development

```bash
poetry install
poetry run ruff check .
poetry run mypy .
poetry run pytest
```

CI runs all three gates on Python 3.13.

## Next slices

1. Open PR / failed CI / current release observation.
2. Scheduled refresh and attention reminders.
3. Bulk classification of imported repositories.
