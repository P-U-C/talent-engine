"""The rubric.

Every dimension is a pure function of (snapshot, config, flags) -> DimensionScore.
No network, no clock, no randomness -- so a stored snapshot always re-scores to
the same number, which is what the audit log promises.

Shape of the curves
-------------------
Almost every component uses `saturate(x, half)` = x / (x + half): zero at zero,
half credit at `half`, asymptotically approaching full.  Two reasons.

1.  It is honest about diminishing returns.  The difference between 0 and 3
    merged PRs is enormous; between 40 and 43 it is noise.  Linear scoring
    would let a high-volume contributor swamp the rubric on one axis.
2.  It is explainable in one sentence -- "you get half the points at N" -- which
    matters because candidates are meant to read this and reproduce it.

The `half` constants are the opinionated part of the product.  They encode what
"good" looks like for a six-month window, and they are the thing a program
operator should expect to tune.
"""

from __future__ import annotations

import math

from ..config import ProgramConfig
from ..model import (
    DimensionScore,
    Evidence,
    Flag,
    ProfileSnapshot,
    RepoActivity,
)
from .flags import discount_for

# Half-credit points, per dimension component. Tuned for a 6-month window.
HALF_ORIGINAL_REPOS = 2.0  # 2 shipped originals = half the origination credit
HALF_COMMIT_VOLUME = 40.0  # 40 commits to own originals = half the depth credit
HALF_EXTERNAL_PRS = 4.0  # 4 merged PRs into others' repos = half
HALF_REVIEWS = 5.0  # 5 reviews given = half
# Commits at which a repository's finishing marks count for half. Deliberately
# low: a small tool that is genuinely done should keep nearly all its
# completeness credit, while a decorated repo with two commits should not.
HALF_COMPLETENESS_COMMITS = 5.0
# Share of a repo's finishing marks that survive regardless of commit count.
# Without a floor this dimension re-measures commit volume, which is already
# 28% of shipping_agency, and punishes small finished work.
COMPLETENESS_FLOOR = 0.5
HALF_ECOSYSTEM_HITS = 3.0
HALF_FRONTIER_HITS = 2.0  # frontier work is rarer, so it saturates sooner

# Repeat contributions to a repo already counted are worth this fraction of a
# first contribution. Breadth of acceptance is the signal; depth in a single
# repo is largely a function of already being inside it.
REPEAT_REPO_WEIGHT = 0.25

# Weight of a merged PR into a repository with no contributors other than the
# applicant. Not zero: a genuinely new project by a genuinely new maintainer
# looks exactly like this, and so does a first contribution to somebody's
# weekend tool. It just is not the "someone else's review bar" signal this
# dimension claims to measure.
DEPENDENT_TARGET_WEIGHT = 0.3

# Fraction of the window's weeks that must show activity for full cadence marks.
CADENCE_TARGET_FRACTION = 0.5


def saturate(value: float, half: float) -> float:
    """Diminishing-returns curve in [0, 1). Half credit at `half`."""
    if value <= 0:
        return 0.0
    return value / (value + half)


def _repo_completeness(repo: RepoActivity) -> tuple[float, list[str]]:
    """How finished is this repo? Fraction in [0,1] plus the reasons.

    This is the most under-weighted signal in most talent screens and, I think,
    the most informative one here.  Starting things is common; the marks below
    all come from the last 10% -- writing the description, cutting a release,
    putting it somewhere a stranger can run it.  That is where agency shows.
    """
    marks: list[str] = []
    if repo.has_description or repo.description:
        marks.append("description")
    if repo.topics:
        marks.append("topics")
    if repo.has_releases:
        marks.append("releases")
    # GitHub Pages is verified by GitHub itself. A bare `homepage` string is
    # not verified by anyone, so it only earns the mark once collection has
    # confirmed something actually answers there -- otherwise "deployed" is a
    # free mark for typing a URL into a settings box.
    if repo.has_pages or (repo.homepage and repo.homepage_verified):
        marks.append("deployed")
    if repo.license:
        marks.append("license")
    return len(marks) / 5.0, marks


# --------------------------------------------------------------------------
# 1. shipping_agency -- the core signal
# --------------------------------------------------------------------------


