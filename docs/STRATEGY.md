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

## What an adversary who has read this document can score

The rubric is published on purpose, so the realistic attacker has read it. The
attack in `tests/fixtures/profiles.py::gamed_profile` — fresh account, bulk
commits, a wall of forks — is what someone builds who has *not*, and it scores
4.68 out of 100 with four flags raised. That number has been used as evidence
the screen resists gaming. It is not evidence of that; it only shows the
cheapest attack fails.

Two profiles model the attacker who read the document. Measured on
`recruit-agent-infra`:

| profile | score | flags |
|---|---|---|
| sockpuppet_ring | **56.79** | none |
| genuine_builder | 49.93 | unverifiable_referrer |
| patient_farmer | 41.36 | none |
| quiet_finisher | 29.43 | none |
| insider_low_shipper | 23.94 | none |
| gamed_profile | 4.68 | 4 |

The manufactured profile wins, and the only credible profile carrying a warning
is the honest one.

### Why the flags miss it

Every authenticity check in `flags.py` keys on **concentration** — account age,
activity collapsed into a few weeks, implausible commits per active week. All
of them are defeated by the same move: commit a little, weekly, for a few
months, from an account aged in advance. `patient_farmer` is a cron entry plus
an afternoon spent adding descriptions, licences, homepages and tagged releases
to three thin repositories. Metadata is the part of "finishing" that can be
produced without finishing anything, and this document argues finishing is the
strongest signal, which tells the attacker exactly where to spend the afternoon.

`sockpuppet_ring` adds the second half. `external_validation` and
`collaboration` gate on `is_own_repo`, which means "not owned by this account".
A second account costs nothing, so PRs merged between two accounts one person
controls are scored as an independent maintainer clearing their review bar.
Nothing in a `ProfileSnapshot` distinguishes an alt's repository from a real
one: not contributor count, not age before the PR landed, not whether anyone
unrelated ever touched it.

### The flag asymmetry

`genuine_builder` is flagged for naming a referrer the program's registry does
not contain. Both manufactured profiles name no referrer and pass clean.
Declaring something checkable is what earns a warning; declaring nothing is
free. An unverifiable referrer should score zero — it already does — without
also being the loudest thing on the dossier.

### What would actually close it

None of these are scoring-curve tweaks; two are collection changes:

1. **Independence of the validating repository.** Count a merged PR as external
   validation only when the receiving repository shows independence — other
   contributors, meaningful age before the PR, or contributors with no other
   overlap with the applicant. Requires collecting contributor lists. *Still
   outstanding.*
2. **Overlap detection across applicants.** ✅ **Built** — see
   `talent_engine/modes/rings.py` and the section below.
3. **Substance behind finishing metadata.** A release with no assets, a
   homepage that does not resolve, a licence added in the same commit as the
   description — all cheap to check, all currently unchecked.

### Where this leaves the design

The exposure is a function of stakes, not of code quality. For an invited
cohort of five, none of it matters: everyone is known, and the rubric ranks
people the operator could already vouch for. For an open form that anyone can
submit to, with sponsorship at the end and the rubric published, the incentive
to run exactly these attacks is created on the day the form goes live.

The honest statement of the current position: this engine measures public
evidence of shipping well, and resists lazy manipulation. It does not yet
resist a patient adversary, and it should not be the sole input to a funding
decision until items 1 and 2 exist.


## Cross-applicant overlap, and why the false positive governs the design

The pool-level check is built. It reads stored snapshots only, so it costs no
API calls and runs on every application rather than being a periodic chore.

The easy half is finding clusters: build edges where one applicant merged a
pull request into another's repository, reviewed one, or pushed to the same
repository, then take connected components. The hard half is that **real
communities produce identical edges.** Two builders in the same city who review
each other's work look exactly like two accounts one person controls.

The costs are not symmetric. Missing a ring loses money. Telling a group of
genuine collaborators they look like a sockpuppet ring attaches an accusation
of fraud to a funding decision, and the engine cannot tell the two apart from
structure alone. So clustering is not the signal.

The signal is **insularity**: what share of a person's merged work went to
their own cluster or to accounts the program does not recognise, rather than to
projects whose review bar means something independently. A real community has
edges pointing outward; a ring, by construction, mostly does not.

Measured on the fixtures:

| pool | clusters | insularity | flagged |
|---|---|---|---|
| `sockpuppet_pool` (4 accounts, one operator) | yes | 1.00 | **review** |
| `sockpuppet_pool` minus one member | yes | 1.00 | **review** |
| `genuine_pool` (3 real collaborators) | yes | 0.29 | no |

Both cluster. Only one is flagged.

### The hole the first version had

The obvious metric — share of validation staying inside the cluster — broke
the first time a *partially applied* ring was tested. With three of four
accounts scored, each member's edge to the absent fourth counted as outside
validation and the group fell under the threshold. A check a ring defeats by
withholding one account is not a check. Hence the current definition, where an
unrecognised account is not independent evidence whether or not it has applied.

### What it still cannot see

A ring whose members have **not applied** is invisible: this reads the pool, and
someone who never submitted the form is not in it. Contributor lists of the
receiving repositories would catch that case, and are the outstanding item
above.

The output is deliberately written as an observation rather than a verdict, and
`needs_review` never rejects anybody — the program overlay already forbids an
automated signal from making a funding decision.
