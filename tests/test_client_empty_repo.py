"""An empty repository is missing data, not a failed application.

Launch day, 2026-08-19: five applications arrived and two never scored. Both
applicants had created a repository and not yet pushed to it, and GitHub answers
`409 Git Repository is empty.` when you ask an empty repo for its commits. The
client raised on any unhandled status, the exception propagated out of the
scorer, and the whole submission was parked back in `queued` -- so one empty repo
was enough to silently strand a real person's application.
"""

from __future__ import annotations

import io
import urllib.error

from talent_engine.github.client import GitHubClient


def _raiser(code: str, message: str):
    def urlopen(req, timeout=None):  # noqa: ARG001 - signature must match
        raise urllib.error.HTTPError(
            req.full_url, int(code), message, {}, io.BytesIO(b"{}")
        )

    return urlopen


def _client(monkeypatch, code, message):
    client = GitHubClient()
    client.sleep_fn = lambda _s: None
    monkeypatch.setattr(
        "talent_engine.github.client.urllib.request.urlopen",
        _raiser(code, message),
    )
    return client


def test_an_empty_repository_reads_as_no_commits(monkeypatch):
    client = _client(monkeypatch, "409", "Git Repository is empty.")
    assert client.get("/repos/someone/unpushed/commits") is None


def test_a_missing_repository_still_reads_as_no_data(monkeypatch):
    """The 404 path this sits next to must keep behaving the same."""
    client = _client(monkeypatch, "404", "Not Found")
    assert client.get("/repos/someone/deleted/commits") is None


def test_an_unexpected_status_still_raises(monkeypatch):
    """409 is handled because it has a known, benign meaning. Widening the
    exception handler to swallow everything would hide real breakage."""
    client = _client(monkeypatch, "422", "Unprocessable Entity")
    try:
        client.get("/repos/someone/thing/commits")
    except urllib.error.HTTPError as exc:
        assert exc.code == 422
    else:  # pragma: no cover - the assertion below reports the failure
        raise AssertionError("an unexpected status must not be swallowed")