def shipping_agency(
    snap: ProfileSnapshot, cfg: ProgramConfig, flags: list[Flag]
) -> DimensionScore:
    """Original, non-fork work the person pushed themselves.

    Split three ways so that no single cheap behaviour can max it out:
    origination (did you start real things), depth (did you work on them), and
    completeness (did you finish them).  Spamming empty repos moves only the
    first, and it saturates at 2.
    """
    max_pts = cfg.max_points("shipping_agency")
    originals = snap.original_repos
    evidence: list[Evidence] = []
    notes: list[str] = []

    # Sub-weights within the dimension: 40% origination, 28% depth, 32% finish.
    w_orig, w_depth, w_complete = 0.40, 0.28, 0.32

    # -- origination
    orig_frac = saturate(len(originals), HALF_ORIGINAL_REPOS)
    orig_pts = max_pts * w_orig * orig_frac
    for r in sorted(originals, key=lambda r: -r.commits_in_window)[:5]:
        evidence.append(
            Evidence(
                claim=f"original repo {r.name} ({r.commits_in_window} commits in window)",
                url=r.url,
                detail=r.description[:160],
            )
        )

    # -- depth, discounted if the burst flag fired
    commits = sum(r.commits_in_window for r in originals)
    depth_discount = discount_for(flags, "commit_volume")
    depth_frac = saturate(commits, HALF_COMMIT_VOLUME) * depth_discount
    depth_pts = max_pts * w_depth * depth_frac
    if depth_discount < 1.0:
        notes.append(
            f"commit volume discounted to {depth_discount:.0%} (burst concentration)"
        )
    if commits:
        evidence.append(
            Evidence(
                claim=f"{commits} commits to own original repositories in window",
                url=f"{snap.profile_url}?tab=repositories",
            )
        )

    # -- completeness, averaged over the person's most active originals
    if originals:
        ranked = sorted(originals, key=lambda r: -r.commits_in_window)[:5]
        fracs = []
        for r in ranked:
            frac, marks = _repo_completeness(r)
            # Finishing marks only mean "finished" if there is something there
            # to finish. All five are metadata, and metadata is the one part of
            # shipping that can be added without doing the work -- five thin
            # repositories with a description, a licence and a tag scored
            # higher on completeness than four real projects with 200 commits
            # between them. Scaling by the repo's own activity makes the marks
            # evidence of a finished project rather than of a decorated empty
            # one. Half the credit is unconditional so that a genuinely small,
            # genuinely finished tool keeps most of its marks -- scaling the
            # whole thing by commit count double-counted `commit_volume`, which
            # is already 28% of this dimension, and took a real three-commit
            # utility down to 37% of its completeness.
            frac *= COMPLETENESS_FLOOR + (1.0 - COMPLETENESS_FLOOR) * saturate(
                r.commits_in_window, HALF_COMPLETENESS_COMMITS
            )
            fracs.append(frac)
            if marks:
                evidence.append(
                    Evidence(
                        claim=f"{r.name} completeness: {', '.join(marks)}",
                        url=r.url,
                    )
                )
        complete_frac = sum(fracs) / len(fracs)
    else:
        complete_frac = 0.0
    complete_pts = max_pts * w_complete * complete_frac

    points = orig_pts + depth_pts + complete_pts
    if points > 0 and not evidence:
        points = 0.0

    return DimensionScore(
        key="shipping_agency",
        points=points,
        max_points=max_pts,
        components={
            "origination": round(orig_pts, 3),
            "commit_volume": round(depth_pts, 3),
            "completeness": round(complete_pts, 3),
            "original_repo_count": float(len(originals)),
            "commits": float(commits),
        },
        evidence=evidence,
        notes=notes,
    )


# --------------------------------------------------------------------------
# 2. consistency -- cadence, not volume
# --------------------------------------------------------------------------


