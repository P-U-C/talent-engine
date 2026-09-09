#!/usr/bin/env python3
"""One applicant at a time, in the order a person can actually judge them.

Why this is not the board
-------------------------
The board answers "what is in the pipeline" -- a table, sorted, scannable, and
correct. It is useless for the thing Chad actually has to do, which is read
thirty-two applications and form a view on each. His words: the spreadsheet is
"no good to do that as a human". A row is a summary of a person; you cannot
read a summary and decide to give someone four months of runway.

So this page shows exactly one applicant, filling the screen, and gets out of
the way. Arrow keys or j/k to move. A verdict key if he wants to record a gut
call as he goes, kept in his own browser and never sent anywhere.

**The order of the page is an argument.** The 2026-08-27 audit found the score
is 75% self-attestable volume, that the written application is worth literally
zero points, and that a thirty-seven-character build plan outranked five people.
So the build plan comes first, at full length, in type meant for reading. What
they have actually shipped comes second. Who else has merged their work comes
third. The score comes LAST, small, at the bottom -- because it is the least
trustworthy thing on the page and putting it at the top makes everything above
it read as justification.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crm_report import DEFAULT_DB, collect, e, render_flags, render_score, when  # noqa: E402

SHORTLIST_MULTIPLIER = 3
SEATS = 5


def dimension(score: dict | None, key: str) -> dict:
    for d in (score or {}).get("dimensions", []) or []:
        if d.get("key") == key:
            return d
    return {}


def evidence_list(score: dict | None, key: str, limit: int = 8) -> str:
    items = dimension(score, key).get("evidence") or []
    if not items:
        return ""
    out = []
    for item in items[:limit]:
        claim = e(item.get("claim"))
        detail = e(item.get("detail"))
        url = item.get("url")
        label = f'<a href="{e(url)}">{claim}</a>' if url else claim
        out.append(f'<li>{label}{f" <span class=sub>{detail}</span>" if detail else ""}</li>')
    return "<ul class=ev>" + "".join(out) + "</ul>"


def paragraphs(text: str) -> str:
    """Preserve the applicant's own paragraphing. They wrote it in paragraphs."""
    blocks = [b.strip() for b in str(text or "").replace("\r", "").split("\n\n")]
    return "".join(f"<p>{e(b)}</p>" for b in blocks if b) or '<p class="sub">Nothing written.</p>'


def card(index: int, total: int, sub: dict) -> str:
    app = sub.get("application") or {}
    score = sub.get("score")
    total_points = float(sub.get("total") or 0)
    rank = index + 1
    shortlisted = rank <= SEATS * SHORTLIST_MULTIPLIER

    external = dimension(score, "external_validation")
    ext_points = float(external.get("points") or 0)
    ext_body = evidence_list(score, "external_validation") or (
        '<p class="warn-note">Nobody outside has merged or reviewed any of this. '
        "Every point on this page was awarded for work nobody else has accepted.</p>"
    )

    concerns = str(sub.get("concerns") or "").strip()
    concerns_html = (
        f'<section class="block concerns"><h2>What the scorer flagged</h2><p>{e(concerns)}</p></section>'
        if concerns else ""
    )

    plan = str(app.get("build_plan") or "")
    context = str(app.get("context_statement") or "")
    factors = app.get("context_factors") or []
    if isinstance(factors, str):
        factors = [factors]
    factor_html = (
        '<p class="chips">' + "".join(f"<span class=chip>{e(f)}</span>" for f in factors) + "</p>"
        if factors else ""
    )
    repo = str(app.get("declared_repo") or "").strip()
    referrer = str(app.get("referrer_name") or "").strip()

    return f"""
<article class="card" data-i="{index}" data-handle="{e(sub.get('handle'))}" hidden>
  <header class="cardhead">
    <div>
      <h1><a href="https://github.com/{e(sub.get('handle'))}">{e(sub.get('handle'))}</a></h1>
      <p class="meta"><span class="uid">{e(sub.get('uid'))}</span> · applied {e(when(sub.get('received_at')))}
        · {e(app.get('region') or 'region not given')}
        {'· referred by ' + e(referrer) if referrer else ''}</p>
    </div>
    <div class="scorebox {'in' if shortlisted else 'out'}">
      <div class="rank">#{rank}<span class="of"> of {total}</span></div>
      <div class="pts">{total_points:.1f}<span class="of">/100</span></div>
      <div class="cut">{'inside the shortlist' if shortlisted else 'below the line'}</div>
    </div>
  </header>

  <section class="block plan">
    <h2>What they say they will build <span class="sub">— {len(plan.split())} words</span></h2>
    {paragraphs(plan)}
    {f'<p class="repo">Declared repo <a href="{e(repo)}">{e(repo)}</a></p>' if repo else ''}
  </section>

  <section class="block">
    <h2>Their situation <span class="sub">— in their words</span></h2>
    {paragraphs(context)}
    {factor_html}
  </section>

  <section class="block">
    <h2>What they have actually shipped</h2>
    {evidence_list(score, 'shipping_agency') or '<p class="sub">No original repositories in the window.</p>'}
  </section>

  <section class="block {'' if ext_points else 'thin'}">
    <h2>Who else has merged their work <span class="sub">— {ext_points:.1f} of 10</span></h2>
    {ext_body}
  </section>

  {concerns_html}

  <details class="block">
    <summary>The score, and where it came from</summary>
    {render_score(score) if score else '<p class="sub">Not scored.</p>'}
    {render_flags(score) if score else ''}
  </details>
</article>"""


