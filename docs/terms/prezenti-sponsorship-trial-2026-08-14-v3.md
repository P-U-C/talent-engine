# Prezenti AI Builder Sponsorships Trial terms

Version: `prezenti-sponsorship-trial-2026-08-14-v3`

This is the single canonical terms release for the Prezenti AI Builder
Sponsorships trial. It states what an accepted builder receives, what they are
asked for in return, what Prezenti owes them, every condition for continuing
support, and how acceptance and close-out are recorded.

`policies/prezenti-sponsorship-trial.json` names this release, the application
form stamps its short digest into the required checkbox, and the Celo EAS pledge
records the full release hash. Changing this document or any material policy
field creates a new digest and requires fresh consent.

Not legal advice. A lawyer must clear this exact release digest before any real
acceptance is recorded.

## The offer

Five places, four months, $1,400 per person: Claude Max 20x at up to $200 per
month, ChatGPT Pro 5x at up to $100 per month, and a $200 one-off flexible
allowance. The maximum programme budget is $7,000.

Applications close on 2026-08-25. The programme term starts in 2026-09 and ends
on 2026-12-29.

The subscriptions are bought by the builder in the builder's own name, and
Prezenti reimburses against receipts. The account, its contents and its history
belong to the builder throughout.

## Selection

The score produces an evidence-linked shortlist; it does not make the final
funding decision. Final selection requires:

1. a scored application under this programme;
2. affirmative acceptance of the current terms digest;
3. verification that the subscription cost is a meaningful access barrier;
4. review of a credible four-month build plan;
5. review that the plan has a credible Celo deployment, integration or material
   ecosystem contribution path;
6. review of authenticity flags and relationships between applicant accounts;
7. conflict review and named steward judgment; and
8. programme-level legal clearance for this exact terms digest.

Celo regional scout endorsements are sourcing and review context only. They are
not technical points and do not decide selection. Selected dossiers or public
announcements beyond the mandatory pledge are published only where the programme
has consent.

## Continuing support conditions

Recipients receive support monthly, subject to these operating conditions:

- Monthly receipts are required for reimbursement.
- Each recipient posts one monthly public build update.
- Thirty days without qualifying project activity triggers review.
- After review is triggered, the recipient has seven days to provide evidence,
  explain the interruption, or cure it before remaining support may be
  cancelled.
- Authenticity flags trigger manual review. A metric flag alone never
  terminates support automatically; confirmed material misrepresentation may
  void the sponsorship.
- Continued support for months three and four requires a verifiable Celo mainnet
  deployment, integration or material ecosystem contribution by the month-two
  checkpoint.
- The term is fixed at four months with no automatic renewal. Unused or vendor
  offset funds return to the Strategic Reserve.

## The mandatory public pledge

Acceptance requires a public Celo EAS attestation signed by the builder's
wallet. It names the builder's GitHub handle, the programme, the covered income,
the cap, the expiry, Prezenti's verified Safe, Prezenti's onward commitment, and
this terms release hash.

There is no private acceptance path in this trial. If a builder does not want
their GitHub handle published in the pledge, they should not apply or should
withdraw before acceptance.

## The give-back

The builder's good-faith pledge is 2% of revenue actually received by the
product through Celo, and any grant, prize and retro-funding income won with the
sponsored work.

**One obligation, one counterparty.** The builder's pledge runs to Prezenti and
to nobody else. Prezenti separately and publicly commits to routing half of
whatever it receives under these pledges to the Celo Community Fund — equivalent
to 1% of covered income. That onward commitment is Prezenti's to keep and
Prezenti's to be judged on; it is not an obligation of the builder.

## Payment route

The calculated give-back is paid directly to the verified Prezenti Safe:

`0xA5c9389A0Ce1bFe24FF883E761Ff313225C77D44`

No 0xSplits collector is deployed for this trial. A collector receiving the full
2% levy would have to route 100% of its balance to Prezenti, which adds a second
policy surface without improving the builder's obligation.

## Bounds and legal character of the pledge

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
  opposite of what is meant.
- Enforcement is **reputational only**: the pledge is public, and so is whether
  it was honoured.

| bound | value | why it exists |
|---|---|---|
| cap | 10× sponsorship — $14,000 | an open-ended claim from an in-kind grant is disproportionate |
| sunset | 36 months after the term ends | it has to end |
| pro-rating | by months actually received | someone who withdraws after two funded months should not owe what a four-month recipient owes |
| enforcement | reputational | stated rather than implied |

## No equity; right of first offer only

No equity is taken. The upside instrument is a right of first offer on a future
round with 14 days' notice — a right to be *offered* participation, not an
obligation to grant it.

It carries no matching right, no pro-rata right, no information right and no
veto. Notice is satisfied by email to the address on file. Prezenti not
responding within 14 days ends the matter for that round. It does not survive a
change of control, binds nobody but Prezenti and the builder, is not assignable,
and expires with the give-back 36 months after the term.

