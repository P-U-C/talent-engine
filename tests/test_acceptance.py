"""The acceptance flow: what gets recorded, and what the builder is told."""

from __future__ import annotations

from argparse import Namespace

import pytest

from talent_engine.cli import cmd_accept
from talent_engine.model import Application
from talent_engine.modes import attestations
from talent_engine.modes.acceptance import acceptance_letter, payment_route
from talent_engine.programs.policy import load_overlay
from talent_engine.store.db import Store


@pytest.fixture
def overlay():
    return load_overlay("prezenti-sponsorship-trial")


def test_payment_route_is_direct_to_the_verified_safe(overlay):
    route = payment_route(overlay)
    assert route.resolved
    assert route.address == overlay.attestation["recipient"]
    assert route.bps == overlay.giveback["total_bps"]
    text = route.render()
    assert "direct transfer" in text
    assert "No 0xSplits collector" in text


def test_nothing_here_deploys_a_contract(overlay):
    """A scoring pipeline takes untrusted public input; it holds no signing key."""
    route = payment_route(overlay)
    assert not hasattr(route, "deploy")
    assert "app.splits.org" not in route.render()


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
    assert overlay.covered_income_text() in letter
    assert "owed to Prezenti and to nobody else" in letter
    assert "half of what it receives" in letter
    assert "1% of covered income" in letter
    assert "One monthly public update" in letter
    assert "30 days without" in letter
    assert "7 days to provide evidence" in letter
    assert "month-two checkpoint" in letter
    assert "No 0xSplits collector" in letter
    assert "GitHub handle" in letter
    assert overlay.terms_digest() in letter


def test_the_letter_names_the_approved_benefits(overlay):
    letter = acceptance_letter("amara-dev", overlay)
    assert "claude max 20x" in letter
    assert "chatgpt pro 5x" in letter


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
    with pytest.raises(ValueError, match="requires payment address"):
        store.record_acceptance("p", "amara-dev")
    assert store.record_acceptance(
        "p",
        "amara-dev",
        payment_address="0xabc",
        attestation_uid="0xuid",
        attestation_signer="0xsigner",
    )
    row = store.cohort("p")[0]
    assert row["payment_address"] == "0xabc"
    assert row["split_address"] == "0xabc"  # legacy alias, not a deployed Split
    assert row["attestation_uid"] == "0xuid"
    assert row["attestation_signer"] == "0xsigner"
    assert row["accepted_at"]
    store.close()


def test_accept_candidate_writes_selection_decision_and_artifacts_atomically(tmp_path):
    store = Store(tmp_path / "t.db")
    assert store.accept_candidate(
        "p",
        "amara-dev",
        selected=True,
        baseline_run_id="run_x",
        declared_repo="amara/project",
        payment_address="0xsafe",
        attestation_uid="0xuid",
        attestation_signer="0xsigner",
        override=(["human_check"], "steward", "checked elsewhere"),
    )
    row = store.cohort("p")[0]
    assert row["declared_repo"] == "amara/project"
    assert row["payment_address"] == "0xsafe"
    assert row["attestation_uid"] == "0xuid"
    assert store.decisions("p")[0]["decision"] == "accepted"
    assert store.overrides("p", "amara-dev")[0]["steward"] == "steward"
    events = store.attestation_events("p", "amara-dev")
    assert [(e["event_type"], e["uid"]) for e in events] == [("initial", "0xuid")]
    store.close()


def test_accept_candidate_requires_artifacts_before_any_write(tmp_path):
    store = Store(tmp_path / "t.db")
    with pytest.raises(ValueError, match="requires payment_address"):
        store.accept_candidate(
            "p",
            "amara-dev",
            selected=True,
            payment_address="",
            attestation_uid="0xuid",
            attestation_signer="0xsigner",
        )
    assert store.cohort("p") == []
    assert store.decisions("p") == []
    assert store.attestation_events("p", "amara-dev") == []
    store.close()


