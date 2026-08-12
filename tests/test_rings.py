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


def test_real_collaborators_cluster_but_are_not_flagged(known):
    """The whole point. They review each other; they are not a ring."""
    clusters = find_clusters(genuine_pool(), known)
    assert len(clusters) == 1
    group = clusters[0]
    assert group.size == 3  # they ARE connected, and that is fine
    assert group.mean_insularity < INSULARITY_REVIEW
    assert not group.needs_review


def test_the_discriminator_is_insularity_not_clustering(known):
    """Both groups cluster identically; only the outward edges differ."""
    ring = find_clusters(sockpuppet_pool(), known)[0]
    real = find_clusters(genuine_pool(), known)[0]
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
