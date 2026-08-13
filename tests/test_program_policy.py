"""The sponsorship layer stays separate from, and safer than, the score."""

from __future__ import annotations

import copy

import pytest

from talent_engine.config import load_program
from talent_engine.programs.policy import ProgramOverlay, load_overlay


def test_prezenti_overlay_reconciles_budget_and_score_config():
    policy = load_overlay("prezenti-sponsorship-trial")
    scoring = load_program(policy.scoring_program)

    assert policy.per_person_usd == 1400
    assert policy.total_budget_usd == 7000
    assert policy.seats == 5
    assert sum(scoring.weights.values()) == 100
    assert scoring.weights["context_statement"] == 0
    assert scoring.weights["trusted_referral"] == 0


def test_program_score_can_shortlist_but_cannot_select():
    data = _policy_dict()
    data["selection"]["automated_final_selection"] = True
    with pytest.raises(ValueError, match="may shortlist"):
        ProgramOverlay.from_dict(data)


def test_human_verification_is_required():
    data = _policy_dict()
    data["selection"]["human_verification_required"] = False
    with pytest.raises(ValueError, match="human verification"):
        ProgramOverlay.from_dict(data)


def test_inactivity_requires_a_cure_period():
    data = _policy_dict()
    data["monitoring"]["cure_days"] = 0
    with pytest.raises(ValueError, match="cure period"):
        ProgramOverlay.from_dict(data)


def test_metric_flag_cannot_automatically_cancel_support():
    data = _policy_dict()
    data["monitoring"]["metric_flag_automatically_terminates"] = True
    with pytest.raises(ValueError, match="cannot auto-terminate"):
        ProgramOverlay.from_dict(data)


def test_budget_and_giveback_must_reconcile():
    data = _policy_dict()
    data["budget_usd"] = 6999
    with pytest.raises(ValueError, match="benefit schedule"):
        ProgramOverlay.from_dict(data)

    data = _policy_dict()
    data["giveback"]["recipients"][0]["bps"] = 99
    with pytest.raises(ValueError, match="do not add up"):
        ProgramOverlay.from_dict(data)


def _policy_dict():
    policy = load_overlay("prezenti-sponsorship-trial")
    return {
        "key": policy.key,
        "name": policy.name,
        "scoring_program": policy.scoring_program,
        "seats": policy.seats,
        "duration_months": policy.duration_months,
        "budget_usd": policy.budget_usd,
        "benefits": [
            {
                "key": b.key,
                "monthly_usd": b.monthly_usd,
                "months": b.months,
                "one_time_usd": b.one_time_usd,
            }
            for b in policy.benefits
        ],
        "selection": copy.deepcopy(policy.selection),
        "monitoring": copy.deepcopy(policy.monitoring),
        "giveback": copy.deepcopy(policy.giveback),
        "kpis": copy.deepcopy(policy.kpis),
        "upside": copy.deepcopy(policy.upside),
        "commitments_to_recipient": copy.deepcopy(policy.commitments_to_recipient),
        "term_start": policy.term_start,
        "term_end": policy.term_end,
        "terms_release": copy.deepcopy(policy.terms_release),
        "attestation": copy.deepcopy(policy.attestation),
        "public_attestation_required": policy.public_attestation_required,
        "payment": copy.deepcopy(policy.payment),
        "operating_owner": policy.operating_owner,
    }


# --------------------------------------------------------------- terms v2
#
# The terms are enforced here rather than described in a document, for the
# same reason every other invariant in this repo is: a policy that lives only
# in prose drifts the first time someone is in a hurry.


def _overlay(**giveback_overrides):
    """A minimal valid overlay, so each test can break exactly one thing."""
    from talent_engine.programs.policy import ProgramOverlay

    giveback = {
        "total_bps": 200,
        "cap_multiple_of_sponsorship": 10,
        "sunset_months_after_term": 36,
        "prorated_by_months_received": True,
        # One counterparty: a builder cannot owe a party they have no agreement with.
        "recipients": [{"name": "A", "bps": 200}],
    }
    giveback.update(giveback_overrides)
    return ProgramOverlay.from_dict(
        {
            "key": "t",
            "name": "T",
            "scoring_program": "p",
            "seats": 2,
            "duration_months": 4,
            "budget_usd": 800,
            "benefits": [{"key": "b", "monthly_usd": 100, "months": 4}],
            "selection": {
                "automated_final_selection": False,
                "human_verification_required": True,
                "build_plan_required": True,
            },
            "monitoring": {"inactivity_review_days": 30, "cure_days": 7},
            "giveback": giveback,
            "term_start": "2026-09",
            "term_end": "2026-12-29",
            "terms_release": {
                "version": "test-terms",
                "document": "docs/terms/prezenti-sponsorship-trial-2026-08-13-v2.md",
            },
            "payment": {
                "method": "direct_to_prezenti_safe",
                "recipient": "0xA5c9389A0Ce1bFe24FF883E761Ff313225C77D44",
            },
            "commitments_to_recipient": {
                "retains_all_ip_and_equity": True,
                "may_withdraw_without_penalty": True,
            },
        }
    )


def test_an_uncapped_giveback_is_refused():
    """The encumbrance a later investor asks to have removed."""
    with pytest.raises(ValueError, match="capped"):
        _overlay(cap_multiple_of_sponsorship=None)


def test_a_perpetual_giveback_is_refused():
    with pytest.raises(ValueError, match="expire"):
        _overlay(sunset_months_after_term=None)


def test_a_giveback_that_is_not_prorated_is_refused():
    with pytest.raises(ValueError, match="pro-rated"):
        _overlay(prorated_by_months_received=False)


