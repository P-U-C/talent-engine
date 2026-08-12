"""Rate-limit pacing across GitHub's two very different buckets.

Search allows 30 requests per minute; everything else allows 5,000 per hour.
Tracking them in one counter, with one absolute reserve, produced a client that
slept a full minute before nearly every request — a run of two candidates took
over two minutes to spend thirteen requests. These tests pin both halves of the
fix.
"""

from __future__ import annotations

from talent_engine.github.client import GitHubClient, RateLimitState, bucket_for


def test_buckets_are_identified_by_path():
    assert bucket_for("https://api.github.com/search/issues?q=x") == "search"
    assert bucket_for("https://api.github.com/users/octocat") == "core"
    assert bucket_for("https://api.github.com/users/octocat/repos") == "core"
    assert bucket_for("https://api.github.com/graphql") == "graphql"


def test_reserve_never_exceeds_a_tenth_of_the_bucket():
    """The bug: a reserve of 50 against a limit of 30 is never satisfiable."""
    search = RateLimitState(remaining=29, reset_at=0, limit=30)
    assert search.reserve_for(50) == 3

    core = RateLimitState(remaining=4999, reset_at=0, limit=5000)
    assert core.reserve_for(50) == 50

    unknown = RateLimitState(remaining=10, reset_at=0, limit=None)
    assert unknown.reserve_for(50) == 50  # no information: keep the caller's value


def test_a_search_response_does_not_pace_core_requests():
    """The regression that cost the minutes: one counter for both buckets.

    After a search response leaves 29 calls in the search bucket, a request to
    a core endpoint with thousands remaining must not sleep.
    """
    slept: list[float] = []
    client = GitHubClient()
    client.sleep_fn = slept.append

    client.rates["search"] = RateLimitState(remaining=1, reset_at=2**31, limit=30)
    client.rates["core"] = RateLimitState(remaining=4900, reset_at=2**31, limit=5000)

    client._pace("https://api.github.com/users/octocat")
    assert slept == []

    client._pace("https://api.github.com/search/issues?q=x")
    assert len(slept) == 1  # the search bucket really is nearly out


def test_a_freshly_touched_search_bucket_does_not_immediately_pace():
    """29 of 30 remaining is a healthy bucket, not an exhausted one."""
    slept: list[float] = []
    client = GitHubClient()
    client.sleep_fn = slept.append
    client.rates["search"] = RateLimitState(remaining=29, reset_at=2**31, limit=30)

    client._pace("https://api.github.com/search/issues?q=x")
    assert slept == []
