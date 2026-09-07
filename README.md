# project-reminders

A local-first control panel for the lifecycle, engineering health, and live operational state of code projects.

The repository keeps three layers separate:

1. **Declared lifecycle** — where you say the project is: idea, active development, hardening, maintenance, and so on.
2. **Engineering health** — deterministic assessment of tests, typing, lint, CI configuration, documentation, packaging, security, reproducibility, releases, and demos.
3. **Observed GitHub state** — current open PRs, default-branch CI, latest repository activity, release/tag evidence, and observation freshness.

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

A refresh records open pull requests, default-branch Actions state and its exact run URL, latest repository activity, release/tag evidence, and observation time. One inaccessible repository does not abort a portfolio-wide operational refresh; its previous snapshot is retained and the failure is reported.

A failing CI snapshot is an attention signal on the dashboard. An open PR by itself is informational. Operational evidence older than 24 hours is displayed as stale; a repository with no successful observation is displayed as unobserved.

## Automated portfolio refresh

The `Refresh Code Portfolio` GitHub Actions workflow runs twice daily and can also be started manually. It performs the complete unattended cycle:

```text
assess repositories
        ↓
observe GitHub state
        ↓
update data/projects.json
        ↓
commit refreshed evidence
        ↓
sync GitHub Project #16
```

Repository failures are isolated. Successful assessment and observation results are persisted, while prior values are preserved for repositories that cannot be read.

The workflow deliberately uses two separate secrets:

- `PROJECT_SCAN_TOKEN` — read-only repository access for assessment and observation.
- `PROJECT_TOKEN` — GitHub Projects access for synchronizing Project #16.

The workflow's built-in `GITHUB_TOKEN` is used only to commit refreshed `data/projects.json` back to `main`.

Project #16 synchronization is handled only by `scripts/sync_project_board.py`; there is no second competing draft-card synchronizer.

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

1. Bulk classification of imported repositories.
2. Portfolio analytics beyond one-refresh trend comparison.
3. Optional reminders for projects that remain blocked or stale across multiple refreshes.
