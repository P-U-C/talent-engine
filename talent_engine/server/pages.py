"""The public page, rendered from an explicit route table.

There is no path joining anywhere in here. A request path is looked up in a
dict of exact strings, and a miss is a 404. Directory traversal is not
defended against; it is unrepresentable, which is the only version of that
defence worth having on a host that also holds credentials.

The form itself stays on Tally, in an iframe. Nothing a member of the public
types ever reaches this process — the only thing that arrives here is a signed
webhook from Tally's servers after the fact.

**Everything is embedded.** The page's own CSP allows no external requests, so
the logo is inlined as SVG markup and the brand fonts as data URIs rather than
pulled from a CDN. That costs about 90KB and buys a page that renders
identically with no third party able to see who visited.

Palette and typography are Prezenti's own, read from their stylesheet rather
than eyeballed: dark forest #112122, cream #fef4ee, orange #eb4b24, mint
#68a9a3, with Outfit for titles and DM Sans for text.
"""

from __future__ import annotations

import base64
import html
import os
from functools import lru_cache
from pathlib import Path

REPO_URL = "https://github.com/P-U-C/talent-engine"
ASSETS = Path(__file__).resolve().parent / "assets"


@lru_cache(maxsize=8)
def _asset_b64(name: str) -> str:
    try:
        return base64.b64encode((ASSETS / name).read_bytes()).decode()
    except OSError:
        return ""


@lru_cache(maxsize=4)
def _logo_svg() -> str:
    """The logo as inline markup, so CSS can recolour it for dark mode."""
    try:
        raw = (ASSETS / "prezenti-logo.svg").read_text()
    except OSError:
        return ""
    # Drop the XML prolog; it is invalid inside an HTML body.
    if raw.startswith("<?xml"):
        raw = raw.split("?>", 1)[-1]
    # The file hardcodes its fill; let the page control it instead.
    raw = raw.replace("fill: #112122;", "fill: currentColor;")
    return raw.replace("<svg ", '<svg class="logo" role="img" aria-label="Prezenti" ', 1)


def _font_face() -> str:
    dm = _asset_b64("dmsans-400.woff2")
    outfit = _asset_b64("outfit-500.woff2")
    blocks = []
    if outfit:
        blocks.append(
            "@font-face{font-family:'Outfit';font-style:normal;font-weight:400 700;"
            "font-display:swap;src:url(data:font/woff2;base64," + outfit + ") format('woff2');}"
        )
    if dm:
        blocks.append(
            "@font-face{font-family:'DM Sans';font-style:normal;font-weight:400 500;"
            "font-display:swap;src:url(data:font/woff2;base64," + dm + ") format('woff2');}"
        )
    return "".join(blocks)


