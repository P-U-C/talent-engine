"""Validated policy layer above the generic talent engine.

The scorer answers one narrow question: what public evidence exists that this
person ships?  A sponsorship program has different responsibilities: access
eligibility, fit, human verification, budget, checkpoints, termination and
outcomes.  Keeping those here prevents program terms from becoming hidden
points in the technical rubric.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
