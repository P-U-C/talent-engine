"""Cross-applicant overlap: the check that only works on a pool.

Every other check in this engine looks at one person at a time, which is
exactly why a patient adversary beats them. One person running several accounts
that merge each other's pull requests produces profiles that are individually
unremarkable — `is_own_repo` only means "not this account", so an alt's repo
reads as an independent maintainer clearing a review bar. Seen together, the
same behaviour is obvious.

**The false positive is the hard part, and it is not symmetric with the false
negative.** Real communities cluster: two builders in the same city who review
each other's work produce the same edges as two accounts one person controls.
Calling those people a sockpuppet ring is a serious harm — it is an accusation
of fraud attached to a funding decision — while missing a ring costs money.
So the discriminator is not clustering, it is **insularity**: whether the
cluster's members validate anyone outside it. A real community has edges
pointing outward; a ring, by construction, mostly does not.

This module therefore reports observations rather than verdicts, and its output
is worded for someone who has to make a judgement, not for someone looking for
permission to reject.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..model import ProfileSnapshot

# Clusters below this size are reported but never flagged for review. Two
# people who validate only each other is the normal shape of a founding team
# building one product together, and it is indistinguishable from a two-account
# ring on structure alone. Flagging pairs would defame co-founders constantly
# to catch the cheapest possible ring, which is the wrong trade: the cost of
# calling real people fraudulent is far higher than the cost of missing a
# two-account operation.
MIN_CLUSTER = 2
MIN_FLAGGABLE_CLUSTER = 3

INSULARITY_REVIEW = 0.75
DENSITY_REVIEW = 0.8          # share of possible member-to-member edges present
SYNCHRONISED_DAYS = 45        # accounts stood up together
THIN_OUTSIDE_MAX = 2          # median independent validations per member

# How many independent signals must fire. One is not enough: a single
# threshold on a single ratio was the first design, and it failed in both
# directions — two throwaway pull requests per account dropped a real ring
# under the line, while two genuine co-founders sat at the maximum.
SIGNALS_FOR_REVIEW = 2


@dataclass
class Signal:
    key: str
    fired: bool
    detail: str


@dataclass
class Edge:
    """One observed relationship, with the evidence that produced it."""

    source: str
    target: str
    kind: str  # pr_into | reviewed | co_contributor
    detail: str

    def key(self) -> tuple[str, str]:
        return tuple(sorted((self.source, self.target)))  # type: ignore[return-value]


@dataclass
class Cluster:
    members: list[str]
    edges: list[Edge]
    insularity: dict[str, float] = field(default_factory=dict)
    created_within_days: int | None = None
    signals: list[Signal] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def mean_insularity(self) -> float:
        if not self.insularity:
            return 0.0
        return sum(self.insularity.values()) / len(self.insularity)

    @property
    def fired(self) -> list[Signal]:
        return [s for s in self.signals if s.fired]

    @property
    def needs_review(self) -> bool:
        """Corroboration, not a single threshold.

        Requires a cluster large enough that its shape is not just a founding
        team, plus at least two independent signals agreeing. Any one of these
        alone is either evadable or produces false positives on real people.
        """
        return (
            self.size >= MIN_FLAGGABLE_CLUSTER
            and len(self.fired) >= SIGNALS_FOR_REVIEW
        )

    def to_dict(self) -> dict:
        return {
            "members": self.members,
            "size": self.size,
            "mean_insularity": round(self.mean_insularity, 3),
            "insularity": {k: round(v, 3) for k, v in self.insularity.items()},
            "created_within_days": self.created_within_days,
            "needs_review": self.needs_review,
            "signals": [
                {"key": s.key, "fired": s.fired, "detail": s.detail} for s in self.signals
            ],
            "edges": [
                {"from": e.source, "to": e.target, "kind": e.kind, "detail": e.detail}
                for e in self.edges
            ],
        }

    def summary(self) -> str:
        """One paragraph for a human. States the observation, not a verdict."""
        who = ", ".join(self.members)
        lines = [f"{self.size} applicants are connected: {who}."]
        for s in self.fired:
            lines.append(s.detail)
        if not self.fired:
            lines.append("Nothing about the group's shape stands out.")
        lines.append(
            "This is consistent with people who work together, and also with "
            "one person running several accounts. It is not evidence of either. "
            "Look at whether the repositories involved have contributors from "
            "outside this group."
        )
        return " ".join(lines)


def _owner(repo: str) -> str:
    return repo.split("/", 1)[0].lower() if "/" in repo else ""


def build_edges(snapshots: dict[str, ProfileSnapshot]) -> list[Edge]:
    """Relationships between people in the pool, from stored snapshots only.

    Costs no API calls: everything here is already collected. That matters
    because it means the check can run over the whole pool on every new
    application rather than being a periodic special event.
    """
    handles = {h.lower(): h for h in snapshots}
    edges: list[Edge] = []

    for handle, snap in snapshots.items():
        me = handle.lower()

        # A merged PR into a repository owned by another applicant. This is the
        # edge that matters most: it is exactly what the scorer counted as
        # independent validation.
        for pr in snap.merged_prs:
            owner = _owner(pr.repo)
            if owner and owner != me and owner in handles:
                edges.append(
                    Edge(handle, handles[owner], "pr_into", f"{pr.repo}#{pr.number}")
                )

        # A review left on another applicant's repository.
        for rv in snap.reviews:
            owner = _owner(rv.repo)
            if owner and owner != me and owner in handles:
                edges.append(
                    Edge(handle, handles[owner], "reviewed", f"{rv.repo}#{rv.number}")
                )

    # Two applicants pushing to the same repository owned by neither is weaker
    # evidence — it is what open source looks like — but it is still a link.
    by_repo: dict[str, set[str]] = {}
    for handle, snap in snapshots.items():
        for repo in snap.repos:
            by_repo.setdefault(repo.name.lower(), set()).add(handle)
    for repo, people in by_repo.items():
        if len(people) < 2:
            continue
        ordered = sorted(people)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                edges.append(Edge(a, b, "co_contributor", repo))

    return edges


def _components(handles: Iterable[str], edges: list[Edge]) -> list[list[str]]:
    parent = {h: h for h in handles}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        if e.source in parent and e.target in parent:
            ra, rb = find(e.source), find(e.target)
            if ra != rb:
                parent[ra] = rb

    groups: dict[str, list[str]] = {}
    for h in parent:
        groups.setdefault(find(h), []).append(h)
    return [sorted(g) for g in groups.values() if len(g) >= MIN_CLUSTER]


def _insularity(
    handle: str,
    members: set[str],
    snap: ProfileSnapshot,
    recognised: set[str] | None = None,
) -> float:
    """Share of this person's validation that establishes nothing independent.

    The obvious version of this — "how much validation stays inside the
    cluster" — has a hole that showed up the first time a partial ring was
    tested: when three of four accounts have applied, each member's edge to the
    absent fourth counts as *outside* validation, and the group drops under the
    review threshold. The missing account is not independent evidence; it is
    just an account that has not applied yet.

    So a target counts as genuine outside validation only when it is neither a
    cluster member nor an account nobody recognises. `recognised` is the
    program's own ecosystem and frontier orgs — the projects whose review bar
    means something. This is the same reasoning the caveat sentence uses: a
    merged PR into a project the program knows is different evidence from one
    into an account nobody has heard of.

    1.0 means nothing they have merged establishes independence. 0.0 means it
    all does. Returns 0.0 when there is no external activity at all: absence of
    evidence is not evidence of a ring, and scoring it 1.0 would flag every
    solo builder in the pool.
    """
    me = handle.lower()
    outside_targets = []
    for pr in snap.merged_prs:
        owner = _owner(pr.repo)
        if owner and owner != me:
            outside_targets.append(owner)
    for rv in snap.reviews:
        owner = _owner(rv.repo)
        if owner and owner != me:
            outside_targets.append(owner)

    if not outside_targets:
        return 0.0
    lowered = {m.lower() for m in members}
    known = {o.lower() for o in (recognised or set())}
    not_independent = sum(
        1 for owner in outside_targets if owner in lowered or owner not in known
    )
    return not_independent / len(outside_targets)


def _density(members: list[str], edges: list[Edge]) -> float:
    """Share of possible member-to-member pairs that are actually linked.

    A ring needs everyone to validate everyone, or the accounts are wasted.
    Real collaboration is sparser and lopsided: people work with the one or two
    others whose project they touch, not with the whole group uniformly.
    """
    n = len(members)
    if n < 2:
        return 0.0
    pairs = {tuple(sorted((e.source, e.target))) for e in edges if e.source != e.target}
    return len(pairs) / (n * (n - 1) / 2)


def _outside_counts(
    members: list[str], snapshots: dict[str, ProfileSnapshot], recognised: set[str]
) -> list[int]:
    """Per member, how many validations came from a recognised outside project."""
    lowered = {m.lower() for m in members}
    known = {o.lower() for o in recognised}
    counts = []
    for m in members:
        snap = snapshots.get(m)
        if snap is None:
            continue
        n = 0
        for item in list(snap.merged_prs) + list(snap.reviews):
            owner = _owner(item.repo)
            if owner and owner != m.lower() and owner not in lowered and owner in known:
                n += 1
        counts.append(n)
    return counts


def _signals(
    cluster: "Cluster",
    snapshots: dict[str, ProfileSnapshot],
    recognised: set[str],
) -> list[Signal]:
    """Independent observations about the group's shape.

    Each is individually weak and individually evadable. The point is that
    evading all of them costs real work — an attacker who builds genuine
    outside track records on several accounts, spaced apart in time, with
    asymmetric collaboration, has done most of the work of being real.
    """
    out: list[Signal] = []

    insular = cluster.mean_insularity >= INSULARITY_REVIEW
    out.append(
        Signal(
            "insular",
            insular,
            f"{cluster.mean_insularity:.0%} of their merged work went to each other "
            "or to accounts this program does not recognise.",
        )
    )

    density = _density(cluster.members, cluster.edges)
    out.append(
        Signal(
            "dense",
            density >= DENSITY_REVIEW,
            f"{density:.0%} of the possible pairs in the group are linked — nearly "
            "everyone validates nearly everyone, which is not how collaboration "
            "usually distributes.",
        )
    )

    synced = (
        cluster.created_within_days is not None
        and cluster.created_within_days <= SYNCHRONISED_DAYS
    )
    out.append(
        Signal(
            "synchronised_accounts",
            synced,
            f"Their accounts were created within {cluster.created_within_days} days "
            "of one another."
            if cluster.created_within_days is not None
            else "Account creation dates unavailable.",
        )
    )

    counts = _outside_counts(cluster.members, snapshots, recognised)
    median = sorted(counts)[len(counts) // 2] if counts else 0
    out.append(
        Signal(
            "thin_outside",
            bool(counts) and median <= THIN_OUTSIDE_MAX,
            f"The median member has {median} accepted contribution(s) to a project "
            "this program recognises.",
        )
    )
    return out


def _creation_spread(members: list[str], snapshots: dict[str, ProfileSnapshot]) -> int | None:
    dates = [
        snapshots[m].account_created_at
        for m in members
        if snapshots.get(m) and snapshots[m].account_created_at
    ]
    if len(dates) < 2:
        return None
    from datetime import datetime

    parsed = []
    for d in dates:
        try:
            parsed.append(datetime.fromisoformat(str(d).replace("Z", "+00:00")))
        except ValueError:
            continue
    if len(parsed) < 2:
        return None
    return (max(parsed) - min(parsed)).days


def find_clusters(
    snapshots: dict[str, ProfileSnapshot],
    recognised_orgs: set[str] | None = None,
) -> list[Cluster]:
    """Connected groups of applicants, scored by how inward-facing they are.

    `recognised_orgs` should be the program's ecosystem and frontier orgs.
    Without it every target outside the cluster counts as independent, which
    is what lets a partially-applied ring slip under the threshold.
    """
    edges = build_edges(snapshots)
    clusters: list[Cluster] = []

    for members in _components(snapshots.keys(), edges):
        member_set = set(members)
        internal = [e for e in edges if e.source in member_set and e.target in member_set]
        cluster = Cluster(members=members, edges=internal)
        cluster.insularity = {
            m: _insularity(m, member_set, snapshots[m], recognised_orgs)
            for m in members
            if m in snapshots
        }
        cluster.created_within_days = _creation_spread(members, snapshots)
        cluster.signals = _signals(cluster, snapshots, recognised_orgs or set())
        clusters.append(cluster)

    # Most inward-facing first: that is the order a reviewer should read them.
    clusters.sort(key=lambda c: (-len(c.fired), -c.mean_insularity, -c.size))
    return clusters


def report(clusters: list[Cluster]) -> str:
    if not clusters:
        return (
            "No applicants in this pool are connected to each other.\n"
            "Note that this check can only see relationships between people who "
            "have both been scored — a ring whose members have not all applied "
            "is invisible to it."
        )
    out = []
    for c in clusters:
        marker = "REVIEW" if c.needs_review else "note  "
        out.append(f"[{marker}] {c.summary()}")
        if c.size < MIN_FLAGGABLE_CLUSTER:
            out.append(
                "         (groups this small are never flagged: two people who "
                "validate only each other is the normal shape of a founding team)"
            )
        out.append(
            "         signals: "
            + ", ".join(f"{s.key}={'yes' if s.fired else 'no'}" for s in c.signals)
        )
        kinds: dict[str, int] = {}
        for e in c.edges:
            kinds[e.kind] = kinds.get(e.kind, 0) + 1
        detail = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))
        out.append(f"         edges: {detail}")
        for e in c.edges[:6]:
            out.append(f"           {e.source} -> {e.target}  {e.kind}  {e.detail}")
        if len(c.edges) > 6:
            out.append(f"           …and {len(c.edges) - 6} more")
        out.append("")
    return "\n".join(out)