def consistency(
    snap: ProfileSnapshot, cfg: ProgramConfig, flags: list[Flag]
) -> DimensionScore:
    """Distinct active weeks, spread across the window.

    Deliberately measured in *weeks touched*, never in commits.  A week is a
    coarse enough unit that it cannot be inflated by splitting work into more
    commits, and it is the natural unit of "kept showing up".

    The spread factor stops a single hot month from reading as six consistent
    ones: activity is checked against thirds of the window.
    """
    max_pts = cfg.max_points("consistency")
    weeks = snap.active_weeks
    total_weeks = max(1, round(cfg.window_days / 7))
    target = max(1.0, total_weeks * CADENCE_TARGET_FRACTION)

    base = min(1.0, len(weeks) / target)

    # Spread: how many thirds of the window contain activity.
    thirds_hit = _thirds_covered(weeks, snap.window_start, snap.window_end)
    spread_factor = {0: 0.0, 1: 0.70, 2: 0.85, 3: 1.0}[thirds_hit]

    points = max_pts * base * spread_factor
    evidence: list[Evidence] = []
    if weeks:
        evidence.append(
            Evidence(
                claim=(
                    f"active in {len(weeks)} distinct weeks of ~{total_weeks} "
                    f"({thirds_hit}/3 of the window covered)"
                ),
                url=f"{snap.profile_url}?tab=overview",
                detail=f"first {weeks[0]}, last {weeks[-1]}",
            )
        )

    notes = []
    if spread_factor < 1.0 and weeks:
        notes.append(
            f"activity covers {thirds_hit}/3 of the window; cadence scaled by "
            f"{spread_factor:.0%}"
        )

    return DimensionScore(
        key="consistency",
        points=points if evidence else 0.0,
        max_points=max_pts,
        components={
            "active_weeks": float(len(weeks)),
            "target_weeks": round(target, 2),
            "spread_factor": spread_factor,
        },
        evidence=evidence,
        notes=notes,
    )


def _thirds_covered(weeks: list[str], window_start: str, window_end: str) -> int:
    """How many thirds of the window contain at least one active week."""
    from ..model import _parse_iso

    if not weeks:
        return 0
    start, end = _parse_iso(window_start), _parse_iso(window_end)
    if start is None or end is None or end <= start:
        return 1
    span = (end - start).total_seconds()
    hit = set()
    for w in weeks:
        try:
            year, wk = w.split("-W")
            # Monday of that ISO week.
            from datetime import date, timezone as _tz, datetime as _dt

            d = date.fromisocalendar(int(year), int(wk), 1)
            dt = _dt(d.year, d.month, d.day, tzinfo=_tz.utc)
        except (ValueError, AttributeError):
            continue
        offset = (dt - start).total_seconds()
        if offset < 0 or offset > span:
            continue
        hit.add(min(2, int(3 * offset / span)))
    return len(hit) if hit else 1


# --------------------------------------------------------------------------
# 3 & 4. external validation and collaboration -- supporting evidence only
# --------------------------------------------------------------------------


def external_validation(
    snap: ProfileSnapshot, cfg: ProgramConfig, flags: list[Flag]
) -> DimensionScore:
    """Merged PRs into repositories the person does not own.

    Someone else's review bar was cleared -- genuinely informative, and hard to
    fake in any repo that reviews.  But it is also strongly access-correlated:
    it rewards people already inside projects that accept outside contributions.
    Config validation caps this and `collaboration` below the agency dimensions
    for exactly that reason (invariant 1).
    """
    max_pts = cfg.max_points("external_validation")
    external = [pr for pr in snap.merged_prs if not pr.is_own_repo]
    distinct_repos = {pr.repo.lower() for pr in external}
    distinct_owners = {r.split("/")[0] for r in distinct_repos if "/" in r}

    # Breadth over volume. Clearing the bar in five different projects is a
    # far stronger signal than clearing it five times in one, and the latter is
    # what a maintainer of a single busy monorepo accumulates by default.
    # Repeat PRs to an already-counted repo are worth a quarter each.
    effective = len(distinct_repos) + REPEAT_REPO_WEIGHT * (
        len(external) - len(distinct_repos)
    )

    # Distinct *owners*, not just distinct repos. `is_own_repo` only means "not
    # this account", so five repos belonging to one other account read as five
    # independent maintainers clearing a review bar -- which is exactly the
    # shape of a two-account ring, and two-account clusters are below
    # `rings.MIN_FLAGGABLE_CLUSTER` and so never flagged. Counting owners costs
    # a genuine contributor almost nothing (five PRs into five projects is
    # normally five owners) while removing the cheap version of the attack.
    if distinct_owners:
        effective = min(effective, len(distinct_owners) + REPEAT_REPO_WEIGHT * (
            len(distinct_repos) - len(distinct_owners)
        ))

    # Independence of the target, where collection could establish it. A repo
    # with contributors other than the applicant had a review bar somebody else
    # maintained; one without is indistinguishable from an alt account's shell.
    # Repos we could not check (`None`) keep full weight -- a rate limit is our
    # failure, not the applicant's, and `partial_data` already says so.
    checked = {
        pr.repo.lower(): pr.independent_target
        for pr in external
        if pr.independent_target is not None
    }
    if checked:
        dependent = sum(1 for ok in checked.values() if not ok)
        effective = max(0.0, effective - dependent * (1.0 - DEPENDENT_TARGET_WEIGHT))
    frac = saturate(effective, HALF_EXTERNAL_PRS)
    evidence = [
        Evidence(claim=f"merged PR: {pr.repo}#{pr.number} {pr.title}"[:200], url=pr.url)
        for pr in external[:8]
    ]
    return DimensionScore(
        key="external_validation",
        points=max_pts * frac if evidence else 0.0,
        max_points=max_pts,
        components={
            "merged_external_prs": float(len(external)),
            "distinct_repos": float(len(distinct_repos)),
            "distinct_owners": float(len(distinct_owners)),
            "effective": round(effective, 2),
        },
        evidence=evidence,
    )


