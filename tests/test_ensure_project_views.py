"""Tests for supported GitHub Project view reconciliation state."""

from project_reminders.application.project_views import (
    ManagedViewState,
    ViewSpec,
    needs_supported_view_update,
)


def _state(**changes: object) -> ManagedViewState:
    values: dict[str, object] = {
        "node_id": "PVTV_one",
        "name": "Portfolio",
        "layout": "table",
        "filter_query": "",
        "visible_fields": ("Title", "Lifecycle"),
    }
    values.update(changes)
    return ManagedViewState(**values)  # type: ignore[arg-type]


def _spec(**changes: object) -> ViewSpec:
    values: dict[str, object] = {
        "name": "Portfolio",
        "layout": "table",
        "filter_query": "",
        "visible_fields": ("Title", "Lifecycle"),
    }
    values.update(changes)
    return ViewSpec(**values)  # type: ignore[arg-type]


def test_matching_supported_view_state_is_idempotent() -> None:
    assert not needs_supported_view_update(_state(), _spec())


def test_supported_view_drift_requires_update() -> None:
    assert needs_supported_view_update(_state(layout="board"), _spec())
    assert needs_supported_view_update(_state(filter_query="CI:failing"), _spec())
    assert needs_supported_view_update(
        _state(visible_fields=("Lifecycle", "Title")),
        _spec(),
    )


def test_sort_and_group_drift_are_not_claimed_as_reconcilable() -> None:
    spec = _spec(
        sort_by=(("Priority", "desc"),),
        group_by=("Lifecycle",),
        vertical_group_by=("Priority",),
    )

    assert not needs_supported_view_update(_state(), spec)
