"""Human-facing output: ranked tables and per-candidate evidence dossiers.

The dossier is the trust mechanism made concrete.  A candidate should be able to
read it and either agree with the number or point at the specific line that is
wrong.  That means every point shown has to trace to a URL, and the arithmetic
has to be visible rather than summarised.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Iterable

from .config import ProgramConfig
from .model import CandidateScore, ProfileSnapshot
from .scoring.concerns import concerns

SEVERITY_MARK = {"critical": "!!", "warn": " !", "review": " ?"}


# Scores closer together than this are not distinguishable by this engine.
# Adversarial review put a manufactured profile within a point of a genuine
# builder, and collection itself varies by more than that -- a sampled repo, a
# rate limit, a PR merged the morning after. Printing 3rd and 4th as though the
# order meant something is the single easiest way for a reviewer to mistake a
# number for a judgement.
MATERIAL_MARGIN = 3.0


def bands(scores: Iterable[CandidateScore], margin: float = MATERIAL_MARGIN):
    """Group a ranked list into ties, widest-first.

    A new band starts only when the score drops more than `margin` below the
    band's own top. Within a band the ordering is arbitrary and should be
    presented that way.
    """
    grouped: list[list[CandidateScore]] = []
    for s in scores:
        if grouped and (grouped[-1][0].total - s.total) <= margin:
            grouped[-1].append(s)
        else:
            grouped.append([s])
    return grouped


def ranked_table(scores: Iterable[CandidateScore], *, limit: int | None = None) -> str:
    rows = list(scores)[: limit or None]
    if not rows:
        return "(no candidates)"
    width = max(len(s.handle) for s in rows)
    grouped = bands(rows)
    # Keyed by position, not by handle: two candidates can carry the same
    # handle (the fixtures do), and a dict keyed on it silently merges them
    # into one band.
    band_of: list[int] = []
    for i, g in enumerate(grouped, 1):
        band_of.extend([i] * len(g))
    out = [
        f"{'band':>4}  {'handle':<{width}}  {'total':>6}  {'auto':>5}  {'app':>5}  flags"
    ]
    out.append("-" * (len(out[0]) + 8))
    for pos, s in enumerate(rows):
        flags = ", ".join(
            f"{SEVERITY_MARK.get(f.severity, '')}{f.key}".strip() for f in s.flags
        )
        out.append(
            f"{band_of[pos]:>4}  {s.handle:<{width}}  {s.total:>6.2f}  "
            f"{s.automated_total:>5.1f}  {s.application_total:>5.1f}  {flags or '-'}"
        )
    ties = sum(1 for g in grouped if len(g) > 1)
    if ties:
        out.append("")
        out.append(
            f"Rows sharing a band are within {MATERIAL_MARGIN:g} points and this "
            "engine cannot tell them apart. Read their dossiers; do not read the "
            "order."
        )
    return "\n".join(out)


def dossier(
    score: CandidateScore,
    cfg: ProgramConfig,
    snapshot: ProfileSnapshot | None = None,
) -> str:
    """Markdown evidence dossier for one candidate.

    `snapshot` is optional but sharpens the caveat line: some of what a
    reviewer should be sceptical about is visible in the raw activity rather
    than in the score.
    """
    lines: list[str] = []
    add = lines.append

    add(f"# {score.handle} — {score.total:.2f} / {sum(cfg.weights.values()):.0f}")
    add("")
    add(f"**Program:** {cfg.name} (`{score.program}`)  ")
    add(f"**Window:** {score.window_start[:10]} → {score.window_end[:10]}  ")
    add(f"**Profile:** https://github.com/{score.handle}")
    add("")
    add(
        f"Automated signal: **{score.automated_total:.2f}** · "
        f"Application-declared: **{score.application_total:.2f}**"
    )
    add("")
    add(f"> {concerns(score, cfg, snapshot)}")
    add("")

    if score.flags:
        add("## Review flags")
        add("")
        add("_Flags never add or subtract points on their own; where a flag "
            "discounts a component, that is shown in the dimension below._")
        add("")
        for f in score.flags:
            add(f"- **{f.key}** ({f.severity}) — {f.message}")
            for e in f.evidence:
                add(f"  - [{e.claim}]({e.url})")
        add("")

    add("## Score breakdown")
    add("")
    for d in score.dimensions:
        pct = (d.points / d.max_points * 100) if d.max_points else 0
        add(f"### {d.key} — {d.points:.2f} / {d.max_points:.0f} ({pct:.0f}%)")
        if d.components:
            parts = ", ".join(f"{k} = {v:g}" for k, v in d.components.items())
            add(f"")
            add(f"`{parts}`")
        for note in d.notes:
            add(f"")
            add(f"> {note}")
        if d.evidence:
            add("")
            for e in d.evidence:
                detail = f" — {e.detail}" if e.detail else ""
                add(f"- [{e.claim}]({e.url}){detail}")
        elif d.points == 0:
            add("")
            add("- _no qualifying activity found in window_")
        add("")

    add("## Reproducing this score")
    add("")
    add("```")
    add(f"snapshot_digest : {score.snapshot_digest}")
    add(f"weights_digest  : {score.weights_digest}")
    add(f"code_version    : {score.code_version}")
    add(f"scored_at       : {score.scored_at}")
    add("```")
    add("")
    add(
        "The rubric, the weights, and the scorer are public. Re-running the same "
        "snapshot through the same weights reproduces this number exactly; "
        "`talent-engine verify` does it for you."
    )
    return "\n".join(lines)


def scores_to_csv(scores: Iterable[CandidateScore]) -> str:
    rows = list(scores)
    buf = io.StringIO()
    dims = [d.key for d in rows[0].dimensions] if rows else []
    writer = csv.writer(buf)
    writer.writerow(
        ["rank", "handle", "total", "automated", "application", *dims, "flags", "profile"]
    )
    for i, s in enumerate(rows, 1):
        writer.writerow(
            [
                i,
                s.handle,
                f"{s.total:.2f}",
                f"{s.automated_total:.2f}",
                f"{s.application_total:.2f}",
                *[f"{(s.dimension(k).points if s.dimension(k) else 0):.2f}" for k in dims],
                "|".join(f.key for f in s.flags),
                f"https://github.com/{s.handle}",
            ]
        )
    return buf.getvalue()


def scores_to_json(
    scores: Iterable[CandidateScore], cfg: ProgramConfig | None = None
) -> str:
    """JSON export. The caveat sentence always travels with the score.

    Machine consumers are the ones most likely to treat a bare number as a
    verdict, so when no config is supplied this emits an explicit marker rather
    than silently omitting the field — an absent key reads as "no concerns",
    which is the one thing this must never imply.
    """
    rows = []
    for s in scores:
        row = s.to_dict()
        row["concerns"] = (
            concerns(s, cfg)
            if cfg is not None
            else "not evaluated — export without a program config"
        )
        rows.append(row)
    return json.dumps(rows, indent=2)
