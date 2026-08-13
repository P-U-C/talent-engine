# Sponsorship terms

What an accepted builder receives, what they are asked for in return, what the
programme owes them, and how each part is enforced. This describes the terms as
they stand; `policies/prezenti-sponsorship-trial.json` is the source of truth
and `ProgramOverlay` refuses to load a policy that breaks the rules below.

Not legal advice. The pledge collects governing law and dispute resolution,
which means a lawyer should read the final wording — see *Gaps* at the end.

## The offer

Five places, four months, $1,400 per person: Claude Max 20x and ChatGPT Pro for
the term, plus a $200 one-off allowance. $7,000 total.

## The give-back

2% of revenue the sponsored project receives through Celo, and of grant, prize
and retro-funding income won with the sponsored work.

| bound | value | why it exists |
|---|---|---|
| cap | 10× sponsorship — $14,000 | an open-ended claim from an in-kind grant is the kind of encumbrance a later investor asks to have removed |
| sunset | 36 months after the term ends | it has to end |
| pro-rating | by months actually received | otherwise someone who withdrew honourably at the month-two gate owes what someone who completed four owes |
| enforcement | reputational | stated rather than implied |

Grant and prize income is included because that is where money actually appears
for early builders, and it arrives on-chain, which makes it the one category a
Splits address can genuinely capture.

**No equity is taken.** The upside instrument is a right of first offer on a
future round with 14 days' notice — a right to be *offered* participation, not
an obligation to grant it. It costs the builder nothing today, creates no
cap-table object, and needs no enforcement.

## What the programme owes the recipient

Terms that run one way are not a relationship, and at this cheque size the
relationship is the entire return.

- Keeps all IP and all equity
- No exclusivity
- May withdraw without penalty
- A public record of having been backed
- Introductions on request
- Their score and its evidence shared with them
- Feedback to unsuccessful applicants

The last is the one most programmes skip. It is implemented, not just promised:
`talent-engine decline` generates specific feedback from the evidence the
decision was made on, and `feedback-queue` exits non-zero while anyone is still
waiting.

## What the on-chain parts do, and do not do

These are frequently discussed as if they combine into enforcement. They do
not, and that governs the choice of instrument.

**The Prezenti Pledge** writes an EAS attestation on Celo, signed by the
builder's wallet. That is a public, timestamped, signed promise. Its force is
reputational — visible, attributable, and legible to anyone who looks.

**0xSplits** distributes funds that arrive at a split contract. It has no reach
over funds that arrive anywhere else.

Together they give a credible promise and frictionless payment when it is
honoured. They do not give a claim. Revenue landing in a builder's own wallet,
or a Stripe account, is untouched by either. The terms are therefore shaped so
their value does not depend on enforcement.

## Why the terms are bounded rather than maximal

The binding constraint is not what Prezenti could extract, it is who accepts.

The engine exists to find high-agency builders who are under-recognised —
people who *could* be funded elsewhere but have not been seen. Those people have
alternatives. A builder with options reads a perpetual uncapped claim attached
to $1,400 of tooling and declines; a builder with no options signs anything. So
disproportionate terms filter the pool toward exactly the profiles the rubric is
built to look past, and the terms would quietly undo the sourcing.

For scale: $1,400 for 2% implies a $70,000 valuation on the claim. It is not
equity, so the comparison is imperfect, but it is worth seeing before deciding
the terms are generous.

## How agreement is recorded

Displaying terms on a page is not agreement. The application form carries a
**required checkbox** that restates the substance — 2%, the $14,000 cap, the
36-month sunset, the pro-rating, no equity, IP retained, withdrawal without
penalty — so nobody can accept a link they did not open.

Silence is never read as agreement: an unticked box, an empty value, or an
absent field all record as *not accepted*, and `talent-engine submissions`
prints `TERMS NOT ACCEPTED` in that case rather than staying quiet.

Each acceptance is stamped with `terms_digest()`, a fingerprint of the
substantive terms — the give-back, the upside instrument, and the commitments
owed to the recipient. Without it, editing the policy would silently rewrite
what everyone who already applied is taken to have agreed to, and nobody could
tell afterwards which version they saw. Editing headline copy or the seat count
does not invalidate an existing agreement; changing an obligation does.

## Enforcement in code

`ProgramOverlay.__post_init__` refuses to load a policy that:

- permits automated final selection
- lets an authenticity flag terminate support on its own
- has an inactivity rule with no cure period
- has a benefit schedule that does not match the declared budget
- has give-back recipient shares that do not add up
- leaves the give-back uncapped, perpetual, or not pro-rated
- takes equity
- fails to state what the programme owes, including that the recipient keeps
  all IP and equity and may withdraw without penalty

`talent-engine serve` loads and validates the policy at startup and **refuses
to start if it is invalid**, so applications cannot be taken under terms that
break these rules. The public page renders the terms from the same object, so
the page cannot say something the code does not enforce.

`giveback_owed_bps(months)` does the pro-rating: two months of a four-month
term owes 100bps of the 200.

## Mechanics at acceptance

- The split is created **at acceptance**, not at first revenue, so it exists
  before anyone needs it.
- It is **immutable**, with long-lived recipient addresses. A mutable split
  needs a controller, and a controller is a party the builder must trust not to
  change terms afterwards.
- Recipient addresses come from environment variables, never the policy file,
  so the policy can live in a public repository.
- `talent-engine accept` records the split address and the pledge attestation
  UID against the cohort row, and prints the letter. **It deploys nothing.**
  Creating the split needs a funded signing key, and a process that parses
  untrusted input from a public form is the wrong place to hold one.

## Gaps

Known and unresolved. A sharp builder would ask for these, and they matter in a
dispute:

- the exact legal parties, governing law and dispute forum
- tax treatment
- a precise definition of "revenue actually received"
- what "won with the sponsored work" covers for grants and prizes
- ROFO mechanics beyond the notice period
- assignment and change-of-control treatment
- a written release once the cap or sunset is satisfied

## Selection integrity is coupled to this

Gaming pressure is a function of what sits at the end of the pipeline. At
$1,400 of subscriptions a manufactured profile is worth an afternoon, not an
operation. If the terms ever grow into a real equity claim, the cross-applicant
checks in `modes/rings.py` move from precautionary to load-bearing, and the
outstanding collector work — contributor lists of validating repositories —
stops being optional. Terms and selection defences are decided together.
