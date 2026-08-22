"""Collector attribution: the noreply email fallback.

Regression coverage for a real failure: an applicant whose local git email is
the legacy `user@users.noreply.github.com` form is invisible to GitHub's
`?author=` commit filter, so months of shipping read as nil behind a partial
flag. The collector must recover those commits from the server-generated
noreply addresses, and must tell the applicant why the fallback fired.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from talent_engine.github.collector import Collector, noreply_email_variants


class FakeClient:
    """Records requests and replays canned pages, keyed on path AND params so
    author-filtered and unfiltered commit calls can return different pages."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.calls: list[tuple[str, dict]] = []
        self.stats = {"requests_spent": 0, "served_from_cache_304": 0}

    def _key(self, path, params):
        return (path, frozenset((params or {}).items()))

    def paginate(self, path, params=None, max_pages=10):
        self.calls.append((path, dict(params or {})))
        items = self.pages.get(self._key(path, params))
        if items is None:
            items = self.pages.get(path, [])
        yield from items

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        return self.pages.get(path, {})


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)
SINCE = (NOW - timedelta(days=183)).isoformat()


HANDLE = "builder"
USER_ID = 12345
VARIANT = f"{USER_ID}+{HANDLE}@users.noreply.github.com"


def user_page():
    return {
        f"/users/{HANDLE}": {"login": HANDLE, "id": USER_ID, "created_at": "2018-01-01T00:00:00Z"}
    }


def repo_page(pushed):
    return {
        "/users/builder/repos": [
            {
                "full_name": "builder/app",
                "owner": {"login": "builder"},
                "fork": False,
                "pushed_at": pushed,
                "created_at": "2026-01-01T00:00:00Z",
                "description": "an app",
                "language": "Python",
                "topics": [],
                "stargazers_count": 0,
                "has_pages": False,
                "homepage": "",
                "license": None,
            }
        ]
    }


def commit(email, login, date):
    return {
        "author": {"login": login} if login else None,
        "commit": {"author": {"email": email, "date": date}},
    }


def test_variants_cover_prefixed_and_legacy_forms():
    assert noreply_email_variants("Builder", USER_ID) == [
        VARIANT,
        "builder@users.noreply.github.com",
    ]
    assert noreply_email_variants("Builder", None) == ["builder@users.noreply.github.com"]


def test_fallback_recovers_unlinked_noreply_commits():
    """Login filter finds zero; email fallback recovers the real history."""
    pages = {
        **user_page(),
        **repo_page("2026-08-01T00:00:00Z"),
        "/repos/builder/releases": [],
        "/search/issues": [],
    }
    # Author-filtered call: nothing (GitHub could not link the emails).
    # Unfiltered call: the applicant's own unlinked commits + a colleague's.
    pages[("/repos/builder/app/commits", frozenset({"author": HANDLE, "since": SINCE}.items()))] = []
    pages[("/repos/builder/app/commits", frozenset({"since": SINCE}.items()))] = [
        commit(VARIANT, None, "2026-08-10T10:00:00Z"),
        commit(f"{HANDLE}@users.noreply.github.com", None, "2026-08-03T10:00:00Z"),
        commit("coworker@example.com", "coworker", "2026-08-11T10:00:00Z"),
    ]

    collector = Collector(FakeClient(pages), now=NOW)
    snap = collector.collect(HANDLE)

    assert snap.repos[0].commits_in_window == 2  # both noreply forms, not the coworker's
    assert len(snap.active_weeks) == 2
    assert any("attributed by noreply email fallback" in n for n in snap.collection_notes)
    assert any(VARIANT in n for n in snap.collection_notes)  # actionable fix for the applicant
    assert not snap.partial


def test_no_fallback_when_login_filter_works():
    """Linked accounts must never pay the extra request."""
    pages = {
        **user_page(),
        **repo_page("2026-08-01T00:00:00Z"),
        "/repos/builder/releases": [],
        "/search/issues": [],
    }
    pages[("/repos/builder/app/commits", frozenset({"author": HANDLE, "since": SINCE}.items()))] = [
        commit(VARIANT, HANDLE, "2026-08-10T10:00:00Z"),
    ]

    collector = Collector(FakeClient(pages), now=NOW)
    snap = collector.collect(HANDLE)

    assert snap.repos[0].commits_in_window == 1
    unfiltered = [c for c in collector.client.calls if "author" not in c[1] and c[0].endswith("/commits")]
    assert unfiltered == []  # no fallback call made
    assert not any("noreply email fallback" in n for n in snap.collection_notes)


def test_fallback_matches_only_server_generated_addresses():
    """An attacker's arbitrary email string must not leak into the count."""
    pages = {
        **user_page(),
        **repo_page("2026-08-01T00:00:00Z"),
        "/repos/builder/releases": [],
        "/search/issues": [],
    }
    pages[("/repos/builder/app/commits", frozenset({"author": HANDLE, "since": SINCE}.items()))] = []
    pages[("/repos/builder/app/commits", frozenset({"since": SINCE}.items()))] = [
        commit("builder@gmail.com", None, "2026-08-10T10:00:00Z"),  # arbitrary: no match
        commit(VARIANT.upper(), None, "2026-08-10T10:00:00Z"),  # case-insensitive match
    ]

    collector = Collector(FakeClient(pages), now=NOW)
    snap = collector.collect(HANDLE)

    assert snap.repos[0].commits_in_window == 1
