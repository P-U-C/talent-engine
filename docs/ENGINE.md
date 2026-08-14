# talent-engine (the engine)

An open-source engine that identifies high-agency software talent from public
code activity, and selects people worth backing on transparent, evidence-linked
scoring of what they have actually shipped.

One engine, four verbs: **scout → score → monitor → measure**, all sharing the
same rubric so sourcing, selection, and outcome measurement cannot drift apart.

- **[RUBRIC.md](RUBRIC.md)** — the complete scoring model, published so any
  candidate can reproduce their own score.
- **[docs/STRATEGY.md](docs/STRATEGY.md)** — why these signals, what they resist,
  and what they miss.
- **[docs/PROGRAM_LAYER.md](docs/PROGRAM_LAYER.md)** — how governed programs sit
  above the score without turning an automated rank into a funding decision.
- **[docs/PREZENTI_SPONSORSHIP_TRIAL.md](docs/PREZENTI_SPONSORSHIP_TRIAL.md)** —
  the first live overlay: attract outside builders and prove useful Celo work.

## Install

Zero dependencies for scoring — Python 3.10+ standard library only. A candidate
must be able to clone this and reproduce their number with no install step.

```
git clone https://github.com/P-U-C/talent-engine && cd talent-engine
python3 -m pytest tests/ -q
```

`cryptography` is needed only for GitHub App authentication. PyYAML is optional
(program configs are JSON).

## Use

```bash
export GITHUB_TOKEN=...        # or GITHUB_APP_ID + GITHUB_APP_INSTALLATION_ID
                               #    + GITHUB_APP_PRIVATE_KEY_PATH

# score an applicant CSV, writing a linked evidence dossier per person
python3 -m talent_engine.cli score --program celo-trial --csv applications.csv \
                    --dossier-dir out/ --format csv

# find candidates who never applied
python3 -m talent_engine.cli scout --program celo-trial --seeds celo-org/celo-composer

# how is the funded cohort doing?
python3 -m talent_engine.cli monitor --program celo-trial

# did backing them change anything? (same rubric, before vs after)
python3 -m talent_engine.cli measure --program celo-trial --baseline run_a --endline run_b

# reproduce any historical score exactly
python3 -m talent_engine.cli verify --run run_a --handle octocat
```

### Form intake

`serve` receives form webhooks and scores each submission as it arrives, so an
applicant is ranked without anyone exporting a CSV.

```bash
export TALLY_SIGNING_SECRET=...   # from the form's webhook settings; required
python3 -m talent_engine.cli serve --program celo-trial --host 0.0.0.0 --port 8787
#   POST /webhook/tally    signed submissions in
#   GET  /healthz

python3 -m talent_engine.cli submissions --program celo-trial                  # what came in
python3 -m talent_engine.cli submissions --program celo-trial --with-contact   # + how to reach them
```

Three properties worth knowing, because each replaces a failure that is hard to
see once it has happened:

- **Signature verification is mandatory.** There is no unauthenticated mode:
  an open scoring endpoint is an open GitHub-API spend and an open way to push
  applicants into a ranking.
- **The request path does no network work.** Scoring an applicant takes tens of
  seconds of GitHub calls; form platforms time out in a few and retry on
  anything non-2xx. Submissions are committed to SQLite, then scored on a
  worker thread, and a restart requeues anything still pending.
- **Redelivery is a no-op.** Idempotency is keyed on the form's own submission
  id, so a retried webhook does not score a person twice.

Contact details are stored in their own table and never enter a snapshot, a
score, or a dossier — see invariant 7.

### Program overlays

Scoring and sponsorship are deliberately separate. `programs/` answers "what
public evidence says this person ships?"; `policies/` owns eligibility, fit,
human verification, budget, checkpoints, termination and outcomes.

```python
from talent_engine.programs import load_overlay

trial = load_overlay("prezenti-sponsorship-trial")
assert trial.per_person_usd == 1400
assert trial.total_budget_usd == 7000
```

The overlay validator refuses automated final selection, termination from a
metric flag alone, an inactivity rule without a cure period, or a benefit
schedule that does not match the declared budget.

## Design invariants

These are enforced in code, not asserted in documentation:

1. **Agency over pedigree.** `ProgramConfig` refuses to load a rubric where
   insider-network weight ≥ agency weight. Stars and followers are not scored
   at any weight.
2. **No demographic inference, ever.** Context enters only by self-declaration
   or a verified referrer. The data model has nowhere to put an inferred trait,
   and a test asserts it stays that way.
3. **Transparency is the trust mechanism.** `DimensionScore` raises if points
   are awarded without linked evidence — an unevidenced score cannot be
   constructed.
4. **Flags, not silent points.** `Flag` has no points field. Its optional
   `discount` is clamped to [0,1]: it can shrink a component, never grow one.
5. **Public data only.**
6. **One instrument.** Scout, score, monitor and measure share one rubric.
7. **Contact details are quarantined.** A form asks for an email; an evidence
   dossier is an artefact you hand to third parties. Form intake returns
   contact fields as a separate record written to a separate table, and strips
   anything address-shaped from the application — so the publishable half of
   the system is separable from the identifying half by dropping one table.

## Architecture

```
talent_engine/
  model.py           Evidence / DimensionScore / Flag / ProfileSnapshot
  config.py          program configs: weights, taxonomies, referrers, thresholds
  scoring/
    dimensions.py    the eight rubric dimensions
    flags.py         authenticity checks
    engine.py        pure: (snapshot, config) -> CandidateScore
  github/
    auth.py          anonymous / PAT / GitHub App (RS256 signed inline)
    client.py        ETag caching, request budget, rate-limit pacing
    collector.py     API -> ProfileSnapshot
  modes/
    scout.py         three discovery channels
    monitor.py       cohort status + before/after measurement
  programs/
    policy.py        validated selection, budget, checkpoint + give-back layer
  store/db.py        persistence + audit log + replay
  ingest/normalize.py CSV ingest, handle normalisation
  ingest/tally.py    form webhooks -> Application + quarantined Contact
  server/webhook.py  signed intake endpoint, scoring worker, idempotency
  report.py          ranked tables, CSV/JSON export, evidence dossiers
```

The split that matters: **collection touches the network, scoring is pure.**
`ProfileSnapshot` is the seam. Because scoring is a pure function of a
serialisable record, any historical score can be regenerated exactly from a
stored snapshot plus the stored weights — which is what the audit log promises
and what `verify` checks.

## Status

Working: rubric, flags, config validation, GitHub client (auth/cache/budget),
collector, scout, monitor, measure, persistence, audit log + replay, CSV and
signed-webhook ingest, dossiers, CLI, adversarial fixtures, and validated
program overlays.

Not yet built: UI, the optional LLM pass for free-text, applicant-relationship
graph checks, and a real-world calibration run against known-good profiles.
