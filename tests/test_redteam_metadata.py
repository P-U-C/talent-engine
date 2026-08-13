"""The metadata attack, and the four countermeasures that answer it.

Found by adversarial review on 2026-08-13 against the live
`prezenti-sponsorship-trial` weights. The attack needs no accomplices and does
nothing a human would call fraud: five thin repositories, taxonomy keywords in
every field the taxonomy reads, all five finishing marks set, and a weekly cron.

It scored 67.52 clean -- ahead of `patient_farmer` by 6.65 -- and 74.97 with
three typo-fix pull requests added, beating the genuine builder by 5.33 with no
flag raised on either.

Four things changed, all of them in the direction of "who else says so":

1.  A `homepage` string only earns the deployed mark if something answered
    there at collection time. GitHub does not validate that field.
2.  Taxonomy matches on repositories the candidate controls count 0.4 of ones
    corroborated by a third party. Decided by provenance, not by comparing
    owner strings -- the first version compared `repo.owner` to the handle and
    was defeated for free by moving the repositories into an organisation.
3.  `external_validation` counts distinct *owners*, so five repositories
    belonging to one other account are not five independent maintainers.
4.  Finishing marks scale with the repository's own commit count, so metadata
    on an empty repo is decoration rather than evidence of shipping.
"""

from __future__ import annotations

import pytest

from talent_engine.config import load_program
from talent_engine.model import PullRequestActivity, ReviewActivity
from talent_engine.scoring.engine import score_snapshot
from .fixtures.profiles import (
    genuine_builder,
    metadata_maximiser,
    patient_farmer,
    _iso,
)


@pytest.fixture
def cfg():
    """The live programme, not the reference defaults."""
    return load_program("prezenti-sponsorship-trial")


def score(snap, cfg):
    return score_snapshot(snap, cfg)


def _with_trivial_outside_work(snap):
    """Three typo PRs into three real projects, plus three reviews."""
    snap.merged_prs = [
        PullRequestActivity(
            repo=repo, number=900 + i, title="Fix typo in README",
            merged_at=_iso(2026, 3 + i, 11), created_at=_iso(2026, 3 + i, 10),
        )
        for i, repo in enumerate(
            ["celo-org/celo-composer", "modelcontextprotocol/servers", "wevm/viem"]
        )
    ]
    snap.reviews = [
        ReviewActivity(repo=repo, number=800 + i, submitted_at=_iso(2026, 3 + i, 20))
        for i, repo in enumerate(
            ["celo-org/celo-composer", "elizaos/eliza", "wevm/viem"]
        )
    ]
    return snap


def test_the_metadata_attack_no_longer_beats_a_real_builder(cfg):
    """The headline regression. It used to win by 5.33 with no flag."""
    attack = score(_with_trivial_outside_work(metadata_maximiser()), cfg)
    real = score(genuine_builder(), cfg)
    assert real.total > attack.total, (
        f"metadata maximiser {attack.total:.2f} >= genuine builder "
        f"{real.total:.2f} — a countermeasure regressed"
    )


def test_bare_metadata_is_well_behind(cfg):
    """Without any outside validation the attack should not be near the front."""
    attack = score(metadata_maximiser(), cfg)
    real = score(genuine_builder(), cfg)
    assert attack.total < real.total - 5


def test_self_declared_taxonomy_is_discounted(cfg):
    """Topics the candidate wrote must not count like a third party's org."""
    s = score(metadata_maximiser(), cfg)
    for key in ("ecosystem_footprint", "frontier_signal"):
        dim = s.dimension(key)
        assert dim.components["effective"] < dim.components["matches"], (
            f"{key}: self-declared matches counted at full weight"
        )


def test_moving_repos_into_an_org_does_not_restore_full_credit(cfg):
    """The fixture's repos are owned by `agentworks`, not by the handle.

    Provenance decides, not the owner string: everything in `snap.repos` came
    from the candidate's own account listing regardless of who owns it.
    """
    snap = metadata_maximiser()
    assert all(r.owner != snap.handle for r in snap.repos)
    dim = score(snap, cfg).dimension("ecosystem_footprint")
    assert dim.components["effective"] < dim.components["matches"]


def test_an_unreachable_homepage_earns_no_deployed_mark(cfg):
    """`homepage` is unvalidated free text, so it cannot buy a finishing mark."""
    snap = metadata_maximiser()
    assert all(r.homepage and not r.homepage_verified for r in snap.repos)
    text = " ".join(
        e.claim for e in score(snap, cfg).dimension("shipping_agency").evidence
    )
    assert "deployed" not in text


def test_decorated_thin_repos_score_below_real_ones_on_completeness(cfg):
    """Five marks on a 7-commit repo must not equal five on a real project."""
    attack = score(metadata_maximiser(), cfg).dimension("shipping_agency")
    real = score(genuine_builder(), cfg).dimension("shipping_agency")
    assert real.components["completeness"] > attack.components["completeness"]


def test_the_reviewer_is_still_told_what_to_look_at(cfg):
    """Scoring is not the only defence; the sentence has to name the weakness."""
    from talent_engine.scoring.concerns import concerns

    snap = metadata_maximiser()
    line = concerns(score(snap, cfg), cfg, snap).lower()
    assert "thin on commits" in line or "cheapest" in line


def test_patient_farmer_also_lost_ground(cfg):
    """The countermeasures should generalise, not special-case one fixture."""
    assert score(patient_farmer(), cfg).total < 56
