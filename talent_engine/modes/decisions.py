"""Decisions, and the feedback owed to people who were not selected.

The policy commits the programme to giving feedback to unsuccessful applicants.
A commitment with no queue, no owner and no record is a commitment that gets
kept for the first three people and quietly dropped at scale — which is worse
than never having made it, because the applicants were told.

So this is a tracked obligation: a decision is recorded, feedback is owed until
it is marked sent, and `pending_feedback` exists so nobody has to remember.

The feedback itself is generated from the same evidence the decision was made
on. That is the point: a rejection that says "strong pool this time" teaches
nothing, and the applicant already has the right to reproduce their own score,
so anything vaguer than the truth reads as evasion.
"""

from __future__ import annotations

from ..config import ProgramConfig
from ..model import CandidateScore

# Dimensions where a low score is genuinely actionable — a person can go and do
# something about these. `trusted_referral` and `context_statement` are not
# here: telling someone their weakness is not knowing the right people, or not
# having declared enough hardship, is neither useful nor kind.
ACTIONABLE = {
    "shipping_agency": (
        "Ship something original and finish it — a description, a licence, a "
        "release, a URL someone can open. Finishing is the signal most people "
        "skip and the one that moves this the most."
    ),
    "consistency": (
        "Commit in more distinct weeks. Not more commits — more weeks. Ten "
        "small weeks beat one enormous one, and that is deliberate."
    ),
    "external_validation": (
        "Get work merged into projects you do not own. One accepted pull "
        "request into a real project counts for more here than a large "
        "repository nobody else has touched."
    ),
    "collaboration": (
        "Review other people's work. It is the cheapest way to show you can "
        "read code you did not write."
    ),
    "ecosystem_footprint": (
        "Nothing you have built matched this programme's ecosystem. That is a "
        "fit question, not a quality judgement — the same work would score "
        "differently against a different programme."
    ),
    "frontier_signal": (
        "Nothing matched the areas this programme is specifically looking for. "
        "Again a fit question rather than a verdict on the work."
    ),
}


def weakest_actionable(score: CandidateScore, limit: int = 3) -> list[tuple[str, float, float]]:
    """The dimensions where the most points were left, worst first.

    Ranked by points *missed*, not by points scored, because a dimension worth
    40 where they got 10 matters more than one worth 5 where they got 0.
    """
    gaps = [
        (d.key, d.points, d.max_points)
        for d in score.dimensions
        if d.key in ACTIONABLE and d.max_points > 0
    ]
    gaps.sort(key=lambda g: -(g[2] - g[1]))
    return [g for g in gaps[:limit] if g[2] - g[1] > 0.5]


def feedback_letter(
    handle: str,
    score: CandidateScore,
    cfg: ProgramConfig,
    *,
    caveat: str = "",
    seats: int | None = None,
    applicants: int | None = None,
    note: str = "",
) -> str:
    """What an unsuccessful applicant is told.

    Specific, reproducible, and honest about the limits of the method. They
    can recompute this themselves, so anything evasive is both pointless and
    obvious.
    """
    total_max = sum(cfg.weights.values())
    lines: list[str] = []
    add = lines.append

    add(f"Thank you for applying to {cfg.name}. You were not selected this round.")
    add("")
    if seats and applicants:
        add(f"There were {seats} places and {applicants} applications.")
        add("")
    add(f"Your score was {score.total:.1f} out of {total_max:.0f}.")
    add("")

    gaps = weakest_actionable(score)
    if gaps:
        add("Where the points went, and what would move them:")
        add("")
        for key, points, max_points in gaps:
            add(f"  {key.replace('_', ' ').title()} — {points:.1f} of {max_points:.0f}")
            add(f"    {ACTIONABLE[key]}")
            add("")
    else:
        add("Your score was spread evenly rather than held back by one thing.")
        add("")

    if caveat:
        add("The caveat we attached internally, which you should see too:")
        add(f"  {caveat}")
        add("")

    if note:
        add(note)
        add("")

    add("Two things worth saying plainly.")
    add("")
    add(
        "A score never decided this. It produced a shortlist and people made "
        "the decision, so a number close to someone else's does not mean the "
        "method preferred them."
    )
    add(
        "And you can check our work. The rubric and the code that applies it "
        "are public, every component is evidence-linked, and you can reproduce "
        "this number yourself:"
    )
    add("  git clone https://github.com/P-U-C/talent-engine")
    add(f"  python3 -m talent_engine.cli score --program {cfg.key} --handles {handle}")
    add("")
    add(
        "If you think it is wrong, tell us where — that is the point of "
        "publishing it, and it is how the rubric gets better."
    )
    return "\n".join(lines)