def collaboration(
    snap: ProfileSnapshot, cfg: ProgramConfig, flags: list[Flag]
) -> DimensionScore:
    """Reviews given on other people's pull requests.

    Reviewing is work with no personal artifact at the end of it, which makes it
    a clean signal of the disposition you want in a cohort.  Weighted low
    because access to review is unevenly distributed, not because it matters
    little.
    """
    max_pts = cfg.max_points("collaboration")
    given = [r for r in snap.reviews if not r.is_own_repo]
    distinct_repos = {r.repo.lower() for r in given}
    distinct_owners = {r.split("/")[0] for r in distinct_repos if "/" in r}
    effective = len(distinct_repos) + REPEAT_REPO_WEIGHT * (
        len(given) - len(distinct_repos)
    )
    # Owners, not just repositories -- the same correction `external_validation`
    # needs, for the same reason. One accomplice with several repositories is
    # one relationship, not several, and a two-account cluster sits below the
    # ring detector's flagging threshold so nothing else will catch it.
    if distinct_owners:
        effective = min(
            effective,
            len(distinct_owners)
            + REPEAT_REPO_WEIGHT * (len(distinct_repos) - len(distinct_owners)),
        )
    frac = saturate(effective, HALF_REVIEWS)
    evidence = [
        Evidence(claim=f"review on {r.repo}#{r.number}", url=r.url) for r in given[:8]
    ]
    return DimensionScore(
        key="collaboration",
        points=max_pts * frac if evidence else 0.0,
        max_points=max_pts,
        components={
            "reviews_given": float(len(given)),
            "distinct_repos": float(len(distinct_repos)),
            "distinct_owners": float(len(distinct_owners)),
            "effective": round(effective, 2),
        },
        evidence=evidence,
    )


# --------------------------------------------------------------------------
# 5 & 6. taxonomy fit
# --------------------------------------------------------------------------


# A taxonomy hit on a repository the candidate owns, matched only on strings
# the candidate wrote -- topic, keyword, description, language -- is an
# assertion, not evidence. Repo topics and descriptions are one API call to
# set, and this program publishes its own taxonomy, so the exact strings that
# score are known to anyone who reads the repository. Corroborated hits are
# different in kind: `org:` means the repository lives in an ecosystem
# organisation, and a merged PR means someone else's review bar was cleared.
# Self-asserted hits still count -- naming your project accurately is not
# cheating -- but they cannot carry a dimension on their own.
SELF_ASSERTED_HIT_WEIGHT = 0.4
CORROBORATING_PREFIXES = ("org:", "repo:")
# Commits at which a self-owned taxonomy match has earned back half the gap
# between the discounted floor and full credit.
HALF_SELF_ASSERTED_COMMITS = 30.0


