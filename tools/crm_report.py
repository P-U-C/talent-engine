#!/usr/bin/env python3
"""Every inbound applicant on one page: score, notes, flags, and what went wrong.

Chad, 2026-08-19, on launch day: "I need a crm that will show all inbounds,
score, notes, issues. This will be able to be accessible for other stewards as
well."

The immediate reason it is needed: five applications arrived and three scored.
The other two failed on a GitHub 409 and sat in `queued` -- no score, no email,
no trace anywhere a human looks. An absent applicant looks exactly like an
applicant who never applied, which is the most expensive failure this system
has, because the two silent ones included the highest scorer of the round.
So this report leads with what is broken, not with what worked.

Contact details are withheld by default. That is not caution, it is the terms
the applicants accepted:

    Contact details -- email, name, and messaging handles -- are stored apart
    from everything scoreable and never appear in a score, snapshot, dossier,
    or public artefact.
    No unselected applicant is named publicly.

Pass --contacts to include them, and only for a file that stays on this box or
goes to a named steward. The default output is safe to share.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

DEFAULT_DB = os.path.expanduser("~/talent-engine-runtime/talent_engine.db")

# Anything not in this set is a person the pipeline did not finish with, and
# belongs at the top of the page rather than buried in a status column.
FINISHED = {"scored"}

STATUS_LABEL = {
    "scored": "scored",
    "queued": "stuck — never scored",
    "error": "failed — parked for a human",
    "unparsable": "could not be read",
}


def rows(conn, sql, args=()):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def collect(db_path: str) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        subs = rows(
            conn,
            "select submission_id, program, source, handle, raw_handle,"
            " application_json, received_at, status, run_id, total, concerns, error"
            " from submissions order by received_at",
        )
        contacts = {c["submission_id"]: c for c in rows(conn, "select * from contacts")}
        decisions = {d["handle"]: d for d in rows(conn, "select * from decisions")}
        cohort = {c["handle"]: c for c in rows(conn, "select * from cohort")}
        quarantine = defaultdict(list)
        for q in rows(conn, "select * from applicant_quarantine"):
            quarantine[q["handle"]].append(q)

        # The newest score per handle. A handle can be scored more than once --
        # a re-run, or a resubmission -- and the report should show what stands
        # now, not the first attempt.
        payloads: dict[str, dict] = {}
        for s in rows(conn, "select handle, payload, scored_at from scores order by scored_at"):
            try:
                payloads[s["handle"]] = {**json.loads(s["payload"]), "scored_at": s["scored_at"]}
            except json.JSONDecodeError:
                continue
    finally:
        conn.close()

    for sub in subs:
        try:
            sub["application"] = json.loads(sub["application_json"])
        except json.JSONDecodeError:
            sub["application"] = {}
        sub["contact"] = contacts.get(sub["submission_id"], {})
        sub["score"] = payloads.get(sub["handle"])
        sub["decision"] = decisions.get(sub["handle"])
        sub["cohort"] = cohort.get(sub["handle"])
        sub["quarantine"] = quarantine.get(sub["handle"], [])
    return {"submissions": subs}


def e(v) -> str:
    return html.escape(str(v or ""))


def when(ts: str) -> str:
    """`2026-08-19T20:32:00+00:00` reads as noise in a table. Trim to the minute."""
    return e((ts or "").replace("T", " ")[:16])


def bar(points: float, maximum: float) -> str:
    pct = 0 if not maximum else max(0.0, min(100.0, 100.0 * points / maximum))
    return (
        f'<div class="bar"><span style="width:{pct:.1f}%"></span></div>'
        f'<div class="barnum">{points:.1f}<span class="muted"> / {maximum:.0f}</span></div>'
    )


def render_score(score: dict) -> str:
    if not score:
        return ""
    out = ['<table class="dims">']
    for d in score.get("dimensions", []):
        notes = "".join(f"<li>{e(n)}</li>" for n in d.get("notes", []))
        ev = "".join(
            f'<li><a href="{e(x.get("url"))}">{e(x.get("claim"))}</a>'
            + (f' <span class="muted">{e(x.get("detail"))[:160]}</span>' if x.get("detail") else "")
            + "</li>"
            for x in d.get("evidence", [])[:4]
        )
        out.append(
            f'<tr><th>{e(d.get("key","").replace("_"," "))}</th>'
            f'<td class="barcell">{bar(float(d.get("points",0)), float(d.get("max_points",0)))}</td>'
            f'<td>{f"<ul class=notes>{notes}</ul>" if notes else ""}'
            f'{f"<ul class=ev>{ev}</ul>" if ev else ""}</td></tr>'
        )
    out.append("</table>")
    return "".join(out)


def render_flags(score: dict) -> str:
    flags = (score or {}).get("flags") or []
    if not flags:
        return '<p class="muted">No authenticity flags raised.</p>'
    items = []
    for f in flags:
        disc = f.get("discount")
        tail = (
            f' <span class="muted">(discounts {e(f.get("discounts_component"))} to {disc:.0%})</span>'
            if disc is not None and f.get("discounts_component")
            else ""
        )
        items.append(f'<li><b>{e(f.get("key","").replace("_"," "))}</b>{tail}<br>{e(f.get("message"))}</li>')
    return f'<ul class="flags">{"".join(items)}</ul>'


def render_contact(sub: dict, show: bool) -> str:
    c = sub.get("contact") or {}
    if not show:
        held = [k for k in ("email", "name", "telegram", "x", "discord") if c.get(k)]
        return (
            '<p class="muted">Contact withheld — '
            + (", ".join(held) + " on file" if held else "nothing on file")
            + ". The terms keep contact details out of any shared artefact.</p>"
        )
    bits = []
    if c.get("name"):
        bits.append(f'<b>{e(c["name"])}</b>')
    if c.get("email"):
        bits.append(f'<a href="mailto:{e(c["email"])}">{e(c["email"])}</a>')
    for label, key in (("Telegram", "telegram"), ("X", "x"), ("Discord", "discord")):
        if c.get(key):
            bits.append(f'{label} {e(c[key])}')
    return f'<p class="contact">{" · ".join(bits) or "nothing on file"}</p>'


# Column order mirrors the Pools CRM sheet the programme already runs on, so a
# steward reading both is not re-learning a layout. `Notes` is deliberately left
# empty: it is the steward's column, and this tool never writes into it.
CSV_COLUMNS = [
    "Handle", "Name", "Email", "Telegram", "X", "Continent", "Score",
    "Automated", "Application", "Flags", "Status", "Applied", "Declared repo",
    "Decision", "Notes",
]


def csv_rows(data: dict, show_contacts: bool) -> list[list[str]]:
    out = []
    order = sorted(
        data["submissions"],
        key=lambda s: (s["status"] != "scored", s["total"] is None, -(s["total"] or 0)),
    )
    for s in order:
        c = s["contact"] if show_contacts else {}
        sc = s["score"] or {}
        app = s["application"]
        flags = sc.get("flags") or []
        out.append([
            s["handle"] or s["raw_handle"],
            c.get("name", ""),
            c.get("email", ""),
            c.get("telegram", ""),
            c.get("x", ""),
            app.get("region", ""),
            f'{s["total"]:.2f}' if s["total"] is not None else "",
            f'{float(sc.get("automated_total", 0)):.2f}' if sc else "",
            f'{float(sc.get("application_total", 0)):.2f}' if sc else "",
            "; ".join(f.get("key", "").replace("_", " ") for f in flags),
            STATUS_LABEL.get(s["status"], s["status"]),
            (s["received_at"] or "")[:16].replace("T", " "),
            app.get("declared_repo", ""),
            (s["decision"] or {}).get("decision", ""),
            "",
        ])
    return out


def stat(label: str, value: str, tone: str = "") -> str:
    return (
        f'<div class="stat {tone}"><div class="statnum">{e(value)}</div>'
        f'<div class="statlab">{e(label)}</div></div>'
    )


def render(data: dict, show_contacts: bool) -> str:
    subs = data["submissions"]
    unfinished = [s for s in subs if s["status"] not in FINISHED]
    scored = sorted(
        (s for s in subs if s["status"] in FINISHED),
        key=lambda s: (s["total"] is None, -(s["total"] or 0)),
    )
    flagged = [s for s in scored if (s["score"] or {}).get("flags")]
    now = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    top = f'{scored[0]["total"]:.1f}' if scored and scored[0]["total"] is not None else "—"

    tiles = "".join([
        stat("inbound", str(len(subs))),
        stat("scored", str(len(scored)), "good"),
        stat("needs attention", str(len(unfinished)), "bad" if unfinished else "good"),
        stat("carrying flags", str(len(flagged)), "warn" if flagged else "good"),
        stat("highest score", top),
    ])

    if unfinished:
        items = "".join(
            f'<li><b>{e(s["handle"] or s["raw_handle"])}</b> — '
            f'{e(STATUS_LABEL.get(s["status"], s["status"]))}, applied {when(s["received_at"])}'
            + (f'<div class="mono">{e(s["error"])[:300]}</div>' if s["error"] else "")
            + "</li>"
            for s in unfinished
        )
        issues = (
            '<section class="panel bad"><h2>Needs attention</h2>'
            "<p>These people applied and the pipeline never finished with them. "
            "Nothing external retries a submission, so they stay here until "
            "someone acts. An applicant stuck here is invisible everywhere else — "
            "it looks exactly like nobody applied.</p>"
            f"<ul>{items}</ul></section>"
        )
    else:
        issues = (
            '<section class="panel good"><h2>Needs attention</h2>'
            "<p>Every inbound has been scored. Nothing is stuck.</p></section>"
        )

    # A card each is right for reading one person closely and wrong for
    # comparing twenty. The table is the review surface: one row per applicant,
    # every column sortable by eye, and each row jumps to its own card.
    trows = []
    for rank, s in enumerate(scored, 1):
        sc = s["score"] or {}
        nflags = len(sc.get("flags") or [])
        trows.append(
            f'<tr><td class="num">{rank}</td>'
            f'<td><a href="#a-{e(s["handle"])}">{e(s["handle"])}</a></td>'
            f'<td>{e((s["application"] or {}).get("region",""))}</td>'
            f'<td class="num strong">{(s["total"] or 0):.2f}</td>'
            f'<td class="num">{float(sc.get("automated_total",0)):.1f}</td>'
            f'<td class="num">{float(sc.get("application_total",0)):.1f}</td>'
            f'<td>{f"<span class=pill-warn>{nflags}</span>" if nflags else "<span class=dash>—</span>"}</td>'
            f'<td>{e((s["decision"] or {}).get("decision","")) or "<span class=dash>not decided</span>"}</td>'
            f'<td class="when">{when(s["received_at"])}</td></tr>'
        )
    for s in unfinished:
        trows.append(
            f'<tr class="row-bad"><td class="num">—</td>'
            f'<td>{e(s["handle"] or s["raw_handle"])}</td>'
            f'<td>{e((s["application"] or {}).get("region",""))}</td>'
            f'<td class="num" colspan="4">{e(STATUS_LABEL.get(s["status"], s["status"]))}</td>'
            f'<td><span class=dash>—</span></td>'
            f'<td class="when">{when(s["received_at"])}</td></tr>'
        )
    table = (
        '<section><h2>All inbound</h2><div class="scroll">'
        '<table class="grid"><thead><tr>'
        "<th>#</th><th>Handle</th><th>Continent</th><th>Score</th>"
        "<th>Auto</th><th>App</th><th>Flags</th><th>Decision</th><th>Applied</th>"
        f'</tr></thead><tbody>{"".join(trows)}</tbody></table></div></section>'
    )

    cards = []
    for rank, s in enumerate(scored, 1):
        app = s["application"]
        sc = s["score"] or {}
        badges = []
        if s["decision"]:
            badges.append(f'<span class="pill decision">{e(s["decision"]["decision"])}</span>')
        if s["cohort"]:
            badges.append('<span class="pill decision">in cohort</span>')
        for q in s["quarantine"]:
            badges.append(f'<span class="pill bad">quarantined: {e(q["reason"])}</span>')
        nflags = len(sc.get("flags") or [])
        if nflags:
            badges.append(f'<span class="pill warn">{nflags} flag{"s" if nflags > 1 else ""}</span>')
        if app.get("region"):
            badges.append(f'<span class="pill">{e(app["region"])}</span>')

        total = s["total"] if s["total"] is not None else 0.0
        split = (
            f'automated {float(sc.get("automated_total", 0)):.1f}'
            f' · application {float(sc.get("application_total", 0)):.1f}'
        ) if sc else ""
        plan = (app.get("build_plan") or "").strip()
        repo = (app.get("declared_repo") or "").strip()
        tone = "warn" if nflags else "good"

        cards.append(
            f"""<article class="card {tone}" id="a-{e(s['handle'])}">
  <header>
    <div class="who">
      <span class="rank">{rank}</span>
      <h3><a href="https://github.com/{e(s['handle'])}">{e(s['handle'])}</a></h3>
    </div>
    <div class="total">{total:.2f}<span class="outof">/100</span></div>
  </header>
  <div class="meta">applied {when(s['received_at'])} · via {e(s['source'])}{' · ' + e(split) if split else ''}</div>
  <div class="pills">{''.join(badges)}</div>
  {render_contact(s, show_contacts)}
  {f'<p class="repo">Declared repo <a href="{e(repo)}">{e(repo)}</a></p>' if repo else ''}
  {f'<details><summary>Build plan</summary><p>{e(plan)}</p></details>' if plan else ''}
  <h4>Where the score came from</h4>
  <div class="scroll">{render_score(sc)}</div>
  <h4>Flags and concerns</h4>
  {render_flags(sc)}
  {f'<p class="concerns">{e(s["concerns"])}</p>' if s['concerns'] else ''}
