"""Validated policy layer above the generic talent engine.

The scorer answers one narrow question: what public evidence exists that this
person ships?  A sponsorship program has different responsibilities: access
eligibility, fit, human verification, budget, checkpoints, termination and
outcomes.  Keeping those here prevents program terms from becoming hidden
points in the technical rubric.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def _valid_month(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 7 or value[4] != "-":
        return False
    try:
        year, month = int(value[:4]), int(value[5:])
    except ValueError:
        return False
    return year >= 2000 and 1 <= month <= 12


def _valid_date(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    last = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(day.day, last))


@dataclass(frozen=True)
class Benefit:
    key: str
    monthly_usd: float = 0.0
    months: int = 0
    one_time_usd: float = 0.0

    @property
    def per_person_usd(self) -> float:
        return round(self.monthly_usd * self.months + self.one_time_usd, 2)


@dataclass
class ProgramOverlay:
    key: str
    name: str
    scoring_program: str
    seats: int
    duration_months: int
    budget_usd: float
    benefits: list[Benefit]
    selection: dict[str, Any]
    monitoring: dict[str, Any]
    giveback: dict[str, Any]
    kpis: dict[str, Any] = field(default_factory=dict)
    # Whether the programme is accepting applications. The public page
    # reads this, so the page cannot look open while the programme is not.
    status: str = "open"
    applications_close: str = ""
    # First programme month, as YYYY-MM. The operating tracker derives its
    # expected receipt/reimbursement/update periods from this; making it policy
    # state prevents one month-one receipt from covering a whole term just
    # because an operator forgot an optional CLI flag.
    term_start: str = ""
    # Last calendar day of the programme term, as YYYY-MM-DD. Attestation
    # expiry is derived from this plus the sunset, so the schema field and the
    # native EAS expiry cannot drift from the operating calendar.
    term_end: str = ""
    # The single versioned terms release applicants agree to. The public page
    # links here, the Tally marker is the short hash of it, and the pledge app
    # records the full hash.
    terms_release: dict[str, Any] = field(default_factory=dict)
    # On-chain attestation metadata for the trial pledge. The UID is not stored
    # by `accept` unless the attestation matches these values and the current
    # terms release.
    attestation: dict[str, Any] = field(default_factory=dict)
    # Who is accountable for the operating obligations after acceptance --
    # receipts, reimbursements, the month-two Celo result, KPIs. Every ledger
    # entry requires an owner; this is the default so the common case is not a
    # flag on every command, and so "who owns this programme's follow-through"
    # has a written answer rather than an assumed one.
    operating_owner: str = ""
    upside: dict[str, Any] = field(default_factory=dict)
    # What the program owes the recipient. A sponsorship where only one
    # side carries obligations is not a relationship, and at this cheque
    # size the relationship is the entire return.
    commitments_to_recipient: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.seats <= 0 or self.duration_months <= 0:
            raise ValueError(f"{self.key}: seats and duration must be positive")

        if self.selection.get("automated_final_selection", False):
            raise ValueError(
                f"{self.key}: the automated score may shortlist, not make a "
                "funding decision"
            )
        if not self.selection.get("human_verification_required", False):
            raise ValueError(f"{self.key}: final selection requires human verification")
        if not self.selection.get("build_plan_required", False):
            raise ValueError(f"{self.key}: a sponsorship requires a build plan")

        inactivity = int(self.monitoring.get("inactivity_review_days", 0))
        cure = int(self.monitoring.get("cure_days", 0))
        if inactivity and cure <= 0:
            raise ValueError(
                f"{self.key}: inactivity may trigger review, but must include a cure period"
            )
        if self.monitoring.get("metric_flag_automatically_terminates", False):
            raise ValueError(
                f"{self.key}: an authenticity flag is not proof and cannot auto-terminate"
            )

        total_bps = int(self.giveback.get("total_bps", 0))
        recipients = self.giveback.get("recipients", [])
        if sum(int(r.get("bps", 0)) for r in recipients) != total_bps:
            raise ValueError(f"{self.key}: give-back recipient shares do not add up")

        # One obligation, one counterparty. The policy used to split the
        # give-back 100 bps to Prezenti and 100 bps to the Celo Community Fund,
        # which asks a builder to owe something to a party they have no
        # agreement with, that cannot know the obligation exists, and that
        # would have no standing to act on it. Prezenti's onward promise to the
        # Fund belongs in `prezenti_onward_commitment`, where it is published
        # without being something the builder owes.
        #
        # This is enforced rather than documented because `terms_digest()`
        # fingerprints this block: while the policy said 1% + 1%, the
        # "current terms accepted" gate was certifying a structure the written
        # terms had already abandoned.
        if total_bps > 0 and len(recipients) != 1:
            raise ValueError(
                f"{self.key}: a give-back must name exactly one counterparty "
                f"(found {len(recipients)}). A builder cannot owe a third party "
                "they have no agreement with; use prezenti_onward_commitment."
            )
        onward = self.giveback.get("prezenti_onward_commitment") or {}
        if onward:
            if "bps_of_receipts" in onward:
                raise ValueError(
                    f"{self.key}: use bps_of_covered_income for the onward "
                    "commitment. One hundred basis points is 1% of covered "
                    "income, not 1% of Prezenti's receipts."
                )
            onward_bps = int(onward.get("bps_of_covered_income", 0))
            if onward_bps * 2 != total_bps:
                raise ValueError(
                    f"{self.key}: the onward commitment must be half of what "
                    "Prezenti receives, expressed as bps_of_covered_income"
                )

        # An uncapped, perpetual give-back is disproportionate to an in-kind
        # grant of this size, and it selects against builders who have other
        # options — which are exactly the builders the rubric exists to find.
        # See docs/SPONSORSHIP_TERMS.md.
        if total_bps > 0:
            if not self.giveback.get("cap_multiple_of_sponsorship"):
                raise ValueError(
                    f"{self.key}: a give-back must be capped. An open-ended claim "
                    "from an in-kind grant is the kind of encumbrance a later "
                    "investor asks to have removed."
                )
            if not self.giveback.get("sunset_months_after_term"):
                raise ValueError(f"{self.key}: a give-back must expire")
            if not self.giveback.get("prorated_by_months_received"):
                raise ValueError(
                    f"{self.key}: a give-back must be pro-rated by months actually "
                    "received — the terms otherwise punish someone who withdrew "
                    "honourably at the month-two gate"
                )

        # Equity is not taken at this cheque size; a right to be *offered*
        # participation costs the builder nothing and needs no enforcement.
        if self.upside.get("equity_taken"):
            raise ValueError(
                f"{self.key}: this program does not take equity. A right of first "
                "offer is the instrument at this size."
            )

        if self.status not in ("open", "closed"):
            raise ValueError(f"{self.key}: status must be open or closed")

        if not _valid_month(self.term_start):
            raise ValueError(
                f"{self.key}: term_start must be configured as YYYY-MM so the "
                "operating tracker is period-aware by default"
            )
        if not _valid_date(self.term_end):
            raise ValueError(
                f"{self.key}: term_end must be configured as YYYY-MM-DD so "
                "attestation expiry is derived from the programme calendar"
            )
        if not self.terms_release.get("version") or not self.terms_release.get("document"):
            raise ValueError(
                f"{self.key}: terms_release must name one versioned canonical "
                "terms document"
            )
        self._terms_document_path()
        att = self.attestation or {}
        if att:
            for required in ("schema_uid", "eas_contract", "recipient", "community_fund_recipient"):
                if not att.get(required):
                    raise ValueError(f"{self.key}: attestation.{required} is required")

        if not self.commitments_to_recipient:
            raise ValueError(
                f"{self.key}: state what the program owes the recipient. Terms that "
                "run one way are not a relationship, and the relationship is the "
                "return here."
            )
        for required in ("retains_all_ip_and_equity", "may_withdraw_without_penalty"):
            if not self.commitments_to_recipient.get(required):
                raise ValueError(f"{self.key}: recipients must be guaranteed {required}")

        if abs(self.total_budget_usd - float(self.budget_usd)) > 0.01:
            raise ValueError(
                f"{self.key}: benefit schedule totals ${self.total_budget_usd:,.2f}, "
                f"not declared budget ${self.budget_usd:,.2f}"
            )

    @property
    def per_person_usd(self) -> float:
        return round(sum(b.per_person_usd for b in self.benefits), 2)

    @property
    def total_budget_usd(self) -> float:
        return round(self.per_person_usd * self.seats, 2)

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    def _terms_document_path(self) -> Path:
        document = Path(str(self.terms_release.get("document", "")))
        if document.is_absolute() or ".." in document.parts:
            raise ValueError(f"{self.key}: terms_release.document must be repo-relative")
        path = ROOT / document
        if not path.exists():
            raise ValueError(f"{self.key}: terms release document not found: {document}")
        return path

    def _terms_payload(self) -> str:
        """The canonical, versioned terms release this programme accepts.

        The form marker and pledge hash both derive from this exact payload.
        It includes the canonical terms document and the policy fields the code
        enforces, so changing either the words or the operative values retires
        the previous version.
        """
        path = self._terms_document_path()
        payload = json.dumps(
            {
                "release": {
                    "version": self.terms_release.get("version"),
                    "document": str(self.terms_release.get("document")),
                    "hash_algorithm": "sha256",
                },
                "document_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "giveback": self.giveback,
                "upside": self.upside,
                "commitments_to_recipient": self.commitments_to_recipient,
                "term_start": self.term_start,
                "term_end": self.term_end,
                "duration_months": self.duration_months,
                "benefits": [b.__dict__ for b in self.benefits],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return payload

    def terms_hash(self) -> str:
        """Full SHA-256 bytes32 hash of the canonical terms release."""
        return "0x" + hashlib.sha256(self._terms_payload().encode()).hexdigest()

    def terms_digest(self) -> str:
        """Short marker stamped into the Tally acceptance option."""
        return self.terms_hash()[2:14]

    @property
    def terms_uri(self) -> str:
        return str(self.terms_release.get("uri") or self.terms_release.get("document") or "")

    @property
    def attestation_expiration(self) -> int:
        end = date.fromisoformat(self.term_end)
        expires = _add_months(end, int(self.giveback.get("sunset_months_after_term", 0)))
        return int(datetime(expires.year, expires.month, expires.day, tzinfo=timezone.utc).timestamp())

    def terms_summary(self) -> list[str]:
        """The terms in one place, for logs and for the public page.

        Rendered from the policy rather than written twice, so the page cannot
        drift from what is actually enforced.
        """
        g = self.giveback
        lines = [
            f"{self.seats} places, {self.duration_months} months, "
            f"${self.per_person_usd:,.0f} each (${self.total_budget_usd:,.0f} total)",
            f"give-back {g.get('total_bps', 0) / 100:.0f}% of Celo revenue and "
            f"grant income, capped at ${self.giveback_cap_usd:,.0f}, expiring "
            f"{g.get('sunset_months_after_term')} months after the term, "
            "pro-rated by months received",
            f"equity taken: {'yes' if self.upside.get('equity_taken') else 'none'}"
            + (
                "; right of first offer on a future round"
                if self.upside.get("right_of_first_offer_next_round")
                else ""
            ),
            "enforcement: " + str(g.get("enforcement", "unspecified")),
        ]
        # Say who is owed. "2%" without a counterparty is the ambiguity that let
        # the policy and the written terms disagree for as long as they did.
        if g.get("obligation_runs_to"):
            lines.insert(2, f"owed to {g['obligation_runs_to']}, and to nobody else")
        onward = g.get("prezenti_onward_commitment") or {}
        if onward:
            covered_bps = int(onward.get("bps_of_covered_income", 0))
            lines.insert(
                3,
                f"Prezenti separately routes half of what it receives onward to "
                f"{onward.get('name')} — equivalent to {covered_bps / 100:.0f}% "
                "of covered income, and a commitment made by Prezenti, not by you",
            )
        return lines

    @property
    def giveback_cap_usd(self) -> float:
        """The most any one recipient could ever owe."""
        multiple = float(self.giveback.get("cap_multiple_of_sponsorship", 0))
        return round(self.per_person_usd * multiple, 2)

    def giveback_owed_bps(self, months_received: int) -> int:
        """Give-back scaled to what they actually took.

        Someone who left at the month-two gate owes half of what someone who
        completed the term owes. Without this the terms are worst for the
        person who withdrew early and honestly.
        """
        if not self.giveback.get("prorated_by_months_received"):
            return int(self.giveback.get("total_bps", 0))
        months = max(0, min(int(months_received), self.duration_months))
        return round(int(self.giveback.get("total_bps", 0)) * months / self.duration_months)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProgramOverlay":
        payload = dict(data)
        payload["benefits"] = [Benefit(**b) for b in payload.get("benefits", [])]
        return cls(**payload)

    @classmethod
    def load(cls, path: str | Path) -> "ProgramOverlay":
        return cls.from_dict(json.loads(Path(path).read_text()))


def load_overlay(name_or_path: str, search_dir: str | Path | None = None) -> ProgramOverlay:
    path = Path(name_or_path)
    if path.exists():
        return ProgramOverlay.load(path)
    base = (
        Path(search_dir)
        if search_dir
        else Path(__file__).resolve().parent.parent.parent / "policies"
    )
    candidate = base / f"{name_or_path}.json"
    if candidate.exists():
        return ProgramOverlay.load(candidate)
    available = sorted(p.stem for p in base.glob("*.json")) if base.exists() else []
    raise FileNotFoundError(
        f"no program overlay {name_or_path!r} in {base} (available: {available})"
    )