# Prezenti's tokens, taken from prezenti.webflow.shared.css.
PAGE_CSS = """
:root {
  --forest: #112122;
  --cream: #fef4ee;
  --orange: #eb4b24;
  --orange-deep: #dc331a;
  --peach: #f9c7af;
  --mint: #68a9a3;
  --mint-light: #b4dbd4;
  --green-600: #346d6a;

  --bg: var(--cream);
  --surface: #ffffff;
  --ink: var(--forest);
  --muted: #515151;
  --line: #e6ddd6;
  --accent: var(--orange-deep);
}
:root:not([data-theme="light"]) {
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0d1718;
    --surface: #152526;
    --ink: #f2ece7;
    --muted: #a9b5b4;
    --line: #24393a;
    --accent: #ff7a55;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0d1718;
  --surface: #152526;
  --ink: #f2ece7;
  --muted: #a9b5b4;
  --line: #24393a;
  --accent: #ff7a55;
  color-scheme: dark;
}

* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 17px/1.65 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 44rem; margin: 0 auto; padding: 3rem 1.5rem 5rem; }

.logo { height: 2.5rem; width: auto; color: var(--ink); display: block; }
header { margin-bottom: 3.5rem; }

h1 {
  font-family: 'Outfit', sans-serif;
  font-size: clamp(2rem, 5.5vw, 3rem);
  line-height: 1.08;
  letter-spacing: -0.025em;
  font-weight: 600;
  margin: 0 0 1.25rem;
}
h2 {
  font-family: 'Outfit', sans-serif;
  font-size: 1.3rem;
  letter-spacing: -0.015em;
  font-weight: 600;
  margin: 3.5rem 0 1rem;
}
p { margin: 0 0 1.1rem; }
.lede { font-size: 1.2rem; color: var(--muted); margin-bottom: 2rem; max-width: 34rem; }

a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }

ul.signals { list-style: none; padding: 0; margin: 0 0 1.5rem; }
ul.signals li {
  padding: 0.9rem 0 0.9rem 1.6rem;
  border-bottom: 1px solid var(--line);
  position: relative;
}
ul.signals li:before {
  content: "";
  position: absolute; left: 0; top: 1.5rem;
  width: 0.55rem; height: 0.55rem; border-radius: 50%;
  background: var(--mint);
}
ul.signals strong { font-weight: 500; }

.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 1.5rem 1.6rem;
  margin: 1.75rem 0;
}
.card.accent { border-left: 3px solid var(--accent); }

code {
  font: 0.85em ui-monospace, SFMono-Regular, Menlo, monospace;
  background: rgba(104,169,163,0.16);
  padding: 0.15em 0.4em; border-radius: 4px;
}
pre {
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 1rem 1.1rem;
  overflow-x: auto;
  font-size: 0.85rem;
  margin: 1rem 0 0;
}
pre code { background: none; padding: 0; }

.form-frame {
  width: 100%; min-height: 44rem;
  border: 1px solid var(--line); border-radius: 14px;
  background: var(--surface);
}

footer {
  margin-top: 4rem; padding-top: 1.75rem;
  border-top: 1px solid var(--line);
  color: var(--muted); font-size: 0.92rem;
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


DEFAULT_COPY = {
    "headline": "Sponsorship for people who ship",
    "lede": (
        "We back builders on evidence of what they have actually shipped — not "
        "on where they studied, who they know, or how many stars a repository "
        "has."
    ),
    "footer": "",
}


def landing_page(program_name: str, form_id: str, copy: dict[str, str] | None = None) -> bytes:
    """Render the application page.

    `copy` comes from the program config so the running organisation owns the
    words it publishes under its own domain, and can change them without a code
    change. Everything is escaped: the copy is trusted-ish, but it is read from
    a file on disk and rendered into a public page, which is not a combination
    to be casual about.
    """
    text = {**DEFAULT_COPY, **(copy or {})}
    headline = html.escape(text["headline"])
    lede = html.escape(text["lede"])
    extra_footer = f"<p>{html.escape(text['footer'])}</p>" if text.get("footer") else ""
    program = html.escape(program_name)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{program} — apply</title>
<meta name="description" content="{headline}. Scored on public code activity
against a rubric you can read and reproduce.">
<style>{_font_face()}{PAGE_CSS}</style>
</head>
<body>
<div class="wrap">

<header>{_logo_svg()}</header>

<h1>{headline}</h1>
<p class="lede">{lede}</p>

<h2>How you are assessed</h2>
<p>Your public code activity is scored against a fixed rubric. Four signals
carry most of the weight:</p>
<ul class="signals">
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

<div class="card accent">
<p><strong>You can check our work.</strong> The rubric is published in full,
along with the code that applies it. Clone it and reproduce your own score:</p>
<pre><code>git clone {REPO_URL}
cd talent-engine
talent-engine score --handles YOUR_GITHUB_HANDLE</code></pre>
<p style="margin-top:1rem">If a number looks wrong to you, you can show us
exactly where — which is the point of publishing it. Every score comes with
linked evidence for each component; a score with no evidence behind it cannot
be produced.</p>
</div>

<h2>A score is not a decision</h2>
<p>The automated score produces a shortlist. People decide, after reading the
evidence and talking to you. No one is funded or refused by a number, and the
checks that flag manipulated profiles are published alongside the rubric —
including an honest account of what they do not yet catch.</p>

<h2>What we collect</h2>
<p>Public code activity only. Nothing about your background is inferred —
there is nowhere in the system to record an inferred trait. Anything about
your circumstances enters because you chose to tell us. Your contact details
are stored separately from everything used for assessment, and never appear in
an assessment record.</p>

<h2>Apply</h2>
{_embed(form_id)}

<footer>
{extra_footer}
<p>Scoring engine: <a href="{REPO_URL}">talent-engine</a> — open source,
including the rubric, the anti-gaming checks, and their known limits.</p>
</footer>

</div>
</body>
</html>
""".encode()


def routes(
    program_name: str,
    form_id: str | None = None,
    copy: dict[str, str] | None = None,
) -> dict[str, tuple[str, bytes]]:
    """Exact path -> (content type, body). Anything not in here is a 404."""
    form_id = form_id if form_id is not None else os.environ.get("TALLY_FORM_ID", "")
    page = landing_page(program_name, form_id, copy)
    return {
        "/": ("text/html; charset=utf-8", page),
        "/apply": ("text/html; charset=utf-8", page),
    }
