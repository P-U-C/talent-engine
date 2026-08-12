# Strategy: what we are measuring, and why it works

## The thesis

Agency is the disposition to start things and finish them without being asked.
It is what a grant program is buying and what a hiring pipeline is screening
for, and it is almost never what a screen actually measures.

Public code activity contains a small number of genuinely hard-to-fake
signatures of that disposition. The whole product is a bet on four of them:

1. **Origination.** They create things that did not exist. Forking is free;
   originating is not.
2. **Finishing.** Most side projects die around commit three. Descriptions,
   releases, deployed URLs, licenses — all of it comes from the last 10%, the
   part with no dopamine in it. This is the most under-used signal in talent
   screening and, I would argue, the most informative.
3. **Cadence.** They keep showing up. Distinct weeks of activity is a much
   harder number to inflate than commit count.
4. **Acceptance breadth.** Other people merged their work, across several
   different projects.

Everything else in the rubric is supporting evidence or context.

## The failure mode this exists to correct

The default proxies — stars, followers, merged PRs into big-name repos, prestige
of employer — all measure *access*. They select people who already got in
somewhere. That population is real, but it is exactly the population that does
not need finding: they are already legible, already recruited, already funded.

A screen built on access proxies has no ability to find the person in Nairobi
who shipped two complete projects nobody starred. That person is the entire
reason to build this.

So invariant 1 is not a values statement, it is the product spec. It shows up
in three concrete places:

- `ProgramConfig` **refuses to load** a rubric where insider-network weight
  (external_validation + collaboration) meets or exceeds agency weight
  (shipping_agency + consistency).
- Stars and followers are not scored anywhere, at any weight.
- Ranking ties break toward measured shipping, not toward network signals.

### It failed the first time I tested it

Worth recording, because it is the strongest argument for adversarial fixtures.

The first run of the four test profiles produced:

```
amara-dev (genuine independent builder)   73.70
wellconnected (insider, 4 own commits)    39.08   <-- wrong
tobi-k (quiet finisher, 2 real projects)  35.19
fastbuilder99 (manufactured)              10.67
```

The insider beat the finisher, and the config guard did not catch it, because
the failure was not in the weights — it was in the counting. All 14 of the
insider's merged PRs went into a *single* monorepo. Counting per-event read
that as 14 units of ecosystem footprint and 14 units of external validation.
Volume against one repo was impersonating breadth.

The fix was to make the **repository** the unit rather than the event, and to
weight repeat contributions to an already-counted repo at 0.25. After it:

```
amara-dev      73.18
tobi-k         35.19   <-- correct
wellconnected  27.98
fastbuilder99  10.67
```

The quiet finisher now wins on automated points alone, having filled in no
application fields at all. That ordering is the product working.

The general lesson: **an invariant enforced only on the config is not enforced.**
Aggregation logic can violate it while every declared weight stays legal.

## Gaming analysis

The design rule is that gaming should be *worthless*, not merely detectable.
Cheapest attacks first:

| attack | cost | what it earns |
|---|---|---|
| fork 20 popular repos | minutes | nothing — forks are excluded from agency |
| 80 commits in a weekend | hours | ~3% of the volume component (burst discount) + 2 flags |
| generate 5,000 lines of boilerplate | minutes | volume saturates at 40 commits; `metric_inflation` flag |
| create 15 empty repos | minutes | origination saturates at 2; completeness averages toward zero |
| buy stars and followers | dollars | nothing — not scored |
| 14 tiny PRs into one busy repo | days | ~one repo's worth of credit, not fourteen |
| invent a referrer | seconds | zero points + a flag |
| **actually ship two finished projects over six months** | months | full marks |

The last row is the design target. The cheapest way to score well should be to
do the work.

The residual: **cadence over a long window is expensive to fake, but not
impossible** — a patient adversary committing weekly for six months scores real
points. I am comfortable with that. Six months of consistent weekly work *is*
the signal, whatever the motive.

## Known limits — stated, not hidden

- **`context_statement` is self-declared and therefore gameable.** The gamed
  fixture still banked 3.8 of 10 for one sentence. This is inherent: the engine
  is forbidden to verify or infer it (invariant 2), so it can only check that
  something structured was submitted. Mitigations are the 10-point cap and
  human review, not detection. A program that cannot tolerate this should set
  `context_statement_enabled: false` and run on 90 points.
- **Private work is invisible.** Someone whose best work is in a private
  monorepo scores low. Public-data-only is a deliberate constraint
  (invariant 5), but it means a low score is evidence of *absent public
  evidence*, never of absent ability. Language in the dossier should keep
  saying so.
- **The review signal is weak by construction.** `reviewed-by` search returns
  update time rather than review time, so review timestamps are approximate and
  only used for week bucketing.
- **Taxonomy matching is lexical.** It matches names, topics, languages, and
  keywords with word boundaries. It will miss a relevant project that describes
  itself in unusual terms. That is a precision-over-recall choice: a false
  ecosystem match is worse than a miss, because it is invisible to the reader.
- **Monitor depends on a ~90-day public events horizon.** Beyond that, absence
  of evidence is not evidence of absence, and `partial_data` says so.
- **Six months favours the currently-active.** Someone who shipped brilliantly
  8 months ago and had a quiet half-year scores low. For a program funding
  *forward* work that is arguably correct; for hiring it may not be, and
  `window_months` is per-program for that reason.

## Why scout matters more than score

Ranking applicants is the easy half. The pile self-selected — everyone in it
already knew the program existed, which is itself an access filter.

The scout module runs three channels with deliberately different biases:

- **contributors** — recent merged-PR authors in seed repos. High precision,
  structurally insider-biased: everyone it returns has already been let in
  somewhere.
- **originators** — owners of recently-created, actively-pushed repos matching
  the taxonomy, sorted by *recency, not stars*. This is the channel that finds
  people who have never touched a seed org.
- **adjacent** — contributors to those small repos. Two- and three-person
  projects are where people do their most legible work.

Running only the first channel would reproduce precisely the access bias the
rubric is built to correct, so the default runs all three, and ranking prefers
candidates corroborated by more than one channel — with originators outranking
pure insiders at equal corroboration.

## Recruitment mode

Same engine, same rubric core, different taxonomy pack and a different default:
`context_statement_enabled: false`, because an access-barrier field is
appropriate for an access-focused grant program and not for a hiring pipeline.

Compliance notes for employment use: public data only; the candidate can read
the rubric and their own dossier; and jurisdiction review is required before
using any automated score in an employment decision. The engine produces an
evidence-linked shortlist for a human, not a decision.
