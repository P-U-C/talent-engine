"""Tally intake: parsing, PII quarantine, signature auth, idempotency."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import urllib.error
import urllib.request

import pytest

from talent_engine.config import load_program
from talent_engine.ingest.tally import (
    TallyPayloadError,
    parse_webhook,
    verify_signature,
)
from talent_engine.model import ProfileSnapshot, utc_now_iso
from talent_engine.server.webhook import IntakeService, build_server
from talent_engine.store.db import Store

SECRET = "tally-signing-secret"


def payload(fields, submission_id="sub_1"):
    return {
        "eventId": "evt_1",
        "eventType": "FORM_RESPONSE",
        "createdAt": "2026-08-12T10:00:00.000Z",
        "data": {
            "responseId": "resp_1",
            "submissionId": submission_id,
            "formId": "form_1",
            "formName": "Builder application",
            "createdAt": "2026-08-12T10:00:00.000Z",
            "fields": fields,
        },
    }


def f(label, value, type_="INPUT_TEXT", options=None):
    out = {"key": f"question_{label}", "label": label, "type": type_, "value": value}
    if options is not None:
        out["options"] = options
    return out


# ------------------------------------------------------------------ parsing


def test_parses_handle_from_a_question_not_a_column_name():
    sub = parse_webhook(payload([f("What is your GitHub?", "https://github.com/octocat/")]))
    assert sub.handle == "octocat"
    assert sub.ok


def test_unusable_handle_is_reported_not_guessed():
    sub = parse_webhook(payload([f("GitHub", "i don't have one")]))
    assert sub.handle == ""
    assert sub.raw_handle == "i don't have one"
    assert not sub.ok


def test_checkbox_option_ids_resolve_to_their_text():
    """Unresolved ids would score as unrecognised factors, silently."""
    sub = parse_webhook(
        payload(
            [
                f("GitHub", "octocat"),
                f(
                    "Which factors apply?",
                    ["opt_a", "opt_c"],
                    "CHECKBOXES",
                    options=[
                        {"id": "opt_a", "text": "self-taught"},
                        {"id": "opt_b", "text": "unrelated"},
                        {"id": "opt_c", "text": "no local tech industry"},
                    ],
                ),
            ]
        )
    )
    assert sub.application.context_factors == ["self-taught", "no local tech industry"]


def test_multiple_choice_single_id_resolves():
    sub = parse_webhook(
        payload(
            [
                f("GitHub", "octocat"),
                f(
                    "Referred by",
                    "opt_x",
                    "MULTIPLE_CHOICE",
                    options=[{"id": "opt_x", "text": "Prezenti"}],
                ),
            ]
        )
    )
    assert sub.application.referrer_name == "Prezenti"


def test_rejects_non_form_response_events():
    with pytest.raises(TallyPayloadError):
        parse_webhook({"eventType": "FORM_CREATED", "data": {"fields": []}})
    with pytest.raises(TallyPayloadError):
        parse_webhook({"eventType": "FORM_RESPONSE", "data": {}})


# ------------------------------------------------------- PII does not leak


def test_contact_details_are_separated_from_the_application():
    sub = parse_webhook(
        payload(
            [
                f("GitHub", "octocat"),
                f("Email", "someone@example.com", "INPUT_EMAIL"),
                f("Name", "A Person"),
                f("Telegram", "@someone"),
                f("What are you building?", "a thing"),
            ]
        )
    )
    assert sub.contact.email == "someone@example.com"
    assert sub.contact.name == "A Person"

    blob = json.dumps(sub.application.__dict__)
    assert "someone@example.com" not in blob
    assert "A Person" not in blob
    assert "@someone" not in blob


def test_email_in_an_oddly_labelled_field_still_does_not_reach_the_application():
    """The label filter alone is not enough; the value shape is checked too."""
    sub = parse_webhook(
        payload(
            [
                f("GitHub", "octocat"),
                f("How do we reach you?", "someone@example.com"),
            ]
        )
    )
    assert "someone@example.com" not in json.dumps(sub.application.extra)
    assert sub.contact.email == "someone@example.com"


def test_email_typed_field_is_caught_even_with_no_matching_label():
    sub = parse_webhook(
        payload([f("GitHub", "octocat"), f("Contact", "x@y.dev", "INPUT_EMAIL")])
    )
    assert sub.contact.email == "x@y.dev"
    assert "x@y.dev" not in json.dumps(sub.application.extra)


def test_an_email_field_is_never_mistaken_for_the_github_handle():
    """`normalize_handle` accepts bare words, so an email field must be skipped."""
    sub = parse_webhook(
        payload(
            [
                f("Your email", "octopus@example.com", "INPUT_EMAIL"),
                f("GitHub username", "octocat"),
            ]
        )
    )
    assert sub.handle == "octocat"


def test_contact_reaches_the_contacts_table_and_nothing_else(tmp_path):
    store = Store(tmp_path / "t.db")
    sub = parse_webhook(
        payload([f("GitHub", "octocat"), f("Email", "a@b.com", "INPUT_EMAIL")])
    )
    store.record_submission(
        sub.submission_id, "celo-trial", "tally", sub.handle, sub.raw_handle,
        sub.application, sub.form_id,
    )
    store.record_contact(sub.submission_id, sub.contact)

    row = store.get_submission(sub.submission_id)
    assert "a@b.com" not in json.dumps(row)
    assert store.contact_for(sub.submission_id)["email"] == "a@b.com"
    store.close()


# ------------------------------------------------------------- signatures


def sign(body: bytes, secret: str = SECRET) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def test_signature_roundtrip_and_rejections():
    body = b'{"a":1}'
    assert verify_signature(body, sign(body), SECRET)
    assert not verify_signature(body, sign(body, "wrong-secret"), SECRET)
    assert not verify_signature(body + b" ", sign(body), SECRET)
    assert not verify_signature(body, None, SECRET)
    assert not verify_signature(body, sign(body), "")  # no configured secret == no trust


def test_server_refuses_to_start_without_a_secret(tmp_path):
    cfg = load_program("celo-trial")
    service = IntakeService(cfg, str(tmp_path / "t.db"), collector_factory=lambda: None)
    with pytest.raises(ValueError, match="signing secret"):
        build_server(service, secret="", port=0)


# ------------------------------------------------------------- end to end


class FakeCollector:
    """Stands in for the GitHub-touching collector. Records what it was asked."""

    def __init__(self):
        self.collected = []

    def collect(self, handle, application):
        self.collected.append(handle)
        now = utc_now_iso()
        return ProfileSnapshot(
            handle=handle,
            account_created_at="2020-01-01T00:00:00Z",
            collected_at=now,
            window_start="2026-02-12T00:00:00Z",
            window_end=now,
            application=application,
        )


@pytest.fixture
def live(tmp_path):
    cfg = load_program("celo-trial")
    collector = FakeCollector()
    service = IntakeService(cfg, str(tmp_path / "t.db"), collector_factory=lambda: collector)
    httpd = build_server(service, SECRET, host="127.0.0.1", port=0)
    service.start()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield url, service, collector
    finally:
        httpd.shutdown()
        service.stop()
        thread.join(timeout=5)


def post(url, body: bytes, signature: str | None):
    req = urllib.request.Request(url + "/webhook/tally", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if signature is not None:
        req.add_header("tally-signature", signature)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_signed_submission_is_accepted_and_scored(live):
    url, service, collector = live
    body = json.dumps(
        payload([f("GitHub", "octocat"), f("Email", "a@b.com", "INPUT_EMAIL")])
    ).encode()

    status, text = post(url, body, sign(body))
    assert status == 202
    assert text.strip() == "queued"

    service.stop(drain=True)
    assert collector.collected == ["octocat"]

    store = Store(service.db_path)
    row = store.get_submission("sub_1")
    assert row["status"] == "scored"
    assert row["total"] is not None
    store.close()


def test_unsigned_submission_is_rejected_and_never_reaches_the_store(live):
    url, service, collector = live
    body = json.dumps(payload([f("GitHub", "octocat")])).encode()

    assert post(url, body, None)[0] == 401
    assert post(url, body, "not-a-signature")[0] == 401
    assert post(url, body, sign(body, "attacker-secret"))[0] == 401

    assert collector.collected == []
    store = Store(service.db_path)
    assert store.get_submission("sub_1") is None
    store.close()


def test_redelivery_does_not_score_twice(live):
    """Form platforms retry. A retry must not double-spend the API budget."""
    url, service, collector = live
    body = json.dumps(payload([f("GitHub", "octocat")])).encode()
    sig = sign(body)

    assert post(url, body, sig)[1].strip() == "queued"
    assert post(url, body, sig)[1].strip() == "duplicate"
    assert post(url, body, sig)[1].strip() == "duplicate"

    service.stop(drain=True)
    assert collector.collected == ["octocat"]


def test_unparsable_handle_is_stored_for_review_not_dropped(live):
    url, service, collector = live
    body = json.dumps(payload([f("GitHub", "no idea")])).encode()

    status, text = post(url, body, sign(body))
    assert status == 202  # not an error: retrying will never help
    assert text.strip() == "unparsable"

    service.stop(drain=True)
    assert collector.collected == []
    store = Store(service.db_path)
    row = store.get_submission("sub_1")
    assert row["status"] == "unparsable"
    assert "no idea" in row["error"]
    store.close()


def test_garbage_bodies_are_rejected_by_shape(live):
    url, _service, _collector = live
    bad = b"not json at all"
    assert post(url, bad, sign(bad))[0] == 400

    wrong = json.dumps({"eventType": "FORM_CREATED", "data": {}}).encode()
    assert post(url, wrong, sign(wrong))[0] == 422


def test_oversized_body_is_refused(live):
    url, _service, _collector = live
    huge = b"x" * (1 << 21)
    assert post(url, huge, sign(huge))[0] == 413


def test_health_endpoint(live):
    url, _service, _collector = live
    with urllib.request.urlopen(url + "/healthz", timeout=5) as resp:
        assert resp.status == 200


def test_a_crash_mid_scoring_leaves_the_submission_recoverable(tmp_path):
    """Durability is in SQLite, not the queue: `serve` requeues on restart."""
    cfg = load_program("celo-trial")

    class Exploding:
        def collect(self, handle, application):
            raise RuntimeError("github fell over")

    service = IntakeService(cfg, str(tmp_path / "t.db"), collector_factory=lambda: Exploding())
    service.start()
    sub = parse_webhook(payload([f("GitHub", "octocat")]))
    service.accept(sub)
    service.stop(drain=True)

    store = Store(service.db_path)
    row = store.get_submission("sub_1")
    assert row["status"] == "error"
    assert "github fell over" in row["error"]
    store.close()
