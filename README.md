# talent-engine

An open-source engine that identifies high-agency software talent from public
code activity, and selects people worth backing on transparent, evidence-linked
scoring of what they have actually shipped.

One engine, four verbs: **scout → score → monitor → measure**, all sharing the
same rubric so sourcing, selection, and outcome measurement cannot drift apart.

- **[RUBRIC.md](RUBRIC.md)** — the complete scoring model, published so any
  candidate can reproduce their own score.
- **[docs/STRATEGY.md](docs/STRATEGY.md)** — why these signals, what they resist,
  and what they miss.

## Install

Zero dependencies for scoring — Python 3.10+ standard library only. A candidate
must be able to clone this and reproduce their number with no install step.

```
git clone <repo> && cd talent-engine
python3 -m pytest tests/ -q          # 49 tests
```

`cryptography` is needed only for GitHub App authentication. PyYAML is optional
(program configs are JSON).

## Use

```bash
export GITHUB_TOKEN=...        # or GITHUB_APP_ID + GITHUB_APP_INSTALLATION_ID
                               #    + GITHUB_APP_PRIVATE_KEY_PATH

# score an applicant CSV, writing a linked evidence dossier per person
talent-engine score --program celo-trial --csv applications.csv \
                    --dossier-dir out/ --format csv

# find candidates who never applied
talent-engine scout --program celo-trial --seeds celo-org/celo-composer

# how is the funded cohort doing?
talent-engine monitor --program celo-trial

# did backing them change anything? (same rubric, before vs after)
talent-engine measure --program celo-trial --baseline run_a --endline run_b

# reproduce any historical score exactly
talent-engine verify --run run_a --handle octocat
```

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
  store/db.py        persistence + audit log + replay
  ingest/normalize.py CSV ingest, handle normalisation
  report.py          ranked tables, CSV/JSON export, evidence dossiers
```

The split that matters: **collection touches the network, scoring is pure.**
`ProfileSnapshot` is the seam. Because scoring is a pure function of a
serialisable record, any historical score can be regenerated exactly from a
stored snapshot plus the stored weights — which is what the audit log promises
and what `verify` checks.

## Status

Working: rubric, flags, config validation, GitHub client (auth/cache/budget),
collector, scout, monitor, measure, persistence, audit log + replay, CSV
ingest, dossiers, CLI. 49 tests, no network required.

Not yet built: HTTP API and UI, webhook ingestion, the optional LLM pass for
free-text, and a real-world calibration run against known-good profiles.
