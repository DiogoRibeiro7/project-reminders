"""Tests for supported GitHub Project view reconciliation state."""

from project_reminders.application.project_views import ViewSpec
from scripts.ensure_project_views import FieldRef, ViewState, _field_refs, _needs_update


def _state(**changes: object) -> ViewState:
    values: dict[str, object] = {
        "node_id": "PVTV_one",
        "name": "Portfolio",
        "layout": "table",
        "filter_query": "",
        "visible_fields": ("Title", "Lifecycle"),
    }
    values.update(changes)
    return ViewState(**values)  # type: ignore[arg-type]


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
    assert not _needs_update(_state(), _spec())


def test_supported_view_drift_requires_update() -> None:
    assert _needs_update(_state(layout="board"), _spec())
    assert _needs_update(_state(filter_query="CI:failing"), _spec())
    assert _needs_update(_state(visible_fields=("Lifecycle", "Title")), _spec())


def test_sort_and_group_drift_are_not_claimed_as_reconcilable() -> None:
    spec = _spec(
        sort_by=(("Priority", "desc"),),
        group_by=("Lifecycle",),
        vertical_group_by=("Priority",),
    )

    assert not _needs_update(_state(), spec)


def test_field_refs_preserve_requested_order_and_both_identifier_types() -> None:
    fields = {
        "Title": FieldRef(node_id="PVTF_title", database_id=10),
        "Lifecycle": FieldRef(node_id="PVTSSF_lifecycle", database_id=20),
    }

    assert _field_refs(("Lifecycle", "Title"), fields) == (
        FieldRef(node_id="PVTSSF_lifecycle", database_id=20),
        FieldRef(node_id="PVTF_title", database_id=10),
    )
