"""Tally form webhooks -> Application, with contact details kept separate.

Two things here are load-bearing and easy to get wrong:

**Option ids.** Tally sends CHECKBOXES and MULTIPLE_CHOICE values as option
*ids*, not their text, with the mapping in a sibling `options` list. Reading
`value` directly gives you a list of UUIDs, and since `context_factors` feeds a
scored dimension, unresolved ids would silently score as unrecognised factors.
Every value is resolved through `options` before it is used.

**Contact details never enter the Application.** The CSV path puts the whole
row into `Application.extra`, which is fine for an export the operator already
holds but wrong for a public form: `Application` is embedded in
`ProfileSnapshot`, snapshots are persisted and rendered into evidence dossiers,
and dossiers are the artefact you hand to third parties. So the parser returns
contact fields as a separate `Contact` record, and anything that looks like
contact information is stripped from `extra` rather than being trusted to stay
unread. Invariant 5 is "public data only" — an email address is not public
data, and it has no business inside the scoring record.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Any

from ..model import Application
from .normalize import (
    CONTEXT_KEYS,
    FACTOR_KEYS,
    HANDLE_KEYS,
    PLAN_KEYS,
    REGION_KEYS,
    REFERRER_KEYS,
    REPO_KEYS,
    normalize_handle,
)

EMAIL_KEYS = ("email", "e-mail", "email address", "contact email")
NAME_KEYS = ("name", "full name", "your name", "first name")
TELEGRAM_KEYS = ("telegram", "telegram handle", "tg")
X_KEYS = ("x", "twitter", "x handle", "twitter handle", "x / twitter")
DISCORD_KEYS = ("discord", "discord handle")
CONTACT_KEYS = EMAIL_KEYS + NAME_KEYS + TELEGRAM_KEYS + X_KEYS + DISCORD_KEYS

# The affirmative acceptance of the programme terms. Ordered most specific
# first, because "agree" and "terms" are words that appear in other questions.
TERMS_KEYS = (
    "accept the sponsorship terms",
    "accept the terms",
    "agree to the terms",
    "terms",
)

# The acceptance option carries the digest of the terms it was written
# against, as "[terms-version: <hex>]". Tally exposes no API for hidden fields,
# and a ticked checkbox is submitted as its own option text — so this is the
# one channel that transmits what the applicant actually saw. Stamping the
# server's current digest when the webhook arrived recorded acceptance of
# words a stale form, cached embed or queued retry never showed them.
TERMS_VERSION_RE = re.compile(r"\[terms-version:\s*([0-9a-f]{6,64})\]", re.I)

# A hidden field, if a deployment adds one by hand in the Tally builder.
# Checked before TERMS_KEYS, because "terms version" also contains "terms".
TERMS_VERSION_KEYS = ("terms version", "terms_version", "termsversion")

# Field types Tally uses for contact information, regardless of the label the
# form author typed.
CONTACT_TYPES = {"INPUT_EMAIL", "INPUT_PHONE_NUMBER"}

_EMAILISH = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")

# Contact shapes that survive inside free text. A label denylist cannot win
# here: the leak is not a mis-labelled contact field, it is someone typing
# "reach me on Telegram @x, cell +1-415-555-0199" into "anything else you want
# us to know". Dropping the whole answer would lose the substance a reviewer is
# meant to read, so each shape is redacted in place and only an answer that
# becomes empty is dropped.
_CONTACT_SHAPES: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("[email redacted]", _EMAILISH),
    # discord.gg/…, t.me/…, wa.me/…, signal.me/…, and bare handles on those.
    (
        "[link redacted]",
        re.compile(
            r"\b(?:https?://)?(?:www\.)?"
            r"(?:t\.me|telegram\.me|wa\.me|discord\.gg|signal\.me|m\.me)/\S+",
            re.I,
        ),
    ),
    # Discord's legacy name#1234 form.
    ("[handle redacted]", re.compile(r"\b[\w.]{2,32}#\d{4}\b")),
    # Telegram/X/Discord style @handle. Deliberately broad: losing an
    # occasional "@someorg" from an operator's reading copy is a far smaller
    # harm than publishing a way to contact the applicant off-platform.
    ("[handle redacted]", re.compile(r"(?<![\w/])@[A-Za-z0-9_]{3,32}\b")),
    # Phone numbers: optional +country, then 7+ digits with common separators.
    # Boundaries are digit-based, not word-based: `(?![\w.])` treated a
    # sentence-ending full stop as part of the number and backtracked, leaving
    # the last group of "+1-415-555-0199." unredacted.
    (
        "[phone redacted]",
        re.compile(r"(?<![\w.])\+?\d[\d\s().-]{6,}\d(?!\d)"),
    ),
)


def redact_contacts(text: str) -> str:
    """Strip contact shapes from free text, preserving everything else."""
    out = text
    for replacement, pattern in _CONTACT_SHAPES:
        out = pattern.sub(replacement, out)
    return re.sub(r"\s{2,}", " ", out).strip()


class TallyPayloadError(ValueError):
    """The body is not a Tally form-response webhook we can read."""


@dataclass
class Contact:
    """Personally identifying data. Stored apart from anything scoreable.

    Never embedded in `Application`, `ProfileSnapshot`, or a dossier.
    """

    email: str = ""
    name: str = ""
    telegram: str = ""
    x: str = ""
    discord: str = ""

    def is_empty(self) -> bool:
        return not any((self.email, self.name, self.telegram, self.x, self.discord))


@dataclass
class Submission:
    """One parsed form response."""

    submission_id: str
    form_id: str
    submitted_at: str
    handle: str  # "" when the response had no usable GitHub identity
    raw_handle: str
    application: Application = field(default_factory=Application)
    contact: Contact = field(default_factory=Contact)

    @property
    def ok(self) -> bool:
        return bool(self.handle)


def verify_signature(raw_body: bytes, header_value: str | None, secret: str) -> bool:
    """Constant-time check of Tally's `tally-signature` header.

    The signature is base64(HMAC-SHA256(raw request body, signing secret)), so
    it must be computed over the exact bytes received — re-serialising the JSON
    first will not match.
    """
    if not secret or not header_value:
        return False
    expected = base64.b64encode(
        hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, header_value.strip())


def _resolve(field_obj: dict[str, Any]) -> Any:
    """Return a field's value with option ids replaced by their text."""
    value = field_obj.get("value")
    options = field_obj.get("options") or []
    if not options:
        return value

    by_id = {o.get("id"): (o.get("text") or "") for o in options if isinstance(o, dict)}
    if isinstance(value, list):
        return [by_id.get(v, v) for v in value]
    if isinstance(value, str) and value in by_id:
        return by_id[value]
    return value


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else ""
    if isinstance(value, list):
        return ", ".join(_flatten(v) for v in value if v not in (None, ""))
    return str(value).strip()


