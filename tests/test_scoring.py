"""Rubric behaviour and design-invariant tests.

The tests that matter most here are not the arithmetic ones -- they are the
adversarial ones. A rubric that cannot be shown to resist gaming is a ranking
of who tried hardest to look good.
"""

from __future__ import annotations

import copy

import pytest

from talent_engine.config import REFERENCE_WEIGHTS, ProgramConfig, load_program
from talent_engine.model import DimensionScore, Evidence, Flag
from talent_engine.scoring.engine import rank, score_snapshot
from talent_engine.scoring.flags import has_flag

from .fixtures.profiles import (
    genuine_builder,
    gamed_profile,
    insider_low_shipper,
    quiet_finisher,
)


@pytest.fixture()
def cfg() -> ProgramConfig:
    return load_program("celo-trial")


# ---------------------------------------------------------------- core claim


def test_gamed_profile_cannot_outrank_genuine_builder(cfg):
    genuine = score_snapshot(genuine_builder(), cfg)
    gamed = score_snapshot(gamed_profile(), cfg)
    assert gamed.total < genuine.total
    # Not merely lower -- decisively so. Gaming must be worthless, not cheap.
    assert gamed.total < genuine.total / 3


def test_gamed_profile_raises_every_expected_flag(cfg):
    gamed = score_snapshot(gamed_profile(), cfg)
    for key in ("new_account", "burst_activity", "metric_inflation", "unverifiable_referrer"):
        assert has_flag(gamed.flags, key), f"missing flag {key}"


def test_flags_never_add_points(cfg):
    """A flag object has no way to increase a score, by construction."""
    assert not hasattr(Flag("k", "warn", "m"), "points")
    with pytest.raises(ValueError):
        Flag("k", "warn", "m", discount=1.5)
    with pytest.raises(ValueError):
        Flag("k", "warn", "m", discount=-0.1)


def test_burst_discount_guts_commit_volume(cfg):
    """80 commits in one week must earn near-nothing on volume.

    Asserted against the undiscounted counterfactual rather than a magic
    number: the same 80 commits spread across the window are worth ~20x more.
    """
    snap = gamed_profile()
    gamed = score_snapshot(snap, cfg)
    ship = gamed.dimension("shipping_agency")
    assert ship.components["commits"] == 80

    spread = copy.deepcopy(snap)
    spread.active_weeks = [f"2026-W{6 + i:02d}" for i in range(14)]
    honest = score_snapshot(spread, cfg).dimension("shipping_agency")

    ratio = ship.components["commit_volume"] / honest.components["commit_volume"]
    assert ratio == pytest.approx(cfg.thresholds.burst_commit_discount, rel=0.01)
    assert ship.components["commit_volume"] < 0.05 * ship.max_points


def test_quiet_finisher_beats_gamed_by_a_wide_margin(cfg):
    """53 commits done properly must dominate 80 commits manufactured."""
    quiet = score_snapshot(quiet_finisher(), cfg)
    gamed = score_snapshot(gamed_profile(), cfg)
    assert quiet.total > gamed.total * 3


def test_insider_does_not_beat_independent_builder(cfg):
    """Invariant 1, tested rather than asserted."""
    genuine = score_snapshot(genuine_builder(), cfg)
    insider = score_snapshot(insider_low_shipper(), cfg)
    assert insider.total < genuine.total


def test_insider_does_not_beat_quiet_shipper_on_automated_signal(cfg):
    """The regression that motivated repo-level dedupe.

    `wellconnected` has 14 merged PRs and 15 reviews but 4 commits of their own;
    `tobi-k` shipped two finished projects and applied with nothing. Counting
    per-event let the insider win on volume against a single monorepo. Compared
    on automated points only, since tobi-k declares no application fields.
    """
    insider = score_snapshot(insider_low_shipper(), cfg)
    quiet = score_snapshot(quiet_finisher(), cfg)
    assert quiet.automated_total > insider.automated_total


def test_repeat_prs_to_one_repo_do_not_equal_breadth(cfg):
    """Ten PRs to one repo must score below ten PRs across ten repos."""
    from talent_engine.model import PullRequestActivity

    base = quiet_finisher()

    narrow = copy.deepcopy(base)
    narrow.merged_prs = [
        PullRequestActivity(repo="celo-org/celo-monorepo", number=i, title="fix",
                            merged_at="2026-04-01T00:00:00+00:00", created_at=None)
        for i in range(10)
    ]
    broad = copy.deepcopy(base)
    broad.merged_prs = [
        PullRequestActivity(repo=f"celo-org/project-{i}", number=i, title="fix",
                            merged_at="2026-04-01T00:00:00+00:00", created_at=None)
        for i in range(10)
    ]

    n = score_snapshot(narrow, cfg).dimension("external_validation")
    b = score_snapshot(broad, cfg).dimension("external_validation")
    assert b.points > n.points
    assert n.components["distinct_repos"] == 1
    assert b.components["distinct_repos"] == 10


