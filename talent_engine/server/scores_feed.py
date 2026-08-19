"""A CSV of scores, for the stewards' own spreadsheet to pull.

Chad, 2026-08-19: "I wonder if we could use the sheet that tally publishes to
and add a tab or append just the scores (G-L) but I couldnt share externally."

That last clause is the constraint that decides the design. The Tally sheet is
owned inside the Prezenti workspace and shared with the stewards there; it
cannot be shared out, and nothing outside that workspace can be granted access
to it. So the scores have to travel *to* the sheet rather than the sheet being
opened up. A tab containing

    =IMPORTDATA("https://sponsorships.prezenti.xyz/scores/<token>.csv")

pulls this endpoint on Google's own schedule, inside their workspace, with no
account to share and no credential to hand round.

Two deliberate limits:

*   This module never opens the `contacts` table. Not "filters it out" -- never
    reads it. The terms applicants accepted keep contact details out of any
    shared artefact, and the strongest way to keep a projection honest is to
    make the data absent rather than excluded.
*   The path carries a random token because IMPORTDATA fetches anonymously, so
    the URL is the only thing standing between this and the open web. Scores and
    public GitHub handles are not secrets, but "no unselected applicant is named
    publicly" is a promise, and an unguessable URL is what keeps it.
"""

from __future__ import annotations

import csv
import io
import sqlite3

# Mirrors the score columns of the Pools CRM sheet the programme already runs
# on, so the pulled tab lines up with what the stewards read elsewhere.
COLUMNS = [
    "Handle",
    "Continent",
    "Score",
    "Automated",
    "Application",
    "Flags",
    "Status",
    "Applied",
    "Declared repo",
]

STATUS_LABEL = {
    "scored": "scored",
    "queued": "stuck — never scored",
    "error": "failed — parked for a human",
    "unparsable": "could not be read",
}


def _flag_keys(payload: str) -> str:
    import json

    try:
        flags = json.loads(payload).get("flags") or []
    except (json.JSONDecodeError, AttributeError):
        return ""
    return "; ".join(f.get("key", "").replace("_", " ") for f in flags)


def _split(payload: str) -> tuple[str, str]:
    import json

    try:
        d = json.loads(payload)
        return f'{float(d.get("automated_total", 0)):.2f}', f'{float(d.get("application_total", 0)):.2f}'
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return "", ""


def csv_for(db_path: str) -> str:
    """Every inbound as one row, ranked, with no contact detail anywhere."""
    import json

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        subs = conn.execute(
            "select handle, raw_handle, application_json, received_at, status, total"
            " from submissions"
        ).fetchall()
        # Newest score per handle: a handle can be re-scored, and the sheet
        # should show what stands now rather than the first attempt.
        payloads: dict[str, str] = {}
        for row in conn.execute(
            "select handle, payload from scores order by scored_at"
        ):
            payloads[row["handle"]] = row["payload"]
    finally:
        conn.close()

    rows = sorted(
        subs,
        key=lambda s: (s["status"] != "scored", s["total"] is None, -(s["total"] or 0)),
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    for s in rows:
        payload = payloads.get(s["handle"], "")
        automated, application = _split(payload) if payload else ("", "")
        try:
            app = json.loads(s["application_json"])
        except (json.JSONDecodeError, TypeError):
            app = {}
        w.writerow([
            s["handle"] or s["raw_handle"],
            app.get("region", ""),
            f'{s["total"]:.2f}' if s["total"] is not None else "",
            automated,
            application,
            _flag_keys(payload) if payload else "",
            STATUS_LABEL.get(s["status"], s["status"]),
            (s["received_at"] or "")[:16].replace("T", " "),
            app.get("declared_repo", ""),
        ])
    return buf.getvalue()
