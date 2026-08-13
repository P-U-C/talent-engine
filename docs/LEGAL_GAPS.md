# Open legal questions

Not legal advice, and not decisions this repository can make. Listed here so
they are tracked rather than remembered, and so that anyone reading the terms
can see what is unsettled. Each needs an answer from counsel before the first
acceptance, not before publication.

## 1. What the give-back actually is

The pledge is described as good faith, uncapped by any security interest, and
enforced reputationally. That is a coherent position, but it needs confirming
that a public on-chain attestation reciting a percentage of revenue does not
create an enforceable obligation, a security interest, or a revenue-share
arrangement in the recipient's jurisdiction — particularly where the recipient
is outside the programme's own jurisdiction, which is the common case for this
cohort.

## 2. Two counterparties, one pledge

`docs/PREZENTI_SPONSORSHIP_TRIAL.md` splits the give-back 1% to Prezenti and 1%
to the Celo Community Fund. The application-facing copy says "2%". These are the
same number but not the same commitment, and they run to different parties with
different standing to enforce. The pledge instrument needs to record both legs
explicitly, and someone needs to decide whether the Celo Community Fund leg is a
commitment *to* the Fund or a statement of intent *about* it.

## 3. Governing law and dispute resolution

The current pledge hardcodes `governingLaw = "Celo Community Governance"` and
`disputeResolution = "Celo Governance Proposals and Arbitration"`. For an
obligation running from a builder to Prezenti, that is probably the wrong forum
and arguably not a forum at all. Needs a real answer before any new attestation
records it.

## 4. Right of first offer

The ROFO is described as a right to be *offered* participation in a future
round with 14 days' notice, never an obligation. Whether that survives contact
with a term sheet — and whether it needs to be disclosed to a future lead
investor — is a question for counsel, not for the rubric.

## 5. Tooling paid for by a third party

The programme reimburses vendor subscriptions bought in the recipient's own
name. Who owns the account, what happens to it at month four, and whether any
vendor's terms prohibit third-party payment or transfer, are unresolved. Vendor
offsets (credits given to Prezenti instead of cash) may also have tax treatment
distinct from reimbursement.

## 6. Withdrawal and pro-rating

Terms allow withdrawal at any time with the give-back scaling to months
actually taken. The mechanism for computing and recording that is now in the
operating ledger (`months_funded`), but whether a pro-rated obligation survives
withdrawal at all, and for how long, is a drafting question.

## 7. Data protection

Applications collect contact details and free text from applicants who may be
anywhere. Contact data is quarantined from scoring and dossiers, and free text
is redacted for contact shapes, which is a good technical posture but not a
lawful-basis analysis. Retention periods, deletion on request, and the basis
for scouting people who never applied all need a position.

## 8. Public record of unsuccessful applicants

The programme commits to feedback for everyone who applied. Nothing publishes
an unsuccessful applicant's name or score, and it should stay that way — but
the commitment to a "public record that we backed you" for recipients needs an
explicit consent step, which currently rides on acceptance rather than being
asked separately.
