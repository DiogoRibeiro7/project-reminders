"""Closed vocabularies used by the project portfolio."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    """Lifecycle state of a code project."""

    IDEA = "idea"
    PROTOTYPE = "prototype"
    ACTIVE_DEVELOPMENT = "active_development"
    HARDENING = "hardening"
    PORTFOLIO_READY = "portfolio_ready"
    MAINTENANCE = "maintenance"
    PAUSED = "paused"
    ARCHIVED = "archived"
    ABANDONED = "abandoned"


class Priority(StrEnum):
    """Relative portfolio priority."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HealthState(StrEnum):
    """Assessment state for one engineering-health dimension."""

    UNKNOWN = "unknown"
    MISSING = "missing"
    PARTIAL = "partial"
    COMPLETE = "complete"
    NOT_APPLICABLE = "not_applicable"


class HealthDimension(StrEnum):
    """Engineering concerns tracked independently from project lifecycle."""

    TESTS = "tests"
    TYPING = "typing"
    LINT = "lint"
    CI = "ci"
    DOCUMENTATION = "documentation"
    PACKAGING = "packaging"
    SECURITY = "security"
    REPRODUCIBILITY = "reproducibility"
    RELEASE = "release"
    DEMO = "demo"
