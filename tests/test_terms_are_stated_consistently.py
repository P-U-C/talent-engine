"""One fact, stated in many places, must be stated the same way everywhere.

The give-back structure lived in the policy JSON, the terms document, the trial
document, the application README and the pledge app. It was corrected in one
place at a time, as each external reviewer pointed at whichever copy they had
read — so a version saying "1% to Prezenti and 1% to the Celo Community Fund"
survived three review rounds in a document nobody had happened to open, while
`terms_digest()` fingerprinted a policy that still agreed with it.

Grepping for what you have been told about only ever fixes the copy you were
shown. These tests assert the fact itself, everywhere it is written down.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from talent_engine.programs.policy import load_overlay

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERLAY = load_overlay("prezenti-sponsorship-trial")

# Every published surface that states the give-back in prose.
PROSE = [
    ROOT / "docs" / "SPONSORSHIP_TERMS.md",
    ROOT / "docs" / "terms" / "prezenti-sponsorship-trial-2026-08-14-v3.md",
    ROOT / "docs" / "PREZENTI_SPONSORSHIP_TRIAL.md",
    ROOT / "RUBRIC.md",
    ROOT / "README.md",
]

# Claims that describe the *current* deal as a split obligation. Historical
# notes ("used to be written as…", "Was: …") are how the correction is
# explained and must stay readable, so they are excluded by their framing.
SPLIT_CLAIMS = (
    re.compile(r"1%\s*/\s*1%"),
    re.compile(r"1% of revenue\s+actually received will be routed"),
    re.compile(r"routed to Prezenti and 1% to the Celo"),
)
HISTORICAL = ("used to be", "Was:", "previously", "no longer", "old model")


def _lines(path: pathlib.Path):
    if not path.exists():
        return []
    return path.read_text().splitlines()


def _context(lines, i, span=2):
    return " ".join(lines[max(0, i - span) : i + span + 1])


@pytest.mark.parametrize("path", PROSE, ids=lambda p: p.name)
def test_no_document_still_describes_a_split_obligation(path):
    lines = _lines(path)
    for i, line in enumerate(lines):
        for pattern in SPLIT_CLAIMS:
            if pattern.search(line):
                ctx = _context(lines, i)
                assert any(h in ctx for h in HISTORICAL), (
                    f"{path.name}:{i + 1} still states the give-back as a split "
                    f"obligation, and not as history:\n  {line.strip()}"
                )


@pytest.mark.parametrize("path", PROSE, ids=lambda p: p.name)
def test_current_surfaces_do_not_send_builders_to_a_splits_collector(path):
    text = "\n".join(_lines(path))
    assert "app.splits.org" not in text
    assert "public Splits contract" not in text
    assert "split is created" not in text


def test_the_policy_names_exactly_one_counterparty():
    recipients = OVERLAY.giveback.get("recipients", [])
    assert len(recipients) == 1, (
        "the builder cannot owe a party they have no agreement with; "
        "Prezenti's onward promise belongs in prezenti_onward_commitment"
    )
    assert recipients[0]["bps"] == OVERLAY.giveback["total_bps"]


def test_the_onward_commitment_is_recorded_but_is_not_an_obligation():
    onward = OVERLAY.giveback.get("prezenti_onward_commitment") or {}
    assert onward, "Prezenti's onward promise must still be published"
    assert "bps" not in onward
    assert "bps_of_receipts" not in onward, (
        "one hundred basis points is 1% of covered income, not 1% of "
        "Prezenti's receipts"
    )
    assert onward["bps_of_covered_income"] * 2 == OVERLAY.giveback["total_bps"]


@pytest.mark.parametrize("path", PROSE, ids=lambda p: p.name)
def test_every_stated_headline_percentage_matches_the_policy(path):
    """A document may omit the figure, but it may not contradict it."""
    expected = f"{OVERLAY.giveback['total_bps'] / 100:.0f}%"
    text = "\n".join(_lines(path))
    for match in re.finditer(r"good-faith pledge of \*\*(\d+%)", text):
        assert match.group(1) == expected, (
            f"{path.name} advertises {match.group(1)}, policy says {expected}"
        )


def test_the_terms_summary_names_who_is_owed():
    """"2%" with no counterparty is the ambiguity that let the copies drift."""
    joined = " ".join(OVERLAY.terms_summary()).lower()
    assert "owed to" in joined
    assert "nobody else" in joined
    assert "half of what it receives" in joined
    assert "1% of covered income" in joined
    assert "direct to the verified prezenti safe" in joined
    assert "public celo eas pledge" in joined


def test_the_form_marker_is_derived_from_the_terms_release():
    spec = json.loads((ROOT / "forms" / "sponsorship-application.json").read_text())
    terms = [q for q in spec["questions"] if q.get("maps_to") == "application.accepted_terms"]
    assert len(terms) == 1
    option = terms[0]["options"][0]
    assert "[terms-version: {terms_digest}]" in option
    assert OVERLAY.covered_income_text() in option
    assert "Claude Max 20x, ChatGPT Pro 5x" in option
    assert "paid directly to the verified Prezenti Safe" in option
    assert "monthly receipts" in option
    assert "monthly public updates" in option
    assert "30 days inactive" in option
    assert "7-day cure period" in option
    assert "month-two Celo deployment" in option
    assert "public Celo EAS pledge" in option


def test_the_generated_landing_page_links_the_canonical_terms_release():
    from talent_engine.server.pages import landing_page

    page = landing_page("P", "formid", None, OVERLAY).decode()
    assert OVERLAY.terms_uri in page
    assert f"terms-version: {OVERLAY.terms_digest()}" in page
    assert "ChatGPT Pro 5x" in page
    assert "half of what it receives" in page
    assert "1% of covered income" in page
    assert "direct to the verified Prezenti Safe" in page
    assert "monthly receipts" in page
    assert "monthly public updates" in page
    assert "30 days inactive" in page
    assert "7-day cure period" in page
    assert "month-two Celo deployment" in page
    assert "public Celo EAS pledge" in page


def test_the_acceptance_letter_links_the_same_terms_release():
    from talent_engine.modes.acceptance import acceptance_letter

    letter = acceptance_letter("amara", OVERLAY)
    assert OVERLAY.terms_uri in letter
    assert OVERLAY.terms_digest() in letter
    assert OVERLAY.covered_income_text() in letter
    assert "owed to Prezenti and to nobody else" in letter
    assert "Monthly receipts" in letter
    assert "One monthly public update" in letter
    assert "30 days without" in letter
    assert "7 days to provide evidence" in letter
    assert "months three and four requires" in letter
    assert "No 0xSplits collector" in letter
    assert "GitHub handle" in letter


def test_public_backing_copy_uses_the_separate_consent_rule():
    from talent_engine.modes.acceptance import acceptance_letter

    letter = acceptance_letter("amara", OVERLAY)
    current = "\n".join(p.read_text() for p in PROSE if p.exists()) + "\n" + letter
    assert "with the evidence" not in current
    assert "separate consent" in current


def test_no_current_surface_adds_a_token_or_other_structure_obligation():
    current = "\n".join(p.read_text() for p in PROSE if p.exists())
    assert "creates value through another structure" not in current
    assert "same 2% commitment" not in current


def test_months_funded_is_not_selected_at_acceptance_anywhere_here():
    for path in PROSE + [ROOT / "forms" / "sponsorship-application.json"]:
        assert "monthsFundedAtSigning" not in path.read_text()
        assert "Months funded at signing" not in path.read_text()


def test_fresh_clone_docs_do_not_advertise_a_missing_console_script():
    paths = [ROOT / "README.md"]
    engine_doc = ROOT / "docs" / "ENGINE.md"
    if engine_doc.exists():
        paths.append(engine_doc)
    texts = [p.read_text() for p in paths]
    for text in texts:
        assert not re.search(r"(?m)^talent-engine\s+", text)
    joined = "\n".join(texts)
    assert "python3 -m compileall -q talent_engine tests" in joined
    assert "python3 -m pip install pytest" in joined
    assert "python3 -m talent_engine.cli score" in joined
    assert "python3 -m talent_engine.cli serve" in joined