def render(data: dict) -> str:
    subs = [s for s in data["submissions"] if s.get("status") == "scored"]
    subs.sort(key=lambda s: -(float(s.get("total") or 0)))
    total = len(subs)
    cards = "".join(card(i, total, s) for i, s in enumerate(subs))
    handles = json.dumps([s.get("handle") for s in subs])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>Read the applicants</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&family=JetBrains+Mono:wght@400&display=swap">
<style>
  :root {{
    --forest:#112122; --cream:#fef4ee; --mint:#b4dbd4; --green:#346d6a;
    --orange:#eb4b24; --peach:#f9c7af;
    --bg:var(--cream); --fg:var(--forest); --muted:#5f6f6c; --line:#e6d9d0;
    --card:#fffaf6; --accent:var(--green); --good:var(--green);
    --warn:#b4531f; --bad:var(--orange); --warnbg:#fdeee4; --goodbg:#eaf2f0;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg:#0d1718; --fg:#e9efed; --muted:#93a5a2; --line:#243231; --card:#132122;
      --accent:var(--mint); --good:var(--mint); --warn:var(--peach); --bad:#ff7a55;
      --warnbg:#2b2019; --goodbg:#16292a;
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font-size:17px; line-height:1.6;
         font-family:"DM Sans",ui-sans-serif,system-ui,-apple-system,sans-serif; }}
  h1,h2,summary {{ font-family:Outfit,"DM Sans",sans-serif; margin:0; text-wrap:balance; }}
  a {{ color:var(--accent); text-underline-offset:.15em; }}

  /* The rail is fixed because the one thing that must never be hunted for is
     "where am I and how do I get to the next one". */
  .rail {{ position:sticky; top:0; z-index:5; background:var(--bg);
           border-bottom:1px solid var(--line); padding:.6rem 1rem .5rem; }}
  .railrow {{ max-width:52rem; margin:0 auto; display:flex; align-items:center; gap:.75rem; }}
  .count {{ font-family:Outfit,sans-serif; font-weight:600; font-variant-numeric:tabular-nums;
            white-space:nowrap; }}
  .track {{ flex:1; height:5px; background:var(--line); border-radius:99px; overflow:hidden; }}
  .fill {{ height:100%; width:0; background:var(--accent); }}
  button {{ font:inherit; font-family:Outfit,sans-serif; font-size:.85rem; cursor:pointer;
            border:1px solid var(--line); background:var(--card); color:var(--fg);
            border-radius:.4rem; padding:.3rem .7rem; }}
  button:hover {{ border-color:var(--accent); }}
  button[aria-pressed="true"] {{ background:var(--accent); color:var(--bg); border-color:var(--accent); }}
  .verdicts {{ display:flex; gap:.35rem; }}
  .hint {{ max-width:52rem; margin:.35rem auto 0; color:var(--muted); font-size:.78rem; }}

  main {{ max-width:52rem; margin:0 auto; padding:1.5rem 1rem 6rem; }}
  .cardhead {{ display:flex; justify-content:space-between; align-items:flex-start;
               gap:1.5rem; padding-bottom:1rem; border-bottom:1px solid var(--line); }}
  h1 {{ font-size:1.9rem; font-weight:600; letter-spacing:-.02em; overflow-wrap:anywhere; }}
  .meta {{ color:var(--muted); font-size:.85rem; margin:.25rem 0 0; }}
  .uid {{ font-family:"JetBrains Mono",ui-monospace,monospace; font-size:.78rem; }}
  .scorebox {{ text-align:right; white-space:nowrap; }}
  .rank {{ font-family:Outfit,sans-serif; font-weight:600; font-size:1.05rem; }}
  .pts {{ font-family:Outfit,sans-serif; font-size:1.9rem; font-weight:600; line-height:1.05;
          font-variant-numeric:tabular-nums; }}
  .of {{ font-size:.8rem; color:var(--muted); font-weight:400; }}
  .cut {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.07em; margin-top:.15rem; }}
  .scorebox.in .cut {{ color:var(--good); }}
  .scorebox.out .cut {{ color:var(--warn); }}

  .block {{ margin:2rem 0 0; }}
  .block h2 {{ font-size:.78rem; font-weight:600; text-transform:uppercase; letter-spacing:.09em;
               color:var(--muted); margin-bottom:.6rem; }}
  .sub {{ color:var(--muted); font-weight:400; text-transform:none; letter-spacing:0; }}
  /* The build plan is the point of the page, so it gets the reading measure. */
  .plan p {{ font-size:1.06rem; max-width:64ch; margin:0 0 .9rem; }}
  .block p {{ max-width:66ch; margin:0 0 .8rem; }}
  .repo {{ font-size:.9rem; }}
  ul.ev {{ margin:0; padding-left:1.1rem; }}
  ul.ev li {{ margin-bottom:.45rem; }}
  .thin {{ border-left:3px solid var(--warn); padding-left:.9rem; }}
  .warn-note {{ color:var(--warn); }}
  .concerns {{ border-left:3px solid var(--line); padding-left:.9rem; }}
  .chips {{ display:flex; flex-wrap:wrap; gap:.35rem; }}
  .chip {{ font-size:.75rem; border:1px solid var(--line); border-radius:1rem;
           padding:.1rem .6rem; color:var(--muted); }}
  details summary {{ cursor:pointer; color:var(--muted); font-size:.8rem;
                     text-transform:uppercase; letter-spacing:.09em; font-weight:600; }}
  details[open] summary {{ margin-bottom:.8rem; }}
  table.dims {{ width:100%; border-collapse:collapse; font-size:.9rem; }}
  table.dims th {{ text-align:left; font-weight:500; width:11rem; vertical-align:top;
                   padding:.45rem .8rem .45rem 0; border-top:1px solid var(--line); }}
  table.dims td {{ vertical-align:top; padding:.45rem 0; border-top:1px solid var(--line); }}
  .bar {{ background:var(--line); border-radius:99px; height:6px; overflow:hidden; }}
  .bar span {{ display:block; height:100%; background:var(--accent); }}
  td.barcell {{ width:9rem; padding-right:1rem; }}
  .barnum {{ font-size:.78rem; font-variant-numeric:tabular-nums; margin-top:.2rem; }}
  ul.flags, ul.notes {{ margin:.2rem 0 .2rem 1rem; padding:0; font-size:.86rem; }}
  [hidden] {{ display:none !important; }}

  /* The tally is the reason to have kept verdicts at all. */
  #tally {{ margin-top:2rem; }}
  #tally table {{ border-collapse:collapse; width:100%; font-size:.9rem; }}
  #tally td, #tally th {{ text-align:left; padding:.35rem .6rem .35rem 0;
                          border-bottom:1px solid var(--line); }}
  @media (max-width:620px) {{
    body {{ font-size:16px; }}
    .cardhead {{ flex-direction:column; gap:.6rem; }}
    .scorebox {{ text-align:left; }}
  }}
