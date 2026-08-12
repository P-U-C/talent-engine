# The rubric

This is the complete scoring model. It is published because a score you cannot
inspect is not evidence, it is an assertion. If you are being scored by this
engine, you can read this page, read `talent_engine/scoring/`, and reproduce
your own number.

100 points = **80 measured from public activity** + **20 from what you tell us**.

All measurement covers a window of the last N months (default 6).

---

## What is measured

### shipping_agency — 25 points

Original, non-fork repositories you pushed to during the window. Three parts:

| part | weight | what it measures |
|---|---|---|
| origination | 40% | how many original repos you actually pushed to (half credit at 2) |
| commit_volume | 28% | commits to your own original repos (half credit at 40) |
| completeness | 32% | how *finished* those repos are |

Completeness counts five marks per repo, averaged over your five most active:
a description, topics, a release, a deployed URL or Pages site, a license.

This is the heaviest single dimension, and completeness is a third of it on
purpose. Starting things is common. The five marks above all come from the
last 10% of a project — the part people skip. That is where agency shows.

**Forks earn nothing here.** A fork is free to create; originating is not.

### consistency — 15 points

The number of **distinct weeks** you were active, out of the window's ~26.
Full marks at 13 active weeks.

Measured in weeks, never in commits, because a week cannot be inflated by
splitting the same work into more commits.

Multiplied by a *spread* factor based on how much of the window your activity
covers: all three thirds = 1.0, two thirds = 0.85, one third = 0.70. One hot
month does not read as six consistent ones.

### external_validation — 12 points

Pull requests you got merged into repositories **you do not own**. Someone
else's review bar was cleared.

Counted by **distinct repository**, not by PR. Five merged PRs across five
projects beats five into one, because the second is largely a function of
already being inside that project. Repeat PRs into an already-counted repo
are worth 0.25 each. Half credit at an effective 4.

### collaboration — 8 points

Reviews you gave on other people's pull requests. Same distinct-repository
counting. Half credit at an effective 5.

Reviewing is work that leaves you no artifact, which makes it a clean signal.
It is weighted low only because access to review is unevenly distributed.

### ecosystem_footprint — 10 points

Distinct repositories of yours matching the program's ecosystem taxonomy — by
organisation, repository, topic, language, or keyword. The taxonomy is in the
program config and you can read it. Half credit at 3.

### frontier_signal — 10 points

The same, against a second, narrower taxonomy of emerging technologies the
program is specifically betting on. Half credit at 2 — this work is rarer, so
it saturates sooner.

---

## What you tell us

### context_statement — 10 points

A structured field you fill in yourself. 60% for declaring specific factors,
40% for writing something substantive.

**The engine never infers this.** Nothing about your background or
circumstances is derived from your name, your location, your avatar, or any
other proxy. It comes from you, or from a verified referrer, or it does not
enter the system at all.

### trusted_referral — 10 points

An endorsement from someone on the program's referrer registry.

Binary: verified is full marks, anything else is zero and raises a flag.
Partial credit would mean an invented name still buys something.

---

## Flags

Flags route a dossier to human review. **A flag can never add points.** Where
one appears in your dossier it is stated explicitly whether it discounted
anything.

| flag | trigger |
|---|---|
| `new_account` | account younger than 180 days |
| `no_original_repos` | no original repo pushed in the window |
| `burst_activity` | all activity inside ≤2 distinct weeks |
| `metric_inflation` | ≥60 commits per active week |
| `unverifiable_referrer` | declared referrer not on the registry |
| `fork_shell_profile` | ≥3 forks and no original repos |
| `partial_data` | *our* collection was incomplete — not about you |

`burst_activity` is the only flag that discounts: it cuts the commit_volume
component to 5%. Concentrated volume is the cheapest thing to manufacture and
the weakest evidence of sustained work.

`partial_data` deserves a note. If we could not collect fully — rate limits,
API windows, private activity — your score is a **floor, not a measurement**,
and the dossier says so. A truncated collection must never be mistaken for a
quiet candidate.

---

## What is deliberately not scored

- **Stars, forks-of-your-repo, followers.** These measure audience and
  distribution. They are the access advantage this rubric exists to correct
  for, not evidence of capability.
- **Account age**, beyond the new-account flag. Being early is not a skill.
- **Employer, school, or any credential.** Not collected.
- **Free-text plans and proposals.** Collected and shown to human reviewers,
  but unscored by default. An optional LLM pass against a published sub-rubric
  is available as a module; it is off unless a program turns it on.
- **Anything inferred about who you are.** See invariant 2.

## Reproducing your score

Every dossier ends with a `snapshot_digest`, a `weights_digest`, and a
`code_version`. The snapshot is the exact set of inputs the scorer saw. Running
that snapshot through those weights on that code produces the same number,
every time:

```
talent-engine verify --run <run_id> --handle <you>
```

If it ever does not, that is a bug and the recorded score stands.
