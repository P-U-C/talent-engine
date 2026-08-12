"""Authenticity checks.

Design rule (invariant 4): a flag routes a candidate to human review and may
*discount* a score component.  It can never add points.  `Flag` enforces this
structurally -- it has no points field and its discount is clamped to [0, 1].

The point of these checks is not to catch cheaters after the fact.  It is to
make the cheapest attacks worthless *by construction*, so that manufacturing a
profile costs about as much as just doing the work.

Attack surface considered, cheapest first:

  fresh account + bulk commits   -> burst discount + cadence is week-based
  forked repo shells             -> excluded from `original_repos` entirely
  generated/vendored commit bulk -> volume saturates and is burst-discounted
  invented referrer              -> exact-match registry, zero + flag
  many empty repos               -> completeness component, not repo count
  stars/followers                -> not scored anywhere in the rubric
"""

from __future__ import annotations

from ..config import ProgramConfig
from ..model import Evidence, Flag, ProfileSnapshot


def evaluate_flags(snap: ProfileSnapshot, cfg: ProgramConfig) -> list[Flag]:
    """All authenticity flags for a snapshot, most severe first."""
    flags: list[Flag] = []
    t = cfg.thresholds

    # --- account age ------------------------------------------------------
    age = snap.account_age_days
    if age is not None and age < t.new_account_days:
        flags.append(
            Flag(
                key="new_account",
                severity="review",
                message=(
                    f"Account is {age} days old (threshold {t.new_account_days}). "
                    "Not disqualifying on its own -- genuine newcomers exist -- "
                    "but it removes the history the rubric relies on."
                ),
                evidence=(
                    Evidence(
                        claim=f"account created {snap.account_created_at}",
                        url=snap.profile_url,
                    ),
                ),
            )
        )

    # --- nothing original shipped ----------------------------------------
    if not snap.original_repos:
        flags.append(
            Flag(
                key="no_original_repos",
                severity="warn",
                message=(
                    "No original (non-fork) repository received a commit in the "
                    "window. The core agency signal is absent."
                ),
                evidence=(
                    Evidence(
                        claim="no original repos pushed in window",
                        url=f"{snap.profile_url}?tab=repositories",
                    ),
                ),
            )
        )

    # --- burst concentration ---------------------------------------------
    # The single most important anti-gaming check. Commit *volume* is trivially
    # manufactured; showing up across many distinct weeks is not. When activity
    # collapses into <= N weeks we both flag it and discount the volume
    # component to near-nothing, which is what makes a manufactured profile
    # score near zero instead of merely "a bit lower".
    active = len(snap.active_weeks)
    total_commits = sum(r.commits_in_window for r in snap.repos)
    if 0 < active <= t.burst_week_threshold:
        flags.append(
            Flag(
                key="burst_activity",
                severity="critical",
                message=(
                    f"All activity falls in {active} distinct week(s) "
                    f"({total_commits} commits). Commit volume is discounted to "
                    f"{t.burst_commit_discount:.0%} -- concentrated volume is the "
                    "cheapest signal to manufacture and the weakest evidence of "
                    "sustained agency."
                ),
                evidence=(
                    Evidence(
                        claim=f"activity confined to weeks {', '.join(snap.active_weeks)}",
                        url=snap.profile_url,
                    ),
                ),
                discount=t.burst_commit_discount,
                discounts_component="commit_volume",
            )
        )

    # --- implausible commit density ---------------------------------------
    if active > 0:
        per_week = total_commits / active
        if per_week >= t.metric_inflation_commits_per_week:
            flags.append(
                Flag(
                    key="metric_inflation",
                    severity="warn",
                    message=(
                        f"{per_week:.0f} commits per active week. Consistent with "
                        "generated, vendored, or bulk-imported code rather than "
                        "authored work. Volume credit is capped regardless; this "
                        "flags the dossier for a human to eyeball the diffs."
                    ),
                    evidence=(
                        Evidence(
                            claim=f"{total_commits} commits across {active} active weeks",
                            url=snap.profile_url,
                        ),
                    ),
                )
            )

    # --- referrer verification -------------------------------------------
    declared = snap.application.referrer_name.strip()
    if declared and not cfg.is_verified_referrer(declared):
        flags.append(
            Flag(
                key="unverifiable_referrer",
                severity="warn",
                message=(
                    f"Declared referrer {declared!r} is not in this program's "
                    "referrer registry. Scores zero -- an unverifiable endorsement "
                    "is not evidence."
                ),
                evidence=(
                    Evidence(
                        claim="referrer not found in program registry",
                        url=snap.profile_url,
                    ),
                ),
            )
        )

    # --- fork-heavy profile ------------------------------------------------
    forks = [r for r in snap.repos if r.is_fork]
    if forks and len(snap.original_repos) == 0 and len(forks) >= 3:
        flags.append(
            Flag(
                key="fork_shell_profile",
                severity="warn",
                message=(
                    f"{len(forks)} forks and no original repos with commits. A wall "
                    "of forks reads as activity at a glance and costs nothing to "
                    "produce."
                ),
                evidence=(
                    Evidence(
                        claim=f"{len(forks)} forked repositories, 0 original",
                        url=f"{snap.profile_url}?tab=repositories",
                    ),
                ),
            )
        )

    # --- collection completeness ------------------------------------------
    # Not an authenticity signal: an honesty signal about our own data. A
    # partial snapshot must never read as a low score.
    if snap.partial:
        flags.append(
            Flag(
                key="partial_data",
                severity="review",
                message=(
                    "Collection was incomplete (rate limit, API window, or private "
                    "activity). This score is a floor, not a measurement. "
                    + "; ".join(snap.collection_notes[:3])
                ),
                evidence=(
                    Evidence(claim="partial collection", url=snap.profile_url),
                ),
            )
        )

    order = {"critical": 0, "warn": 1, "review": 2}
    return sorted(flags, key=lambda f: order[f.severity])


def discount_for(flags: list[Flag], component: str) -> float:
    """Strongest discount applying to a named component (1.0 = untouched)."""
    factor = 1.0
    for f in flags:
        if f.discounts_component == component and f.discount is not None:
            factor = min(factor, f.discount)
    return factor


def has_flag(flags: list[Flag], key: str) -> bool:
    return any(f.key == key for f in flags)
