"""The form spec and the webhook parser must agree.

Question labels are the wire format between Tally and this codebase: the parser
identifies fields by matching words in the label, so a reworded question stops
a field being read and nothing anywhere raises. In production that looks like
applicants whose declared repo is quietly empty.

These tests build a synthetic webhook payload from the spec and assert every
declared mapping resolves. Renaming a question in `forms/*.json` without
updating the alias tables fails here rather than in the field.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from talent_engine.ingest.tally import parse_webhook

SPEC_PATH = Path(__file__).resolve().parent.parent / "forms" / "sponsorship-application.json"


@pytest.fixture(scope="module")
def spec():
    return json.loads(SPEC_PATH.read_text())


SAMPLE = {
    "contact.name": "Amara O.",
    "contact.email": "amara@example.com",
    "contact.telegram": "@amarabuilds",
    "contact.x": "@amara_eth",
    "handle": "https://github.com/amara-dev",
    "application.declared_repo": "amara-dev/minipay-savings-circle",
    "application.build_plan": "A savings circle mini app for MiniPay.",
    "application.context_statement": "Self-funded, building from Nairobi.",
    "application.extra": "Deploying the contracts on Celo mainnet.",
}


def build_payload(spec) -> dict:
    """Turn the spec into the webhook Tally would send for a filled-in form."""
    fields = []
    for i, q in enumerate(spec["questions"]):
        target = q["maps_to"]
        if q["type"] == "CHECKBOX":
            options = [
                {"id": f"opt_{i}_{j}", "text": text}
                for j, text in enumerate(q.get("options", []))
            ]
            field = {
                "key": f"question_{i}",
                "label": q["label"],
                "type": "CHECKBOX",
                "value": [options[0]["id"], options[1]["id"]],
                "options": options,
            }
        else:
            field = {
                "key": f"question_{i}",
                "label": q["label"],
                "type": q["type"],
                "value": SAMPLE.get(target, f"answer for {q['label']}"),
            }
        fields.append(field)
    return {
        "eventType": "FORM_RESPONSE",
        "data": {
            "submissionId": "spec_1",
            "formId": "form_spec",
            "createdAt": "2026-08-12T20:00:00Z",
            "fields": fields,
        },
    }


def test_every_declared_mapping_actually_resolves(spec):
    sub = parse_webhook(build_payload(spec))
    app, contact = sub.application, sub.contact

    resolved = {
        "handle": sub.handle,
        "contact.name": contact.name,
        "contact.email": contact.email,
        "contact.telegram": contact.telegram,
        "contact.x": contact.x,
        "application.declared_repo": app.declared_repo,
        "application.build_plan": app.build_plan,
        "application.context_statement": app.context_statement,
        "application.referrer_name": app.referrer_name,
        "application.context_factors": app.context_factors,
    }

    for q in spec["questions"]:
        target = q["maps_to"]
        if target == "application.extra":
            assert q["label"] in app.extra, f"{q['label']!r} did not reach extra"
            continue
        assert resolved.get(target), (
            f"{q['label']!r} claims to map to {target}, but the parser resolved "
            f"nothing. Either the label lost the word the alias table matches on, "
            f"or the alias table needs the new wording."
        )


def test_the_github_handle_wins_over_the_telegram_handle(spec):
    """'Telegram handle' matches HANDLE_KEYS on 'handle'.

    In the spec it is asked *before* the GitHub question, which is exactly the
    ordering that used to produce a Telegram name as the GitHub login.
    """
    labels = [q["label"] for q in spec["questions"]]
    assert labels.index("Telegram handle") < labels.index("GitHub username")

    sub = parse_webhook(build_payload(spec))
    assert sub.handle == "amara-dev"
    assert sub.contact.telegram == "@amarabuilds"


def test_checkbox_factors_arrive_as_text_not_option_ids(spec):
    sub = parse_webhook(build_payload(spec))
    assert sub.application.context_factors
    assert not any(f.startswith("opt_") for f in sub.application.context_factors)


def test_no_contact_value_reaches_the_application(spec):
    sub = parse_webhook(build_payload(spec))
    blob = json.dumps(sub.application.__dict__)
    for value in (
        SAMPLE["contact.email"],
        SAMPLE["contact.name"],
        SAMPLE["contact.telegram"],
        SAMPLE["contact.x"],
    ):
        assert value not in blob, f"{value!r} leaked into the application record"


def test_required_questions_cover_what_selection_needs(spec):
    """The overlay refuses to run without a build plan; the form must ask for one."""
    required = {q["maps_to"] for q in spec["questions"] if q.get("required")}
    assert "handle" in required
    assert "application.build_plan" in required
    assert "application.declared_repo" in required


def test_every_question_documents_why_it_is_asked(spec):
    """A form that collects something nobody can justify is how scope creeps."""
    for q in spec["questions"]:
        assert q.get("why"), f"{q['label']!r} has no stated purpose"