def test_ranking_puts_genuine_first(cfg):
    scores = [
        score_snapshot(s(), cfg)
        for s in (gamed_profile, insider_low_shipper, quiet_finisher, genuine_builder)
    ]
    ordered = [s.handle for s in rank(scores)]
    assert ordered[0] == "amara-dev"
    assert ordered[-1] == "fastbuilder99"


# ------------------------------------------------------------- transparency


def test_points_require_evidence(cfg):
    with pytest.raises(ValueError, match="no evidence"):
        DimensionScore(key="shipping_agency", points=5.0, max_points=25.0)


def test_every_scored_dimension_carries_evidence(cfg):
    genuine = score_snapshot(genuine_builder(), cfg)
    for d in genuine.dimensions:
        if d.points > 0:
            assert d.evidence, f"{d.key} scored {d.points} with no evidence"
            for e in d.evidence:
                assert e.url.startswith("https://")


def test_evidence_rejects_non_public_url():
    with pytest.raises(ValueError):
        Evidence(claim="x", url="file:///etc/passwd")


def test_score_is_reproducible(cfg):
    """Same snapshot + same weights -> identical total and digest."""
    snap = genuine_builder()
    a = score_snapshot(snap, cfg)
    b = score_snapshot(copy.deepcopy(snap), cfg)
    assert a.total == b.total
    assert a.snapshot_digest == b.snapshot_digest
    assert a.weights_digest == b.weights_digest


def test_dimension_cannot_exceed_its_weight(cfg):
    genuine = score_snapshot(genuine_builder(), cfg)
    for d in genuine.dimensions:
        assert d.points <= cfg.max_points(d.key) + 1e-9
    assert genuine.total <= sum(cfg.weights.values()) + 1e-9


# ------------------------------------------------------------ config guards


def test_config_rejects_insider_heavy_rubric():
    """A program cannot configure its way around invariant 1."""
    with pytest.raises(ValueError, match="insider-network weight"):
        ProgramConfig(
            key="bad",
            name="insider heavy",
            weights={
                "shipping_agency": 10,
                "consistency": 5,
                "external_validation": 30,
                "collaboration": 25,
                "ecosystem_footprint": 10,
                "frontier_signal": 10,
                "context_statement": 5,
                "trusted_referral": 5,
            },
        )


def test_config_rejects_unknown_dimension():
    with pytest.raises(ValueError, match="unknown rubric dimensions"):
        ProgramConfig(key="bad", name="x", weights={"followers": 50, "shipping_agency": 50})


def test_referrer_matching_is_exact_not_fuzzy(cfg):
    assert cfg.is_verified_referrer("Celo Regional Scout - East Africa")
    assert cfg.is_verified_referrer("celo regional scout - east africa")
    # A near-match is the attack, not a convenience.
    assert not cfg.is_verified_referrer("Celo Regional Scout East Africa")
    assert not cfg.is_verified_referrer("Celo Scout")


def test_recruitment_mode_disables_context_statement():
    rec = ProgramConfig(
        key="rec",
        name="senior solidity",
        mode="recruitment",
        context_statement_enabled=False,
        # The default weights score trusted_referral, and a weighted referral
        # dimension now requires a registry to check against (invariant 4).
        referrers=["Internal Referrer"],
    )
    assert rec.max_points("context_statement") == 0.0


def test_a_weighted_referral_dimension_requires_a_registry():
    """Invariant 4: a rubric must not advertise points nobody can earn."""
    with pytest.raises(ValueError, match="referrer registry is empty"):
        ProgramConfig(key="bad", name="no registry", referrers=[])


def test_an_unweighted_referral_dimension_needs_no_registry():
    cfg = ProgramConfig(
        key="ok",
        name="referral not scored",
        weights={**REFERENCE_WEIGHTS, "trusted_referral": 0},
        referrers=[],
    )
    assert cfg.max_points("trusted_referral") == 0.0


def test_keyword_matching_respects_word_boundaries(cfg):
    """'mcp' must not match 'mcpherson'."""
    assert cfg.frontier.match_reasons(full_name="a/mcp-server", description="")
    assert not cfg.frontier.match_reasons(full_name="a/mcpherson-blog", description="")


# ------------------------------------------------------------ no inference


def test_no_demographic_inference_surface():
    """Invariant 2 is structural: the model has nowhere to put inferred traits.

    Context reaches the engine only through applicant-declared fields.
    """
    from talent_engine.model import Application, ProfileSnapshot
    import dataclasses

    app_fields = {f.name for f in dataclasses.fields(Application)}
    snap_fields = {f.name for f in dataclasses.fields(ProfileSnapshot)}
    banned = {"gender", "ethnicity", "race", "age", "nationality", "location", "country", "avatar", "photo", "name_origin"}
    assert not (app_fields & banned)
    assert not (snap_fields & banned)
