"""Pure rules for deciding whether a managed Project card needs synchronization."""

from __future__ import annotations

FINGERPRINT_PREFIX = "<!-- project-reminders:last-activity="
FINGERPRINT_SUFFIX = " -->"


def body_with_last_activity(base_body: str, last_activity: str) -> str:
    """Attach the last-activity field value as a stable managed-card fingerprint."""

    fingerprint = f"{FINGERPRINT_PREFIX}{last_activity}{FINGERPRINT_SUFFIX}"
    return f"{base_body}\n{fingerprint}"


def needs_card_sync(current_body: str, desired_body: str) -> bool:
    """Return whether the draft body or its field-driving fingerprint changed."""

    return current_body != desired_body
