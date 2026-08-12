"""Cross-applicant overlap detection.

The test that matters is not "does it find the ring" — connected components are
easy. It is "does it leave real collaborators alone", because the two produce
the same edges and the costs are not symmetric: missing a ring loses money,
while flagging a real community attaches an accusation of fraud to a funding
decision.
"""

from __future__ import annotations

import pytest

from talent_engine.config import load_program
from talent_engine.modes.rings import (
    INSULARITY_REVIEW,
    build_edges,
    find_clusters,
    report,
)
from tests.fixtures.profiles import genuine_pool, sockpuppet_pool


@pytest.fixture
def known():
    """The program's recognised orgs — projects whose review bar means something."""
    cfg = load_program("prezenti-sponsorship-trial")
    return set(cfg.ecosystem.orgs) | set(cfg.frontier.orgs)


def test_the_ring_is_found_and_flagged(known):
    clusters = find_clusters(sockpuppet_pool(), known)
    assert len(clusters) == 1
    ring = clusters[0]
    assert ring.size == 4
    assert ring.mean_insularity == 1.0  # nobody outside the group ever merged their work
    assert ring.needs_review
    assert len(ring.fired) >= 2, "flagging must rest on corroboration, not one number"


def test_real_collaborators_cluster_but_are_not_flagged(known):
    """The whole point. They review each other; they are not a ring."""
    clusters = find_clusters(genuine_pool(), known)
    assert len(clusters) == 1
    group = clusters[0]
    assert group.size == 3  # they ARE connected, and that is fine
    assert group.mean_insularity < INSULARITY_REVIEW
    assert not group.needs_review


def test_the_discriminator_is_corroboration_not_clustering(known):
    """Both groups cluster identically; the signals that fire differ."""
    ring = find_clusters(sockpuppet_pool(), known)[0]
    real = find_clusters(genuine_pool(), known)[0]
    assert len(ring.fired) > len(real.fired)
    assert ring.mean_insularity > real.mean_insularity * 3


def test_a_solo_applicant_is_never_a_cluster(known):
    """Absence of external validation must not read as a ring of one."""
    pool = dict(list(genuine_pool().items())[:1])
    assert find_clusters(pool, known) == []


def test_someone_with_no_external_activity_scores_zero_insularity():
    """Otherwise every solo builder in the pool would look maximally insular."""
    from talent_engine.modes.rings import _insularity
    from tests.fixtures.profiles import quiet_finisher

    snap = quiet_finisher()  # no merged PRs, no reviews
    assert _insularity(snap.handle, {snap.handle}, snap) == 0.0


def test_edges_carry_their_evidence():
    """A reviewer must be able to check the claim, per invariant 3."""
    edges = build_edges(sockpuppet_pool())
    pr_edges = [e for e in edges if e.kind == "pr_into"]
    assert pr_edges
    for e in pr_edges:
        assert "#" in e.detail  # repo#number, the thing to go and look at


def test_account_creation_clustering_is_reported(known):
    ring = find_clusters(sockpuppet_pool(), known)[0]
    assert ring.created_within_days is not None
    assert ring.created_within_days <= 7

    real = find_clusters(genuine_pool(), known)[0]
    assert real.created_within_days is not None
    assert real.created_within_days > 365


def test_the_summary_states_an_observation_not_a_verdict(known):
    """Language check. This text goes in front of someone deciding on money.

    It must not assert fraud: the same evidence is produced by people who
    genuinely work together, and the engine cannot tell them apart on its own.
    """
    summary = find_clusters(sockpuppet_pool(), known)[0].summary()
    lowered = summary.lower()
    assert "consistent with" in lowered
    assert "not evidence of either" in lowered
    for accusation in ("fraud", "fake", "sockpuppet", "cheat", "reject"):
        assert accusation not in lowered


def test_the_empty_report_admits_what_it_cannot_see():
    """A ring whose members have not all applied is invisible here."""
    text = report([])
    assert "have both been scored" in text


def test_report_marks_only_what_needs_review(known):
    assert "[REVIEW]" in report(find_clusters(sockpuppet_pool(), known))
    assert "[REVIEW]" not in report(find_clusters(genuine_pool(), known))


def test_a_new_application_inside_a_ring_is_flagged_on_arrival(tmp_path):
    """The check has to fire when a person applies, not when someone remembers.

    Ring membership is most actionable while they are still an applicant, and
    it costs no API calls, so there is no reason to make it a periodic chore.
    """
    from talent_engine.config import load_program
    from talent_engine.scoring.engine import CODE_VERSION, score_snapshot
    from talent_engine.server.webhook import IntakeService
    from talent_engine.store.db import Store

    cfg = load_program("prezenti-sponsorship-trial")
    db = str(tmp_path / "pool.db")

    # Three of the four ring members have already been scored.
    store = Store(db)
    run = store.start_run(cfg, "score", CODE_VERSION)
    pool = sockpuppet_pool()
    for handle in ["ring-a", "ring-b", "ring-c"]:
        store.save_snapshot(pool[handle])
        store.save_score(run, score_snapshot(pool[handle], cfg))
    store.close()

    service = IntakeService(cfg, db, collector_factory=lambda: None)
    service._store = Store(db)
    try:
        assert service._ring_note("ring-a")
        assert "consistent with" in service._ring_note("ring-a")
        # Someone with no relationship to the pool gets nothing appended.
        assert service._ring_note("a-stranger") == ""
    finally:
        service._store.close()


