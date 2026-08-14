# Prezenti AI Builder Sponsorships

**Apply: [sponsorships.prezenti.xyz](https://sponsorships.prezenti.xyz)**

We back builders on evidence of what they have actually shipped — not on where
they studied, who they know, or how many stars a repository has.

This repository is the whole thing: the programme's terms, the rubric your
application is scored against, and the running code that does the scoring. It
is public so that anyone we assess can check our work, and so that anyone who
wants to run a programme like this can take it.

It is a fork of [P-U-C/talent-engine](https://github.com/P-U-C/talent-engine),
which is the general engine. This fork is Prezenti's live deployment of it.

---

## The programme

A trial: **5 places, 4 months, $7,000 total.** Applications close **2026-08-25**.
Each place is $1,400 of tooling that removes the main constraint on someone
building alone.

| | |
|---|---|
| Claude Max 20x | $200/month × 4 |
| ChatGPT Pro 5x | $100/month × 4 |
| Flexible allowance | $200 one-off |

We are looking for people building **agent infrastructure, protocol
engineering and on-chain tooling** — deliberately including people who have
never touched Celo. Scoring rewards what you have shipped anywhere; a credible
Celo plan is required at selection, and real Celo work at the month-two
checkpoint. Scoring on Celo-nativeness would only find people already inside
the ecosystem we are trying to bring people into.

### What we ask in return

A good-faith pledge of **2%** to Prezenti, and to nobody else, covering revenue
actually received by the product through Celo, and any grant, prize and
retro-funding income won with the sponsored work. Prezenti separately routes
half of what it receives onward to the Celo Community Fund, equivalent to 1% of
covered income. Bounded in every direction:

- **Capped at $14,000** — ten times the sponsorship. It cannot exceed that.
- **Expires 36 months** after the programme ends.
- **Pro-rated** by the months you actually take. Leave at the month-two
  checkpoint and you owe proportionally less.
- **No equity.** We ask for a right of first offer on a future round — the
  right to be *offered* participation, with 14 days' notice. Never an
  obligation on you.

Continuing support also requires monthly receipts, one monthly public update,
and qualifying activity. Thirty days without qualifying activity triggers
review; you then have seven days to provide evidence or cure it. Months three
and four require a verifiable Celo deployment, integration or material ecosystem
contribution by the month-two checkpoint.

Enforcement is reputational. The pledge is recorded publicly as an on-chain
attestation that names your GitHub handle, and we are straight about what that
means: it is a promise, not a security interest, and nothing here gives us a
claim on your company. Acceptance is blocked until counsel clears the exact
current terms digest.

### What the programme owes you

Stated because terms that run one way are not a relationship, and because at
this cheque size the relationship is the entire return:

- You keep **all IP and all equity**. We take none.
- **No exclusivity.** Take other funding, other grants, other work.
- **Withdraw at any time without penalty**, with the give-back scaling down.
- A **public record** that we backed you, with the evidence.
- **Introductions** where we can make them.
- **Your score and every piece of evidence behind it**, shared with you.
- **Feedback if you are not selected.** Everyone, not just the shortlist.

These are enforced in code, not just written here: `ProgramOverlay` refuses to
load a policy that takes equity, leaves the give-back uncapped, lets it run
forever, or fails to state what the programme owes. See
[`talent_engine/programs/policy.py`](talent_engine/programs/policy.py).

---

## How you are assessed

Four signals carry most of the weight. The complete model is in
[RUBRIC.md](RUBRIC.md), published so you can reproduce your own number.

1. **Origination** — you create things that did not exist. Forking is free;
   originating is not.
2. **Finishing** — releases, documentation, a licence, a deployed URL. The
   last ten percent, the part with no dopamine in it.
3. **Cadence** — distinct *weeks* of activity, which is far harder to inflate
   than a commit count.
4. **Acceptance** — other people merged your work, across several projects.

**Stars and follower counts are not scored at any weight.** They measure
access, and access is what this is built to look past. The configuration
refuses to load if insider-network signals are weighted above measured
shipping.

### Reproduce your own score

```bash
git clone https://github.com/prezenti/talent-engine
cd talent-engine
python3 -m pytest tests/ -q                       # full local suite, no network needed
export GITHUB_TOKEN=...
python3 -m talent_engine.cli score \
    --program prezenti-sponsorship-trial --handles YOUR_HANDLE
```

Every component is evidence-linked — a score with no evidence behind it cannot
be constructed, structurally. If a number looks wrong, open an issue and point
at the line. That is what publishing it is for.

---

## What we do not claim

This matters more than the parts that flatter us.

**A score never decides anything.** It produces a shortlist; people read the
evidence and decide. The code enforces this — a policy that permits automated
final selection will not load.

**The scoring can be gamed by a patient adversary, and we can prove it.**
[docs/STRATEGY.md](docs/STRATEGY.md) contains measured results showing a
manufactured profile outranking a genuine builder, kept as failing-if-fixed
regression tests in [tests/test_redteam.py](tests/test_redteam.py). We publish
this because a rubric everyone can read is a rubric someone will farm, and
pretending otherwise would be the dishonest part.

**Our defence against that is not clever, it is corroboration.** Cross-applicant
ring detection requires several independent signals to agree before flagging
anything, and it never flags pairs — two people who validate only each other is
the normal shape of a founding team. Two external model reviews broke the first
version in both directions; both attacks are now permanent tests.

**Every score carries a caveat sentence** saying what to be sceptical about,
and it is never reassuring. When nothing specific stands out it says what the
score does *not* establish, because silence would be a claim we cannot support.

---

## Implementation

```
you fill in the form  ─┐
                       ├─→  Tally signs a webhook
frontier-lab and       │         │
outreach traffic  ─────┘         ↓
                          clawd verifies the signature
                                 ↓
                          collect public GitHub activity
                                 ↓
                          score against the rubric  ──→  caveat sentence
                                 ↓                            │
                          cross-applicant ring check  ────────┤
                                 ↓                            ↓
                          emailed to the programme operator, with evidence
                                 ↓
                          humans decide  ──→  accept: terms, Safe payment route, public pledge
                                          └─→  decline: feedback, tracked
```

Alongside it, a daily sourcing run finds people who never applied, scores the
best of them, and emails a ranked few.

| Piece | Where |
|---|---|
| Public page and signed intake | `talent_engine/server/` |
| Form parsing, PII quarantine | `talent_engine/ingest/tally.py` |
| Rubric, flags, caveat sentence | `talent_engine/scoring/` |
| Ring detection | `talent_engine/modes/rings.py` |
| Acceptance, decline, feedback | `talent_engine/modes/` |
| Programme terms, validated | `policies/`, `talent_engine/programs/` |
| Form questions (source of truth) | `forms/sponsorship-application.json` |

Some properties worth knowing, each of which replaces a failure that is hard to
see after it has happened:

- **Signature verification is mandatory.** There is no unauthenticated mode.
- **Scoring happens off the request path.** It takes tens of seconds; form
  platforms retry anything that is not a fast 2xx.
- **Redelivery is a no-op**, keyed on the form's own submission id.
- **An incomplete collection is never scored.** A partial snapshot is a floor,
  not a measurement, and a low number with a soft warning beside it is worse
  than no number.
- **Contact details are quarantined** in their own table, stripped from the
  application by label, field type *and* value shape, and never present in an
  assessment record or an evidence dossier.
- **Question labels are the wire format.** They live in `forms/*.json` and a
  test round-trips them through the parser, so renaming a question in the form
  builder fails the suite instead of silently dropping a field.

Zero dependencies for scoring — Python 3.10+ standard library only, so that
reproducing your score requires no install step.

---

## Running your own

The engine is program-agnostic. A programme is two files: a scoring config in
`programs/` (weights, ecosystem taxonomy, window) and a policy in `policies/`
(seats, budget, terms, what you owe recipients). Both are validated on load.

```bash
python3 -m talent_engine.cli serve --program <your-program>
python3 -m talent_engine.cli rings --program <your-program>      # before selection
python3 -m talent_engine.cli feedback-queue --program <your-program>
```

Fixes and improvements to the engine belong upstream at
[P-U-C/talent-engine](https://github.com/P-U-C/talent-engine). Prezenti-specific
configuration lives here.

---

## Documents

| | |
|---|---|
| [RUBRIC.md](RUBRIC.md) | the complete scoring model |
| [docs/STRATEGY.md](docs/STRATEGY.md) | why these signals, and what an adversary can do to them |
| [docs/SPONSORSHIP_TERMS.md](docs/SPONSORSHIP_TERMS.md) | current terms index |
| [docs/terms/prezenti-sponsorship-trial-2026-08-14-v3.md](docs/terms/prezenti-sponsorship-trial-2026-08-14-v3.md) | canonical terms release agreed by applicants |
| [docs/PREZENTI_SPONSORSHIP_TRIAL.md](docs/PREZENTI_SPONSORSHIP_TRIAL.md) | the trial in full |
| [docs/PROGRAM_LAYER.md](docs/PROGRAM_LAYER.md) | how programmes sit above the score |
| [docs/ENGINE.md](docs/ENGINE.md) | the engine's own README |
