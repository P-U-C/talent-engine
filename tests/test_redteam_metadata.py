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
    quiet_finisher,
    sockpuppet_ring,
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


def test_the_countermeasures_cost_adversaries_far_more_than_real_builders(cfg):
    """The property that actually generalises, asserted as a ratio not a winner.

    Scores before these countermeasures, on the live weights:

        genuine_builder 69.64 · quiet_finisher 49.90
        metadata+PRs    74.97 · metadata only  67.52
        sockpuppet_ring 68.24 · patient_farmer 60.87

    After: the two genuine profiles lose about 1.8 points each, every
    adversarial one loses between 4.8 and 7.7. That asymmetry is the thing to
    protect, and it is what a regression would destroy.

    Deliberately *not* asserted: that the genuine builder outranks the escalated
    attack. It does not, by about half a point, and pretending otherwise would
    be the same false reassurance `concerns.py` exists to refuse. Once the
    attacker adds three genuinely merged pull requests to three real projects
    and three reviews, their measurable public evidence really is comparable to
    this fixture's. No amount of weight tuning separates them, because on the
    axes this rubric can see they are not very different. That is an argument
    for the caveat sentence and for human review, not for a cleverer constant.
    """
    real_loss = [
        69.64 - score(genuine_builder(), cfg).total,
        49.90 - score(quiet_finisher(), cfg).total,
    ]
    adversary_loss = [
        74.97 - score(_with_trivial_outside_work(metadata_maximiser()), cfg).total,
        67.52 - score(metadata_maximiser(), cfg).total,
        68.24 - score(sockpuppet_ring(), cfg).total,
        60.87 - score(patient_farmer(), cfg).total,
    ]
    assert max(real_loss) < 3.0, f"a genuine profile lost too much: {real_loss}"
    assert min(adversary_loss) > 4.0, f"an adversary got off lightly: {adversary_loss}"
    assert min(adversary_loss) > max(real_loss) * 2


def test_bare_metadata_is_well_behind(cfg):
    """Without any outside validation the attack must not be near the front.

    This is the version of the attack that costs nothing at all, and it is the
    one the countermeasures must decisively answer: 67.52 -> 59.79 against a
    genuine builder at 67.75.
    """
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


def test_finishing_marks_on_thin_repos_are_worth_less_than_they_were(cfg):
    """Five marks on a 7-commit repo must not be worth five on a real project.

    Asserted as the asymmetry rather than as an ordering. The attacker still
    posts a higher raw completeness number than this particular genuine fixture
    — it decorates five repositories where the builder has four, and decoration
    is what this component is defined to measure. What changed is the price:
    the attacker's completeness fell 10.24 -> 8.54 while the genuine builder's
    moved 8.32 -> 8.01, because the marks now scale with each repository's own
    activity and half the credit is unconditional so small finished work is not
    punished.
    """
    attack = score(metadata_maximiser(), cfg).dimension("shipping_agency")
    real = score(genuine_builder(), cfg).dimension("shipping_agency")
    attack_loss = 10.24 - attack.components["completeness"]
    real_loss = 8.32 - real.components["completeness"]
    assert attack_loss > 1.0, "decorated thin repos barely lost anything"
    assert attack_loss > real_loss * 3


def test_the_reviewer_is_still_told_what_to_look_at(cfg):
    """Scoring is not the only defence; the sentence has to name the weakness."""
    from talent_engine.scoring.concerns import concerns

    snap = metadata_maximiser()
    line = concerns(score(snap, cfg), cfg, snap).lower()
    assert "thin on commits" in line or "cheapest" in line


def test_patient_farmer_also_lost_ground(cfg):
    """The countermeasures should generalise, not special-case one fixture."""
    assert score(patient_farmer(), cfg).total < 57


# ---------------------------------------------------- the collector's own risk

@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1", "127.1", "2130706433", "0x7f000001", "0177.0.0.1",
        "localhost", "localhost.", "169.254.169.254", "10.0.0.1",
        "192.168.1.1", "::1", "metadata.google.internal", "anything.internal",
    ],
)
def test_the_homepage_check_refuses_non_public_targets(host):
    """Verifying `homepage` means fetching an applicant-controlled URL.

    That turns the collector into an SSRF probe against its own network unless
    every target is checked. The numeric forms matter: `ipaddress.ip_address`
    raises on `127.1`, `2130706433`, `0x7f000001` and `0177.0.0.1` while libc
    resolves all of them to loopback, so a first version that caught
    `ValueError` and assumed "it must be a hostname" let every one through.
    """
    from talent_engine.github.collector import _host_is_public

    assert not _host_is_public(host)


def test_the_homepage_check_still_allows_real_hosts():
    from talent_engine.github.collector import _host_is_public

    assert _host_is_public("example.com")


def test_pr_titles_cannot_launder_taxonomy_credit(cfg):
    """A merged PR's title is written by the applicant, so it is not evidence.

    Titling a typo fix "fix mcp x402 celo docs" would otherwise convert a
    self-chosen keyword into a full-weight third-party corroborated hit.
    """
    from talent_engine.model import PullRequestActivity
    from talent_engine.scoring.dimensions import _taxonomy_hits

    snap = metadata_maximiser()
    snap.repos = []
    snap.merged_prs = [
        PullRequestActivity(
            repo="unrelated-user/unrelated-project",
            number=1,
            title="fix mcp x402 celo agentic docs",
            merged_at=_iso(2026, 5, 1),
            created_at=_iso(2026, 5, 1),
        )
    ]
    hits = _taxonomy_hits(snap, cfg.frontier)
    assert hits, "the title should still match, just not at full weight"
    assert all(w < 1.0 for *_rest, w in hits)
