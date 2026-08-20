"""Where to find a scouted candidate, from what GitHub already publishes.

Chad, 2026-08-20: "for the scouting thats done nightly. I need reconizance on
each to find twitter profiles so I can reach out."

The nightly scout answers "who exists". It says nothing about how to reach
them, so a promising handle and no way to message it is a lead that dies in the
digest. This closes that gap using only what a person has chosen to publish on
their own GitHub profile, in one deliberate order:

1.  `twitter_username` on the user record. GitHub asks for this explicitly and
    renders it on the profile, so it is a stated handle rather than an inferred
    one -- the only source here that cannot be a coincidence.
2.  The profile's linked social accounts. Most people who add socials in
    GitHub's own settings never fill the older twitter field, so this roughly
    doubles the hit rate -- and it surfaces the Bluesky, Mastodon or LinkedIn
    of the many developers who have no X account at all. Someone reachable
    somewhere is worth more than a blank row.
3.  Links in the profile's website field and bio. Someone who puts x.com/name
    in their bio is publishing a way to reach them.
4.  The profile README -- the `<user>/<user>` repository GitHub renders at the
    top of a profile. Most people who maintain one put their links in it.

Every answer carries the source it came from, because these are not equally
strong and an operator about to spend an outreach message deserves to know
which one they are trusting. A README link on a shared project page is a much
weaker claim than a profile field.

Two things this deliberately does not do. It does not guess handles from a
name, and it does not follow the personal site off GitHub. Both would raise the
hit rate and both would produce confident wrong answers -- messaging a stranger
because a scraper matched their name is the failure worth designing out.
"""

from __future__ import annotations

import base64
import re
from typing import Any

# The path segment of an x.com/twitter.com link, minus the reserved words that
# are pages rather than people. Without that exclusion, "share this on Twitter"
# buttons in a README resolve to the handle "intent".
_RESERVED = {
    "i", "home", "share", "intent", "search", "hashtag", "explore", "settings",
    "login", "signup", "about", "privacy", "tos", "compose", "messages",
    "notifications", "status", "www",
}
_LINK = re.compile(
    r"(?:https?://)?(?:www\.)?(?:x|twitter|fxtwitter|vxtwitter)\.com/"
    r"(?:#!/)?(@?[A-Za-z0-9_]{1,15})",
    re.IGNORECASE,
)


def _from_links(text: str) -> str:
    for raw in _LINK.findall(text or ""):
        handle = raw.lstrip("@")
        if handle.lower() not in _RESERVED:
            return handle
    return ""


def find(client, handle: str) -> dict[str, Any]:
    """Public profile detail for one handle. Never raises on a missing profile."""
    user = client.get(f"/users/{handle}") or {}
    out = {
        "handle": handle,
        "name": (user.get("name") or "").strip(),
        "blog": (user.get("blog") or "").strip(),
        "bio": " ".join((user.get("bio") or "").split()),
        "location": (user.get("location") or "").strip(),
        # The address on the profile page, which a person sets deliberately and
        # GitHub shows to anyone. For most of this list it is the only channel
        # they publish at all: two thirds have no X, no Bluesky and no LinkedIn.
        "email": (user.get("email") or "").strip(),
        "x_handle": "",
        "x_source": "",
        "socials": "",
    }

    # Everything the person linked in their own GitHub settings. Collected
    # whether or not an X handle turns up, because "no X but an active
    # Bluesky" is the answer for a real share of this list and a blank row
    # would throw that away.
    accounts = client.get(f"/users/{handle}/social_accounts") or []
    linked, x_from_accounts = [], ""
    for acc in accounts:
        url = (acc.get("url") or "").strip()
        provider = (acc.get("provider") or "").strip() or "link"
        if not url:
            continue
        if provider == "twitter" or _LINK.match(url.replace("https://", "")):
            x_from_accounts = x_from_accounts or _from_links(url)
            continue
        linked.append(f"{provider}: {url}")
    out["socials"] = "; ".join(linked)

    stated = (user.get("twitter_username") or "").strip().lstrip("@")
    if stated:
        out["x_handle"], out["x_source"] = stated, "profile field"
        return out
    if x_from_accounts:
        out["x_handle"], out["x_source"] = x_from_accounts, "linked account"
        return out

    for field, source in (("blog", "website"), ("bio", "bio")):
        found = _from_links(out[field])
        if found:
            out["x_handle"], out["x_source"] = found, source
            return out

    # Only now spend a second request. Most profiles answer above, and the
    # README is a 404 for the majority of accounts that never made one.
    readme = client.get(f"/repos/{handle}/{handle}/readme") or {}
    if readme.get("encoding") == "base64" and readme.get("content"):
        try:
            text = base64.b64decode(readme["content"]).decode("utf-8", "replace")
        except (ValueError, TypeError):
            text = ""
        found = _from_links(text)
        if found:
            out["x_handle"], out["x_source"] = found, "profile README"
    return out
