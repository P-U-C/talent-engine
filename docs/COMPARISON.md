# Clean-room build vs. `prezenti_trial_scorer.py` (v1)

This engine was built without reading v1, from the product prompt only. The
comparison below was done afterwards. Every claim about v1 was verified by
executing v1's own functions, not by reading them.

## What is *not* independent confirmation

The rubric dimensions, the 100-point split (80 automated / 20 application), the
weights, the flags-never-add-points rule, and the unscored-free-text decision
were all specified in the prompt. Both implementations having them proves
nothing except that I followed the brief.

What is genuinely independent is everything below: the counting units, the
scoring curves, the matching strategy, the failure defaults. Those were free
choices, and that is where the two builds diverge.

---

## Findings in v1

### 1. Referrer verification fails open — 10 points to any invented name

`score_application()`, lines 190–193:

```python
if not SCOUTS or scout in SCOUTS:
    sc["scout_endorse"] = 10
    if not SCOUTS:
        notes.append("scout named but PREZENTI_SCOUTS not set - unverified")
```

`SCOUTS` comes from the `PREZENTI_SCOUTS` env var. When it is unset — the
default, and nothing in the code or docs enforces setting it — **`not SCOUTS`
is true and every declared name scores full marks.** Verified by execution:

```
SCOUTS registry loaded as: (empty - env unset)
  referrer='Santa Claus'  -> scout_endorse=10/10
  referrer='asdfasdf'     -> scout_endorse=10/10
```

Combined with `access_barrier`, which awards a flat 10 for the string `"yes"`,
an applicant collects the **full 20 application points** by ticking one box and
typing any name at all. The only defence is a note in a list that, in a batch of
fifty applicants, scrolls past.

This is a fail-open default on precisely the dimension designed to resist
fabrication. It is the most consequential difference between the two builds.

This engine fails closed: a name absent from the registry scores zero and
raises `unverifiable_referrer`. There is no unset state that awards points.

### 2. Per-event counting lets volume impersonate breadth

v1 scores `external_valid` from the search API's `total_count`:

```
 1 merged PRs (any distribution) ->  1.2/12
10 merged PRs (any distribution) -> 12.0/12
```

Ten PRs into one monorepo score identically to ten PRs across ten projects.
The same applies to `collaboration` (review `total_count`) and to
`web3_prs` / `agentic_prs`, which increment once per PR.

I hit this independently. My first fixture run put a well-connected insider
(14 merged PRs into a single monorepo, 4 commits of their own) *above* a genuine
builder who had shipped two finished projects. Making the repository the
counting unit — with repeat contributions worth 0.25 — reversed it.

Note what this means for invariant 1: the weights in v1 are correct, agency
outweighs insider signal on paper, and the aggregation violates it anyway.
**An invariant enforced only on the weights is not enforced.**

### 3. Substring taxonomy matching produces false positives

`classify()` does `any(k in haystack for k in KEYWORDS)` against a keyword list
including `"mcp"`, `"a2a"`, `"8004"`, and `"agent"`. Verified:

| repo | v1 verdict |
|---|---|
| `mcpherson/personal-blog` | **agentic ✓** (`mcp`) |
| `someone/data2array` | **agentic ✓** (`a2a`) |
| `acme/issue-18004` | **agentic ✓** (`8004`) |
| `x/user-agent-parser` | **agentic ✓** (`agent`) |
| `jane/nomcphere` | **agentic ✓** (`mcp`) |

`frontier_signal` is the highest-priority scarce signal in the rubric, worth 10
points. Awarding it to a personal blog because the owner is named McPherson is
not a rounding error — and it is invisible to the candidate, who sees only a
score. This engine matches on word boundaries; the regression test is
`test_keyword_matching_respects_word_boundaries`.

### 4. Five thin repos max out origination

`cap(len(active), 5, 10)` is a linear ramp to a hard cap:

```
1 active repo  ->  2.0/10
5 active repos -> 10.0/10
```

The only completeness requirement is a non-empty description (`cap(len(complete), 5, 5)`).
Five repos with one commit and a one-line description each collect full
origination plus full completeness credit. This engine saturates origination at
2 and scores completeness across five marks (description, topics, release,
deployed URL, license), averaged — so thin repos drag the average down instead
of adding to it.

### 5. Known v1 limitations, now fixed

Documented in the handoff, and addressed here: commit sampling covered only the
3 most recently pushed repos (now 12, with explicit `partial` marking beyond);
no persistence, no audit trail (now a full audit log with `verify` replay); no
caching or App auth (now ETag conditional requests, request budgets, and
inline-signed RS256 App auth); referrer registry was an env var (now a program
config with an optional file pointer).

---

## Where v1 is better, and what I took from it

**The declared-repo rule.** v1's monitor treats "active, but not on the declared
project" as `AT_RISK`, not merely as a note. That is the right call for a
program whose terms fund a specific project and run a month-2 checkpoint — being
busy elsewhere is exactly the case the checkpoint exists to catch. My version
recorded it as a note and left the state `ACTIVE`. **Adopted**, with the
constraint that the rule may only downgrade: a genuinely inactive member stays
`INACTIVE` rather than being lifted to `AT_RISK`.

**The rate-limit UX.** v1 exits immediately with "resets ~14:32:07, set
GITHUB_TOKEN and rerun". For an operator running one batch by hand that is
kinder than my silent pacing. Mine is built for unattended runs and sleeps to
the reset instead; both are defensible, and v1's message is better for the
interactive case.

---

## A genuine tradeoff, not a defect

v1 uses `cap(n, at, pts)` — a linear ramp to a hard cap. I use
`x / (x + half)` — saturating, no cliff.

v1's is **more transparent**: an applicant can compute it in their head, which
carries real weight under a published-rubric invariant. Mine is more
informative at the low end (the gap between 0 and 1 shipped repo is much larger
than between 4 and 5, and linear scoring denies that) and has no cliff where
the sixth repo becomes worthless.

I stand by the saturating curve, but v1's transparency argument is the stronger
counter-argument to it, and worth revisiting if candidates report the model as
hard to reproduce by hand.

---

## Fixture scores

| profile | v1 | this engine |
|---|---|---|
| genuine builder | 62.1 | 73.18 |
| gamed profile | 4.5 | 10.67 |
| ratio | 13.8× | 6.9× |

Same ordering, same conclusion, different spread. v1 is harsher on the gamed
profile. The gap is almost entirely `context_statement`: my gamed fixture banks
3.8 of 10 for a single declared factor plus one sentence, where v1's binary
`{"yes": 10, "partial": 5}` awards 0 when nothing is declared.

Neither approach is safe. v1's is a single tickbox worth 10 points; mine is
harder to max but still pays for a sentence. This dimension is self-declared by
design and cannot be verified without violating invariant 2. The honest
mitigations are the cap, human review, and turning it off
(`context_statement_enabled: false`) for programs that cannot tolerate it.
