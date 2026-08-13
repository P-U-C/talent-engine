"""RUBRIC.md must not drift from the configs it claims to describe.

The published rubric is the product's central promise: read this page, read the
scorer, reproduce your own number. That promise failed silently once. RUBRIC.md
documented `celo-trial`'s weights (25/15/12/8/10/10/10/10) while the programme
the README actually points applicants to scored on 40/20/10/5/10/15/0/0 --
zeroing `context_statement` and `trusted_referral` entirely, so the rubric's
headline "80 measured + 20 from what you tell us" was false for every live
applicant, and reproducing your own score from the published page gave an
answer wrong by up to fifteen points.

Nothing caught it because nothing compared the prose to the configs. These
tests do.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from talent_engine.config import REFERENCE_WEIGHTS, load_program

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUBRIC = (ROOT / "RUBRIC.md").read_text()
RENDER = ROOT / "tools" / "render_rubric_weights.py"
PROGRAMS = sorted(p.stem for p in (ROOT / "programs").glob("*.json"))


def test_the_generated_weights_block_is_current():
    """The committed table must equal what the configs render right now."""
    result = subprocess.run(
        [sys.executable, str(RENDER), "--check"], capture_output=True, text=True
    )
    assert result.returncode == 0, (
        "RUBRIC.md weights table is stale — a program config changed without "
        "regenerating the rubric. Run tools/render_rubric_weights.py --write.\n"
        f"{result.stdout}{result.stderr}"
    )


@pytest.mark.parametrize("key", PROGRAMS)
def test_every_program_appears_in_the_rubric(key):
    """A programme that scores people must be documented on the page they read."""
    assert f"`{key}`" in RUBRIC, (
        f"program {key!r} scores applicants but does not appear in RUBRIC.md"
    )


@pytest.mark.parametrize("key", PROGRAMS)
def test_the_rubric_states_each_live_weight(key):
    """Every non-zero live weight must be findable in the generated table row."""
    cfg = load_program(key)
    table = RUBRIC[RUBRIC.index("| dimension |") : RUBRIC.index("| **total** |")]
    for dim, weight in cfg.weights.items():
        row = next((l for l in table.splitlines() if l.startswith(f"| `{dim}` |")), None)
        assert row is not None, f"{dim} missing from the rubric table"
        cells = [c.strip() for c in row.strip("|").split("|")]
        # cells[0] is the dimension name; program columns follow in sorted order
        got = cells[1 + PROGRAMS.index(key)]
        want = "0" if not weight else f"{weight:g}"
        assert got == want, (
            f"{key}.{dim}: rubric says {got}, config says {want}"
        )


def test_the_rubric_does_not_claim_a_fixed_split():
    """The old headline asserted 80/20 for everyone. It was false for the live program."""
    assert "80 measured from public activity" not in RUBRIC
    assert "set per programme" in RUBRIC


def test_every_reference_dimension_is_documented():
    for dim in REFERENCE_WEIGHTS:
        assert f"`{dim}`" in RUBRIC, f"{dim} is scoreable but undocumented"