def _norm_label(text: str) -> str:
    """Lowercase, and treat _ - and whitespace as the same separator.

    The alias tables are written in column-name style (`referred_by`) because
    they are shared with the CSV path, but form authors write questions
    ("Referred by?"). Without this the two spellings do not match and the
    field is silently dropped — which for `referrer_name` means silently not
    awarding a verified referral.
    """
    return re.sub(r"[\s_\-]+", " ", text.strip().lower())


def _match(label: str, keys: tuple[str, ...]) -> bool:
    """Label match: exact alias, or an alias as a whole phrase inside the label.

    Whole-word matching is what keeps a question about someone's favourite
    GitHub repo from being read as the handle field. It is not airtight, so
    the first match in field order wins and the alias tables are ordered
    most-specific-first.
    """
    lowered = _norm_label(label)
    normalised = [_norm_label(k) for k in keys]
    if lowered in normalised:
        return True
    return any(re.search(rf"\b{re.escape(k)}\b", lowered) for k in normalised)


def parse_webhook(payload: dict[str, Any]) -> Submission:
    """Parse a Tally FORM_RESPONSE payload.

    Raises TallyPayloadError for anything that is not a readable form response,
    so a misconfigured webhook fails loudly instead of recording empty
    applications.
    """
    if not isinstance(payload, dict):
        raise TallyPayloadError("payload is not an object")

    event_type = payload.get("eventType")
    if event_type and event_type != "FORM_RESPONSE":
        raise TallyPayloadError(f"unsupported eventType {event_type!r}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise TallyPayloadError("payload has no data object")

    fields = data.get("fields")
    if not isinstance(fields, list):
        raise TallyPayloadError("payload has no fields list")

    # label -> flattened value, first non-empty wins
    values: list[tuple[str, str, Any]] = []  # (label, type, resolved value)
    for f in fields:
        if not isinstance(f, dict):
            continue
        label = str(f.get("label") or f.get("key") or "")
        values.append((label, str(f.get("type") or ""), _resolve(f)))

    def pick(
        keys: tuple[str, ...],
        *,
        exclude_contact: bool = False,
        exclude: tuple[str, ...] = (),
    ) -> str:
        for label, ftype, value in values:
            # "Telegram handle" matches HANDLE_KEYS on the word "handle", and a
            # form that asks for it before the GitHub question would otherwise
            # score the applicant's Telegram name as their GitHub login. Field
            # order must not decide this, so contact fields are skipped by
            # label as well as by type.
            if exclude_contact and (ftype in CONTACT_TYPES or _match(label, CONTACT_KEYS)):
                continue
            # "Terms version" contains "terms", so the acceptance checkbox
            # would otherwise read the digest as its own value.
            if exclude and _match(label, exclude):
                continue
            flat = _flatten(value)
            if flat and _match(label, keys):
                return flat
        return ""

    def pick_list(keys: tuple[str, ...]) -> list[str]:
        for label, _ftype, value in values:
            if _match(label, keys):
                if isinstance(value, list):
                    return [_flatten(v) for v in value if _flatten(v)]
                flat = _flatten(value)
                if flat:
                    return [p.strip() for p in re.split(r"[;,|]", flat) if p.strip()]
        return []

    raw_handle = pick(HANDLE_KEYS, exclude_contact=True)
    handle = normalize_handle(raw_handle) or ""

    contact = Contact(
        email=pick(EMAIL_KEYS) or _first_email(values),
        name=pick(NAME_KEYS),
        telegram=pick(TELEGRAM_KEYS),
        x=pick(X_KEYS),
        discord=pick(DISCORD_KEYS),
    )

    # A ticked checkbox arrives as the option text, an unticked one as empty.
    # Anything other than a positive value is treated as NOT accepted: silence
    # must never be read as agreement.
    terms_raw = pick(TERMS_KEYS, exclude=TERMS_VERSION_KEYS)
    accepted = bool(terms_raw) and terms_raw.strip().lower() not in ("no", "false", "0")

    # The digest of the terms the form was rendered with. Submitted by the
    # applicant, never supplied by the server: stamping the server's current
    # digest at webhook time recorded acceptance of words a stale form never
    # showed them.
    application = Application(
        accepted_terms=accepted,
        accepted_terms_version=_terms_version(terms_raw, pick(TERMS_VERSION_KEYS)),
        context_statement=pick(CONTEXT_KEYS),
        context_factors=pick_list(FACTOR_KEYS),
        referrer_name=pick(REFERRER_KEYS),
        declared_repo=pick(REPO_KEYS),
        build_plan=pick(PLAN_KEYS),
        region=pick(REGION_KEYS),
        extra=_safe_extra(values),
    )

    return Submission(
        submission_id=str(data.get("submissionId") or data.get("responseId") or ""),
        form_id=str(data.get("formId") or ""),
        submitted_at=str(data.get("createdAt") or payload.get("createdAt") or ""),
        handle=handle,
        raw_handle=raw_handle,
        application=application,
        contact=contact,
    )


def _first_email(values: list[tuple[str, str, Any]]) -> str:
    """Find an address when neither the label nor the field type declared one.

    Type first, then value shape. The shape pass matters because `_safe_extra`
    strips address-like values from `extra` regardless of how the field was
    labelled — without this the address would be dropped entirely rather than
    filed as contact information, and the applicant would be unreachable.
    """
    for _label, ftype, value in values:
        if ftype == "INPUT_EMAIL":
            flat = _flatten(value)
            if flat:
                return flat
    for _label, _ftype, value in values:
        flat = _flatten(value)
        match = _EMAILISH.search(flat)
        if match and flat == match.group(0):
            return flat
    return ""


def _terms_version(accepted_text: str, hidden_field: str) -> str:
    """The terms digest the applicant submitted, or empty if unknown.

    Empty is a meaningful answer: the acceptance gate treats an unknown version
    as not-current and fails closed, which is the correct reading of "we do not
    know which words they agreed to".
    """
    match = TERMS_VERSION_RE.search(accepted_text or "")
    if match:
        return match.group(1).lower()
    return (hidden_field or "").strip()


def _safe_extra(values: list[tuple[str, str, Any]]) -> dict[str, Any]:
    """Everything else the form asked, minus anything identifying.

    Four filters, because any one of them alone leaks: the declared contact
    labels, Tally's contact field *types* (a form author can label an email
    field "how do we reach you"), a value-shape check for address-like strings
    that slipped through both, and finally redaction *within* free text.

    That last one is the case the first three cannot reach. An answer to
    "anything else you want us to know" reading "reach me on Telegram
    @mallory_p or Discord mallory#4021, cell +1-415-555-0199" has a
    non-contact label, a non-contact type, and no email in it, and so used to
    land intact in `Application.extra` -- which travels into the snapshot and
    the dossier that README.md promises never carries contact data. Dropping
    the whole answer would throw away the substance the reviewer is meant to
    read, so the contact shapes are removed and the rest survives.
    """
    extra: dict[str, Any] = {}
    for label, ftype, value in values:
        flat = _flatten(value)
        if not flat:
            continue
        if ftype in CONTACT_TYPES or _match(label, CONTACT_KEYS):
            continue
        if _EMAILISH.search(flat) and _EMAILISH.sub("", flat).strip() == "":
            continue  # the whole answer was an address
        cleaned = redact_contacts(flat)
        if not cleaned:
            continue
        extra[label] = cleaned
    return extra
