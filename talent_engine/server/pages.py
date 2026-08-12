"""The public page, rendered from an explicit route table.

There is no path joining anywhere in here. A request path is looked up in a
dict of exact strings, and a miss is a 404. Directory traversal is not
defended against; it is unrepresentable, which is the only version of that
defence worth having on a host that also holds credentials.

The form itself stays on Tally, in an iframe. Nothing a member of the public
types ever reaches this process — the only thing that arrives here is a signed
webhook from Tally's servers after the fact.
"""

from __future__ import annotations

import html
import os

REPO_URL = "https://github.com/P-U-C/talent-engine"

PAGE_CSS = """
:root {
  --ink: #14161a; --muted: #5b6470; --line: #e2e5ea;
  --bg: #fbfbfc; --accent: #1f4fd8; --card: #ffffff;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ink: #e9ecf1; --muted: #9aa3b0; --line: #262b33;
    --bg: #0d0f12; --accent: #7fa2ff; --card: #14171c;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 46rem; margin: 0 auto; padding: 4rem 1.5rem 6rem; }
h1 { font-size: 2.1rem; line-height: 1.2; letter-spacing: -0.02em; margin: 0 0 1rem; }
h2 { font-size: 1.15rem; letter-spacing: -0.01em; margin: 3rem 0 0.75rem; }
p { margin: 0 0 1rem; }
.lede { font-size: 1.15rem; color: var(--muted); margin-bottom: 2.5rem; }
a { color: var(--accent); }
ul { padding-left: 1.1rem; margin: 0 0 1rem; }
li { margin-bottom: 0.5rem; }
.card {
  background: var(--card); border: 1px solid var(--line);
  border-radius: 10px; padding: 1.25rem 1.4rem; margin: 1.5rem 0;
}
code {
  font: 0.875em ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  background: rgba(127,127,127,0.12); padding: 0.15em 0.4em; border-radius: 4px;
}
pre {
  background: var(--card); border: 1px solid var(--line); border-radius: 8px;
  padding: 1rem; overflow-x: auto; font-size: 0.85rem;
}
pre code { background: none; padding: 0; }
.form-frame {
  width: 100%; min-height: 42rem; border: 1px solid var(--line);
  border-radius: 10px; background: var(--card);
}
footer {
  margin-top: 4rem; padding-top: 1.5rem; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 0.9rem;
}
"""


def _embed(form_id: str) -> str:
    """The Tally iframe, or an honest placeholder when no form is configured."""
    if not form_id:
        return (
            '<div class="card"><p><strong>The application form is not connected '
            "yet.</strong> Set <code>TALLY_FORM_ID</code> on the intake service "
            "and this section becomes the form.</p></div>"
        )
    fid = html.escape(form_id, quote=True)
    return (
        f'<iframe class="form-frame" src="https://tally.so/embed/{fid}'
        '?alignLeft=1&hideTitle=1&transparentBackground=1&dynamicHeight=1" '
        'loading="lazy" title="Application form"></iframe>'
    )


def landing_page(program_name: str, form_id: str) -> bytes:
    program = html.escape(program_name)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{program} — apply</title>
<meta name="description" content="Sponsorship for people who ship. Scored on
public code activity against a rubric you can read and reproduce.">
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="wrap">

<h1>Sponsorship for people who ship</h1>
<p class="lede">We back builders on evidence of what they have actually
shipped — not on where they studied, who they know, or how many stars a
repository has.</p>

<h2>How you are assessed</h2>
<p>Your public code activity is scored against a fixed rubric. Four signals
carry most of the weight:</p>
<ul>
  <li><strong>Origination.</strong> You create things that did not exist.
      Forking is free; originating is not.</li>
  <li><strong>Finishing.</strong> Most side projects die around commit three.
      Releases, documentation, a deployed URL — the last ten percent, the part
      with no dopamine in it.</li>
  <li><strong>Cadence.</strong> You keep showing up. Distinct weeks of
      activity, which is much harder to inflate than a commit count.</li>
  <li><strong>Acceptance.</strong> Other people merged your work, across
      several different projects.</li>
</ul>
<p>Stars and follower counts are not scored at any weight. They measure
access, and access is exactly what this is built to look past.</p>

<div class="card">
<p><strong>You can check our work.</strong> The rubric is published in full,
along with the code that applies it. Clone it and reproduce your own score:</p>
<pre><code>git clone {REPO_URL}
cd talent-engine
talent-engine score --handles YOUR_GITHUB_HANDLE</code></pre>
<p>If a number looks wrong to you, you can show us exactly where — which is
the point of publishing it. Every score comes with linked evidence for each
component; a score with no evidence behind it cannot be produced.</p>
</div>

<h2>What we collect</h2>
<p>Public code activity only. Nothing about your background is inferred —
there is nowhere in the system to record an inferred trait. Anything about
your circumstances enters because you chose to tell us. Your contact details
are stored separately from everything used for assessment, and never appear in
an assessment record.</p>

<h2>Apply</h2>
{_embed(form_id)}

<footer>
<p>Scoring engine: <a href="{REPO_URL}">P-U-C/talent-engine</a> — open source,
including the rubric and the checks that flag manipulated profiles.</p>
</footer>

</div>
</body>
</html>
""".encode()


def routes(program_name: str, form_id: str | None = None) -> dict[str, tuple[str, bytes]]:
    """Exact path -> (content type, body). Anything not in here is a 404."""
    form_id = form_id if form_id is not None else os.environ.get("TALLY_FORM_ID", "")
    page = landing_page(program_name, form_id)
    return {
        "/": ("text/html; charset=utf-8", page),
        "/apply": ("text/html; charset=utf-8", page),
    }