</style>
</head>
<body>
<div class="rail">
  <div class="railrow">
    <span class="count" id="count">1 / {total}</span>
    <span class="track"><span class="fill" id="fill"></span></span>
    <button id="prev" type="button">‹ prev</button>
    <button id="next" type="button">next ›</button>
    <span class="verdicts">
      <button data-v="yes" type="button">yes</button>
      <button data-v="maybe" type="button">maybe</button>
      <button data-v="no" type="button">no</button>
    </span>
    <button id="showtally" type="button">tally</button>
  </div>
  <p class="hint">← → or j / k to move · 1 yes · 2 maybe · 3 no · verdicts stay in this browser only</p>
</div>
<main id="main">
{cards}
<section id="tally" hidden><h2>Your verdicts so far</h2><div id="tallybody"></div></section>
</main>
<script>
(function () {{
  "use strict";
  var handles = {handles};
  var cards = Array.prototype.slice.call(document.querySelectorAll(".card"));
  var at = 0, KEY = "prezenti-reader-verdicts";
  var store = {{}};
  try {{ store = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (err) {{ store = {{}}; }}

  function save() {{
    try {{ localStorage.setItem(KEY, JSON.stringify(store)); }} catch (err) {{ /* private mode */ }}
  }}
  function show(i) {{
    if (i < 0) i = 0;
    if (i > cards.length - 1) i = cards.length - 1;
    cards.forEach(function (c, n) {{ c.hidden = n !== i; }});
    at = i;
    document.getElementById("count").textContent = (i + 1) + " / " + cards.length;
    document.getElementById("fill").style.width = ((i + 1) / cards.length * 100) + "%";
    var mine = store[handles[i]] || "";
    document.querySelectorAll("[data-v]").forEach(function (b) {{
      b.setAttribute("aria-pressed", b.dataset.v === mine ? "true" : "false");
    }});
    document.getElementById("tally").hidden = true;
    window.scrollTo({{ top: 0, behavior: "instant" }});
    try {{ location.hash = handles[i]; }} catch (err) {{ /* ignore */ }}
  }}
  function verdict(v) {{
    if (store[handles[at]] === v) delete store[handles[at]]; else store[handles[at]] = v;
    save();
    show(at);
  }}
  function tally() {{
    var order = {{ yes: 0, maybe: 1, no: 2 }};
    var marked = handles.filter(function (h) {{ return store[h]; }});
    marked.sort(function (a, b) {{ return order[store[a]] - order[store[b]]; }});
    var body = document.getElementById("tallybody");
    if (!marked.length) {{ body.innerHTML = "<p>Nothing marked yet.</p>"; }}
    else {{
      body.innerHTML = "<table><tr><th>handle</th><th>call</th></tr>" + marked.map(function (h) {{
        return "<tr><td>" + h + "</td><td>" + store[h] + "</td></tr>";
      }}).join("") + "</table><p>" + marked.length + " of " + handles.length + " marked.</p>";
    }}
    cards.forEach(function (c) {{ c.hidden = true; }});
    document.getElementById("tally").hidden = false;
  }}

  document.getElementById("prev").onclick = function () {{ show(at - 1); }};
  document.getElementById("next").onclick = function () {{ show(at + 1); }};
  document.getElementById("showtally").onclick = tally;
  document.querySelectorAll("[data-v]").forEach(function (b) {{
    b.onclick = function () {{ verdict(b.dataset.v); }};
  }});
  document.addEventListener("keydown", function (ev) {{
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    var tag = (ev.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") return;
    if (ev.key === "ArrowRight" || ev.key === "j") {{ show(at + 1); ev.preventDefault(); }}
    else if (ev.key === "ArrowLeft" || ev.key === "k") {{ show(at - 1); ev.preventDefault(); }}
    else if (ev.key === "1") verdict("yes");
    else if (ev.key === "2") verdict("maybe");
    else if (ev.key === "3") verdict("no");
  }});

  var start = handles.indexOf((location.hash || "").replace("#", ""));
  show(start > -1 ? start : 0);
}}());
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=os.path.expanduser("~/talent-engine-runtime/reader.html"))
    args = ap.parse_args()
    page = render(collect(args.db))
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(page)
    os.replace(tmp, args.out)
    print(f"{args.out} ({os.path.getsize(args.out):,} bytes)")


if __name__ == "__main__":
    main()
