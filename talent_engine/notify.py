"""Push notifications for things a human needs to act on.

A pull-only pipeline is a pipeline nobody reads. Submissions landing silently
in SQLite means an applicant waits days because the operator had no reason to
run a command that day, and a system that never speaks is indistinguishable
from a system that has broken.

**Contact details are deliberately not sent.** The notification carries the
handle, the score, and the caveat sentence — enough to decide whether to look
now. Reaching the person needs `submissions --with-contact`, which reads the
quarantined table on the box. A notification is delivered to and stored by a
third party, and invariant 7 is not worth trading for saving one command.

Unconfigured is a no-op, never an error: notification is a convenience, and a
missing token must never cost a scored submission.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("talent_engine.notify")

# Where the rest of this machine keeps its bot credentials, used when the
# service env does not carry its own.
FALLBACK_ENV = Path.home() / ".claude" / "channels" / "telegram" / ".env"


def _from_env_file(path: Path, key: str) -> str:
    try:
        for line in path.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def credentials() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or _from_env_file(
        FALLBACK_ENV, "TELEGRAM_BOT_TOKEN"
    )
    chat = os.environ.get("TELEGRAM_CHAT_ID") or _from_env_file(
        FALLBACK_ENV, "TELEGRAM_CHAT_ID"
    )
    return token, chat


def send(text: str, *, timeout: int = 20) -> bool:
    """Best effort. Returns whether it went out; never raises."""
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
) -> bool:
    """A new application has been scored.

    The caveat travels with the number here for the same reason it does
    everywhere else: this message is where the operator forms their first
    impression, and a bare score is the most misleading thing to send.
    """
    lines = [
        f"New application — {handle}",
        f"{total:.1f} / {max_points:.0f}   ({program})",
    ]
    if declared_repo:
        lines.append(f"repo: {declared_repo}")
    lines += [
        "",
        caveat,
        "",
        f"https://github.com/{handle}",
        "Contact details: talent-engine submissions --with-contact",
    ]
    return send("\n".join(lines))


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
    lines.append("These have not applied. Score one: talent-engine score --handles <handle>")
    return send("\n".join(lines))
