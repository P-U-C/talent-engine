# The program layer

`talent-engine` measures public evidence of shipping. It does not decide who
receives money.

That boundary matters most when a published rubric is attached to an open call.
The red-team fixtures show that a patient manufactured profile can outscore a
real builder. A score is still useful: it compresses a large applicant pool into
an evidence-linked shortlist. It is not proof of identity, need, project fit or
future value.

Program overlays live in `policies/`. They define what happens above the scorer:

```
scout -> apply -> score -> shortlist -> verify -> select -> support -> measure
                    |          |          |          |
                 evidence   program    human      program
                  engine     gates      review      terms
```

## Separation of responsibilities

| talent engine | program overlay |
|---|---|
| public GitHub evidence | access eligibility |
| technical score and flags | build-plan and ecosystem fit |
| ranked shortlist | identity and evidence verification |
| activity snapshots | final selection and conflicts |
| before/after technical signal | budget, checkpoints and outcomes |

The score remains public and reproducible. Fields that are easy to assert but
hard to verify — need, demographic context, endorsements and future plans — do
not secretly become technical points. A program may use them as disclosed gates
or human-review context.

## Enforced overlay invariants

`ProgramOverlay` rejects policies where:

- the automated score makes the final funding decision;
- human verification is absent;
- no build plan is required;
- an inactivity rule has no cure period;
- a metric flag automatically terminates support;
- give-back shares do not add up; or
- the benefit schedule does not reconcile to the declared budget.

These checks do not make judgment objective. They keep the decision boundary
honest and make policy drift visible in code review.

## Prezenti trial

The first overlay is
[`prezenti-sponsorship-trial.json`](../policies/prezenti-sponsorship-trial.json).
Its matching scoring configuration is
[`programs/prezenti-sponsorship-trial.json`](../programs/prezenti-sponsorship-trial.json).

The scoring taxonomy is deliberately broader than Celo. The acquisition thesis
is to find strong blockchain and agent-infrastructure builders who are not yet
inside Celo. Celo commitment is tested in the build-plan review and proven at
the month-two continuation gate; filtering only for existing Celo history would
defeat the trial.
