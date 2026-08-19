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
*   Rows come out in arrival order, not score order, because this tab is read
    beside the one Tally writes and the two have to agree line for line.
    Standing travels as a Rank column instead.
*   The path carries a random token because IMPORTDATA fetches anonymously, so
    the URL is the only thing standing between this and the open web. Scores and
    public GitHub handles are not secrets, but "no unselected applicant is named
    publicly" is a promise, and an unguessable URL is what keeps it.
"""

from __future__ import annotations

import csv
import io
import sqlite3

# Submission ID leads because VLOOKUP matches on the FIRST column of its range
# and nothing else. Putting UID in front of it silently broke every lookup in
# the stewards' sheet -- the formula went looking for a submission id in a
# column of references and matched nothing. The join key comes first; where the
# UID appears in their sheet is a matter for their own column order.
# Everything the Tally tab already holds is left out. Continent, submitted-at and
# the declared repo are all columns over there already, and duplicating them
# invites the two copies to disagree. Submission ID leads because it is the
# join key: it appears in column A of the Tally tab, it is exact, and it does
# not depend on the two tabs staying in the same order.
#
# Handle is worth carrying even though Tally captured one, because this is the
# NORMALISED handle the engine actually scored. Applicants typed "Gideonnut",
# "Trovic1" and a full github.com URL; matching on what they typed would fail
# on exactly the rows a steward most wants to look up.
COLUMNS = [
    "Submission ID",
    "UID",
    "Rank",
    "Handle",
    "Score",
    "Automated",
    "Application",
    "Flags",
    "Status",
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
    """Every inbound as one row, in arrival order, with no contact detail."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        subs = conn.execute(
            "select s.submission_id, s.handle, s.raw_handle, s.received_at,"
            " s.status, s.total, coalesce(u.uid, '') as uid"
            " from submissions s"
            " left join applicant_uids u on u.submission_id = s.submission_id"
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

    # Arrival order, matching the tab Tally writes. The sheet is read beside
    # that tab, so row N here has to be the same person as row N there --
    # ranking the feed instead made the two tabs disagree line for line, which
    # is worse than useless when you are reading across.
    rows = sorted(subs, key=lambda s: (s["received_at"] or ""))

    # Standing still matters, so it travels as a column rather than as the sort
    # order. Only scored applicants have one.
    ranked = sorted(
        (s for s in subs if s["status"] == "scored" and s["total"] is not None),
        key=lambda s: -s["total"],
    )
    rank_of = {s["handle"]: i for i, s in enumerate(ranked, 1)}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    for s in rows:
        payload = payloads.get(s["handle"], "")
        automated, application = _split(payload) if payload else ("", "")
        w.writerow([
            s["submission_id"],
            s["uid"],
            rank_of.get(s["handle"], ""),
            s["handle"] or s["raw_handle"],
            f'{s["total"]:.2f}' if s["total"] is not None else "",
            automated,
            application,
            _flag_keys(payload) if payload else "",
            STATUS_LABEL.get(s["status"], s["status"]),
        ])
    return buf.getvalue()
