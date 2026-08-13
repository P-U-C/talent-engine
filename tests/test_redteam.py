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


@pytest.fixture
def cfg_with_registry():
    """A program that actually publishes referrers, so the check has a basis."""
    return load_program("celo-trial")


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


def test_patient_farming_is_now_flagged_and_honest_profiles_are_not(cfg):
    """This test used to assert the opposite, and that was the whole problem.

    Every authenticity check keyed on *concentration* — a fresh account, a
    burst of weeks, implausible commits per week — so slowness defeated all of
    them and `patient_farmer` passed cleanly while the genuine builder was the
    only profile flagged, for honestly naming a referrer.

    `unverified_cadence` is the signal that is not about concentration. It asks
    whether the claimed cadence is corroborated by anything the applicant
    cannot set: commit dates are client-side (`GIT_AUTHOR_DATE`), but
    `pushed_at` is stamped by GitHub. A wide span of active weeks with every
    repository last pushed inside a couple of days is what bulk-backdated
    history looks like.

    The asymmetry now runs the right way: all three manufactured fixtures trip
    it, and neither genuine fixture does.
    """
    manufactured = {
        "patient_farmer": patient_farmer(),
        "sockpuppet_ring": sockpuppet_ring(),
    }
    for name, snap in manufactured.items():
        keys = {f.key for f in score(snap, cfg).flags}
        assert "unverified_cadence" in keys, f"{name} is no longer flagged: {keys}"

    for name, snap in {
        "genuine_builder": genuine_builder(),
        "quiet_finisher": quiet_finisher(),
    }.items():
        keys = {f.key for f in score(snap, cfg).flags}
        assert keys == set(), f"{name} was flagged, which is the old bug: {keys}"


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


def test_declaring_a_referrer_is_no_longer_the_loudest_signal(cfg):
    """The flag asymmetry is fixed: honesty must not be the thing that flags you.

    This previously asserted the bug. A human reviewing these dossiers was
    warned about exactly one of them — the genuine builder, because they named
    a referrer this program's registry does not contain — while both
    manufactured profiles named none and passed clean. Declaring something
    checkable got you flagged; declaring nothing was free.

    `prezenti-sponsorship-trial` publishes no registry at all (`referrers: []`),
    so *every* declared referrer was unverifiable by construction and the flag
    carried no information about the applicant. It now fires only where a
    registry exists to be checked against, which is the only case where failing
    the check means anything.
    """
    assert {f.key for f in score(genuine_builder(), cfg).flags} == set()
    # The manufactured profiles are no longer clean either -- they now trip
    # `unverified_cadence` -- but the property under test here is only that the
    # honest profile is not the loudest dossier in the pile.
    assert "unverifiable_referrer" not in {
        f.key for f in score(genuine_builder(), cfg).flags
    }


def test_an_unverifiable_referrer_still_flags_where_a_registry_exists(cfg_with_registry):
    """The fix must not disarm the check for programs that do publish a registry."""
    snap = genuine_builder()
    snap.application.referrer_name = "Someone Not On The List"
    keys = {f.key for f in score(snap, cfg_with_registry).flags}
    assert "unverifiable_referrer" in keys
