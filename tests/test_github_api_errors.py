"""GitHub REST transport-error diagnostics tests."""

from __future__ import annotations

import io
import json
from email.message import Message
from urllib.error import HTTPError

import pytest

import project_reminders.infrastructure.github as github_module
from project_reminders.infrastructure.github import GitHubApiError, GitHubRepositoryDiscovery


def _http_error(
    *,
    status: int = 403,
    message: str = "Forbidden",
    headers: dict[str, str] | None = None,
    extra_body: dict[str, object] | None = None,
) -> HTTPError:
    response_headers = Message()
    for name, value in (headers or {}).items():
        response_headers[name] = value
    payload: dict[str, object] = {"message": message}
    payload.update(extra_body or {})
    body = io.BytesIO(json.dumps(payload).encode("utf-8"))
    return HTTPError(
        "https://api.github.com/user/repos",
        status,
        message,
        response_headers,
        body,
    )


def _raise(error: HTTPError):  # type: ignore[no-untyped-def]
    def raising_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise error

    return raising_urlopen


def test_primary_rate_limit_preserves_safe_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    error = _http_error(
        message="API rate limit exceeded for user ID 123.",
        headers={
            "X-GitHub-Request-Id": "REQ-123",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1789134000",
            "X-RateLimit-Resource": "core",
        },
        extra_body={"token": "must-not-leak"},
    )
    monkeypatch.setattr(github_module, "urlopen", _raise(error))

    with pytest.raises(GitHubApiError) as captured:
        GitHubRepositoryDiscovery("secret-token").repositories()

    exc = captured.value
    assert exc.status == 403
    assert exc.kind == "primary_rate_limit"
    assert exc.endpoint == "/user/repos"
    assert exc.request_id == "REQ-123"
    assert exc.rate_limit_limit == "5000"
    assert exc.rate_limit_remaining == "0"
    assert exc.rate_limit_reset == "1789134000"
    assert exc.rate_limit_resource == "core"
    assert "must-not-leak" not in str(exc)
    assert "secret-token" not in str(exc)
    assert "primary_rate_limit" in str(exc)


def test_secondary_rate_limit_uses_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    error = _http_error(
        message="You have exceeded a secondary rate limit.",
        headers={"Retry-After": "60", "X-GitHub-Request-Id": "REQ-SECONDARY"},
    )
    monkeypatch.setattr(github_module, "urlopen", _raise(error))

    with pytest.raises(GitHubApiError) as captured:
        GitHubRepositoryDiscovery("token").repositories()

    assert captured.value.kind == "secondary_rate_limit"
    assert captured.value.retry_after == "60"
    assert "request_id=REQ-SECONDARY" in str(captured.value)


def test_permission_error_is_distinguished_from_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = _http_error(message="Resource not accessible by personal access token")
    monkeypatch.setattr(github_module, "urlopen", _raise(error))

    with pytest.raises(GitHubApiError) as captured:
        GitHubRepositoryDiscovery("token").repositories()

    assert captured.value.kind == "permission"
    assert captured.value.rate_limit_remaining is None


def test_authentication_error_is_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    error = _http_error(status=401, message="Bad credentials")
    monkeypatch.setattr(github_module, "urlopen", _raise(error))

    with pytest.raises(GitHubApiError) as captured:
        GitHubRepositoryDiscovery("token").repositories()

    assert captured.value.kind == "authentication"


def test_error_message_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    error = _http_error(message="x" * 1000)
    monkeypatch.setattr(github_module, "urlopen", _raise(error))

    with pytest.raises(GitHubApiError) as captured:
        GitHubRepositoryDiscovery("token").repositories()

    assert captured.value.message is not None
    assert len(captured.value.message) == 300
    assert captured.value.message.endswith("…")
