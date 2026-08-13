# Prezenti AI Builder Sponsorships Trial terms

Version: `prezenti-sponsorship-trial-2026-08-13`

What an accepted builder receives, what they are asked for in return, what the
programme owes them, and how each part is enforced. This describes the terms as
they stand; `policies/prezenti-sponsorship-trial.json` is the source of truth
and `ProgramOverlay` refuses to load a policy that breaks the rules below.

Not legal advice, and a lawyer should read the final wording before the first
acceptance — `docs/LEGAL_GAPS.md` lists what is settled and what is not.

## The offer

Five places, four months, $1,400 per person: Claude Max 20x and ChatGPT Pro 5x for
the term, plus a $200 one-off allowance. $7,000 total.

## The give-back

2% of revenue the sponsored project receives through Celo, and of grant, prize
and retro-funding income won with the sponsored work.

**One obligation, one counterparty.** The builder's pledge runs to Prezenti and
to nobody else. Prezenti then commits, separately and publicly, to routing half
of everything it receives under these pledges to the Celo Community Fund —
equivalent to 1% of covered income.

That split used to be written as "1% to Prezenti and 1% to the Celo Community
Fund", which reads the same and is not the same. It asked a builder to owe
something to a third party they have no agreement with, that has no way to
know the obligation exists, and that would have no standing to do anything
about it. Prezenti's onward commitment is Prezenti's to keep and Prezenti's to
be judged on, which is where it belongs. The attestation records both legs so
the second one is as public as the first.

## Legal character of the pledge

Stated plainly because an on-chain attestation reciting a percentage of revenue
can easily look like more than it is:

- It is a **good-faith commitment**, not a contract, and it is intended to be
  unenforceable at law.
- It creates **no security interest, no lien, no charge and no debt**, and it
  is not a revenue-share agreement, a royalty, or a financial instrument.
- It conveys **no equity, no option, no warrant and no conversion right**, and
  creates no cap-table entry.
- It gives Prezenti **no claim over the builder's company, assets or future
  financings**, and nothing in it survives as an encumbrance a future investor
  would need cleared.
- It is **not subject to arbitration** and specifies no governing law, because
  naming a forum for a commitment nobody intends to enforce implies the
  opposite of what is meant. The earlier pledge recorded
  `"Celo Community Governance"` and `"Celo Governance Proposals and
  Arbitration"`; neither describes an obligation running from a builder to
  Prezenti, and neither is carried forward.
- Enforcement is **reputational only**: the pledge is public, and so is whether
  it was honoured.

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

To remove the obvious ambiguities: it is a right of first **offer**, never a
right of first refusal, and it carries no matching right, no pro-rata right, no
information right and no veto. Notice is satisfied by an email to the address
on file. Prezenti not responding within 14 days ends the matter for that round.
It **does not survive a change of control**, it binds nobody but Prezenti and
the builder, it is not assignable, and it expires with the give-back 36 months
after the term. A builder can honestly answer "no" when a lead investor asks
whether anyone holds rights over the round.

## Tooling, accounts and reimbursement

The subscriptions are bought by the builder in the builder's own name, and
Prezenti reimburses against a receipt. That ordering is deliberate: the account,
its contents and its history belong to the builder throughout, and nothing has
to be transferred at the end of the term.

- The builder is responsible for complying with each vendor's terms, including
  any restriction on paid-for-by-a-third-party or shared accounts.
- Reimbursement stops at the end of the term. The account continues, at the
  builder's expense, or does not — either way it is theirs.
- Where a vendor gives Prezenti credit instead of cash, the builder receives
  the same tooling and owes nothing further; the offset is recorded in the
  operating ledger as a `vendor_offset` so the programme's real cost stays
  visible.
- Reimbursements are for tooling, not compensation. Neither party is the
  other's employer, contractor or agent. Tax treatment is the builder's own
  affair, and Prezenti gives no advice on it.

## Withdrawing

A builder may stop at any time, for any reason, without penalty and without
explaining. The give-back pro-rates by whole months actually funded:

```
obligation = 2% × (months funded ÷ 4)
```

Two months funded halves it; withdrawing before any month is funded removes it
entirely. The figure is recorded once, at withdrawal or at the end of the term,
in the operating ledger as `months_funded`. The initial pledge does not let the
builder choose this value at acceptance; a close-out replacement attestation is
made only once the actual number is known.

## Your data

- **Contact details** — email, name, and any messaging handles — are stored
  apart from everything scoreable and never appear in a score, a snapshot, a
  dossier, or any public artefact. Free-text answers are scanned and contact
  details are removed from them before they reach a reviewer.
- **Applicants** are asked to consent when they apply. **People found by
  scouting** are assessed only on public code activity that GitHub already
  publishes, and are contacted only to invite an application.
- **Retention**: application data is kept for the trial and twelve months
  afterwards, then deleted. Contact details are deleted at the same point.
- **Deletion on request** at any time, including after acceptance, by asking.
  Deleting contact details ends the ability to reimburse anyone, so a request
  during the term ends the sponsorship — that is a consequence, not a penalty.
- **The public record of backing** is a separate, explicit opt-in asked at
  acceptance. Declining it changes nothing else. Nobody who is not selected is
  ever named publicly.

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

Each acceptance is stamped with `terms_digest()`, the short SHA-256 marker of
the canonical terms release named in the policy. The pledge records the full
SHA-256 `termsHash` from the same release. Without that shared release, editing
a page, a policy field or a pledge document could silently rewrite what everyone
who already applied is taken to have agreed to, and nobody could tell afterwards
which version they saw.

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

## Attestation lifecycle

The pledge is revocable because a good-faith commitment with a sunset and
pro-rating needs a way to be closed out or corrected.

1. At acceptance, the builder signs the current pledge terms. The attestation
   must match the programme schema, Prezenti Safe recipient, builder handle,
   builder signing wallet, native EAS expiry, and the current `termsHash`.
2. At withdrawal or term end, Prezenti records the actual whole months funded
   in the operating ledger as `months_funded`.
3. The builder signs a replacement close-out attestation that references the
   original UID and carries the actual months funded.
4. Prezenti revokes the superseded attestation after the replacement UID is
   recorded, leaving both the original promise and the close-out event visible.
5. If the cap is met, the sunset passes, or a material mistake is found, the
   same replacement-then-revoke sequence is used. A UID is never overwritten in
   the ledger; every transition is an event.

`talent-engine accept` validates the initial UID before storing it. A UID that
cannot be checked against the current schema, signer, recipient, handle, expiry
and terms hash is not an acceptance artefact.

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
