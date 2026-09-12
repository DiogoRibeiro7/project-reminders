# Repository-local project metadata

Managed repositories may declare planning metadata in `.project.json`.

The file is deliberately small. It describes planning state that GitHub cannot infer reliably and that is not already owned by the central portfolio record.

## Source-of-truth boundary

The central `data/projects.json` portfolio remains authoritative for:

- repository identity
- declared lifecycle
- portfolio priority
- summary and next action
- blockers during the current migration
- engineering-health assessment
- observed GitHub state such as CI, pull requests, releases, tags, and repository activity

`.project.json` owns only the new planning concepts introduced by the portfolio operating model:

- project type
- strategic themes
- planning horizon
- WIP membership
- current milestone and acceptance criteria
- milestone dependencies
- target outcomes

This boundary avoids two writable copies of the same field while repositories are migrated progressively.

## Version 1 example

```json
{
  "schema_version": 1,
  "project_type": "research",
  "strategic_themes": ["mathematical-research", "scientific-software"],
  "planning": {
    "horizon": "now",
    "wip": true
  },
  "milestone": {
    "id": "M04",
    "title": "Complete identifiability analysis",
    "status": "wip",
    "acceptance": [
      {
        "id": "A1",
        "text": "Derive weak-identification condition",
        "done": true
      },
      {
        "id": "A2",
        "text": "Produce alpha/tau curvature map",
        "done": false
      }
    ]
  },
  "dependencies": [
    {
      "kind": "soft",
      "target": "breakinfer:M05"
    }
  ],
  "outcomes": [
    {
      "id": "O1",
      "type": "paper",
      "status": "in_progress",
      "target": "submission candidate"
    }
  ]
}
```

## Closed vocabularies

Project types:

`research`, `package`, `data`, `teaching`, `infrastructure`, `application`, `other`

Planning horizons:

`now`, `week`, `month`, `later`

Milestone states:

`ready`, `wip`, `finishing`, `blocked`, `done`, `stopped`

Dependency kinds:

`hard`, `soft`, `external`

Outcome types:

`paper`, `software_release`, `dataset`, `deliverable`, `reusable_asset`, `professional_artifact`, `research_result`

Outcome states:

`planned`, `in_progress`, `completed`, `stopped`

## Invariants

The validator enforces several portfolio rules rather than merely checking JSON syntax:

- `now` requires `wip=true`
- WIP requires a current milestone
- a WIP milestone must be `wip` or `finishing`
- `wip`/`finishing` milestone states require project WIP membership
- `finishing` requires every acceptance criterion to be complete
- current milestones cannot already be `done` or `stopped`
- acceptance-criterion IDs and outcome IDs must be unique
- duplicate strategic themes and dependencies are rejected
- unknown fields are rejected to surface schema drift

## Validation

From the repository root:

```bash
poetry run python scripts/validate_project_metadata.py
```

CI runs the same validation for this control-plane repository.

## Migration policy

Do not add `.project.json` to every repository at once.

Migration order is:

1. current WIP
2. active portfolio
3. recently active repositories
4. everything else only when touched or when an exception requires classification

Repository metadata represents current state, not full history. Historical decisions and reviews belong in the central control plane or Git history.
