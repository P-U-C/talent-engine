"""What an accepted builder is told, and what gets recorded when they are.

Two design positions worth stating, because both are places this could have
been built differently and worse.

**No contract is deployed from here.** Creating the 0xSplits contract needs a
funded key with signing authority, and a scoring pipeline is the wrong process
to hold one: it takes untrusted input from a public form, and the blast radius
of a compromise should not include an on-chain wallet. So this emits the exact
split parameters and records the address once it exists. Deploying is a
deliberate act by a person, not a side effect of marking someone accepted.

**The letter states the terms in full, including the ones that constrain the
program.** An acceptance email that lists what the recipient owes and omits
what they are owed is how a relationship starts badly. The obligations run both
ways in the policy; they run both ways here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..programs.policy import ProgramOverlay

SPLITS_APP = "https://app.splits.org"
PLEDGE_APP = "https://pledge.prezenti.xyz"

# Human-readable renderings of the commitment keys, so the letter reads as
# sentences rather than as a dump of the JSON.
COMMITMENT_TEXT = {
    "retains_all_ip_and_equity": "You keep all IP and all equity in what you build. We take none.",
    "no_exclusivity": "No exclusivity. Take other funding, other grants, other work.",
    "may_withdraw_without_penalty": (
        "You can withdraw at any time without penalty, and the give-back scales "
        "down to what you actually received."
    ),
    "public_record_of_backing": "We say publicly that we backed you, with the evidence.",
    "introductions_on_request": "Introductions where we can make them — just ask.",
    "score_and_evidence_shared_with_applicant": (
        "Your score and every piece of evidence behind it, shared with you."
    ),
    "feedback_to_unsuccessful_applicants": (
        "Everyone who applied and was not selected gets feedback."
    ),
}


@dataclass
class SplitPlan:
    """Everything needed to create the split, and nothing that creates it."""

    recipients: list[dict[str, Any]]
    chain: str = "celo"

    @property
    def resolved(self) -> bool:
        return all(r.get("address") for r in self.recipients)

    def render(self) -> str:
        lines = [f"Chain: {self.chain}", "Recipients:"]
        for r in self.recipients:
            addr = r.get("address") or f"<unset: set {r.get('address_env')}>"
            lines.append(f"  {r['name']:<24} {r['bps'] / 100:.2f}%   {addr}")
        lines.append(f"\nCreate at: {SPLITS_APP}")
        return "\n".join(lines)


def split_plan(overlay: ProgramOverlay, env: dict[str, str]) -> SplitPlan:
    """Split parameters, with recipient addresses read from the environment.

    Addresses are held in env vars rather than the policy file so the policy
    can live in a public repository without publishing payout addresses.
    """
    recipients = []
    for r in overlay.giveback.get("recipients", []):
        env_key = r.get("address_env", "")
        recipients.append(
            {
                "name": r.get("name", ""),
                "bps": int(r.get("bps", 0)),
                "address_env": env_key,
                "address": env.get(env_key, "") if env_key else "",
            }
        )
    return SplitPlan(recipients=recipients)


def acceptance_letter(
    handle: str,
    overlay: ProgramOverlay,
    *,
    split_address: str = "",
    score: float | None = None,
    caveat: str = "",
) -> str:
    """The letter an accepted builder receives.

    Written to be read by the person it is about, which means the terms are
    stated in plain words and the unflattering ones are not buried.
    """
    g = overlay.giveback
    cap = overlay.giveback_cap_usd
    lines: list[str] = []
    add = lines.append

    add(f"You have been selected for {overlay.name}.")
    add("")
    add(f"What you get, for {overlay.duration_months} months:")
    for b in overlay.benefits:
        if b.months:
            add(f"  · {b.key.replace('_', ' ')} — ${b.monthly_usd:.0f}/month for {b.months} months")
        if b.one_time_usd:
            add(f"  · {b.key.replace('_', ' ')} — ${b.one_time_usd:.0f} one-off")
    add(f"  Total value: ${overlay.per_person_usd:,.0f}")
    add("")

    add("What we ask in return:")
    add(
        f"  · {g.get('total_bps', 0) / 100:.0f}% of revenue your sponsored project "
        "receives through Celo, and of any grant or prize income you win with"
    )
    add("    this work.")
    add(f"  · Capped at ${cap:,.0f} in total. It cannot exceed that, ever.")
    add(
        f"  · It expires {g.get('sunset_months_after_term')} months after the "
        "programme ends."
    )
    add(
        "  · It is pro-rated by the months you actually take. Leave at the "
        f"month-{overlay.monitoring.get('inactivity_review_days', 30) // 30 + 1} "
        "point and you owe proportionally less."
    )
    add("  · A monthly public update on what you are building.")
    add("")
    add(
        "  This is a good-faith pledge, and we want to be straight with you about "
        "what that means: it is not legally enforced and we are not taking a "
        "security interest in anything. It is a promise, made publicly, that we "
        "expect to be kept because you made it."
    )
    add("")

    add("What we owe you:")
    for key, promised in overlay.commitments_to_recipient.items():
        if promised and key in COMMITMENT_TEXT:
            add(f"  · {COMMITMENT_TEXT[key]}")
    add("")

    if overlay.upside.get("right_of_first_offer_next_round"):
        days = overlay.upside.get("rofo_notice_days", 14)
        add(
            f"If you raise a round later, we ask for {days} days' notice and the "
            "chance to be offered participation. That is a right to be offered, "
            "not an obligation on you to accept — we take no equity here."
        )
        add("")

    if score is not None:
        add(f"Your score was {score:.1f} out of 100, and here is the honest caveat")
        add("we attached to it internally:")
        add(f"  {caveat}")
        add(
            "  A score never decided this. It produced a shortlist; people read "
            "the evidence and decided. You can reproduce the number yourself: "
            "https://github.com/P-U-C/talent-engine"
        )
        add("")

    add("Two things to set up:")
    if split_address:
        add(f"  1. The give-back split is live at {split_address} on Celo.")
        add("     Routing revenue through it is voluntary and makes paying trivial.")
    else:
        add("  1. We will send you the give-back split address shortly.")
    add(f"  2. Sign the pledge at {PLEDGE_APP} — it records the terms above")
    add("     publicly, so what was agreed is legible to everyone including you.")
    return "\n".join(lines)
