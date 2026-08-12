"""Monitor and measure.

Monitor answers "is this cohort still working?" during a term.
Measure answers "did backing them change anything?" at the end of it.

Measure re-runs the *same rubric* that made the selection, which is what lets
the selection score double as the baseline.  A separate outcome metric would
let selection and evaluation drift apart, and then neither number means much.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import ProgramConfig
from ..model import CandidateScore, ProfileSnapshot, _parse_iso

ACTIVE = "ACTIVE"
AT_RISK = "AT_RISK"
INACTIVE = "INACTIVE"


@dataclass
class CohortStatus:
    handle: str
    state: str
    days_since_activity: int | None
    declared_repo: str = ""
    declared_repo_active: bool | None = None
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "state": self.state,
            "days_since_activity": self.days_since_activity,
            "declared_repo": self.declared_repo,
            "declared_repo_active": self.declared_repo_active,
            "evidence": self.evidence,
            "notes": self.notes,
        }


def assess(
    snap: ProfileSnapshot,
    cfg: ProgramConfig,
    *,
    declared_repo: str = "",
    now: datetime | None = None,
) -> CohortStatus:
    """Classify one cohort member's current activity.

    Two thresholds off one number: past the inactivity threshold is INACTIVE,
    past half of it is AT_RISK. The halfway point exists so a program can
    intervene while there is still term left to save.
    """
    now = now or datetime.now(timezone.utc)
    threshold = cfg.thresholds.inactivity_days

    last = _latest_activity(snap)
    days = (now - last).days if last else None

    if days is None:
        state = INACTIVE
    elif days <= threshold / 2:
        state = ACTIVE
    elif days <= threshold:
        state = AT_RISK
    else:
        state = INACTIVE

    status = CohortStatus(
        handle=snap.handle,
        state=state,
        days_since_activity=days,
        declared_repo=declared_repo,
        evidence=[snap.profile_url],
    )

    if declared_repo:
        match = next(
            (r for r in snap.repos if r.name.lower() == declared_repo.lower()), None
        )
        if match is None:
            status.declared_repo_active = False
            status.notes.append(
                f"declared project {declared_repo} not found among visible repos"
            )
        else:
            status.declared_repo_active = match.commits_in_window > 0
            status.evidence.append(match.url)
            if not match.commits_in_window:
                status.notes.append(
                    f"general activity present but {declared_repo} has no commits "
                    "in window -- working, but not on the funded project"
                )

        # A program that funds a specific project is not served by "they are
        # active somewhere". Being busy elsewhere is exactly the case a
        # month-2 checkpoint exists to catch, so it downgrades rather than
        # passing silently. Never upgrades: a genuinely inactive member stays
        # INACTIVE.
        if state == ACTIVE and not status.declared_repo_active:
            state = AT_RISK
            status.state = AT_RISK
            status.notes.append(
                "downgraded to AT_RISK: active, but not on the declared project"
            )

    if snap.partial:
        status.notes.append(
            "collection was partial; treat an INACTIVE result as unconfirmed"
        )

    return status


def _latest_activity(snap: ProfileSnapshot) -> datetime | None:
    stamps = [
        _parse_iso(r.pushed_at) for r in snap.repos if r.pushed_at
    ] + [
        _parse_iso(pr.merged_at) for pr in snap.merged_prs if pr.merged_at
    ] + [
        _parse_iso(rv.submitted_at) for rv in snap.reviews if rv.submitted_at
    ]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else None


# --------------------------------------------------------------------- measure


@dataclass
class Delta:
    handle: str
    before: float
    after: float

    @property
    def change(self) -> float:
        return round(self.after - self.before, 2)

    @property
    def pct_change(self) -> float | None:
        if self.before <= 0:
            return None
        return round(100 * (self.after - self.before) / self.before, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "before": round(self.before, 2),
            "after": round(self.after, 2),
            "change": self.change,
            "pct_change": self.pct_change,
        }


def measure(
    baseline: list[CandidateScore], endline: list[CandidateScore]
) -> dict[str, Any]:
    """Per-person and per-dimension before/after, on the same rubric."""
    before = {s.handle: s for s in baseline}
    after = {s.handle: s for s in endline}
    shared = sorted(set(before) & set(after))

    deltas = [Delta(h, before[h].total, after[h].total) for h in shared]

    dimension_shift: dict[str, float] = {}
    for h in shared:
        for dim in after[h].dimensions:
            prev = before[h].dimension(dim.key)
            if prev is not None:
                dimension_shift[dim.key] = dimension_shift.get(dim.key, 0.0) + (
                    dim.points - prev.points
                )
    if shared:
        dimension_shift = {
            k: round(v / len(shared), 2) for k, v in dimension_shift.items()
        }

    improved = [d for d in deltas if d.change > 0]
    return {
        "cohort_size": len(shared),
        "measured_on_same_rubric": True,
        "mean_before": round(sum(d.before for d in deltas) / len(deltas), 2) if deltas else 0,
        "mean_after": round(sum(d.after for d in deltas) / len(deltas), 2) if deltas else 0,
        "mean_change": round(sum(d.change for d in deltas) / len(deltas), 2) if deltas else 0,
        "improved": len(improved),
        "regressed": len([d for d in deltas if d.change < 0]),
        "per_person": [d.to_dict() for d in sorted(deltas, key=lambda d: -d.change)],
        "mean_dimension_change": dimension_shift,
        "missing_from_endline": sorted(set(before) - set(after)),
    }
