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
