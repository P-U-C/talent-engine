"""What an adversary who has read the published rubric can actually score.

The rubric is published deliberately, so the realistic attacker is not the one
`gamed_profile` models — that profile is what someone builds who has not read
it, and it scores near zero, correctly. These tests measure the attacker who
has, and they are written to fail loudly if the exposure ever changes in either
direction.

They are characterisation tests, not aspirations. Where a countermeasure does
not exist yet the assertion records what gets through, with the mitigation
named in the failure message, so nobody reads a green suite as "manufactured
profiles cannot compete."
"""

from __future__ import annotations

import pytest

from talent_engine.config import load_program
from talent_engine.scoring.engine import score_snapshot
from talent_engine.scoring.flags import has_flag
from tests.fixtures.profiles import (
    gamed_profile,
    genuine_builder,
    patient_farmer,
    quiet_finisher,
    sockpuppet_ring,
)


@pytest.fixture
def cfg():
    return load_program("recruit-agent-infra")


def score(snap, cfg):
    return score_snapshot(snap, cfg)


# ------------------------------------------------- what the flags do catch


def test_the_naive_attack_is_still_crushed(cfg):
    """Baseline: the cheap attack must stay near zero, or the rest means nothing."""
    naive = score(gamed_profile(), cfg)
    real = score(genuine_builder(), cfg)
    assert naive.total < real.total / 3
    assert has_flag(naive.flags, "burst_activity")
    assert has_flag(naive.flags, "new_account")


# ------------------------------------------- what the flags do NOT catch


def test_patient_farming_raises_no_flag_at_all(cfg):
    """Every authenticity check keys on concentration; slowness defeats all of them.

    Mitigation if this is unacceptable: the checks need a signal that is not
    about timing — commit content, diff size distribution, or whether anyone
    other than the author has ever interacted with the repositories.
    """
    farmed = score(patient_farmer(), cfg)
    triggered = [f.key for f in farmed.flags]
    assert triggered == [], (
        f"patient_farmer now trips {triggered} — if that is a new countermeasure, "
        "update this test; it previously passed every check cleanly"
    )


def test_patient_farming_outscores_a_real_low_volume_builder(cfg):
    """The uncomfortable result: manufactured beats genuine-but-quiet.

    `quiet_finisher` is the profile the product exists to find. A farmed
    profile costing one cron job and an afternoon of metadata currently ranks
    above it, because both of the things separating them — real cadence and
    finishing metadata — are exactly what a scheduler and a text field can
    produce.
    """
    farmed = score(patient_farmer(), cfg)
    quiet = score(quiet_finisher(), cfg)
    assert farmed.total > quiet.total, (
        "if this now fails, a countermeasure landed and the docs claiming this "
        "exposure should be updated"
    )


def test_patient_farming_alone_does_not_beat_a_full_genuine_builder(cfg):
    """The one thing still holding: external validation is not farmable...

    ...by an attacker who does not bother to create alt accounts. Creating them
    is free, which is the next test.
    """
    assert score(patient_farmer(), cfg).total < score(genuine_builder(), cfg).total


def test_sockpuppet_prs_are_scored_as_independent_validation(cfg):
    """`is_own_repo` means "not this account", which a second account defeats.

    Mitigation: treat a repository as independent evidence only when something
    about it is independent of the applicant — other contributors, meaningful
    age before the PR, or activity from accounts with no other overlap. None of
    that is collected today, so this is a collector change, not a scoring one.
    """
    ring = score(sockpuppet_ring(), cfg)
    dims = {d.key: d for d in ring.dimensions}
    assert dims["external_validation"].points > 0, (
        "sockpuppet PRs no longer score — a countermeasure landed"
    )
    assert dims["collaboration"].points > 0


def test_the_sockpuppet_ring_outranks_every_real_profile(cfg):
    """The headline result: the full attack wins outright.

    Priced out, it is four throwaway accounts, a scheduled committer, and an
    afternoon of repository metadata. No reviewed code, no users, no
    independent reviewer — and on `recruit-agent-infra` it tops the board:

        sockpuppet_ring      56.79
        genuine_builder      49.93
        patient_farmer       41.36
        quiet_finisher       29.43
        insider_low_shipper  23.94
        gamed_profile         4.68

    Only the last of those is caught, and it is the one attack nobody
    sophisticated would run.
    """
    ring = score(sockpuppet_ring(), cfg)
    others = {
        "genuine_builder": score(genuine_builder(), cfg).total,
        "quiet_finisher": score(quiet_finisher(), cfg).total,
    }
    assert all(ring.total > t for t in others.values()), (
        f"ring={ring.total:.2f} vs {others} — if the ring no longer wins, a "
        "countermeasure landed and this test should record which"
    )


def test_the_only_flagged_credible_profile_is_the_honest_one(cfg):
    """The flag asymmetry, which is worse than the score gap.

    A human reviewing these dossiers is warned about exactly one of them: the
    genuine builder, because they named a referrer this program's registry does
    not contain. Both manufactured profiles name none, and pass clean.

    Declaring something checkable is what gets you flagged; declaring nothing
    is free. That is backwards, and it is a scoring-layer bug rather than a
    collection one — an unverifiable referrer should be worth zero points
    (it already is) without also being the loudest signal on the dossier.
    """
    assert {f.key for f in score(genuine_builder(), cfg).flags} == {"unverifiable_referrer"}
    assert {f.key for f in score(sockpuppet_ring(), cfg).flags} == set()
    assert {f.key for f in score(patient_farmer(), cfg).flags} == set()