## Tooling, accounts and reimbursement

- The builder is responsible for complying with each vendor's terms.
- Reimbursement stops at the end of the term. The account continues, at the
  builder's expense, or does not — either way it is theirs.
- Where a vendor gives Prezenti credit instead of cash, the builder receives the
  same tooling and owes nothing further; the offset is recorded in the operating
  ledger as a `vendor_offset`.
- Reimbursements are for tooling, not compensation. Neither party is the other's
  employer, contractor or agent. Tax treatment is the builder's own affair, and
  Prezenti gives no advice on it.

## Withdrawing and close-out

A builder may stop at any time, for any reason, without penalty and without
explaining. The give-back pro-rates by whole months actually funded:

```
obligation = 2% × (months funded ÷ 4)
```

Two months funded halves it; withdrawing before any month is funded removes it
entirely. The figure is recorded once, at withdrawal or at the end of the term,
in the operating ledger as `months_funded`.

The initial pledge always records zero months funded, because actual months
funded are not known at acceptance. At withdrawal, term end, cap satisfaction,
expiry, or material correction, the builder signs a replacement close-out
attestation that references the original UID and carries the final months-funded
value. The builder then revokes the superseded original attestation unless a
separate delegated authority exists. Prezenti records the replacement UID and
the revocation transaction as separate durable lifecycle events; a UID is never
overwritten in place.

## Your data

- **Contact details** — email, name, and messaging handles — are stored apart
  from everything scoreable and never appear in a score, snapshot, dossier, or
  public artefact.
- **Applicants** consent when they apply. **People found by scouting** are
  assessed only on public code activity that GitHub already publishes, and are
  contacted only to invite an application.
- **Retention**: application data is kept for the trial and twelve months
  afterwards, then deleted. Contact details are deleted at the same point.
- **Deletion on request** at any time, including after acceptance, by asking.
  Deleting contact details during the term ends reimbursement because there is
  no way to operate the sponsorship; that is a consequence, not a penalty.
- **Publicity**: the mandatory pledge publicly names accepted builders by
  GitHub handle. No unselected applicant is named publicly. Additional selected
  dossiers or announcements are published only where the programme has consent.

## What the programme owes the recipient

Terms that run one way are not a relationship, and at this cheque size the
relationship is the entire return.

- Keeps all IP and all equity
- No exclusivity
- May withdraw without penalty
- A public record of having been backed through the mandatory pledge
- Introductions on request
- Their score and its evidence shared with them
- Feedback to unsuccessful applicants

Feedback is implemented, not just promised: `python3 -m talent_engine.cli
decline` generates specific feedback from the evidence the decision was made
on, and `python3 -m talent_engine.cli feedback-queue` exits non-zero while
anyone is still waiting.

## How agreement is recorded

Displaying terms on a page is not agreement. The application form carries a
required checkbox that restates the substance — the benefits, covered income,
2%, the $14,000 cap, the 36-month sunset, pro-rating, monthly updates,
inactivity review, the seven-day cure period, the month-two Celo continuation
gate, no equity, IP retained, withdrawal without penalty, direct payment to
Prezenti's Safe, and the mandatory public pledge.

Each application is stamped with the short `terms_digest()` marker of this
canonical release. The pledge records the full SHA-256 `termsHash` from the same
release. Changing a page, policy field, payment route, pledge requirement,
selection condition, monitoring condition, or this document changes the digest
and requires new consent.

## Enforcement in code

`ProgramOverlay.__post_init__` refuses to load a policy that:

- permits automated final selection
- lets an authenticity flag terminate support on its own
- has an inactivity rule with no cure period
- has a benefit schedule that does not match the declared budget
- has give-back recipient shares that do not add up
- leaves the give-back uncapped, perpetual, or not pro-rated
- takes equity
- omits the period-aware term start or term end
- omits the canonical terms release
- requires a pledge without declaring that public attestation is mandatory
- uses anything other than direct payment to the verified Prezenti Safe
- fails to state what the programme owes, including that the recipient keeps
  all IP and equity and may withdraw without penalty

`python3 -m talent_engine.cli serve` loads and validates the policy at startup
and refuses to start if it is invalid. The public page renders the terms summary
from the same object.

`python3 -m talent_engine.cli accept` validates the candidate gates, the
non-bypassable programme legal clearance for the exact current digest, the
payment address and the initial EAS UID before writing anything. Acceptance
requires the verified Prezenti Safe, the public pledge UID, and the builder
signer. The decision, cohort row, payment route and attestation event are
written in one transaction.

`python3 -m talent_engine.cli closeout-replace` validates and records the
builder-signed replacement UID. `python3 -m talent_engine.cli closeout-revoke`
records the builder's revocation transaction for the original UID. Both steps
are idempotent and retry-safe.
