"""A CSV of scouted candidates and how to reach them, for the stewards' sheet.

The nightly digest is a message: it arrives, it is read, it scrolls away. What
an operator working a lead list needs is the opposite -- a surface that
persists, that says who has already been contacted, and that does not lose a
name because it was found on a busy day.

So this is the scout's output as a table, next to the applicants' one, with the
same access model: a token in the path, pulled by IMPORTDATA into the sheet
inside the Prezenti workspace.

**Order is append-only and that is a contract, not an implementation detail.**
The stewards' outreach tab sits beside this one and is typed by hand; if a row
ever moved, every note beside it would come to describe the wrong person. Rows
therefore come out oldest-first by discovery, ties broken by handle, so a new
candidate can only ever appear at the bottom.

Everyone here is a public GitHub profile that has never applied to anything.
Nothing about them was inferred: the X handle is one they published themselves,
and the column beside it says which page it was published on.
"""

from __future__ import annotations

import csv
import io
import sqlite3

COLUMNS = [
    "Handle",          # the join key, first, for the same reason as the scores feed
    "X",
    "X source",
    "Other socials",
    "Public email",
    "Score",
    "Channels",
    "First seen",
    "Applied",
    "Name",
    "Location",
    "GitHub",
    "Site",
]

# One row per scouted handle: their best score if the scout spent one on them,
# whether they have since applied, and whatever the recon pass turned up.
SQL = """
SELECT sc.handle,
       sc.first_seen,
       sc.channels,
       (SELECT MAX(total) FROM scores s WHERE s.handle = sc.handle) AS total,
       (SELECT COUNT(*) FROM submissions su WHERE su.handle = sc.handle) AS applied,
       r.x_handle, r.x_source, r.name, r.location, r.blog, r.socials, r.email, r.checked_at
  FROM scouted sc
  LEFT JOIN profile_recon r ON r.handle = sc.handle
 WHERE sc.program = ?
 ORDER BY sc.first_seen ASC, sc.handle ASC
"""


def csv_for(db_path: str, program: str, scored_only: bool = True) -> str:
    """Scouted candidates in discovery order, oldest first.

    `scored_only` is the default because the raw scout returns hundreds of
    handles a night and an unfiltered list is homework rather than a lead list.
    The scored ones are those the pipeline thought were worth a look.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(SQL, (program,)).fetchall()
    finally:
        conn.close()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    for r in rows:
        if scored_only and r["total"] is None:
            continue
        w.writerow([
            r["handle"],
            f'@{r["x_handle"]}' if r["x_handle"] else "",
            r["x_source"] or ("not found" if r["checked_at"] else "not looked up yet"),
            r["socials"] or "",
            r["email"] or "",
            f'{r["total"]:.2f}' if r["total"] is not None else "",
            (r["channels"] or "").replace(",", "; "),
            (r["first_seen"] or "")[:10],
            "applied" if r["applied"] else "",
            r["name"] or "",
            r["location"] or "",
            f'https://github.com/{r["handle"]}',
            r["blog"] or "",
        ])
    return buf.getvalue()