def test_cli_override_cannot_bypass_legal_clearance(tmp_path, monkeypatch):
    """Candidate exceptions must not turn uncleared terms into cleared terms."""
    db = tmp_path / "t.db"
    overlay = load_overlay("prezenti-sponsorship-trial")
    store = Store(db)
    store.select_cohort("prezenti-sponsorship-trial", ["amara-dev"], baseline_run_id="run_x")
    store.close()

    def should_not_validate(*args, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("attestation validation should not run before legal clearance")

    monkeypatch.setattr(attestations, "validate_attestation_uid", should_not_validate)
    rc = cmd_accept(
        Namespace(
            db=str(db),
            program="prezenti-sponsorship-trial",
            handle="amara-dev",
            overlay=None,
            payment_address=overlay.attestation["recipient"],
            split_address=None,
            attestation_uid="0x" + "ab" * 32,
            attestation_signer="0x1111111111111111111111111111111111111111",
            attestation_rpc="http://unused.invalid",
            baseline=None,
            select=False,
            override=True,
            steward="zoz",
            reason="test override",
        )
    )
    assert rc == 2
    store = Store(db)
    assert store.decisions("prezenti-sponsorship-trial") == []
    assert store.overrides("prezenti-sponsorship-trial", "amara-dev") == []
    assert store.cohort("prezenti-sponsorship-trial")[0]["accepted_at"] == ""
    store.close()


def test_cli_validates_uid_before_recording_acceptance(tmp_path, monkeypatch):
    """A bad UID must not leave a false accepted decision behind."""
    db = tmp_path / "t.db"
    overlay = load_overlay("prezenti-sponsorship-trial")
    store = Store(db)
    store.select_cohort("prezenti-sponsorship-trial", ["amara-dev"], baseline_run_id="run_x")
    store.record_program_clearance(
        "prezenti-sponsorship-trial",
        "legal",
        overlay.terms_digest(),
        overlay.terms_hash(),
        "counsel",
        "test clearance",
    )
    store.close()

    def reject(*args, **kwargs):
        raise attestations.AttestationValidationError("bad uid")

    monkeypatch.setattr(attestations, "validate_attestation_uid", reject)
    rc = cmd_accept(
        Namespace(
            db=str(db),
            program="prezenti-sponsorship-trial",
            handle="amara-dev",
            overlay=None,
            payment_address=overlay.attestation["recipient"],
            split_address=None,
            attestation_uid="0x" + "ab" * 32,
            attestation_signer="0x1111111111111111111111111111111111111111",
            attestation_rpc="http://unused.invalid",
            baseline=None,
            select=False,
            override=True,
            steward="zoz",
            reason="test override",
        )
    )
    assert rc == 2
    store = Store(db)
    assert store.decisions("prezenti-sponsorship-trial") == []
    assert store.overrides("prezenti-sponsorship-trial", "amara-dev") == []
    assert store.cohort("prezenti-sponsorship-trial")[0]["accepted_at"] == ""
    store.close()


def test_closeout_records_replacement_and_revocation_as_idempotent_transitions(tmp_path):
    store = Store(tmp_path / "t.db")
    store.select_cohort("p", ["amara-dev"], baseline_run_id="run_x")
    store.record_acceptance(
        "p",
        "amara-dev",
        payment_address="0xsafe",
        attestation_uid="0xorig",
        attestation_signer="0xsigner",
    )
    event_id, created = store.record_closeout_replacement(
        "p",
        "amara-dev",
        owner="operator",
        months_funded=2,
        replacement_uid="0xreplacement",
        original_uid="0xorig",
        signer="0xsigner",
    )
    assert created is True
    assert store.record_closeout_replacement(
        "p",
        "amara-dev",
        owner="operator",
        months_funded=2,
        replacement_uid="0xreplacement",
        original_uid="0xorig",
        signer="0xsigner",
    ) == (event_id, False)
    with pytest.raises(ValueError, match="different details"):
        store.record_closeout_replacement(
            "p",
            "amara-dev",
            owner="operator",
            months_funded=3,
            replacement_uid="0xreplacement2",
            original_uid="0xorig",
            signer="0xsigner",
        )

    revoke_id, created = store.record_closeout_revocation(
        "p",
        "amara-dev",
        owner="operator",
        original_uid="0xorig",
        replacement_uid="0xreplacement",
        signer="0xsigner",
        revocation_tx="0xtx",
    )
    assert created is True
    assert store.record_closeout_revocation(
        "p",
        "amara-dev",
        owner="operator",
        original_uid="0xorig",
        replacement_uid="0xreplacement",
        signer="0xsigner",
        revocation_tx="0xtx",
    ) == (revoke_id, False)
    with pytest.raises(ValueError, match="different tx"):
        store.record_closeout_revocation(
            "p",
            "amara-dev",
            owner="operator",
            original_uid="0xorig",
            replacement_uid="0xreplacement",
            signer="0xsigner",
            revocation_tx="0xother",
        )

    events = store.attestation_events("p", "amara-dev")
    assert [e["event_type"] for e in events] == ["replacement", "revocation"]
    assert events[0]["previous_uid"] == "0xorig"
    assert events[0]["months_funded"] == 2
    assert events[1]["uid"] == "0xorig"
    assert events[1]["previous_uid"] == "0xreplacement"
    assert store.cohort("p")[0]["months_received"] == 2
    store.close()


def test_revocation_requires_a_recorded_replacement(tmp_path):
    store = Store(tmp_path / "t.db")
    with pytest.raises(ValueError, match="replacement before revocation"):
        store.record_closeout_revocation(
            "p",
            "amara-dev",
            owner="operator",
            original_uid="0xorig",
            replacement_uid="0xreplacement",
            signer="0xsigner",
            revocation_tx="0xtx",
        )
    store.close()


def test_quarantine_excludes_smoke_tests_from_reporting_and_selection(tmp_path):
    store = Store(tmp_path / "t.db")
    _scored_submission(store, "p", "octocat", 99, "run_a")
    _scored_submission(store, "p", "real-builder", 80, "run_b")
    store.quarantine_applicant("p", "octocat", "smoke test")

    assert [r["handle"] for r in store.submissions("p")] == ["real-builder"]
    assert {r["handle"] for r in store.submissions("p", include_quarantined=True)} == {
        "real-builder",
        "octocat",
    }
    assert [r["handle"] for r in store.shortlist("p")] == ["real-builder"]
    assert store.has_scored_application("p", "octocat") is False
    with pytest.raises(ValueError, match="quarantined"):
        store.select_cohort("p", ["octocat"], baseline_run_id="run_x")
    store.close()


def test_shortlist_is_whole_pool_latest_score_and_deterministic(tmp_path):
    store = Store(tmp_path / "t.db")
    _scored_submission(store, "p", "zoe", 70, "run_old", received_at="2026-08-01T00:00:00Z")
    _scored_submission(store, "p", "zoe", 90, "run_new", received_at="2026-08-02T00:00:00Z")
    _scored_submission(store, "p", "amy", 90, "run_a", received_at="2026-08-03T00:00:00Z")
    rows = store.shortlist("p")
    assert [(r["handle"], r["total"], r["run_id"]) for r in rows] == [
        ("amy", 90, "run_a"),
        ("zoe", 90, "run_new"),
    ]
    store.close()


def _scored_submission(
    store: Store,
    program: str,
    handle: str,
    total: float,
    run_id: str,
    *,
    received_at: str | None = None,
) -> None:
    sid = f"sub_{program}_{handle}_{run_id}"
    assert store.record_submission(
        sid,
        program,
        "test",
        handle,
        handle,
        Application(declared_repo=f"{handle}/repo", accepted_terms=True),
    )
    if received_at:
        store.conn.execute("UPDATE submissions SET received_at = ? WHERE submission_id = ?", (received_at, sid))
        store.conn.commit()
    store.finish_submission(sid, "scored", run_id=run_id, total=total)
