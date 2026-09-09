"""Two stewards, one queue, and their verdicts kept apart until they aren't.

The reader page holds a private gut call per applicant. That was enough for one
person with a scratchpad; it is not enough for a decision two people have to
make together, because a verdict nobody can see later is not a record and a
verdict seen too early is not independent.

So verdicts are stored server-side per steward, and the page **will not show
one steward the other's call on an applicant until they have recorded their
own**. Two correlated reads are worth much less than two independent ones, and
the cheapest way to correlate them is to let the second reader see the first
reader's answer. The comparison is the point, and it only means something if it
comes last.

The steward id in the URL is attribution, not authentication. Anyone holding the
board token can write as either name. That is proportionate here -- the token is
already the access control and the stewards are two people who trust each
other -- but it should be said out loud rather than implied.
"""
from __future__ import annotations

import sqlite3
from typing import Any

VERDICTS = ("yes", "maybe", "no")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def record(db_path: str, steward: str, handle: str, verdict: str, when: str,
           note: str = "") -> bool:
    """Write one steward's call. An empty verdict clears it."""
    conn = _connect(db_path)
    try:
        with conn:
            if not verdict:
                conn.execute(
                    "delete from steward_reviews where steward=? and handle=?",
                    (steward, handle),
                )
                return True
            conn.execute(
                "insert into steward_reviews (steward, handle, verdict, note,"
                " recorded_at) values (?,?,?,?,?)"
                " on conflict(steward, handle) do update set"
                " verdict=excluded.verdict, note=excluded.note,"
                " recorded_at=excluded.recorded_at",
                (steward, handle, verdict, note[:500], when),
            )
        return True
    finally:
        conn.close()


def state(db_path: str, viewer: str) -> dict[str, Any]:
    """Everything the page may know: the viewer's own calls in full, and the
    other stewards' calls ONLY for applicants the viewer has already judged."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "select steward, handle, verdict, recorded_at from steward_reviews"
        ).fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()

    mine = {r["handle"]: r["verdict"] for r in rows if r["steward"] == viewer}
    others: dict[str, dict[str, str]] = {}
    for r in rows:
        if r["steward"] == viewer or r["handle"] not in mine:
            continue
        others.setdefault(r["handle"], {})[r["steward"]] = r["verdict"]

    # Counts are safe to show in full: knowing that somebody has read 20 of 32
    # tells you nothing about what they thought of any one of them.
    progress: dict[str, int] = {}
    for r in rows:
        progress[r["steward"]] = progress.get(r["steward"], 0) + 1

    return {"viewer": viewer, "mine": mine, "others": others, "progress": progress}
