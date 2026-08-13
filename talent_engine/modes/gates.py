"""The checks that must pass before anyone is accepted.

An acceptance moves real money and publishes a public claim that this
programme backed this person. Before this module, `accept --select` would take
an arbitrary GitHub handle, add it to the cohort, and print a complete
acceptance letter -- with no scored application, no record that the person had
agreed to the current terms, and none of the human judgements the programme
says it makes. Nothing failed, because nothing was checked.

Two kinds of gate, and the difference matters.

**Machine-checkable.** Whether a scored application exists, and whether the
applicant affirmatively accepted the terms *at their current version*. The
engine can answer these itself and does.

**Human judgement.** Whether the access barrier was verified, the build plan
reviewed, the Celo fit assessed, the conflict cleared. The engine cannot
answer these and should not pretend to. What it can do is refuse to proceed
until a named person has recorded that they did, which turns "we always check"
from a habit into a record.

Failing closed is the point. An override exists because reality has edge
cases, but it is an event with an author and a reason, written to its own
table, and the acceptance letter says it happened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

MACHINE_GATES = ("scored_application", "terms_accepted")
HUMAN_GATES = (
    "access_barrier_verified",
    "build_plan_reviewed",
    "celo_fit_checked",
    "conflict_cleared",
)
ALL_GATES = MACHINE_GATES + HUMAN_GATES

GATE_LABELS = {
    "scored_application": "a scored application exists under this programme",
    "terms_accepted": "the applicant accepted the current terms",
    "access_barrier_verified": "the access barrier was verified",
    "build_plan_reviewed": "the build plan was reviewed",
    "celo_fit_checked": "the Celo fit was checked",
    "conflict_cleared": "conflicts of interest were cleared",
}


@dataclass
class Gate:
    key: str
    passed: bool
    detail: str

    @property
    def label(self) -> str:
        return GATE_LABELS.get(self.key, self.key)


def evaluate(store, program: str, handle: str, terms_digest: str) -> list[Gate]:
    """Every acceptance gate for one candidate, in the order a human checks them."""
    gates: list[Gate] = []

    scored = store.has_scored_application(program, handle)
    gates.append(
        Gate(
            "scored_application",
            scored,
            "found" if scored else "no scored submission for this handle",
        )
    )

    app = store.latest_application(program, handle)
    accepted, version = False, ""
    if app:
        try:
            data = json.loads(app["application_json"]) or {}
            accepted = bool(data.get("accepted_terms"))
            version = str(data.get("accepted_terms_version") or "")
        except (ValueError, TypeError):
            accepted, version = False, "application could not be parsed"
    current = bool(accepted and terms_digest and version == terms_digest)
    if not app:
        detail = "no application on file"
    elif not accepted:
        detail = "terms were never affirmatively accepted"
    elif not current:
        # The dangerous case: they agreed, but to different words. Terms that
        # changed after acceptance are terms nobody agreed to.
        detail = f"accepted version {version or '(none)'}, current is {terms_digest}"
    else:
        detail = f"accepted version {version}"
    gates.append(Gate("terms_accepted", current, detail))

    signed = store.signoffs(program, handle)
    for key in HUMAN_GATES:
        row = signed.get(key)
        gates.append(
            Gate(
                key,
                bool(row),
                f"signed off by {row['steward']} on {row['signed_at'][:10]}"
                if row
                else "not signed off",
            )
        )
    return gates


def failing(gates: list[Gate]) -> list[Gate]:
    return [g for g in gates if not g.passed]


def render(gates: list[Gate]) -> str:
    lines = []
    for g in gates:
        mark = "pass" if g.passed else "FAIL"
        lines.append(f"  [{mark}] {g.key:26} {g.label} — {g.detail}")
    return "\n".join(lines)