def test_taking_equity_is_refused_at_this_cheque_size():
    from talent_engine.programs.policy import ProgramOverlay

    base = _overlay()
    data = {
        "key": base.key, "name": base.name, "scoring_program": base.scoring_program,
        "seats": base.seats, "duration_months": base.duration_months,
        "budget_usd": base.budget_usd,
        "benefits": [{"key": "b", "monthly_usd": 100, "months": 4}],
        "selection": base.selection, "monitoring": base.monitoring,
        "giveback": base.giveback,
        "term_start": base.term_start,
        "term_end": base.term_end,
        "terms_release": base.terms_release,
        "payment": base.payment,
        "commitments_to_recipient": base.commitments_to_recipient,
        "upside": {"equity_taken": True},
    }
    with pytest.raises(ValueError, match="does not take equity"):
        ProgramOverlay.from_dict(data)


def test_terms_must_run_both_ways():
    """A sponsorship where only one side has obligations is not a relationship."""
    from talent_engine.programs.policy import ProgramOverlay

    base = _overlay()
    data = {
        "key": "t", "name": "T", "scoring_program": "p", "seats": 2,
        "duration_months": 4, "budget_usd": 800,
        "benefits": [{"key": "b", "monthly_usd": 100, "months": 4}],
        "selection": base.selection, "monitoring": base.monitoring,
        "giveback": base.giveback,
        "term_start": base.term_start,
        "term_end": base.term_end,
        "terms_release": base.terms_release,
        "payment": base.payment,
    }
    with pytest.raises(ValueError, match="owes the recipient"):
        ProgramOverlay.from_dict(data)

    data["commitments_to_recipient"] = {"retains_all_ip_and_equity": True}
    with pytest.raises(ValueError, match="may_withdraw_without_penalty"):
        ProgramOverlay.from_dict(data)


def test_the_giveback_scales_with_what_was_actually_received():
    """Someone who left at the month-two gate owes half, not all."""
    o = _overlay()
    assert o.giveback_owed_bps(0) == 0
    assert o.giveback_owed_bps(2) == 100
    assert o.giveback_owed_bps(4) == 200
    assert o.giveback_owed_bps(99) == 200  # cannot exceed the full term


def test_onward_commitment_is_half_of_prezentis_receipts():
    o = _overlay(prezenti_onward_commitment={"name": "Fund", "bps_of_covered_income": 100})
    onward = o.giveback["prezenti_onward_commitment"]
    assert onward["bps_of_covered_income"] * 2 == o.giveback["total_bps"]

    with pytest.raises(ValueError, match="bps_of_covered_income"):
        _overlay(prezenti_onward_commitment={"name": "Fund", "bps_of_receipts": 100})

    with pytest.raises(ValueError, match="half"):
        _overlay(prezenti_onward_commitment={"name": "Fund", "bps_of_covered_income": 50})


def test_payment_route_must_be_direct_to_prezenti_safe():
    base = _policy_dict()
    base["payment"]["method"] = "splits_collector"
    with pytest.raises(ValueError, match="do not deploy a collector"):
        ProgramOverlay.from_dict(base)

    base = _policy_dict()
    base["payment"]["recipient"] = "0x1111111111111111111111111111111111111111"
    with pytest.raises(ValueError, match="verified Prezenti Safe"):
        ProgramOverlay.from_dict(base)


def test_public_attestation_is_declared_when_required():
    base = _policy_dict()
    base["public_attestation_required"] = False
    with pytest.raises(ValueError, match="public_attestation_required"):
        ProgramOverlay.from_dict(base)


def test_the_terms_release_drives_both_form_marker_and_pledge_hash():
    o = load_overlay("prezenti-sponsorship-trial")
    assert o.terms_hash().startswith("0x")
    assert len(o.terms_hash()) == 66
    assert o.terms_digest() == o.terms_hash()[2:14]
    assert o.terms_release["document"] == "docs/terms/prezenti-sponsorship-trial-2026-08-13-v2.md"
    assert o.public_attestation_required is True
    assert o.payment["method"] == "direct_to_prezenti_safe"


def test_the_tracker_calendar_is_policy_state():
    o = load_overlay("prezenti-sponsorship-trial")
    assert o.term_start == "2026-09"
    assert o.term_end == "2026-12-29"
    assert o.attestation_expiration > 0


def test_the_live_program_carries_the_agreed_terms():
    from talent_engine.programs import load_overlay

    o = load_overlay("prezenti-sponsorship-trial")
    assert o.giveback_cap_usd == 14000.0
    assert o.giveback["sunset_months_after_term"] == 36
    assert o.giveback["enforcement"] == "reputational"
    assert o.upside["right_of_first_offer_next_round"] is True
    assert o.upside["equity_taken"] is False
    assert o.commitments_to_recipient["no_exclusivity"] is True
    assert o.commitments_to_recipient["feedback_to_unsuccessful_applicants"] is True


def test_the_page_and_the_policy_cannot_disagree():
    """The public page renders terms from the validated policy object.

    Written twice — once in the policy, once in HTML — they drift, and the
    version the public reads is the one nothing enforces.
    """
    from talent_engine.programs import load_overlay
    from talent_engine.server import landing_page

    overlay = load_overlay("prezenti-sponsorship-trial")
    page = landing_page("P", "formid", None, overlay).decode()
    for line in overlay.terms_summary():
        assert line in page


def test_a_closed_programme_does_not_show_an_application_form():
    """A page rendering a form is a page saying "apply"."""
    from talent_engine.programs import load_overlay
    from talent_engine.server import landing_page

    overlay = load_overlay("prezenti-sponsorship-trial")
    overlay.status = "closed"
    page = landing_page("P", "formid", None, overlay).decode()
    assert "Applications are closed" in page
    assert "tally.so/embed" not in page
