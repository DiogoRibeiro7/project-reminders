"""Declarative GitHub Project view specifications."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ViewSpec:
    """One managed GitHub Project view."""

    name: str
    layout: str
    filter_query: str = ""
    visible_fields: tuple[str, ...] = ()
    sort_by: tuple[tuple[str, str], ...] = ()
    group_by: tuple[str, ...] = ()
    vertical_group_by: tuple[str, ...] = ()


MANAGED_VIEW_SPECS: tuple[ViewSpec, ...] = (
    ViewSpec(
        name="Portfolio",
        layout="table",
        visible_fields=(
            "Title",
            "Lifecycle",
            "Priority",
            "CI",
            "Open PRs",
            "Next action",
            "Health",
            "Health score",
            "Activity date",
            "Repository URL",
        ),
        sort_by=(("Priority", "desc"), ("Open PRs", "desc")),
    ),
    ViewSpec(
        name="Lifecycle Board",
        layout="board",
        filter_query="-Lifecycle:archived -Lifecycle:abandoned",
        visible_fields=("Title", "Priority", "CI", "Open PRs", "Next action"),
        vertical_group_by=("Lifecycle",),
    ),
    ViewSpec(
        name="Needs Classification",
        layout="table",
        filter_query="Lifecycle:unclassified",
        visible_fields=(
            "Title",
            "Repository URL",
            "CI",
            "Health score",
            "Activity date",
        ),
    ),
    ViewSpec(
        name="CI Problems",
        layout="table",
        filter_query="CI:failing,cancelled",
        visible_fields=(
            "Title",
            "Lifecycle",
            "Priority",
            "CI",
            "Open PRs",
            "Next action",
            "Repository URL",
        ),
        sort_by=(("Priority", "desc"),),
    ),
    ViewSpec(
        name="Open PRs",
        layout="table",
        filter_query="open-prs:>0",
        visible_fields=(
            "Title",
            "Lifecycle",
            "Priority",
            "CI",
            "Open PRs",
            "Next action",
            "Repository URL",
        ),
        sort_by=(("Open PRs", "desc"), ("Priority", "desc")),
    ),
    ViewSpec(
        name="Portfolio Ready",
        layout="table",
        filter_query="Lifecycle:portfolio_ready",
        visible_fields=(
            "Title",
            "Priority",
            "CI",
            "Health score",
            "Activity date",
            "Repository URL",
        ),
    ),
    ViewSpec(
        name="Active Work",
        layout="table",
        filter_query=(
            "Lifecycle:prototype,active_development,hardening "
            "-Lifecycle:paused,archived,abandoned"
        ),
        visible_fields=(
            "Title",
            "Lifecycle",
            "Priority",
            "CI",
            "Open PRs",
            "Next action",
            "Health score",
            "Activity date",
        ),
        sort_by=(("Priority", "desc"), ("Open PRs", "desc")),
    ),
    ViewSpec(
        name="High Priority",
        layout="table",
        filter_query="Priority:critical,high -Lifecycle:archived,abandoned",
        visible_fields=(
            "Title",
            "Lifecycle",
            "Priority",
            "CI",
            "Open PRs",
            "Next action",
            "Health score",
            "Activity date",
        ),
        sort_by=(("Priority", "desc"), ("Open PRs", "desc")),
    ),
    ViewSpec(
        name="Maintenance",
        layout="table",
        filter_query="Lifecycle:maintenance",
        visible_fields=(
            "Title",
            "Priority",
            "CI",
            "Health score",
            "Activity date",
            "Next action",
            "Repository URL",
        ),
        sort_by=(("Activity date", "desc"),),
    ),
    ViewSpec(
        name="Engineering Gaps",
        layout="table",
        filter_query="health-score:<10 -Lifecycle:archived,abandoned",
        visible_fields=(
            "Title",
            "Lifecycle",
            "Priority",
            "CI",
            "Health score",
            "Health",
            "Next action",
            "Repository URL",
        ),
        sort_by=(("Health score", "asc"), ("Priority", "desc")),
    ),
    ViewSpec(
        name="Quiet 30d",
        layout="table",
        filter_query=(
            "activity-date:<@today-30d -Lifecycle:archived,abandoned "
            "-Lifecycle:unclassified"
        ),
        visible_fields=(
            "Title",
            "Lifecycle",
            "Priority",
            "CI",
            "Activity date",
            "Health score",
            "Next action",
            "Repository URL",
        ),
        sort_by=(("Activity date", "asc"), ("Priority", "desc")),
    ),
    ViewSpec(
        name="Attention Queue",
        layout="table",
        filter_query="attention-reasons:>0 -Lifecycle:archived,abandoned",
        visible_fields=(
            "Title",
            "Lifecycle",
            "Priority",
            "CI",
            "Open PRs",
            "Next action",
            "Attention",
            "Attention reasons",
            "Repository URL",
        ),
        sort_by=(("Attention", "desc"), ("Priority", "desc")),
    ),
)


def missing_view_specs(existing_names: set[str]) -> tuple[ViewSpec, ...]:
    """Return managed views that do not already exist, preserving declared order."""

    folded = {name.casefold() for name in existing_names}
    return tuple(spec for spec in MANAGED_VIEW_SPECS if spec.name.casefold() not in folded)
