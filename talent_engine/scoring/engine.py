"""Scoring orchestration.

`score_snapshot` is a pure function: same snapshot + same config + same code
version always yields the same result.  All network access happens earlier, in
collection.  That separation is what makes the audit-log promise real -- to
regenerate a historical score you replay the stored snapshot through the stored
weights, and nothing can drift underneath you.
"""

from __future__ import annotations

from ..config import ProgramConfig
from ..model import CandidateScore, ProfileSnapshot, utc_now_iso
from .dimensions import ALL_DIMENSIONS
from .flags import evaluate_flags

CODE_VERSION = "talent-engine/0.1.0"


def score_snapshot(snap: ProfileSnapshot, cfg: ProgramConfig) -> CandidateScore:
    # Flags are computed first: they can discount dimension components, so the
    # dimensions need to see them. They can never add points (see model.Flag).
    flags = evaluate_flags(snap, cfg)
    dimensions = [fn(snap, cfg, flags) for fn in ALL_DIMENSIONS]
    total = sum(d.points for d in dimensions)

    return CandidateScore(
        handle=snap.handle,
        total=round(total, 2),
        dimensions=dimensions,
        flags=flags,
        program=cfg.key,
        window_start=snap.window_start,
        window_end=snap.window_end,
        snapshot_digest=snap.digest(),
        weights_digest=cfg.weights_digest(),
        code_version=CODE_VERSION,
        scored_at=utc_now_iso(),
    )


def rank(scores: list[CandidateScore]) -> list[CandidateScore]:
    """Rank by total, then by the agency dimensions as tie-breaks.

    Ties break toward measured shipping rather than toward self-declared or
    network signals -- the same preference the weights encode, applied again at
    the margin.
    """

    def key(s: CandidateScore):
        ship = s.dimension("shipping_agency")
        cons = s.dimension("consistency")
        critical = sum(1 for f in s.flags if f.severity == "critical")
        return (
            -s.total,
            critical,  # flagged profiles sort below clean ones at equal score
            -(ship.points if ship else 0),
            -(cons.points if cons else 0),
            s.handle,
        )

    return sorted(scores, key=key)
