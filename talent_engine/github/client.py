"""Cached, rate-limit-aware GitHub REST client.

Three things this does that a bare `requests.get` loop does not, and that the
product needs to run at any scale:

1.  Conditional requests.  Every response's ETag is stored; every repeat request
    sends `If-None-Match`.  GitHub does not charge rate limit for a 304, so a
    re-run over an already-scored cohort costs almost nothing.  That is what
    makes "incremental refresh" real rather than aspirational.

2.  An explicit request budget.  A run declares how many calls it may spend and
    stops when it hits the ceiling, marking the snapshot `partial` instead of
    silently returning less data.  A truncated collection that looks like a
    complete one produces a low score for a good candidate, which is the worst
    failure this system can have.

3.  Rate-limit pacing.  Reads `X-RateLimit-Remaining` and sleeps to the reset
    when the reserve is reached, rather than hammering into a 403.
"""

from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .auth import Auth, AnonymousAuth, API_ROOT

USER_AGENT = "talent-engine/0.1 (+https://github.com/)"


class BudgetExhausted(RuntimeError):
    """Raised when a run hits its declared request ceiling."""


@dataclass
class RateLimitState:
    remaining: int | None = None
    reset_at: int | None = None
    limit: int | None = None

    def reserve_for(self, configured: int) -> int:
        """How many calls to hold back in this bucket.

        A fixed reserve cannot be applied to buckets of wildly different sizes.
        Search allows 30 requests per minute against core's 5,000 per hour, so
        a reserve of 50 is unsatisfiable there: `remaining` is at most 29 the
        moment the bucket is touched, the pacer concludes it is inside the
        reserve, and it sleeps to the reset before every subsequent request.
        Never hold back more than a tenth of what the bucket allows.
        """
        if not self.limit:
            return configured
        return max(1, min(configured, self.limit // 10))


def bucket_for(url: str) -> str:
    """Which rate-limit pool a URL draws from.

    GitHub meters search separately from everything else, and the two limits
    differ by two orders of magnitude. Tracking one counter for both means a
    search response overwrites the core budget and vice versa, so the pacer is
    reasoning about the wrong pool half the time.
    """
    path = urllib.parse.urlsplit(url).path
    if path.startswith("/search/"):
        return "search"
    if path.startswith("/graphql"):
        return "graphql"
    return "core"


class ResponseCache:
    """SQLite-backed ETag cache. Survives between runs; that is the point."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS http_cache (
                   url TEXT PRIMARY KEY,
                   etag TEXT,
                   body TEXT,
                   fetched_at REAL
               )"""
        )
        self.conn.commit()

    def get(self, url: str) -> tuple[str | None, Any | None]:
        row = self.conn.execute(
            "SELECT etag, body FROM http_cache WHERE url = ?", (url,)
        ).fetchone()
        if not row:
            return None, None
        etag, body = row
        try:
            return etag, json.loads(body)
        except (TypeError, json.JSONDecodeError):
            return etag, None

    def put(self, url: str, etag: str | None, payload: Any) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO http_cache (url, etag, body, fetched_at) "
            "VALUES (?, ?, ?, ?)",
            (url, etag, json.dumps(payload), time.time()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


@dataclass
class GitHubClient:
    auth: Auth = field(default_factory=AnonymousAuth)
    cache: ResponseCache | None = None
    budget: int = 5000
    reserve: int = 50  # stop this far short of the hard limit
    max_retries: int = 3
    sleep_fn = staticmethod(time.sleep)

    spent: int = 0
    served_from_cache: int = 0
    rate: RateLimitState = field(default_factory=RateLimitState)
    rates: dict[str, RateLimitState] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def rate_for(self, url: str) -> RateLimitState:
        return self.rates.setdefault(bucket_for(url), RateLimitState())

    # ------------------------------------------------------------------ core

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith("http") else f"{API_ROOT}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        etag, cached = (self.cache.get(url) if self.cache else (None, None))

        if self.spent >= self.budget:
            raise BudgetExhausted(
                f"request budget of {self.budget} exhausted at {url}"
            )
        self._pace(url)

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }
        auth_header = self.auth.header()
        if auth_header:
            headers["Authorization"] = auth_header
        if etag:
            headers["If-None-Match"] = etag

        req = urllib.request.Request(url, headers=headers)

        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    self.spent += 1
                    self._record_limits(resp.headers, url)
                    payload = json.loads(resp.read().decode() or "null")
                    if self.cache:
                        self.cache.put(url, resp.headers.get("ETag"), payload)
                    return payload

            except urllib.error.HTTPError as exc:
                self._record_limits(exc.headers, url)
                if exc.code == 304:
                    # Unchanged since last run: free, and the whole reason the
                    # cache exists.
                    self.served_from_cache += 1
                    return cached
                if exc.code == 404:
                    return None
                if exc.code in (403, 429) and self._is_rate_limited(exc.headers):
                    if not self._wait_for_reset(exc.headers):
                        raise BudgetExhausted("rate limited with no reset window")
                    continue
                if exc.code >= 500 and attempt < self.max_retries - 1:
                    self.sleep_fn(2**attempt)
                    continue
                raise
            except urllib.error.URLError:
                if attempt < self.max_retries - 1:
                    self.sleep_fn(2**attempt)
                    continue
                raise
        return None

    def paginate(
        self, path: str, params: dict[str, Any] | None = None, *, max_pages: int = 10
    ) -> Iterator[dict]:
        """Yield items across pages, stopping at `max_pages` or a short page."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        for page in range(1, max_pages + 1):
            params["page"] = page
            batch = self.get(path, params)
            if not batch:
                return
            if isinstance(batch, dict):  # search endpoints wrap in `items`
                batch = batch.get("items", [])
            for item in batch:
                yield item
            if len(batch) < params["per_page"]:
                return

    # ------------------------------------------------------------- internals

    def _record_limits(self, headers, url: str) -> None:
        def as_int(name: str) -> int | None:
            raw = headers.get(name)
            try:
                return int(raw) if raw is not None else None
            except ValueError:
                return None

        state = self.rate_for(url)
        state.remaining = as_int("X-RateLimit-Remaining")
        state.reset_at = as_int("X-RateLimit-Reset")
        state.limit = as_int("X-RateLimit-Limit")
        # `self.rate` stays as the most recent response's figures so existing
        # callers and `stats` keep working; pacing reads the per-bucket state.
        self.rate = state

    @staticmethod
    def _is_rate_limited(headers) -> bool:
        return headers.get("X-RateLimit-Remaining") == "0" or bool(
            headers.get("Retry-After")
        )

    def _wait_for_reset(self, headers) -> bool:
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                self.sleep_fn(min(int(retry_after) + 1, 3600))
                return True
            except ValueError:
                pass
        reset = headers.get("X-RateLimit-Reset")
        if reset:
            try:
                delay = max(0, int(reset) - int(time.time())) + 1
            except ValueError:
                return False
            self.notes.append(f"rate limited; slept {delay}s for reset")
            self.sleep_fn(min(delay, 3600))
            return True
        return False

    def _pace(self, url: str) -> None:
        """Sleep to the reset if this URL's own bucket is inside its reserve."""
        state = self.rate_for(url)
        if state.remaining is None or state.reset_at is None:
            return
        reserve = state.reserve_for(self.reserve)
        if state.remaining > reserve:
            return
        delay = max(0, state.reset_at - int(time.time())) + 1
        if delay > 0:
            self.notes.append(
                f"paced {bucket_for(url)}: {state.remaining} calls left, slept {delay}s"
            )
            self.sleep_fn(min(delay, 3600))

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "requests_spent": self.spent,
            "served_from_cache_304": self.served_from_cache,
            "budget": self.budget,
            "rate_remaining": {k: v.remaining for k, v in sorted(self.rates.items())},
            "auth": self.auth.label,
        }
