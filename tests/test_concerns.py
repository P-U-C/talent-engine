"""The caveat sentence that travels with every score.

The property that matters is not the wording, it is that the sentence is never
absent and never reassuring. A reviewer with thirty seconds per candidate reads
the number and the sentence; if the sentence can be empty for the profiles that
most deserve scrutiny, it is worse than nothing.
"""

from __future__ import annotations

import json

import pytest

from talent_engine.config import load_program
from talent_engine.report import dossier, scores_to_json
from talent_engine.scoring.concerns import NOTHING_SPECIFIC, concerns
from talent_engine.scoring.engine import score_snapshot
from tests.fixtures.profiles import (
    gamed_profile,
    genuine_builder,
    insider_low_shipper,
    patient_farmer,
    quiet_finisher,
    sockpuppet_ring,
)

ALL_PROFILES = [
    ("genuine_builder", genuine_builder),
    ("quiet_finisher", quiet_finisher),
    ("insider_low_shipper", insider_low_shipper),
    ("patient_farmer", patient_farmer),
    ("sockpuppet_ring", sockpuppet_ring),
    ("gamed_profile", gamed_profile),
]


@pytest.fixture
def cfg():
    return load_program("prezenti-sponsorship-trial")


@pytest.mark.parametrize("name,factory", ALL_PROFILES)
def test_every_profile_gets_a_non_empty_sentence(name, factory, cfg):
    snap = factory()
    line = concerns(score_snapshot(snap, cfg), cfg, snap)
    assert line and line.endswith(".")
    assert len(line.split()) >= 5, f"{name}: sentence is too thin to be useful"


@pytest.mark.parametrize("name,factory", ALL_PROFILES)
def test_the_sentence_never_reassures(name, factory, cfg):
    """No profile may produce text a reader could take as a clean bill of health.

    The engine cannot support that claim — the red-team fixtures outrank a real
    builder while raising no flag — so it must never imply it.
    """
    snap = factory()
    line = concerns(score_snapshot(snap, cfg), cfg, snap).lower()
    for phrase in ("no concerns", "nothing to note", "looks good", "no issues", "clean"):
        assert phrase not in line, f"{name}: sentence reads as reassurance"


def test_the_manufactured_ring_is_told_where_its_validation_came_from(cfg):
    """The ring raises no flag, so the sentence has to come from composition."""
    snap = sockpuppet_ring()
    line = concerns(score_snapshot(snap, cfg), cfg, snap)
    assert "does not recognise" in line
    assert "independent" in line


def test_a_profile_with_no_outside_validation_is_told_so(cfg):
    snap = patient_farmer()
    line = concerns(score_snapshot(snap, cfg), cfg, snap)
    assert "nobody else" in line


def test_flags_take_precedence_over_composition(cfg):
    """A reviewer can act on a flag; composition is context."""
    snap = gamed_profile()
    line = concerns(score_snapshot(snap, cfg), cfg, snap)
    assert "week" in line  # burst_activity phrasing


def test_the_default_sentence_states_a_limit_not_an_absence():
    assert "shortlist" in NOTHING_SPECIFIC
    assert "patient faking" in NOTHING_SPECIFIC


def test_the_sentence_reaches_the_dossier(cfg):
    snap = genuine_builder()
    text = dossier(score_snapshot(snap, cfg), cfg, snap)
    assert concerns(score_snapshot(snap, cfg), cfg, snap) in text
    # Above the evidence: a reviewer reads top-down and acts on the number.
    assert text.index("Look closer") < text.index("##")


def test_the_sentence_travels_with_the_json_export(cfg):
    """Machine consumers are the most likely to treat a number as a verdict."""
    scores = [score_snapshot(f(), cfg) for _n, f in ALL_PROFILES]
    rows = json.loads(scores_to_json(scores, cfg))
    assert all(row.get("concerns") for row in rows)

    bare = json.loads(scores_to_json(scores))
    assert all("concerns" not in row for row in bare)
