# What happens after someone is accepted

**Status: agreed and enforced in code.** `policies/prezenti-sponsorship-trial.json` carries these terms and `ProgramOverlay` refuses to load an overlay that breaks them.

Design notes on the give-back, the pledge, and 0xSplits. Not legal advice; the
pledge form already collects governing law and dispute resolution, which means
somebody should have a lawyer read the final wording.

## What the two mechanisms actually do

They are often discussed together as if they combine into enforcement. They do
not, and the distinction decides everything downstream.

**The Prezenti Pledge** (`prezenti/prezenti-pledge`) writes an EAS attestation
on Celo — pledgor, amount, type, frequency, governing law — signed by the
builder's wallet. That is a *public, timestamped, signed promise*. Its force is
reputational: it is visible, it is attributable, and breaking it is legible to
everyone who looks. That is real, and it is not nothing.

**0xSplits** (natively supported on Celo) *distributes* funds that arrive at a
split contract, automatically and trustlessly. It has no reach over funds that
arrive anywhere else.

So the honest position: **on-chain gives you a credible promise and frictionless
payment when it is honoured. It does not give you a claim.** Revenue landing in
a builder's own wallet, or a Stripe account, is untouched by either mechanism.
Any design that assumes otherwise is decoration.

That is not a reason to abandon the idea. It is a reason to pick an instrument
whose value does not depend on enforcement.

## The problem with 2% of revenue

The current overlay pledges 200bps of "revenue actually received by the product
through Celo", split evenly between Prezenti and the Celo Community Fund. Three
problems, in increasing order of importance.

**It is worth approximately nothing in expectation.** Most sponsored builders
will have no revenue in three years. The ones who do will mostly have small
revenue. 2% of small revenue is a rounding error against the cost of tracking
it, invoicing it, and chasing it.

**It is actively harmful in the one case that matters.** A revenue-share
encumbrance is the kind of thing a seed investor finds in diligence and asks to
have removed. An uncapped, perpetual 2% of gross revenue attached to a company
by a $1,400 in-kind grant is disproportionate enough to be embarrassing to
defend, and the builder will come back asking to buy it out. That conversation
costs more goodwill than the term will ever return.

**It selects against the people the engine exists to find.** This is the
decisive argument. The whole thesis is finding high-agency builders who are
under-recognised — people who *could* get funded elsewhere but have not been
seen yet. Those people have alternatives. A builder with options reads
"perpetual 2% of revenue for $1,400 of Claude credits" and declines; a builder
with no options signs anything. Aggressive terms therefore filter the applicant
pool toward exactly the profiles the rubric is designed to look past. The terms
would quietly undo the sourcing.

For scale: $1,400 for 2% implies a $70,000 valuation on the upside claim. Y
Combinator's $500,000 for 7% implies roughly $7,000,000. The comparison is not
apples to apples — revenue share is not equity — but the order of magnitude is
worth seeing before deciding the terms are generous.

## What to take instead

Ordered by what I would actually do.

**1. Cap it and sunset it.** Keep 2% of Celo revenue, but cap the total at a
multiple of the sponsorship — 10x is $14,000 — and expire it three years after
the term ends. This converts an open-ended encumbrance into a finite,
comprehensible "pay it forward". Nearly every sponsored builder will pay zero
either way; the difference is entirely in whether a good builder is willing to
sign, and in whether it survives a future diligence process. Cheap to concede,
large effect on acceptance.

**2. Pro-rate it against what they actually received.** The overlay already has
a month-two Celo gate, an inactivity review, and a cure period, so someone can
leave after one month. Nothing currently says their obligation is smaller than
someone who completed four. It should be: give-back scales with months of
sponsorship actually taken. Otherwise the terms punish the person who
honourably withdrew early.

**3. Take a right of first offer, not equity.** The right to be offered
participation in their next financing round costs the builder nothing today,
creates no cap-table object, needs no enforcement, and is where the real upside
lives at this cheque size. It is also the term a good builder finds reasonable,
which matters more than its expected value.

