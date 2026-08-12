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
    }
