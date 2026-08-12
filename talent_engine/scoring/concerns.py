"""One sentence on what a reviewer should be sceptical about.

A number next to a name reads as a verdict. It is not one, and the red-team
fixtures show why: a manufactured profile can outrank a genuine builder while
raising no authenticity flag at all (`docs/STRATEGY.md`). A reviewer who sees
only "68.24" and an empty flag list will conclude the wrong thing.

Two rules this module follows, both consequences of that result:

**It never reports "no concerns."** Silence would be a claim the engine cannot
support. When nothing specific stands out, the sentence says what the score
does not establish, because that is the true statement.

**It reads score composition, not just flags.** Flags only fire on
concentration — a fresh account, a burst of activity, implausible density —
and the attacks that matter defeat all of those by being slow. Composition
survives that: where the points came from, how much rests on the applicant's
own word, whether anything independent corroborates it.

This is written for a human who has thirty seconds per candidate.
"""

from __future__ import annotations

from ..config import ProgramConfig
from ..model import CandidateScore, ProfileSnapshot

# Flags whose meaning a reviewer should see first, most serious first.
FLAG_PHRASES = {
    "burst_activity": "all activity falls in a week or two",
    "new_account": "the account is too new to have the history this rubric reads",
    "metric_inflation": "commit density looks generated or bulk-imported",
    "fork_shell_profile": "the repositories are forks with nothing original",
    "no_original_repos": "nothing original was pushed in the window",
    "unverifiable_referrer": "the named referrer is not in this program's registry",
    "partial_data": "collection was incomplete, so this score is a floor rather than a measurement",
}

# The sentence used when nothing specific stands out. Deliberately not
# reassuring: see the module docstring.
NOTHING_SPECIFIC = (
    "Nothing here distinguishes this from a profile built to score well — "
    "the checks catch careless faking, not patient faking, so treat this as a "
    "shortlist position rather than a judgement."
)


def _dominant(score: CandidateScore) -> tuple[str, float] | None:
    """The dimension carrying an outsized share of the total."""
    if score.total <= 0:
        return None
    ranked = sorted(score.dimensions, key=lambda d: d.points, reverse=True)
    if not ranked or ranked[0].points <= 0:
        return None
    share = ranked[0].points / score.total
    return (ranked[0].key, share) if share >= 0.45 else None


def concerns(
    score: CandidateScore,
    cfg: ProgramConfig,
    snapshot: ProfileSnapshot | None = None,
) -> str:
    """One sentence naming the most material reason to look closer.

    Ordered by what would change a decision, not by severity in the abstract:
    a flag a reviewer can act on beats a structural observation, and both beat
    the default.
    """
    parts: list[str] = []

    # 1. Flags, in the order a reviewer cares about.
    keys = {f.key for f in score.flags}
    for key, phrase in FLAG_PHRASES.items():
        if key in keys:
            parts.append(phrase)
    if len(parts) > 2:
        parts = parts[:2]

    if parts:
        return _sentence(parts)

    # 2. No flags. Read the composition instead — this is the path the
    #    manufactured profiles take, so it must not come back empty.
    structural: list[str] = []

    external = score.dimension("external_validation")
    collaboration = score.dimension("collaboration")
    if external is not None and external.points == 0 and collaboration is not None:
        if collaboration.points == 0:
            structural.append(
                "nobody else has merged or reviewed their work, so every point "
                "here comes from repositories they control"
            )

    # Where the external validation came FROM, which the score itself ignores.
    # A merged PR into a project this program recognises is a different piece
    # of evidence from one into an account nobody has heard of, and the second
    # is what a ring of alt accounts produces. This does not claim to detect
    # sockpuppets — it reports that the endorsement is only as good as the
    # repositories granting it, and lets the reviewer judge.
    if snapshot is not None and external is not None and external.points > 0:
        known = set(cfg.ecosystem.orgs) | set(cfg.frontier.orgs)
        owners = {
            pr.repo.split("/")[0].lower()
            for pr in snapshot.merged_prs
            if not pr.is_own_repo and "/" in pr.repo
        }
        if owners and not (owners & known):
            structural.append(
                "every merged pull request is into a repository this program "
                "does not recognise, so the outside validation is only as "
                "independent as those accounts are"
            )

    declared = score.application_total
    if declared > 0 and score.total > 0 and declared / score.total >= 0.30:
        structural.append(
            f"{declared / score.total:.0%} of the score rests on what they told "
            "us rather than on anything measured"
        )

    dominant = _dominant(score)
    if dominant and not structural:
        key, share = dominant
        structural.append(
            f"{share:.0%} of the score comes from {key.replace('_', ' ')} alone, "
            "so it is one signal rather than a pattern"
        )

    if snapshot is not None:
        complete = [
            r
            for r in snapshot.original_repos
            if r.has_description and r.license and (r.has_releases or r.homepage)
        ]
        thin = [r for r in complete if r.commits_in_window < 20]
        if complete and len(thin) == len(complete):
            structural.append(
                "the finished-looking repositories are thin on commits — "
                "descriptions, licences and releases are the cheapest part of "
                "finishing to add"
            )

    if structural:
        return _sentence(structural[:2])

    return NOTHING_SPECIFIC


def _sentence(parts: list[str]) -> str:
    body = parts[0] if len(parts) == 1 else f"{parts[0]}, and {parts[1]}"
    return f"Look closer: {body}."


def concern_flags(score: CandidateScore) -> list[str]:
    """Flag keys behind the sentence, for machine consumers."""
    return [f.key for f in score.flags]
