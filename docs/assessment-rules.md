# Engineering-health assessment rules

Assessment is deliberately **evidence based**. It classifies only engineering-health dimensions; it never changes lifecycle status, priority, next action, or blocker.

## States

- `complete`: a strong recognized signal is present.
- `partial`: some useful evidence exists but does not satisfy the full rule.
- `missing`: the complete repository tree was inspected and no recognized signal exists.
- `unknown`: evidence is incomplete or the dimension cannot be judged safely.
- `not_applicable`: reserved for explicit manual classification; automatic assessment does not currently emit it.

## Rules

| Dimension | Complete | Partial | Missing / unknown |
|---|---|---|---|
| tests | `tests/` or `test/` | isolated `test_*` files | absent on complete tree / truncated tree |
| CI | `.github/workflows/`, GitLab CI, or Azure Pipelines | — | absent on complete tree / truncated tree |
| documentation | README + `docs/` | README only | no recognized docs |
| packaging | recognized package manifest | — | none found |
| lint | recognized linter config or `pyproject.toml` | — | none found |
| typing | mypy/pyright config or Python `pyproject.toml` | — | only a negative claim for complete Python repos |
| security | `SECURITY.md`, Dependabot, CodeQL, or security workflow | — | none found |
| reproducibility | lock file + environment/container definition | one of those | neither |
| release | GitHub release | tag only | no release/tag |
| demo | `examples/`, `example/`, `demo/`, or `notebooks/` | — | none found |

## Incomplete trees

GitHub can return a recursively requested tree with `truncated=true`. In that case, **absence is not evidence of missingness**. Dimensions based on missing paths remain `unknown`.

This is the core safety rule of the assessor: positive evidence may be used from a partial tree, but negative conclusions require a complete tree.
