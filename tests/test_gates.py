"""Acceptance must fail closed.

External review reproduced an acceptance for an arbitrary GitHub handle with no
scored application, no recorded terms acceptance, no access-barrier
verification, no build-plan review, no Celo-fit check and no conflict sign-off.
`accept --select` added them to the cohort and printed the full letter. Nothing
failed, because nothing was checked.
"""

from __future__ import annotations


import pytest

from talent_engine.model import Application
from talent_engine.modes import gates as gate_checks
from talent_engine.modes.gates import ALL_GATES, HUMAN_GATES
from talent_engine.store.db import Store


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


PROGRAM = "prezenti-sponsorship-trial"
DIGEST = "terms-v1-abc123"


def test_an_unknown_handle_clears_nothing(store):
    checked = gate_checks.evaluate(store, PROGRAM, "nobody", DIGEST)
    assert {g.key for g in checked} == set(ALL_GATES)
    assert len(gate_checks.failing(checked)) == len(ALL_GATES)


def test_signing_off_a_human_gate_clears_only_that_gate(store):
    store.record_signoff(PROGRAM, "amara", "celo_fit_checked", "chad", "clear plan")
    checked = {g.key: g for g in gate_checks.evaluate(store, PROGRAM, "amara", DIGEST)}
    assert checked["celo_fit_checked"].passed
    assert "chad" in checked["celo_fit_checked"].detail
    for other in set(HUMAN_GATES) - {"celo_fit_checked"}:
        assert not checked[other].passed


def _submit(store, *, accepted: bool, version: str, status: str = "scored"):
    store.record_submission(
        submission_id="sub-1",
        program=PROGRAM,
        source="tally",
        form_id="f",
        handle="amara",
        raw_handle="amara",
        application=Application(
            accepted_terms=accepted, accepted_terms_version=version
        ),
    )
    store.conn.execute(
        "UPDATE submissions SET status = ? WHERE submission_id = 'sub-1'", (status,)
    )
    store.conn.commit()


def test_terms_accepted_at_a_stale_version_does_not_count(store):
    """Terms that changed after acceptance are terms nobody agreed to."""
    _submit(store, accepted=True, version="terms-v0-old")
    checked = {g.key: g for g in gate_checks.evaluate(store, PROGRAM, "amara", DIGEST)}
    assert checked["scored_application"].passed
    assert not checked["terms_accepted"].passed
    assert "terms-v0-old" in checked["terms_accepted"].detail


def test_terms_accepted_at_the_current_version_counts(store):
    _submit(store, accepted=True, version=DIGEST)
    checked = {g.key: g for g in gate_checks.evaluate(store, PROGRAM, "amara", DIGEST)}
    assert checked["terms_accepted"].passed


def test_an_unscored_submission_is_not_an_application(store):
    """Queued but never scored is not evidence of anything."""
    _submit(store, accepted=True, version=DIGEST, status="queued")
    checked = {g.key: g for g in gate_checks.evaluate(store, PROGRAM, "amara", DIGEST)}
    assert not checked["scored_application"].passed


def test_all_gates_can_be_cleared_the_honest_way(store):
    _submit(store, accepted=True, version=DIGEST)
    for gate in HUMAN_GATES:
        store.record_signoff(PROGRAM, "amara", gate, "chad", "checked")
    checked = gate_checks.evaluate(store, PROGRAM, "amara", DIGEST)
    assert gate_checks.failing(checked) == []


def test_an_override_is_an_event_with_an_author_and_a_reason(store):
    store.record_override(
        PROGRAM, "amara", ["conflict_cleared"], "chad", "disclosed collaborator"
    )
    rows = store.overrides(PROGRAM, "amara")
    assert len(rows) == 1
    assert rows[0]["steward"] == "chad"
    assert rows[0]["reason"] == "disclosed collaborator"
    assert rows[0]["gates"] == "conflict_cleared"


def test_overrides_accumulate_rather_than_replace(store):
    """Each exception is its own record; the second must not hide the first."""
    store.record_override(PROGRAM, "amara", ["celo_fit_checked"], "chad", "one")
    store.record_override(PROGRAM, "amara", ["conflict_cleared"], "sam", "two")
    assert len(store.overrides(PROGRAM, "amara")) == 2


def test_a_signoff_is_idempotent_per_gate(store):
    store.record_signoff(PROGRAM, "amara", "celo_fit_checked", "chad", "first")
    store.record_signoff(PROGRAM, "amara", "celo_fit_checked", "sam", "second")
    signed = store.signoffs(PROGRAM, "amara")
    assert len(signed) == 1
    assert signed["celo_fit_checked"]["steward"] == "sam"


def test_render_names_every_gate_and_its_state(store):
    text = gate_checks.render(gate_checks.evaluate(store, PROGRAM, "nobody", DIGEST))
    for gate in ALL_GATES:
        assert gate in text
    assert "FAIL" in text


# ------------------------------------------------------- operating tracker

def test_one_receipt_does_not_satisfy_a_four_month_term(store):
    """Checking only that a type ever appeared let month one cover the term."""
    from talent_engine.store.db import programme_periods

    periods = programme_periods(4, "2026-09")
    assert periods == ["2026-09", "2026-10", "2026-11", "2026-12"]
    store.select_cohort(PROGRAM, ["amara"], baseline_run_id="")
    store.record_ledger_entry(
        PROGRAM, "receipt", "chad", handle="amara", period="2026-09", amount_usd=200.0
    )
    missing = store.ledger_summary(PROGRAM, periods=periods)["recipients"]["amara"][
        "missing"
    ]
    assert "receipt:2026-10" in missing
    assert "receipt:2026-09" not in missing


def test_public_update_is_a_tracked_monthly_obligation(store):
    """The policy commits to a monthly public update; it was not checked at all."""
    from talent_engine.store.db import programme_periods

    store.select_cohort(PROGRAM, ["amara"], baseline_run_id="")
    missing = store.ledger_summary(
        PROGRAM, periods=programme_periods(4, "2026-09")
    )["recipients"]["amara"]["missing"]
    assert [m for m in missing if m.startswith("public_update:")]


def test_once_per_term_obligations_are_not_multiplied_by_month(store):
    from talent_engine.store.db import programme_periods

    store.select_cohort(PROGRAM, ["amara"], baseline_run_id="")
    missing = store.ledger_summary(
        PROGRAM, periods=programme_periods(4, "2026-09")
    )["recipients"]["amara"]["missing"]
    assert missing.count("celo_checkpoint") == 1
    assert missing.count("kpi") == 1


def test_a_closed_out_recipient_has_nothing_missing(store):
    from talent_engine.store.db import programme_periods

    periods = programme_periods(2, "2026-09")
    store.select_cohort(PROGRAM, ["amara"], baseline_run_id="")
    for period in periods:
        for t in ("receipt", "reimbursement", "public_update"):
            store.record_ledger_entry(
                PROGRAM, t, "chad", handle="amara", period=period, amount_usd=1.0
            )
    for t in ("celo_checkpoint", "months_funded", "kpi"):
        store.record_ledger_entry(PROGRAM, t, "chad", handle="amara")
    assert store.ledger_summary(PROGRAM, periods=periods)["recipients"]["amara"][
        "missing"
    ] == []
