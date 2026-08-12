"""Scout: find candidates nobody applied with.

This is the half of the product that actually does *identification*.  Selecting
well from an applicant pile is comparatively easy -- the pile self-selected, and
the people in it already knew the program existed.

Three discovery channels, deliberately different in what they are biased toward:

  contributors  -- recent merged-PR authors in seed org repos.
                   Finds people already inside the ecosystem. High precision,
                   and structurally biased toward insiders: everyone it returns
                   has, by definition, already been let in somewhere.

  originators   -- repos matching the taxonomy by topic/language, ranked toward
                   *recently created, actively pushed* projects, then their
                   owners. Finds independent builders who have shipped something
                   in the space and never contributed to a seed org.
                   This channel is the reason the product can claim to find
                   talent rather than rank applicants.

  adjacent      -- contributors to the repos surfaced by `originators`.
                   Small projects with two or three contributors are where
                   people do their most legible work.

Running only the first channel would reproduce exactly the access bias the
scoring rubric is built to correct, so the default is all three.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from ..config import ProgramConfig
from ..github.client import BudgetExhausted, GitHubClient

BOT_SUFFIXES = ("[bot]", "-bot", "-ci")


@dataclass
class Candidate:
    handle: str
    channels: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)
    evidence_urls: list[str] = field(default_factory=list)

    def merge(self, channel: str, reason: str, url: str) -> None:
        self.channels.add(channel)
        if reason not in self.reasons:
            self.reasons.append(reason)
        if url and url not in self.evidence_urls:
            self.evidence_urls.append(url)

    @property
    def corroboration(self) -> int:
        """Distinct channels that surfaced this person."""
        return len(self.channels)

    def to_dict(self) -> dict:
        return {
            "handle": self.handle,
            "channels": sorted(self.channels),
            "corroboration": self.corroboration,
            "reasons": self.reasons,
            "evidence": self.evidence_urls[:5],
            "profile": f"https://github.com/{self.handle}",
        }


def _is_bot(login: str, user_type: str = "") -> bool:
    if user_type.lower() == "bot":
        return True
    low = login.lower()
    return any(low.endswith(s) for s in BOT_SUFFIXES)


class Scout:
    def __init__(
        self,
        client: GitHubClient,
        cfg: ProgramConfig,
        *,
        window_days: int = 183,
        now: datetime | None = None,
    ) -> None:
        self.client = client
        self.cfg = cfg
        self.window_days = window_days
        self.now = now or datetime.now(timezone.utc)
        self.candidates: dict[str, Candidate] = {}
        self.notes: list[str] = []

    @property
    def _since(self) -> str:
        return (self.now - timedelta(days=self.window_days)).date().isoformat()

    def _add(
        self, login: str, channel: str, reason: str, url: str, user_type: str = ""
    ) -> bool:
        """Record a candidate. Returns whether one was actually accepted.

        Callers use the return value for their quotas: counting rows instead
        meant a busy repository could spend its whole allocation on Dependabot
        and CI accounts and surface nobody.
        """
        if not login or _is_bot(login, user_type):
            return False
        cand = self.candidates.setdefault(login, Candidate(handle=login))
        cand.merge(channel, reason, url)
        return True

    # ------------------------------------------------------------- channels

    def from_contributors(
        self,
        seed_repos: Iterable[str],
        *,
        per_repo: int = 30,
        caps: dict[str, int] | None = None,
    ) -> None:
        """Recent merged-PR authors in seed repositories.

        `caps` sets a per-repository allocation. A uniform quota lets one noisy
        high-traffic repository dominate the digest while a small, dense,
        high-signal one contributes almost nothing.
        """
        caps = caps or {}
        for repo in seed_repos:
            limit = caps.get(repo, per_repo)
            query = f"repo:{repo} is:pr is:merged merged:>={self._since}"
            try:
                found = 0
                for raw in self.client.paginate(
                    "/search/issues", {"q": query, "sort": "updated"}, max_pages=1
                ):
                    user = raw.get("user") or {}
                    login = user.get("login", "")
                    if login.lower() == repo.split("/")[0].lower():
                        continue
                    if self._add(
                        login,
                        "contributors",
                        f"merged PR into {repo}",
                        raw.get("html_url", ""),
                        user.get("type", ""),
                    ):
                        found += 1
                    if found >= limit:
                        break
            except BudgetExhausted:
                self.notes.append("budget exhausted during contributor scan")
                return

    def from_originators(self, *, per_query: int = 30, max_queries: int = 8) -> list[str]:
        """Owners of recently-created repos matching the program taxonomy.

        Returns the repo names it surfaced so `from_adjacent` can reuse them.

        Sorted by recent activity rather than stars on purpose. Stars measure
        distribution and audience, which is precisely the access advantage the
        rubric refuses to reward; a two-month-old repo with real commits and no
        stars is the signal we are hunting for.
        """
        surfaced: list[str] = []
        queries = self._taxonomy_queries()[:max_queries]
        for q in queries:
            try:
                found = 0
                for raw in self.client.paginate(
                    "/search/repositories",
                    {"q": q, "sort": "updated", "order": "desc"},
                    max_pages=1,
                ):
                    owner = raw.get("owner") or {}
                    login = owner.get("login", "")
                    full = raw.get("full_name", "")
                    if raw.get("fork"):
                        continue
                    if owner.get("type", "") == "Organization":
                        # Org-owned repos say nothing about an individual.
                        surfaced.append(full)
                        continue
                    self._add(
                        login,
                        "originators",
                        f"owns {full} matching program taxonomy",
                        raw.get("html_url", ""),
                        owner.get("type", ""),
                    )
                    surfaced.append(full)
                    found += 1
                    if found >= per_query:
                        break
            except BudgetExhausted:
                self.notes.append("budget exhausted during originator scan")
                break
        return surfaced

    def from_adjacent(self, repos: Iterable[str], *, limit: int = 40) -> None:
        """Contributors to taxonomy-matching repos found by `from_originators`."""
        for repo in list(repos)[:limit]:
            try:
                contributors = self.client.get(
                    f"/repos/{repo}/contributors", {"per_page": 10}
                )
            except BudgetExhausted:
                self.notes.append("budget exhausted during adjacency scan")
                return
            for raw in contributors or []:
                self._add(
                    raw.get("login", ""),
                    "adjacent",
                    f"contributor to {repo}",
                    raw.get("html_url", ""),
                    raw.get("type", ""),
                )

    # -------------------------------------------------------------- queries

    def _taxonomy_queries(self) -> list[str]:
        """GitHub search queries derived from the program's taxonomy packs.

        Frontier terms come first: they are the scarcer signal, and the search
        budget usually runs out before the list does.
        """
        pushed = f"pushed:>={self._since}"
        queries: list[str] = []
        for topic in self.cfg.frontier.topics[:6]:
            queries.append(f"topic:{topic} {pushed}")
        for topic in self.cfg.ecosystem.topics[:6]:
            queries.append(f"topic:{topic} {pushed}")
        for lang in self.cfg.ecosystem.languages[:3]:
            queries.append(f"language:{lang} {pushed} stars:<50")
        return queries

    # --------------------------------------------------------------- output

    def run(self, seed_repos: Iterable[str] = ()) -> list[Candidate]:
        seeds = list(seed_repos)
        if seeds:
            self.from_contributors(seeds)
        surfaced = self.from_originators()
        self.from_adjacent(surfaced)
        return self.ranked()

    def ranked(self) -> list[Candidate]:
        """Corroboration first, then originators over pure insiders.

        Someone found by two independent channels is a stronger lead than
        someone found by one. Among single-channel hits, an originator (shipped
        their own thing in the space) ranks above a contributor.
        """
        priority = {"originators": 0, "adjacent": 1, "contributors": 2}

        def key(c: Candidate):
            best = min((priority.get(ch, 9) for ch in c.channels), default=9)
            return (-c.corroboration, best, c.handle)

        return sorted(self.candidates.values(), key=key)