def _hit_weight(
    reasons: list[str], *, self_controlled: bool, commits: int = 0
) -> float:
    """1.0 for a corroborated hit, less for one the candidate asserted itself.

    `self_controlled` is decided by *provenance*, not by comparing owner
    strings to the handle. Everything in `snap.repos` was collected from the
    candidate's own account listing, so they control its metadata whether it
    sits under their username or under an organisation they created. An
    earlier version of this compared `repo.owner == snap.handle`, which a
    candidate defeated for free by moving repositories into an org: the owner
    string stopped matching and every self-written topic scored in full again.

    `org:` and `repo:` survive at full weight because they name third parties
    the program chose in advance. A repository the candidate controls cannot
    match those without actually being inside that organisation.
    """
    if not self_controlled:
        return 1.0
    if any(r.startswith(CORROBORATING_PREFIXES) for r in reasons):
        return 1.0
    # Substance, not ownership, is what is missing from a keyword-stuffed repo.
    # A flat discount on everything self-owned would penalise exactly the
    # independent builder this rubric exists to find -- someone shipping real
    # ecosystem work in their own repositories, in an ecosystem where that is
    # simply how work happens, would be capped while an org member was not.
    # That is the access bias the whole product is against (invariant 1). So
    # the discount decays with the repository's own commit count: a personal
    # repo with real work in it earns close to full credit, while five
    # decorated shells do not.
    substance = saturate(max(commits, 0), HALF_SELF_ASSERTED_COMMITS)
    return SELF_ASSERTED_HIT_WEIGHT + (1.0 - SELF_ASSERTED_HIT_WEIGHT) * substance


def _taxonomy_hits(
    snap: ProfileSnapshot, taxonomy
) -> list[tuple[str, str, list[str], float]]:
    """(label, url, reasons, weight) for every *distinct repository* matching.

    Deduped by repository on purpose.  Counting per-PR let fourteen small fixes
    to one monorepo read as fourteen units of ecosystem presence, which handed
    a well-connected low-shipper a higher footprint score than someone who had
    actually shipped two complete projects.  Footprint means "how much of this
    ecosystem have you touched", so the unit is the repo, not the event.

    Each hit carries a weight so that self-declared metadata on your own
    repositories cannot buy a full dimension.  See `_hit_weight`.
    """
    seen: dict[str, tuple[str, str, list[str], float]] = {}

    def record(
        repo_key: str, label: str, url: str, reasons: list[str], weight: float
    ) -> None:
        if not reasons or repo_key in seen:
            return
        seen[repo_key] = (label, url, reasons, weight)

    for r in snap.repos:
        if r.is_fork and r.commits_in_window == 0:
            continue
        reasons = taxonomy.match_reasons(
            full_name=r.name,
            description=r.description,
            topics=r.topics,
            language=r.language,
        )
        record(
            r.name.lower(),
            r.name,
            r.url,
            reasons,
            _hit_weight(reasons, self_controlled=True, commits=r.commits_in_window),
        )
    for pr in snap.merged_prs:
        # The PR *title* is written by the applicant, so matching a keyword in
        # it is not corroboration -- titling a typo fix "fix mcp x402 celo
        # docs" would otherwise launder a self-declared taxonomy term into a
        # full-weight third-party hit. Only the target repository's own
        # identity counts at full weight; a title-only match is treated exactly
        # like a self-declared one.
        reasons = taxonomy.match_reasons(full_name=pr.repo, description=pr.title)
        corroborated = any(r.startswith(CORROBORATING_PREFIXES) for r in reasons)
        record(
            pr.repo.lower(),
            pr.repo,
            f"https://github.com/{pr.repo}",
            reasons,
            1.0 if corroborated else SELF_ASSERTED_HIT_WEIGHT,
        )
    return list(seen.values())


def ecosystem_footprint(
    snap: ProfileSnapshot, cfg: ProgramConfig, flags: list[Flag]
) -> DimensionScore:
    """Activity inside the program's target ecosystem."""
    max_pts = cfg.max_points("ecosystem_footprint")
    hits = _taxonomy_hits(snap, cfg.ecosystem)
    effective = sum(w for _l, _u, _r, w in hits)
    frac = saturate(effective, HALF_ECOSYSTEM_HITS)
    evidence = [
        Evidence(
            claim=f"{label} matches ecosystem ({', '.join(reasons)})"
            + ("" if w >= 1.0 else " [self-declared metadata]"),
            url=url,
        )
        for label, url, reasons, w in hits[:8]
    ]
    return DimensionScore(
        key="ecosystem_footprint",
        points=max_pts * frac if evidence else 0.0,
        max_points=max_pts,
        components={"matches": float(len(hits)), "effective": round(effective, 2)},
        evidence=evidence,
    )


