"""The acceptance flow: what gets recorded, and what the builder is told."""

from __future__ import annotations

import pytest

from talent_engine.modes.acceptance import acceptance_letter, split_plan
from talent_engine.programs.policy import load_overlay
from talent_engine.store.db import Store


@pytest.fixture
def overlay():
    return load_overlay("prezenti-sponsorship-trial")


ENV = {
    "PREZENTI_GIVEBACK_ADDRESS": "0x1111111111111111111111111111111111111111",
    "CELO_COMMUNITY_FUND_ADDRESS": "0x2222222222222222222222222222222222222222",
}


def test_split_parameters_come_from_the_environment_not_the_policy(overlay):
    """Payout addresses must not live in a public repository."""
    plan = split_plan(overlay, ENV)
    assert plan.resolved
    assert sum(r["bps"] for r in plan.recipients) == overlay.giveback["total_bps"]

    unresolved = split_plan(overlay, {})
    assert not unresolved.resolved
    assert "unset" in unresolved.render()


def test_nothing_here_deploys_a_contract(overlay):
    """A scoring pipeline takes untrusted public input; it holds no signing key."""
    plan = split_plan(overlay, ENV)
    text = plan.render()
    assert "app.splits.org" in text  # a person creates it, deliberately
    assert not hasattr(plan, "deploy")


def test_the_letter_states_the_limits_of_the_pledge(overlay):
    """The builder is told plainly that this is not legally enforced."""
    letter = acceptance_letter("amara-dev", overlay)
    assert "not legally enforced" in letter
    assert "security interest" in letter


def test_the_letter_carries_the_bounds_not_just_the_ask(overlay):
    letter = acceptance_letter("amara-dev", overlay)
    assert "Capped at $14,000" in letter
    assert "expires 36 months" in letter
    assert "pro-rated" in letter
    assert "owed to Prezenti and to nobody else" in letter
    assert "half of what it receives" in letter
    assert "1% of covered income" in letter
    assert overlay.terms_digest() in letter


def test_the_letter_says_what_the_programme_owes(overlay):
    """An acceptance listing only obligations is how a relationship starts badly."""
    letter = acceptance_letter("amara-dev", overlay)
    assert "What we owe you:" in letter
    assert "keep all IP" in letter
    assert "withdraw at any time without penalty" in letter
    assert "No exclusivity" in letter


def test_the_letter_shares_the_score_and_its_caveat(overlay):
    """They get the unflattering sentence too, per the commitment to share evidence."""
    letter = acceptance_letter(
        "amara-dev", overlay, score=68.2, caveat="Look closer: something to check."
    )
    assert "68.2" in letter
    assert "Look closer: something to check." in letter
    assert "A score never decided this" in letter


def test_acceptance_requires_an_existing_cohort_row(tmp_path):
    """Accepting someone never selected should fail rather than invent a decision."""
    store = Store(tmp_path / "t.db")
    assert store.record_acceptance("p", "nobody") is False

    store.select_cohort("p", ["amara-dev"], baseline_run_id="run_x")
    assert store.record_acceptance(
        "p", "amara-dev", split_address="0xabc", attestation_uid="0xuid"
    )
    row = store.cohort("p")[0]
    assert row["split_address"] == "0xabc"
    assert row["attestation_uid"] == "0xuid"
    assert row["accepted_at"]
    store.close()