</article>"""
        )

    withheld = "" if show_contacts else (
        '<p class="note">Contact details are withheld from this copy. The terms '
        "applicants accepted keep email, name and messaging handles apart from "
        "anything scoreable, and out of any shared artefact. Handles and evidence "
        "links below are public GitHub activity.</p>"
    )

    return f"""<title>Prezenti Applicant Board</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&family=JetBrains+Mono:wght@400&display=swap">
<style>
  /* Palette lifted from prezenti.xyz's own stylesheet so this reads as part of
     the programme rather than a tool bolted onto it: dark forest, cream, light
     mint, the secondary green, and the orange CTA scale. Semantic colour is
     deliberately separate from the accent -- attention is orange, healthy is
     the brand green, and the mint is reserved for structure. */
  :root {{
    --forest:#112122; --cream:#fef4ee; --mint:#b4dbd4; --green:#346d6a;
    --orange:#eb4b24; --peach:#f9c7af;

    --bg:var(--cream); --fg:var(--forest);
    --muted:#5f6f6c;                      /* grey biased toward the green */
    --line:#e6d9d0;                       /* grey biased toward the cream */
    --card:#fffaf6; --raise:0 1px 2px rgba(17,33,34,.05);
    --accent:var(--green); --good:var(--green); --warn:#b4531f; --bad:var(--orange);
    --goodbg:#eaf2f0; --warnbg:#fdeee4; --badbg:#fde8e2;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg:#0d1718; --fg:#e9efed; --muted:#93a5a2; --line:#243231;
      --card:#132122; --raise:none;
      --accent:var(--mint); --good:var(--mint); --warn:var(--peach); --bad:#ff7a55;
      --goodbg:#16292a; --warnbg:#2b2019; --badbg:#2e1a15;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg:#0d1718; --fg:#e9efed; --muted:#93a5a2; --line:#243231;
    --card:#132122; --raise:none;
    --accent:var(--mint); --good:var(--mint); --warn:var(--peach); --bad:#ff7a55;
    --goodbg:#16292a; --warnbg:#2b2019; --badbg:#2e1a15;
  }}

  * {{ box-sizing:border-box; }}
  body {{
    background:var(--bg); color:var(--fg); margin:0; padding:2.5rem 1.25rem 6rem;
    font-family:"DM Sans",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
    font-size:16px; line-height:1.55;
  }}
  .wrap {{ max-width:64rem; margin:0 auto; display:flex; flex-direction:column; gap:2rem; }}
  h1,h2,h3 {{ font-family:Outfit,"DM Sans",ui-sans-serif,system-ui,sans-serif;
              text-wrap:balance; margin:0; }}
  h1 {{ font-size:2rem; font-weight:600; letter-spacing:-.02em; }}
  h2 {{ font-size:1.1rem; font-weight:600; margin-bottom:.4rem; }}
  h4 {{ font-family:Outfit,sans-serif; font-size:.72rem; font-weight:600;
        text-transform:uppercase; letter-spacing:.09em; color:var(--muted);
        margin:1.5rem 0 .5rem; }}
  a {{ color:var(--accent); text-underline-offset:.15em; }}
  a:focus-visible, summary:focus-visible {{
    outline:2px solid var(--accent); outline-offset:2px; border-radius:2px; }}
  .lede {{ color:var(--muted); margin:.35rem 0 0; max-width:62ch; }}
  .note {{ color:var(--muted); font-size:.85rem; max-width:62ch; margin:0; }}
  .mono {{ font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
           font-size:.75rem; color:var(--muted); word-break:break-all; margin-top:.35rem; }}

  /* Summary before detail: the five numbers that decide whether to read on. */
  .stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr)); gap:.75rem; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:.5rem;
           padding:.85rem 1rem; box-shadow:var(--raise); }}
  .statnum {{ font-family:Outfit,sans-serif; font-size:1.75rem; font-weight:600;
              line-height:1.1; font-variant-numeric:tabular-nums; }}
  .statlab {{ font-size:.75rem; text-transform:uppercase; letter-spacing:.07em;
              color:var(--muted); margin-top:.15rem; }}
  .stat.good .statnum {{ color:var(--good); }}
  .stat.warn .statnum {{ color:var(--warn); }}
  .stat.bad  .statnum {{ color:var(--bad); }}

  .panel {{ border:1px solid var(--line); border-left:4px solid var(--line);
            border-radius:.5rem; padding:1.1rem 1.3rem; background:var(--card); }}
  .panel.bad {{ border-color:var(--bad); background:var(--badbg); }}
  .panel.good {{ border-left-color:var(--good); }}
  .panel p {{ margin:0 0 .6rem; max-width:62ch; }}
  .panel ul {{ margin:0; padding-left:1.1rem; }}
  .panel li {{ margin-bottom:.5rem; }}

  .card {{ background:var(--card); border:1px solid var(--line);
           border-left:4px solid var(--good); border-radius:.5rem;
           padding:1.2rem 1.4rem; box-shadow:var(--raise); }}
  .card.warn {{ border-left-color:var(--warn); }}
  .card header {{ display:flex; align-items:center; justify-content:space-between; gap:1rem; }}
  .who {{ display:flex; align-items:baseline; gap:.6rem; min-width:0; }}
  .rank {{ font-family:Outfit,sans-serif; font-size:.8rem; font-weight:600;
           color:var(--muted); font-variant-numeric:tabular-nums; }}
  .card h3 {{ font-size:1.25rem; font-weight:600; overflow-wrap:anywhere; }}
  .total {{ font-family:Outfit,sans-serif; font-size:1.7rem; font-weight:600;
            font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .outof {{ font-size:.85rem; color:var(--muted); font-weight:400; margin-left:.15rem; }}
  .meta {{ color:var(--muted); font-size:.82rem; margin:.2rem 0 .55rem; }}
  .pills {{ display:flex; flex-wrap:wrap; gap:.35rem; }}
  .pill {{ font-size:.72rem; font-weight:500; border:1px solid var(--line);
           border-radius:1rem; padding:.12rem .6rem; color:var(--muted); }}
  .pill.decision {{ border-color:var(--good); color:var(--good); }}
  .pill.warn {{ border-color:var(--warn); color:var(--warn); background:var(--warnbg); }}
  .pill.bad {{ border-color:var(--bad); color:var(--bad); background:var(--badbg); }}
  .contact, .repo {{ font-size:.88rem; margin:.55rem 0 0; }}

  .scroll {{ overflow-x:auto; }}
  table.grid {{ width:100%; border-collapse:collapse; font-size:.88rem;
                background:var(--card); border:1px solid var(--line);
                border-radius:.5rem; overflow:hidden; }}
  table.grid th {{ text-align:left; font-family:Outfit,sans-serif; font-size:.72rem;
                   font-weight:600; text-transform:uppercase; letter-spacing:.07em;
                   color:var(--muted); padding:.6rem .7rem; white-space:nowrap;
                   border-bottom:1px solid var(--line); }}
  table.grid td {{ padding:.55rem .7rem; border-bottom:1px solid var(--line);
                   white-space:nowrap; }}
  table.grid tr:last-child td {{ border-bottom:0; }}
  table.grid td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  table.grid td.strong {{ font-weight:600; font-size:1rem; }}
  table.grid td.when {{ color:var(--muted); font-size:.8rem; }}
  table.grid tr.row-bad td {{ background:var(--badbg); }}
  .dash {{ color:var(--muted); }}
  .pill-warn {{ display:inline-block; min-width:1.3rem; text-align:center;
                font-size:.72rem; font-weight:600; border-radius:1rem;
                padding:.05rem .45rem; color:var(--warn);
                background:var(--warnbg); border:1px solid var(--warn); }}
  table.dims {{ width:100%; border-collapse:collapse; }}
  table.dims th {{ text-align:left; font-weight:500; width:11rem; vertical-align:top;
                   padding:.5rem .8rem .5rem 0; border-top:1px solid var(--line); }}
  table.dims td {{ vertical-align:top; padding:.5rem 0; border-top:1px solid var(--line); }}
  td.barcell {{ width:10rem; padding-right:1rem; }}
  .bar {{ background:var(--line); border-radius:99px; height:6px; overflow:hidden; }}
  .bar span {{ display:block; height:100%; background:var(--accent); border-radius:99px; }}
  .barnum {{ font-size:.78rem; font-variant-numeric:tabular-nums; margin-top:.2rem; }}
  ul.notes, ul.ev, ul.flags {{ margin:.15rem 0 .15rem 1rem; padding:0; font-size:.84rem; }}
  ul.ev {{ color:var(--muted); }}
  ul.flags {{ margin-left:1.1rem; }}
  ul.flags li {{ margin-bottom:.55rem; }}
  .concerns {{ font-size:.88rem; border-left:3px solid var(--line);
               padding-left:.85rem; color:var(--muted); }}
  details summary {{ cursor:pointer; font-size:.86rem; color:var(--muted); margin-top:.5rem; }}
  details p {{ max-width:62ch; font-size:.9rem; }}

  @media (prefers-reduced-motion:reduce) {{ * {{ animation:none !important; transition:none !important; }} }}
  @media (max-width:620px) {{
    body {{ padding:1.5rem 1rem 4rem; }}
    h1 {{ font-size:1.6rem; }}
    table.dims th, td.barcell {{ width:auto; }}
    table.dims, table.dims tbody, table.dims tr, table.dims th, table.dims td {{ display:block; }}
    table.dims td {{ border-top:0; }}
    table.dims th {{ padding-bottom:.15rem; }}
  }}
</style>
<div class="wrap">
  <header>
    <h1>Prezenti Applicant Board</h1>
    <p class="lede">AI Builder Sponsorships (Trial) · every inbound, what it
    scored, and what the scorer had to say about it. Generated {now}; nothing
    here is hand-maintained.</p>
  </header>
  <section class="stats">{tiles}</section>
  {issues}
  {table}
  <section>
    <h2>Applicants in detail</h2>
    {withheld}
  </section>
  {''.join(cards)}
</div>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=os.path.expanduser("~/talent-engine-runtime/crm.html"))
    ap.add_argument(
        "--csv",
        help="also write a spreadsheet of the same data, for the stewards' sheet",
    )
    ap.add_argument(
        "--contacts",
        action="store_true",
        help="include applicant contact details; only for a file that stays on "
        "this box or goes to a named steward",
    )
    args = ap.parse_args()

    data = collect(args.db)
    with open(args.out, "w") as fh:
        fh.write(render(data, args.contacts))
    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(CSV_COLUMNS)
            w.writerows(csv_rows(data, args.contacts))
        print(f"wrote {args.csv}")
    n = len(data["submissions"])
    stuck = sum(1 for s in data["submissions"] if s["status"] not in FINISHED)
    print(f"wrote {args.out}: {n} inbound, {stuck} needing attention"
          f"{' (with contacts)' if args.contacts else ''}")


if __name__ == "__main__":
    main()
