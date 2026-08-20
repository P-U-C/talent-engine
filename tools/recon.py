#!/usr/bin/env python3
"""Find out where the scouted candidates can be reached.

The nightly scout produces handles. A handle is not a way to contact anybody,
so the digest kept arriving with names the operator then had to research one by
one. This does that research: for each scouted candidate, what GitHub already
publishes about how to reach them, with the source of every answer.

Scored candidates first, best score first, because those are the ones an
outreach message would actually go to. Nobody is looked up twice unless their
record is old enough to have gone stale.

Usage:
  recon.py --program prezenti-sponsorship-trial --limit 25
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from talent_engine.github.auth import auth_from_env  # noqa: E402
from talent_engine.github.client import BudgetExhausted, GitHubClient, ResponseCache  # noqa: E402
from talent_engine.modes import recon  # noqa: E402
from talent_engine.store.db import Store  # noqa: E402

RUNTIME = Path.home() / "talent-engine-runtime"

# Who to look up, in the order worth spending requests on: anyone scouted, with
# their best score if they have one, newest-scored first among the unscored so
# a long backlog still surfaces recent names. `stale_days` re-checks a record
# old enough that the person may have added links since.
QUEUE = """
SELECT sc.handle, COALESCE(MAX(s.total), -1) AS total
  FROM scouted sc
  LEFT JOIN scores s ON s.handle = sc.handle
  LEFT JOIN profile_recon r ON r.handle = sc.handle
 WHERE sc.program = ?
   AND (r.handle IS NULL OR r.checked_at < ?)
 GROUP BY sc.handle
 ORDER BY total DESC, sc.first_seen DESC
 LIMIT ?
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--program", required=True)
    ap.add_argument("--db", default=str(RUNTIME / "talent_engine.db"))
    ap.add_argument("--cache", default=str(RUNTIME / "github-cache.sqlite"))
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--budget", type=int, default=300)
    ap.add_argument("--stale-days", type=int, default=45)
    ap.add_argument("--scored-only", action="store_true",
                    help="only people the scout thought enough of to score")
    args = ap.parse_args()

    # In the same shape as the timestamps in the table -- ISO with a T and an
    # offset. sqlite's own datetime() returns "2026-08-20 05:16:00", and
    # comparing that against "2026-08-20T05:10:54+00:00" as strings puts every
    # existing row on the wrong side of the cutoff: a refresh pass silently
    # skipped everyone it was meant to re-check and looked up strangers instead.
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=args.stale_days)
    ).isoformat(timespec="seconds")

    store = Store(args.db)
    rows = store.conn.execute(QUEUE, (args.program, cutoff, args.limit)).fetchall()
    if args.scored_only:
        rows = [r for r in rows if r["total"] >= 0]
    if not rows:
        print("nothing to look up")
        store.close()
        return 0

    client = GitHubClient(
        auth=auth_from_env(dict(os.environ)),
        cache=ResponseCache(args.cache),
        budget=args.budget,
    )

    found = 0
    for row in rows:
        try:
            result = recon.find(client, row["handle"])
        except BudgetExhausted as exc:
            # Stop cleanly rather than half-writing the queue: what is already
            # saved stays, and tomorrow's run picks up where this one stopped.
            print(f"stopped early: {exc}", file=sys.stderr)
            break
        except Exception as exc:  # one dead profile must not lose the run
            print(f"skip {row['handle']}: {exc}", file=sys.stderr)
            continue
        store.save_recon(result)
        if result["x_handle"]:
            found += 1
            print(f"  {row['handle']:24} @{result['x_handle']}  ({result['x_source']})")

    print(f"looked up {len(rows)}, found {found} X account(s) ({client.stats})")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