**4. Extend the give-back to grant and prize income, not just product
revenue.** This is where money actually appears for early builders — hackathons,
retro funding, ecosystem grants — and it arrives on-chain already, which makes
it the one category a Splits address can genuinely capture. A builder who wins a
$20,000 grant with work Prezenti sponsored will feel entirely fine sending 2%
back. A builder with a struggling product will resent an invoice.

**5. Be honest that the main return is reputational.** At $7,000 across five
people, the realistic return is not financial. It is that Prezenti found these
people first, publicly, with an evidence trail — and that compounds into deal
flow, standing in the ecosystem, and a defensible claim to a sourcing method
that works. The scoring engine being open source is part of that return.

## Mechanics, if this goes ahead

- Create the split **at acceptance**, not at first revenue. It costs little,
  and it makes the give-back a thing that already exists rather than a thing
  someone has to set up later, at exactly the moment they least want to.
- Make the split **immutable** and use long-lived Prezenti and Celo Community
  Fund addresses. A mutable split needs a controller, and a controller is a
  party the builder has to trust not to change the terms after the fact.
- Put the split address in the acceptance email, alongside the pledge link.
  Routing revenue through it stays voluntary; the point is that it is
  frictionless when they choose to.
- The pledge attestation should record the **capped, pro-rated, sunsetting**
  terms, not the current open-ended ones — the attestation is the public
  artefact, so it should say the thing you actually want to be held to.
- Record the split address and the attestation UID against the cohort row, so
  `monitor` and `measure` can see them.

## The connection to selection integrity

The gaming pressure on this pipeline is a function of what is at the end of it.
Today the prize is $1,400 of AI subscriptions, which is worth manufacturing a
profile for but not worth building an elaborate operation for. Attach a real
equity claim and that changes: the ring detection in `modes/rings.py` moves
from precautionary to load-bearing, and the outstanding item — contributor
lists of validating repositories, which would catch a ring whose members never
applied — stops being optional.

Decide the terms and the selection defences together, not in sequence.


## Agreed position

The framing that settled it: this is about building relationships, not about
extracting initial monetary value. At $1,400 a head the financial claim was
never going to be the return — the standing, the deal flow and the goodwill
are. Terms that read as grasping cost more of that than they could ever
recover.

So the give-back stays, because reciprocity is part of the relationship, but it
is bounded in every direction a person would reasonably worry about:

| term | value | why |
|---|---|---|
| give-back | 200bps of Celo revenue | unchanged |
| also applies to | grant, prize and retro-funding income | where early money actually lands, and the one category a Splits address can capture |
| cap | 10x sponsorship — $14,000 | makes it finite and survivable in diligence |
| sunset | 36 months after term end | it ends |
| pro-rating | by months actually received | leaving at the month-two gate halves it |
| enforcement | reputational | stated plainly rather than implied |
| equity | none taken | — |
| upside | right of first offer on the next round, 14 days' notice | costs nothing today, needs no enforcement |

### What the program owes in return

Terms that run one way are not a relationship, so the overlay now refuses to
load without a `commitments_to_recipient` block, and specifically without
guaranteeing that the recipient keeps all IP and equity and may withdraw
without penalty. The current set:

- keeps all IP and equity
- no exclusivity
- may withdraw without penalty
- a public record of having been backed
- introductions on request
- their score and its evidence shared with them
- feedback to unsuccessful applicants

That last one costs real time and is the one most programs skip. It is also the
one that makes the difference between an applicant who was rejected and an
applicant who was treated with respect, and the second person tells other
people to apply.

### Enforced, not documented

`ProgramOverlay.__post_init__` refuses an uncapped give-back, a give-back that
never expires, one that is not pro-rated, any overlay that takes equity, and
any overlay that does not say what the program owes. `giveback_owed_bps(months)`
does the pro-rating. The reasoning lives in this document; the guarantees live
in the code, because a policy that exists only in prose drifts the first time
somebody is in a hurry.
