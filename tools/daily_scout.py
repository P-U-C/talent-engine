#!/usr/bin/env python3
"""Daily sourcing run: find people who never applied, tell the operator once.

Three things stop this becoming noise.

**It scores before it reports.** A raw run returns hundreds of handles —
two seed repos produced 267, including several obviously auto-generated
accounts. A list that long and that unfiltered is not a lead list, it is
homework. So the best-corroborated new names are scored first and the digest
carries the number and its caveat, which is what makes it actionable.

**It remembers who it has reported**, in a `scouted` table, so the digest
contains genuinely new names rather than the same list every morning. A digest
that repeats itself trains the reader to skip it, and then it gets skipped on
the day it mattered.

**It sends nothing when there is nothing new.** Silence means "no new
candidates", which is information; a daily message saying "0 new" is not.

Usage:
  daily_scout.py --program prezenti-sponsorship-trial --seeds owner/repo,owner/repo
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from talent_engine.config import load_program  # noqa: E402
from talent_engine.github.auth import auth_from_env  # noqa: E402
from talent_engine.github.client import GitHubClient, ResponseCache  # noqa: E402
from talent_engine.modes.scout import Scout  # noqa: E402
from talent_engine.github.collector import Collector  # noqa: E402
from talent_engine.scoring.concerns import concerns  # noqa: E402
from talent_engine.scoring.engine import CODE_VERSION, score_snapshot  # noqa: E402
from talent_engine.store.db import Store  # noqa: E402
from talent_engine.notify import scout_digest  # noqa: E402
from talent_engine.model import utc_now_iso  # noqa: E402

SEEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS scouted (
    program TEXT NOT NULL,
    handle TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    channels TEXT DEFAULT '',
    PRIMARY KEY (program, handle)
);
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--program", required=True)
    ap.add_argument("--seeds", default="", help="comma-separated owner/repo seeds")
    ap.add_argument("--caps", default="", help="owner/repo:N,owner/repo:N per-seed caps")
    ap.add_argument("--db", default=str(Path.home() / "talent-engine-runtime" / "talent_engine.db"))
    ap.add_argument("--cache", default=str(Path.home() / "talent-engine-runtime" / "github-cache.sqlite"))
    ap.add_argument("--budget", type=int, default=1200)
    ap.add_argument("--score-top", type=int, default=12,
                    help="how many of the best-corroborated new names to score")
    ap.add_argument("--limit", type=int, default=8, help="names shown in the digest")
    ap.add_argument("--dry-run", action="store_true", help="print, notify nothing, remember nothing")
    args = ap.parse_args()

    cfg = load_program(args.program)
    client = GitHubClient(
        auth=auth_from_env(dict(os.environ)),
        cache=ResponseCache(args.cache),
        budget=args.budget,
    )
    scout = Scout(client, cfg, window_days=cfg.window_days)
    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]

    # Per-seed caps: a large repository would otherwise spend a uniform quota
    # on maintainer churn while a small dense one contributes almost nothing.
    caps = {}
    for entry in (args.caps or "").split(","):
        if ":" in entry:
            repo, _, n = entry.partition(":")
            caps[repo.strip()] = int(n)

    if seeds:
        scout.from_contributors(seeds, caps=caps)
    candidates = scout.run([] if seeds else seeds)
    for note in scout.notes:
        print(f"note: {note}", file=sys.stderr)
    print(f"scout returned {len(candidates)} candidate(s) ({client.stats})", file=sys.stderr)

    conn = sqlite3.connect(args.db)
    conn.executescript(SEEN_SCHEMA)
    seen = {
        r[0]
        for r in conn.execute("SELECT handle FROM scouted WHERE program = ?", (cfg.key,))
    }

    fresh = [c.to_dict() for c in candidates if c.handle not in seen]
    print(f"{len(fresh)} new since the last run", file=sys.stderr)

    # Corroboration first: someone surfaced by two independent channels is a
    # better use of the scoring budget than someone surfaced by one.
    fresh.sort(key=lambda c: (-len(c.get("channels") or []), c["handle"]))
    to_score = fresh[: args.score_top]

    if args.dry_run:
        for c in to_score:
            print(f"  {c['handle']}  {','.join(c.get('channels') or [])}")
        print(f"(would score {len(to_score)} of {len(fresh)} new)", file=sys.stderr)
        conn.close()
        return 0

    now = utc_now_iso()
    if not to_score:
        _remember(conn, cfg.key, fresh, now)
        conn.close()
        return 0

    # Score them. Discovery says "this person exists"; the score and its caveat
    # are what let the operator decide whether to spend an outreach message.
    store = Store(args.db)
    run_id = store.start_run(cfg, "scout", CODE_VERSION, note=f"daily scout {now[:10]}")
    collector = Collector(client, window_days=cfg.window_days)
    scored: list[dict] = []
    for c in to_score:
        try:
            snap = collector.collect(c["handle"])
        except Exception as exc:  # one bad profile must not lose the digest
            print(f"skip {c['handle']}: {exc}", file=sys.stderr)
            continue
        store.save_snapshot(snap)
        s = score_snapshot(snap, cfg)
        store.save_score(run_id, s)
        scored.append(
            {
                "handle": c["handle"],
                "channels": c.get("channels") or [],
                "reasons": [f"{s.total:.1f} — {concerns(s, cfg, snap)}"],
                "total": s.total,
            }
        )
    store.close()

    scored.sort(key=lambda c: -c["total"])
    print(f"scored {len(scored)}; top {min(args.limit, len(scored))} sent", file=sys.stderr)

    # Only mark people reported once the report actually went out. Recording
    # first meant a failed send silently buried those candidates forever: they
    # counted as seen, so they never appeared in another digest, and the only
    # trace was a log line nobody reads.
    if scout_digest(scored, cfg.name, limit=args.limit):
        _remember(conn, cfg.key, fresh, now)
    else:
        print(
            "digest was not delivered; candidates left unrecorded so tomorrow "
            "reports them again",
            file=sys.stderr,
        )
    conn.close()
    return 0


def _remember(conn, program: str, candidates: list[dict], now: str) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO scouted (program, handle, first_seen, channels) "
        "VALUES (?, ?, ?, ?)",
        [(program, c["handle"], now, ",".join(c.get("channels") or [])) for c in candidates],
    )
    conn.commit()


if __name__ == "__main__":
    raise SystemExit(main())