def frontier_signal(
    snap: ProfileSnapshot, cfg: ProgramConfig, flags: list[Flag]
) -> DimensionScore:
    """Activity in the higher-priority emerging-tech taxonomy.

    Separate from ecosystem_footprint because a program usually wants to pay a
    premium for people already working on the thing it is betting on, and
    because that list changes far more often than the base ecosystem list.
    """
    max_pts = cfg.max_points("frontier_signal")
    hits = _taxonomy_hits(snap, cfg.frontier)
    effective = sum(w for _l, _u, _r, w in hits)
    frac = saturate(effective, HALF_FRONTIER_HITS)
    evidence = [
        Evidence(
            claim=f"{label} matches frontier ({', '.join(reasons)})"
            + ("" if w >= 1.0 else " [self-declared metadata]"),
            url=url,
        )
        for label, url, reasons, w in hits[:8]
    ]
    return DimensionScore(
        key="frontier_signal",
        points=max_pts * frac if evidence else 0.0,
        max_points=max_pts,
        components={"matches": float(len(hits)), "effective": round(effective, 2)},
        evidence=evidence,
    )


# --------------------------------------------------------------------------
# 7 & 8. application-side dimensions
# --------------------------------------------------------------------------

MIN_CONTEXT_CHARS = 120


def context_statement(
    snap: ProfileSnapshot, cfg: ProgramConfig, flags: list[Flag]
) -> DimensionScore:
    """A structured, self-declared field. Never inferred (invariant 2).

    Scored on presence and structure only -- did the person declare specific
    factors, and did they write something substantive.  The engine does not
    judge the *content* of someone's circumstances, and it never derives this
    from a name, location, or any other proxy.
    """
    max_pts = cfg.max_points("context_statement")
    if max_pts <= 0:
        return DimensionScore(
            key="context_statement",
            points=0.0,
            max_points=0.0,
            notes=["dimension disabled for this program"],
        )

    app = snap.application
    text = (app.context_statement or "").strip()
    factors = [f for f in app.context_factors if f.strip()]

    if not text and not factors:
        return DimensionScore(
            key="context_statement",
            points=0.0,
            max_points=max_pts,
            notes=["not declared"],
        )

    # 60% for declaring specific structured factors, 40% for a substantive
    # statement. Both come from the applicant, verbatim.
    factor_frac = min(1.0, len(factors) / 2.0)
    substance_frac = min(1.0, len(text) / MIN_CONTEXT_CHARS) if text else 0.0
    points = max_pts * (0.6 * factor_frac + 0.4 * substance_frac)

    evidence = [
        Evidence(
            claim="self-declared context statement (applicant-supplied, not inferred)",
            url=snap.profile_url,
            detail=(text[:200] + "...") if len(text) > 200 else text,
        )
    ]
    return DimensionScore(
        key="context_statement",
        points=points,
        max_points=max_pts,
        components={
            "declared_factors": float(len(factors)),
            "statement_chars": float(len(text)),
        },
        evidence=evidence,
    )


def trusted_referral(
    snap: ProfileSnapshot, cfg: ProgramConfig, flags: list[Flag]
) -> DimensionScore:
    """An endorsement, verified against the program's referrer registry.

    Binary by design.  A partially-credited endorsement would mean an invented
    name still buys something, and the whole value of this dimension is that it
    cannot.
    """
    max_pts = cfg.max_points("trusted_referral")
    name = snap.application.referrer_name.strip()
    if not name:
        return DimensionScore(
            key="trusted_referral", points=0.0, max_points=max_pts, notes=["none declared"]
        )
    if not cfg.is_verified_referrer(name):
        return DimensionScore(
            key="trusted_referral",
            points=0.0,
            max_points=max_pts,
            notes=[f"referrer {name!r} not in registry -- scores zero, flag raised"],
        )
    return DimensionScore(
        key="trusted_referral",
        points=max_pts,
        max_points=max_pts,
        components={"verified": 1.0},
        evidence=[
            Evidence(
                claim=f"endorsed by {name}, verified against program referrer registry",
                url=snap.profile_url,
            )
        ],
    )


ALL_DIMENSIONS = (
    shipping_agency,
    consistency,
    external_validation,
    collaboration,
    ecosystem_footprint,
    frontier_signal,
    context_statement,
    trusted_referral,
)
