"""Push notifications for things a human needs to act on.

A pull-only pipeline is a pipeline nobody reads. Submissions landing silently
in SQLite means an applicant waits days because the operator had no reason to
run a command that day, and a system that never speaks is indistinguishable
from a system that has broken.

Two channels, chosen by what is configured: SMTP (for an operator who reads
mail and has no shell on this box) and Telegram. When mail is configured it is
used, and **Telegram becomes the fallback for a failed send** rather than being
switched off — a notification that silently goes nowhere is the failure this
module exists to prevent, so a broken relay must degrade rather than drop.

**Whether contact details travel depends on the channel, and that is a
deliberate asymmetry.** Telegram gets the handle, score and caveat only:
reaching someone needs `submissions --with-contact`, run on the box. Email
carries the contact block, because the recipient is the program operator who
cannot run that command, and the form platform already delivers the same
details to the same mailbox — withholding them there would cost real work and
protect nothing. Neither channel ever carries an assessment record.

Unconfigured is a no-op, never an error: notification is a convenience, and a
missing token must never cost a scored submission.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

log = logging.getLogger("talent_engine.notify")

# Set by conftest.py, and available to anyone running the code by hand.
DISABLE_ENV = "TALENT_ENGINE_NOTIFY_DISABLED"


def disabled() -> bool:
    """Hard off switch.

    This exists because the module used to fall back to reading a bot token
    off disk when the environment had none, which meant importing it was
    enough to send real messages — the test suite delivered a burst of
    notifications to a real person's phone. Credentials now come from the
    environment only, and the test suite additionally sets this.
    """
    return os.environ.get(DISABLE_ENV, "").strip() not in ("", "0", "false")


def credentials() -> tuple[str, str]:
    """Telegram credentials, from the environment and nowhere else."""
    return (
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID", ""),
    )


def mail_config() -> dict[str, str]:
    """SMTP settings, or an empty dict when mail is not configured."""
    host = os.environ.get("SMTP_HOST", "")
    to = os.environ.get("NOTIFY_EMAIL_TO", "")
    if not host or not to:
        return {}
    return {
        "host": host,
        "port": os.environ.get("SMTP_PORT", "587"),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from": os.environ.get("NOTIFY_EMAIL_FROM", os.environ.get("SMTP_USER", "")),
        "from_name": os.environ.get("NOTIFY_EMAIL_FROM_NAME", "Prezenti Sponsorships"),
        "to": to,
    }


def send_email(subject: str, body: str, *, timeout: int = 30) -> bool:  # noqa: D401
    """Send over an authenticated relay. Never raises.

    Port 25 out of this host is blocked and unauthenticated mail from it would
    be filtered anyway, so this deliberately requires a relay with credentials
    rather than falling back to a local MTA that would silently defer forever.
    """
    if disabled():
        log.debug("notifications disabled; email suppressed")
        return False
    cfg = mail_config()
    if not cfg:
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg["from_name"], cfg["from"]))
    msg["To"] = cfg["to"]
    msg.set_content(body)

    try:
        port = int(cfg["port"])
        if port == 465:
            server = smtplib.SMTP_SSL(cfg["host"], port, timeout=timeout,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(cfg["host"], port, timeout=timeout)
        with server:
            if port != 465:
                server.starttls(context=ssl.create_default_context())
            if cfg["user"]:
                server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        log.info("emailed %r to %s", subject, cfg["to"])
        return True
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        log.warning("email failed (%s); falling back to telegram", exc)
        return False


def notify(subject: str, body: str, telegram_body: str | None = None) -> bool:
    """Deliver by mail if configured, else Telegram; Telegram on mail failure.

    The fallback is the point: a notification that goes nowhere is worse than
    the pull-only system this replaced, because it looks like nothing happened.

    When BOTH channels fail, that is logged at error level rather than
    swallowed. Silence is the exact failure this module exists to prevent, and
    a returned False that nobody checks is silence.
    """
    if mail_config():
        if send_email(subject, body):
            return True
    if send(telegram_body if telegram_body is not None else f"{subject}\n\n{body}"):
        return True
    if not disabled():
        log.error(
            "NOTIFICATION LOST: every channel failed for %r. Nobody has been told; "
            "recover it with `python3 -m talent_engine.cli submissions`.",
            subject,
        )
    return False


def send(text: str, *, timeout: int = 20) -> bool:
    """Telegram. Best effort. Returns whether it went out; never raises."""
    if disabled():
        log.debug("notifications disabled; telegram suppressed")
        return False
    token, chat = credentials()
    if not token or not chat:
        log.debug("no telegram credentials; notification skipped")
        return False

    data = urllib.parse.urlencode(
        {"chat_id": chat, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode() or "{}").get("ok", False)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        log.warning("notification failed: %s", exc)
        return False


def application_scored(
    handle: str,
    total: float,
    caveat: str,
    program: str,
    declared_repo: str = "",
    max_points: float = 100.0,
    contact: dict[str, Any] | None = None,
) -> bool:
    """A new application has been scored.

    The caveat travels with the number here for the same reason it does
    everywhere else: this message is where the operator forms their first
    impression, and a bare score is the most misleading thing to send.
    """
    head = [
        f"New application — {handle}",
        f"{total:.1f} / {max_points:.0f}   ({program})",
    ]
    if declared_repo:
        head.append(f"repo: {declared_repo}")
    head += ["", caveat, "", f"https://github.com/{handle}"]

    # Telegram: no contact details, they stay on the box.
    telegram_body = "\n".join(
        head + ["Contact details: python3 -m talent_engine.cli submissions --with-contact"]
    )

    # Email: the operator cannot run that command, and the form platform
    # already sent them the same details.
    email_body = "\n".join(
        head
        + [""]
        + _contact_block(contact)
        + [
            "",
            "This score is a shortlist position, not a decision. The rubric and "
            "the code that applies it are public: "
            "https://github.com/P-U-C/talent-engine",
        ]
    )
    return notify(
        subject=f"New application — {handle} ({total:.1f})",
        body=email_body,
        telegram_body=telegram_body,
    )


def _contact_block(contact: dict[str, Any] | None) -> list[str]:
    if not contact:
        return ["(no contact details on file)"]
    fields = [
        ("Name", contact.get("name")),
        ("Email", contact.get("email")),
        ("Telegram", contact.get("telegram")),
        ("X", contact.get("x")),
        ("Discord", contact.get("discord")),
    ]
    present = [f"{label}: {value}" for label, value in fields if value]
    return present or ["(no contact details on file)"]


def scout_digest(candidates: list[dict[str, Any]], program: str, limit: int = 10) -> bool:
    """The daily sourcing run.

    Sends nothing when there is nothing new: a digest that arrives every day
    regardless of content trains the reader to ignore it, and then the day it
    matters it gets ignored too.
    """
    if not candidates:
        log.info("scout found nothing new; no digest sent")
        return False

    shown = candidates[:limit]
    lines = [f"Scout — {len(candidates)} new candidate(s) for {program}", ""]
    for c in shown:
        why = (c.get("reasons") or [""])[0]
        channels = ",".join(c.get("channels") or [])
        lines.append(f"• {c['handle']}  [{channels}]")
        if why:
            lines.append(f"  {why}")
        lines.append(f"  https://github.com/{c['handle']}")
    if len(candidates) > len(shown):
        lines.append("")
        lines.append(f"…and {len(candidates) - len(shown)} more.")
    lines.append("")
    lines.append("These have not applied to anything — they were found by searching "
                 "public activity. Reaching out is the point.")
    body = "\n".join(lines)
    return notify(
        subject=f"Scout — {len(candidates)} new candidate(s), {program}",
        body=body,
    )
