# Open legal questions

Not legal advice. Most of what was listed here was a drafting problem rather
than a legal one, and drafting problems are fixable without counsel. Those are
now closed in `SPONSORSHIP_TERMS.md` and recorded below so the reasoning is
visible. What remains genuinely needs a lawyer, and needs one before the first
acceptance rather than before publication.

---

## Closed by drafting

### 1. Two counterparties, one pledge — **closed**

Was: the trial doc split the give-back 1% to Prezenti and 1% to the Celo
Community Fund, while the application copy said "2%". Same number, two parties
with different standing.

Now: the builder's obligation runs to **Prezenti only**, at 2%. Prezenti
separately and publicly commits to routing half of what it receives to the Celo
Community Fund. Asking a builder to owe something to a third party they have no
agreement with — one that cannot know the obligation exists and would have no
standing to act on it — was never going to mean anything. Prezenti's onward
commitment is Prezenti's to keep and to be judged on. The attestation records
both legs so the second is as public as the first.

### 2. Governing law and dispute resolution — **closed**

Was: the pledge hardcoded `governingLaw = "Celo Community Governance"` and
`disputeResolution = "Celo Governance Proposals and Arbitration"`.

Now: the terms state that the pledge specifies **no governing law and is not
subject to arbitration**, because naming a forum for a commitment nobody
intends to enforce implies the opposite of what is meant. The old values are
not carried into the new schema. This is the honest position for a
reputational commitment; if counsel decides the pledge should be enforceable,
this reopens as question A below.

### 3. What the give-back is — **closed as drafting, open as risk (see A)**

The terms now say plainly that the pledge is a good-faith commitment intended
to be unenforceable, creating no security interest, lien, charge, debt,
royalty, revenue-share, equity, option or cap-table entry, and giving Prezenti
no claim over the builder's company, assets or financings.

That is a clear statement of intent. Whether it is *effective* in a given
jurisdiction is question A.

### 4. Right of first offer — **closed**

Now stated as: offer not refusal; no matching, pro-rata, information or veto
right; notice by email; silence for 14 days ends it for that round; does not
survive a change of control; not assignable; expires with the give-back. A
builder can honestly tell a lead investor that nobody holds rights over the
round.

### 5. Tooling paid for by a third party — **closed**

Accounts are bought by the builder in their own name and reimbursed against a
receipt, so nothing transfers at the end of the term and the account was never
Prezenti's. Vendor-terms compliance sits with the builder, vendor offsets are
recorded in the operating ledger, and reimbursement is explicitly not
compensation with no employment or agency relationship created.

### 6. Withdrawal and pro-rating — **closed**

The formula is published: `2% × (months funded ÷ 4)`. The figure is recorded
once in the operating ledger as `months_funded` and carried in the attestation,
so the arithmetic is checkable by anyone.

### 7. Data protection — **closed as policy, open as compliance (see C)**

Retention (trial plus twelve months), deletion on request, separation of
contact data from anything scoreable, and the distinction between applicants
who consent and scouted people assessed only on already-public activity are all
now stated. Whether that constitutes a lawful basis in every jurisdiction an
applicant might sit in is question C.

### 8. Public record of unsuccessful applicants — **closed**

The public record of backing is now a separate explicit opt-in at acceptance
rather than something riding on acceptance itself. Declining changes nothing
else. Nobody unselected is ever named publicly.

---

## Still needs counsel

### A. Does the disclaimer hold?

The terms say the pledge is unenforceable and creates no security interest. A
public, signed, on-chain attestation reciting a percentage of revenue with a
cap and an expiry has the *shape* of an instrument, and a builder's future
investor or acquirer may treat it as one regardless of what the text says.
Needs confirming in the jurisdictions this cohort will actually sit in, which
for this programme means outside the programme's own. **This is the one that
matters most**, because every other closure above assumes the answer is yes.

### B. Is Prezenti's onward commitment a promise to anyone?

Prezenti now publicly commits to routing 1% to the Celo Community Fund. Whether
that creates an obligation the Fund could rely on, whether it should be
formalised with them, and what happens if the Fund's structure changes over the
36 months, are questions for Prezenti's own counsel rather than the builder's.

### C. Lawful basis, and scouting people who never applied

The engine assesses people from public GitHub activity and contacts them to
invite an application. Retention and deletion are now stated, but the lawful
basis for the scouting itself, and the notice owed to someone assessed without
having applied, need a position under the relevant data-protection regimes.

### D. Tax treatment of reimbursements and vendor offsets

Reimbursing a builder's subscription and receiving a vendor credit instead of
cash are not obviously the same thing for either party. Neither is stated to be
compensation, but stating it does not settle it.
