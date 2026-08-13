"""Build a ProfileSnapshot from the GitHub REST API.

All network access in the scoring path lives here.  The output is a plain
serialisable record, so a score can always be regenerated later without
touching the network.

Honesty rule: whenever collection is truncated -- budget ceiling, API window,
pagination cap -- the snapshot is marked `partial` and the reason is recorded.
A partial collection must never be indistinguishable from a genuinely quiet
candidate, because the two have opposite meanings and only one of them is the
candidate's fault.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

# Seconds to wait for a declared homepage to answer. Short on purpose: this is
# a liveness check inside a collection loop, not a crawl.
HOMEPAGE_TIMEOUT = 5
MAX_HOMEPAGE_REDIRECTS = 3

_BLOCKED_HOST_SUFFIXES = (".localhost", ".internal", ".local", ".home.arpa")
_BLOCKED_HOST_NAMES = ("localhost", "metadata.google.internal")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never auto-follow. `_homepage_answers` validates each hop itself."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None

    opener = None  # populated below


_NoRedirect.opener = urllib.request.build_opener(_NoRedirect)


def _host_is_public(hostname: str) -> bool:
    """Reject anything that is not a public unicast address.

    The homepage string is attacker-controlled, so a naive fetch turns the
    collector into an SSRF probe against its own network. Two traps this has to
    survive, both of which an earlier version of this function failed:

    *   `ipaddress.ip_address` rejects the numeric forms libc happily accepts --
        `127.1`, `2130706433`, `0x7f000001`, `0177.0.0.1`. Parsing the literal
        and treating a `ValueError` as "it must be a hostname" therefore let
        every one of those through.
    *   A name is not an address. `evil.example` can resolve to 127.0.0.1, and
        can answer differently on the second lookup (DNS rebinding).

    So resolve first and judge the resolved addresses, never the string. This
    still leaves a rebinding window between our resolution and the socket's
    own; closing that needs a validated-IP connector or egress filtering at the
    network, which is a deployment concern rather than a scoring one.
    """
    host = (hostname or "").strip().rstrip(".").lower()
    if not host or host in _BLOCKED_HOST_NAMES or host.endswith(_BLOCKED_HOST_SUFFIXES):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        raw = info[4][0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            return False
        # `is_global` is False for private, loopback, link-local, reserved,
        # multicast and unspecified ranges, in both v4 and v6.
        if not addr.is_global:
            return False
    return True

from ..model import (
    Application,
    ProfileSnapshot,
    PullRequestActivity,
    RepoActivity,
    ReviewActivity,
    dedupe_weeks,
    iso_week,
    utc_now_iso,
)
from .client import BudgetExhausted, GitHubClient

# How many of a person's original repos get commit-level inspection. Each one
# costs at least one request. Sampling only the newest few systematically
# undercounts people whose main project is older than their side projects.
DEFAULT_REPO_SAMPLE = 12
MAX_COMMIT_PAGES = 3  # 300 commits per repo is far past the saturation point


class Collector:
    def __init__(
        self,
        client: GitHubClient,
        *,
        window_days: int = 183,
        repo_sample: int = DEFAULT_REPO_SAMPLE,
        now: datetime | None = None,
    ) -> None:
        self.client = client
        self.window_days = window_days
        self.repo_sample = repo_sample
        self.now = now or datetime.now(timezone.utc)

    @property
    def window_start(self) -> datetime:
        return self.now - timedelta(days=self.window_days)

    def collect(self, handle: str, application: Application | None = None) -> ProfileSnapshot:
        since = self.window_start
        snap = ProfileSnapshot(
            handle=handle,
            account_created_at=None,
            collected_at=utc_now_iso(),
            window_start=since.isoformat(),
            window_end=self.now.isoformat(),
            application=application or Application(),
        )

        try:
            self._collect_user(snap)
            self._collect_repos(snap, since)
            self._collect_merged_prs(snap, since)
            self._collect_reviews(snap, since)
        except BudgetExhausted as exc:
            snap.partial = True
            snap.collection_notes.append(f"request budget exhausted: {exc}")

        # Cadence is the union of every source, not the sum. A push and a merged
        # PR in the same week are one week of activity, not two.
        snap.active_weeks = dedupe_weeks(
            [w for r in snap.repos for w in r.commit_weeks]
            + [iso_week(pr.merged_at) for pr in snap.merged_prs]
            + [iso_week(rv.submitted_at) for rv in snap.reviews]
        )
        snap.collection_notes.append(
            f"client: {self.client.stats['requests_spent']} requests, "
            f"{self.client.stats['served_from_cache_304']} served from cache"
        )
        return snap

    # ----------------------------------------------------------------- parts

    def _collect_user(self, snap: ProfileSnapshot) -> None:
        user = self.client.get(f"/users/{snap.handle}")
        if not user:
            snap.partial = True
            snap.collection_notes.append("user not found or not visible")
            return
        snap.account_created_at = user.get("created_at")

    def _collect_repos(self, snap: ProfileSnapshot, since: datetime) -> None:
        repos: list[RepoActivity] = []
        for raw in self.client.paginate(
            f"/users/{snap.handle}/repos",
            {"sort": "pushed", "direction": "desc", "type": "owner"},
            max_pages=3,
        ):
            pushed = _parse(raw.get("pushed_at"))
            repo = RepoActivity(
                name=raw.get("full_name", ""),
                owner=(raw.get("owner") or {}).get("login", ""),
                is_fork=bool(raw.get("fork")),
                pushed_at=raw.get("pushed_at"),
                created_at=raw.get("created_at"),
                description=raw.get("description") or "",
                language=raw.get("language"),
                topics=raw.get("topics") or [],
                stars=raw.get("stargazers_count", 0),
                has_description=bool(raw.get("description")),
                has_pages=bool(raw.get("has_pages")),
                homepage=raw.get("homepage") or "",
                license=((raw.get("license") or {}) or {}).get("spdx_id"),
            )
            repos.append(repo)
            # Repos are returned newest-push-first, so once we are behind the
            # window everything after is older too.
            if pushed and pushed < since:
                break

        # Publish the list BEFORE enrichment. This assignment used to be the
        # last line of the function, so a BudgetExhausted raised while fetching
        # commits or releases discarded every repository already collected —
        # a real builder with active, described projects scored 0.0 with only a
        # soft partial_data flag, indistinguishable from someone with no public
        # work at all. Enrichment failing should cost the enrichment, not the
        # evidence.
        snap.repos = repos

        in_window = [
            r
            for r in repos
            if not r.is_fork and _parse(r.pushed_at) and _parse(r.pushed_at) >= since
        ]
        sample = in_window[: self.repo_sample]
        if len(in_window) > len(sample):
            snap.partial = True
            snap.collection_notes.append(
                f"commit inspection sampled {len(sample)} of {len(in_window)} "
                "in-window original repos"
            )

        for repo in sample:
            self._collect_commits(snap, repo, since)
            repo.has_releases = self._has_releases(repo.name)
            repo.homepage_verified = self._homepage_answers(repo.homepage)

    def _collect_commits(
        self, snap: ProfileSnapshot, repo: RepoActivity, since: datetime
    ) -> None:
        weeks: list[str] = []
        count = 0
        backdated = 0
        # A commit cannot legitimately predate the repository that holds it,
        # except through imported history -- and imported history says nothing
        # about when the applicant did the work. Both `author.date` and
        # `committer.date` are set by the client (`GIT_AUTHOR_DATE`), so an
        # afternoon of backdated commits and one push otherwise manufactures a
        # six-month cadence with no elapsed time at all. `created_at` is
        # server-stamped and is the cheapest thing we already hold that the
        # applicant cannot move.
        created = _parse(repo.created_at)
        for raw in self.client.paginate(
            f"/repos/{repo.name}/commits",
            {"author": snap.handle, "since": since.isoformat()},
            max_pages=MAX_COMMIT_PAGES,
        ):
            count += 1
            date = (
                ((raw.get("commit") or {}).get("author") or {}).get("date")
                or ((raw.get("commit") or {}).get("committer") or {}).get("date")
            )
            authored = _parse(date)
            if created and authored and authored < created:
                backdated += 1
                continue  # unverifiable as evidence of when work happened
            wk = iso_week(date)
            if wk:
                weeks.append(wk)
        repo.commits_in_window = count
        repo.backdated_commits = backdated
        repo.commit_weeks = sorted(set(weeks))

    def _has_releases(self, full_name: str) -> bool:
        releases = self.client.get(f"/repos/{full_name}/releases", {"per_page": 1})
        return bool(releases)

    def _homepage_answers(self, homepage: str) -> bool:
        """Does anything actually answer at the declared homepage?

        GitHub's homepage field is unvalidated free text, so scoring it as a
        "deployed" mark rewards typing a URL into a settings box. This is a
        cheap liveness check, not an audit: any 2xx/3xx means something is
        served there. It deliberately fails closed -- a timeout, a DNS failure
        or any exception leaves the mark unearned rather than granting it, so
        an unreachable URL can never be worth more than an absent one.

        Not routed through the GitHub client: different host, different rate
        limits, and it must never consume the API budget.
        """
        url = (homepage or "").strip()
        if not url:
            return False
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Follow redirects manually, validating every hop. urllib follows them
        # by default, so a public URL that 302s to 169.254.169.254 would sail
        # through a check performed only on the first address.
        for _hop in range(MAX_HOMEPAGE_REDIRECTS + 1):
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return False
            if not _host_is_public(parsed.hostname):
                return False
            req = urllib.request.Request(
                url,
                method="HEAD",
                headers={"User-Agent": "talent-engine/homepage-check"},
            )
            try:
                with _NoRedirect.opener.open(req, timeout=HOMEPAGE_TIMEOUT) as resp:
                    status, location = resp.status, resp.headers.get("Location")
            except urllib.error.HTTPError as exc:
                status, location = exc.code, exc.headers.get("Location")
                if status in (301, 302, 303, 307, 308) and location:
                    url = urllib.parse.urljoin(url, location)
                    continue
                # The host answered but the page is not there. 405 is the
                # exception: some servers reject HEAD and still serve GET.
                return status == 405
            except Exception:
                return False
            if status in (301, 302, 303, 307, 308) and location:
                url = urllib.parse.urljoin(url, location)
                continue
            return 200 <= status < 300
        return False  # redirect budget exhausted

    def _collect_merged_prs(self, snap: ProfileSnapshot, since: datetime) -> None:
        query = (
            f"is:pr author:{snap.handle} is:merged "
            f"merged:>={since.date().isoformat()}"
        )
        for raw in self.client.paginate(
            "/search/issues", {"q": query, "sort": "updated"}, max_pages=2
        ):
            repo = _repo_from_issue_url(raw.get("repository_url", ""))
            if not repo:
                continue
            snap.merged_prs.append(
                PullRequestActivity(
                    repo=repo,
                    number=raw.get("number", 0),
                    title=raw.get("title", "")[:200],
                    merged_at=(raw.get("pull_request") or {}).get("merged_at")
                    or raw.get("closed_at"),
                    created_at=raw.get("created_at"),
                    is_own_repo=repo.split("/")[0].lower() == snap.handle.lower(),
                )
            )

        # Establish independence once per distinct target, not once per PR.
        seen: dict[str, bool | None] = {}
        for pr in snap.merged_prs:
            if pr.is_own_repo:
                continue
            key = pr.repo.lower()
            if key not in seen:
                seen[key] = self._target_is_independent(pr.repo, snap.handle)
            pr.independent_target = seen[key]

    def _target_is_independent(self, full_name: str, handle: str) -> bool | None:
        """Did this repository exist as somebody else's project?

        `is_own_repo` only asks whether the owner string differs from the
        applicant's handle, which an alt account or a self-made organisation
        defeats for free -- and a two-account cluster sits below the ring
        detector's flagging threshold, so nothing else catches it either.

        The cheap discriminator is other people. A project with contributors
        besides the applicant had a review bar that somebody else maintained.
        Returns `None` when the question cannot be answered (rate limit,
        permissions, deleted repo) so that a collection failure reads as
        "unknown" rather than as an accusation.
        """
        contributors = self.client.get(
            f"/repos/{full_name}/contributors", {"per_page": 5, "anon": "false"}
        )
        if not isinstance(contributors, list) or not contributors:
            return None
        logins = {
            (c.get("login") or "").lower() for c in contributors if isinstance(c, dict)
        }
        logins.discard("")
        if not logins:
            return None
        return bool(logins - {handle.lower()})

    def _collect_reviews(self, snap: ProfileSnapshot, since: datetime) -> None:
        query = (
            f"is:pr reviewed-by:{snap.handle} -author:{snap.handle} "
            f"updated:>={since.date().isoformat()}"
        )
        for raw in self.client.paginate(
            "/search/issues", {"q": query, "sort": "updated"}, max_pages=2
        ):
            repo = _repo_from_issue_url(raw.get("repository_url", ""))
            if not repo:
                continue
            snap.reviews.append(
                ReviewActivity(
                    repo=repo,
                    number=raw.get("number", 0),
                    # The search index exposes update time, not review time;
                    # it is the best available proxy and is only used for the
                    # week bucket.
                    submitted_at=raw.get("updated_at"),
                    is_own_repo=repo.split("/")[0].lower() == snap.handle.lower(),
                )
            )


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _repo_from_issue_url(url: str) -> str:
    """'https://api.github.com/repos/owner/name' -> 'owner/name'."""
    marker = "/repos/"
    if marker not in url:
        return ""
    return url.split(marker, 1)[1]