def test_a_genuine_collaborator_gets_no_ring_note(tmp_path):
    from talent_engine.config import load_program
    from talent_engine.scoring.engine import CODE_VERSION, score_snapshot
    from talent_engine.server.webhook import IntakeService
    from talent_engine.store.db import Store

    cfg = load_program("prezenti-sponsorship-trial")
    db = str(tmp_path / "pool.db")
    store = Store(db)
    run = store.start_run(cfg, "score", CODE_VERSION)
    for handle, snap in genuine_pool().items():
        store.save_snapshot(snap)
        store.save_score(run, score_snapshot(snap, cfg))
    store.close()

    service = IntakeService(cfg, db, collector_factory=lambda: None)
    service._store = Store(db)
    try:
        assert service._ring_note("ada-builds") == ""
    finally:
        service._store.close()


def test_a_partially_applied_ring_is_still_caught(known):
    """Three of four accounts applied; the fourth is not independent evidence.

    The first version of the metric counted an edge to the absent member as
    outside validation, which dropped the group below the review threshold.
    A ring that only has to withhold one account to disappear is not a check.
    """
    partial = {k: v for k, v in sockpuppet_pool().items() if k != "ring-d"}
    clusters = find_clusters(partial, known)
    assert clusters and clusters[0].needs_review


# ------------------------------------------------------- external review
#
# Both independent reviewers broke the first design, from different angles.
# These are their attacks, kept so the design cannot regress to a single
# threshold on a single ratio.


def _ring_with_decoys(n: int):
    """A ring where each account buys cover with trivial recognised-org PRs."""
    from tests.fixtures.profiles import _iso, _member

    ring = ["ring-a", "ring-b", "ring-c", "ring-d"]
    pool = {}
    for i, h in enumerate(ring):
        others = [o for o in ring if o != h]
        merged = [(f"{others[0]}/sdk", 10 + i), (f"{others[1]}/tools", 20 + i)]
        merged += [("celo-org/celo-composer", 900 + i * 10 + j) for j in range(n)]
        pool[h] = _member(
            h, merged=merged, reviews=[(f"{others[2]}/sdk", 30 + i)], created=_iso(2024, 6, 3 + i)
        )
    return pool


def _co_founders():
    """Two real people building one product together. Not a ring."""
    from tests.fixtures.profiles import _iso, _member

    names = ["ada-fnd", "kwame-fnd"]
    pool = {}
    for i, h in enumerate(names):
        peer = names[1 - i]
        pool[h] = _member(
            h,
            merged=[(f"{peer}/sdk", 50 + i), (f"{peer}/tools", 60 + i)],
            reviews=[(f"{peer}/sdk", 70 + i)],
            created=_iso(2018 + i, 3, 11),
        )
    return pool


@pytest.mark.parametrize("decoys", [0, 1, 2, 3, 4])
def test_cheap_decoy_contributions_no_longer_buy_cover(decoys, known):
    """The evasion that beat the first design.

    Two throwaway pull requests per account into a recognised org dropped
    insularity from 1.00 to 0.60, under the old 0.75 threshold — and those same
    PRs scored positively elsewhere in the rubric. Corroboration closes it:
    buying down one signal leaves the others standing.
    """
    cluster = find_clusters(_ring_with_decoys(decoys), known)[0]
    assert cluster.needs_review, f"{decoys} decoy PRs each defeated the check"


def test_two_co_founders_are_never_flagged(known):
    """The false positive that beat the first design.

    Two people building one product together score maximum insularity —
    identical to the canonical ring — because they validate only each other.
    Groups this small are structurally indistinguishable from a two-account
    ring, and defaming real co-founders is the more expensive error.
    """
    cluster = find_clusters(_co_founders(), known)[0]
    assert cluster.size == 2
    assert cluster.mean_insularity == 1.0  # the old rule would have flagged this
    assert not cluster.needs_review


def test_a_single_signal_is_never_enough(known):
    """One threshold on one ratio failed in both directions; require two."""
    for pool in (genuine_pool(), _co_founders()):
        for cluster in find_clusters(pool, known):
            if len(cluster.fired) < 2:
                assert not cluster.needs_review


def test_the_summary_names_the_signals_that_fired(known):
    """A reviewer needs to know which observation to go and check."""
    summary = find_clusters(sockpuppet_pool(), known)[0].summary()
    assert "created within" in summary or "possible pairs" in summary
