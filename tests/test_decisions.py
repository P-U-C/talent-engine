"""Decisions and the feedback obligation the policy creates."""

from __future__ import annotations

import pytest

from talent_engine.config import load_program
from talent_engine.modes.decisions import ACTIONABLE, feedback_letter, weakest_actionable
from talent_engine.programs.policy import load_overlay
from talent_engine.scoring.engine import score_snapshot
from talent_engine.store.db import Store
from tests.fixtures.profiles import gamed_profile, quiet_finisher


@pytest.fixture
def cfg():
    return load_program("prezenti-sponsorship-trial")


def test_the_policy_promise_has_a_mechanism_behind_it():
    """The commitment exists; this asserts something implements it."""
    overlay = load_overlay("prezenti-sponsorship-trial")
    assert overlay.commitments_to_recipient["feedback_to_unsuccessful_applicants"]
    # ...and the queue that makes it keepable at scale.
    assert hasattr(Store, "pending_feedback")


def test_feedback_is_never_owed_silently(tmp_path):
    store = Store(tmp_path / "t.db")
    store.record_decision("p", "someone", "declined")
    assert [r["handle"] for r in store.pending_feedback("p")] == ["someone"]

    store.mark_feedback_sent("p", "someone")
    assert store.pending_feedback("p") == []
    store.close()


def test_recording_a_decision_twice_does_not_erase_that_feedback_was_sent(tmp_path):
    """Re-deciding must not silently put someone back in the queue as unpaid."""
    store = Store(tmp_path / "t.db")
    store.record_decision("p", "someone", "declined")
    store.mark_feedback_sent("p", "someone")
    store.record_decision("p", "someone", "declined", note="revisited")
    assert store.pending_feedback("p") == []
    store.close()


def test_accepted_applicants_are_not_in_the_feedback_queue(tmp_path):
    store = Store(tmp_path / "t.db")
    store.record_decision("p", "winner", "accepted")
    assert store.pending_feedback("p") == []
    store.close()


def test_weaknesses_are_ranked_by_points_missed_not_points_scored(cfg):
    """A 40-point dimension scoring 10 matters more than a 5-point one at 0."""
    score = score_snapshot(quiet_finisher(), cfg)
    gaps = weakest_actionable(score)
    missed = [m - p for _k, p, m in gaps]
    assert missed == sorted(missed, reverse=True)


def test_feedback_never_blames_someone_for_who_they_know(cfg):
    """Telling a rejected applicant their problem is not knowing people is
    neither useful nor kind, and it is the opposite of the product thesis."""
    assert "trusted_referral" not in ACTIONABLE
    assert "context_statement" not in ACTIONABLE

    letter = feedback_letter("x", score_snapshot(quiet_finisher(), cfg), cfg)
    assert "referral" not in letter.lower()


def test_the_letter_is_specific_and_reproducible(cfg):
    letter = feedback_letter("tobi-k", score_snapshot(quiet_finisher(), cfg), cfg)
    assert "out of 100" in letter
    assert "python3 -m talent_engine.cli score" in letter  # they can recompute it
    assert "A score never decided this" in letter   # and it did not decide it
    assert "tell us where" in letter                # the rubric improves this way


def test_a_weak_profile_still_gets_actionable_advice(cfg):
    """The lowest scorer is the person most likely to be fobbed off."""
    letter = feedback_letter("fastbuilder99", score_snapshot(gamed_profile(), cfg), cfg)
    assert any(advice[:40] in letter for advice in ACTIONABLE.values())
