# project-reminders

A local-first control panel for the lifecycle, engineering health, and live operational state of code projects.

The repository keeps three layers separate:

1. **Declared lifecycle** — where you say the project is: idea, active development, hardening, maintenance, and so on.
2. **Engineering health** — deterministic assessment of tests, typing, lint, CI configuration, documentation, packaging, security, reproducibility, releases, and demos.
3. **Observed GitHub state** — current open PRs, latest CI result, latest repository activity, release/tag, and observation time.

GitHub is evidence, not the source of truth. The portfolio stays in `data/projects.json`.

## Lifecycle

```text
idea → prototype → active_development → hardening → portfolio_ready → maintenance

paused | archived | abandoned
```

## GitHub discovery

```bash
export PROJECT_SCAN_TOKEN=...
poetry run project-reminders discover
poetry run project-reminders import-github --dry-run
poetry run project-reminders import-github
```

Imported projects start at `idea`, `medium`, with unknown health. Discovery does not infer maturity.

## Engineering-health assessment

```bash
poetry run project-reminders assess project-reminders
poetry run project-reminders assess
poetry run project-reminders assess --write
```

Assessment is deterministic and conservative. If a recursive GitHub tree is truncated, absence cannot become a negative claim.

## Operational state

The next layer observes live GitHub state while leaving lifecycle and health untouched:

```bash
poetry run project-reminders observe project-reminders
poetry run project-reminders observe
poetry run project-reminders observe --write
```

A refresh records open pull requests, the latest Actions state, latest repository activity, latest release and tag. One inaccessible repository does not abort a portfolio-wide refresh; its previous snapshot is retained and the failure is reported.

A failing CI snapshot is an attention signal on the dashboard. An open PR by itself is informational.

## Web dashboard

```bash
poetry run project-reminders serve
```

Open `http://127.0.0.1:8000`. The server is local-only by default.

## Development

Python 3.13+.

```bash
poetry install
poetry run ruff check .
poetry run mypy .
poetry run pytest
```

## Next slices

1. Scheduled GitHub refresh and reminders.
2. Bulk classification of imported repositories.
3. Portfolio analytics and staleness views.
