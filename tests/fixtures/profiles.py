"""Synthetic profiles used to pin the rubric's behaviour.

These are the regression targets for the product's central claim: a
manufactured profile must not be able to outrank a real builder.  Fixed dates
throughout so scores are deterministic.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from talent_engine.model import (
    Application,
    ProfileSnapshot,
    PullRequestActivity,
    RepoActivity,
    ReviewActivity,
)

WINDOW_START = "2026-02-05T00:00:00+00:00"
WINDOW_END = "2026-08-05T00:00:00+00:00"


def _weeks_spread(count: int, *, start_week: int = 6, step: int = 1) -> list[str]:
    """`count` ISO week keys inside the window, evenly spaced."""
    return [f"2026-W{start_week + i * step:02d}" for i in range(count)]


def _iso(y: int, m: int, d: int) -> str:
    return datetime(y, m, d, tzinfo=timezone.utc).isoformat()


def genuine_builder() -> ProfileSnapshot:
    """A real independent builder: originates, finishes, keeps showing up.

    Deliberately *not* an insider: only a handful of external merged PRs and
    few reviews. If the rubric is working, this profile scores well on the
    strength of shipped work alone.
    """
    repos = [
        RepoActivity(
            name="amara-dev/mpesa-celo-bridge",
            owner="amara-dev",
            is_fork=False,
            pushed_at=_iso(2026, 7, 28),
            created_at=_iso(2025, 11, 2),
            description="Off-ramp bridge for cUSD to M-Pesa. Solidity contracts + relayer.",
            language="Solidity",
            topics=["celo", "stablecoin", "solidity"],
            has_releases=True,
            has_description=True,
            homepage="https://mpesa-celo.example",
            homepage_verified=True,
            license="MIT",
            commits_in_window=94,
        ),
        RepoActivity(
            name="amara-dev/minipay-savings-circle",
            owner="amara-dev",
            is_fork=False,
            pushed_at=_iso(2026, 6, 14),
            created_at=_iso(2026, 2, 20),
            description="Rotating savings circles as a MiniPay mini app.",
            language="TypeScript",
            topics=["minipay", "celo", "web3"],
            has_releases=True,
            has_description=True,
            homepage="https://savings-circle.example",
            homepage_verified=True,
            license="Apache-2.0",
            commits_in_window=61,
        ),
        RepoActivity(
            name="amara-dev/mcp-onchain-tools",
            owner="amara-dev",
            is_fork=False,
            pushed_at=_iso(2026, 7, 30),
            created_at=_iso(2026, 5, 9),
            description="MCP server exposing on-chain reads as agent tools.",
            language="Python",
            topics=["mcp", "ai-agents"],
            has_releases=False,
            has_description=True,
            homepage="",
            license="MIT",
            commits_in_window=38,
        ),
        RepoActivity(
            name="amara-dev/dotfiles",
            owner="amara-dev",
            is_fork=False,
            pushed_at=_iso(2026, 3, 3),
            created_at=_iso(2024, 1, 1),
            description="",
            language="Shell",
            topics=[],
            commits_in_window=7,
        ),
        RepoActivity(
            name="amara-dev/hardhat",
            owner="amara-dev",
            is_fork=True,
            pushed_at=_iso(2026, 4, 1),
            created_at=_iso(2026, 4, 1),
            description="Fork of hardhat",
            language="TypeScript",
            commits_in_window=1,
        ),
    ]
    merged = [
        PullRequestActivity(
            repo="celo-org/celo-composer",
            number=412,
            title="Add MiniPay auto-connect example",
            merged_at=_iso(2026, 4, 18),
            created_at=_iso(2026, 4, 11),
        ),
        PullRequestActivity(
            repo="celo-org/docs",
            number=889,
            title="Fix fee-abstraction docs for USDm",
            merged_at=_iso(2026, 5, 22),
            created_at=_iso(2026, 5, 20),
        ),
        PullRequestActivity(
            repo="mento-protocol/mento-sdk",
            number=77,
            title="Handle broker quote rounding",
            merged_at=_iso(2026, 6, 9),
            created_at=_iso(2026, 6, 2),
        ),
        PullRequestActivity(
            repo="modelcontextprotocol/servers",
            number=1204,
            title="Add read-only EVM server",
            merged_at=_iso(2026, 7, 15),
            created_at=_iso(2026, 7, 3),
        ),
    ]
    reviews = [
        ReviewActivity(repo="celo-org/celo-composer", number=420, submitted_at=_iso(2026, 5, 2)),
        ReviewActivity(repo="celo-org/celo-composer", number=431, submitted_at=_iso(2026, 6, 19)),
        ReviewActivity(repo="mento-protocol/mento-sdk", number=81, submitted_at=_iso(2026, 7, 1)),
    ]
    return ProfileSnapshot(
        handle="amara-dev",
        account_created_at=_iso(2021, 3, 14),
        collected_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        repos=repos,
        merged_prs=merged,
        reviews=reviews,
        active_weeks=_weeks_spread(19),
        application=Application(
            context_statement=(
                "I build from Nairobi without institutional backing. No CS degree and "
                "no local investor network, so everything shipped here was self-funded "
                "and self-taught alongside contract work."
            ),
            context_factors=["self-taught", "no institutional funding"],
            referrer_name="Celo Regional Scout - East Africa",
            declared_repo="amara-dev/minipay-savings-circle",
        ),
    )


def gamed_profile() -> ProfileSnapshot:
    """The cheapest credible attack: fresh account, bulk commits, forks, fake referrer."""
    repos = [
        RepoActivity(
            name="fastbuilder99/web3-mega-project",
            owner="fastbuilder99",
            is_fork=False,
            pushed_at=_iso(2026, 7, 22),
            created_at=_iso(2026, 7, 20),
            description="",
            language="Solidity",
            topics=[],
            commits_in_window=80,
        ),
    ] + [
        RepoActivity(
            name=f"fastbuilder99/forked-{i}",
            owner="fastbuilder99",
            is_fork=True,
            pushed_at=_iso(2026, 7, 21),
            created_at=_iso(2026, 7, 21),
            description="celo solidity web3 defi",
            language="Solidity",
            topics=["celo", "defi"],
            commits_in_window=0,
        )
        for i in range(5)
    ]
    return ProfileSnapshot(
        handle="fastbuilder99",
        account_created_at=_iso(2026, 7, 19),
        collected_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        repos=repos,
        merged_prs=[],
        reviews=[],
        active_weeks=["2026-W30"],
        application=Application(
            context_statement="I need funding to build.",
            context_factors=["underrepresented"],
            referrer_name="Totally Real Scout",
            declared_repo="fastbuilder99/web3-mega-project",
        ),
    )


def quiet_finisher() -> ProfileSnapshot:
    """Low volume, high finish: two small complete projects, steady cadence.

    The profile a volume-driven screen throws away.  It should beat the gamed
    profile comfortably and land in credible range of the headline builder.
    """
    repos = [
        RepoActivity(
            name="tobi-k/celo-receipt-printer",
            owner="tobi-k",
            is_fork=False,
            pushed_at=_iso(2026, 7, 10),
            created_at=_iso(2026, 2, 12),
            description="Thermal receipt printing for small merchants taking cUSD.",
            language="Python",
            topics=["celo", "stablecoin"],
            has_releases=True,
            has_description=True,
            homepage="https://receipts.example",
            homepage_verified=True,
            license="MIT",
            commits_in_window=31,
        ),
        RepoActivity(
            name="tobi-k/ussd-wallet-helper",
            owner="tobi-k",
            is_fork=False,
            pushed_at=_iso(2026, 6, 2),
            created_at=_iso(2026, 3, 1),
            description="USSD fallback flows for feature-phone wallet users.",
            language="Go",
            topics=["wallet"],
            has_releases=True,
            has_description=True,
            license="MIT",
            commits_in_window=22,
        ),
    ]
    return ProfileSnapshot(
        handle="tobi-k",
        account_created_at=_iso(2022, 8, 4),
        collected_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        repos=repos,
        merged_prs=[],
        reviews=[],
        active_weeks=_weeks_spread(13, start_week=7, step=2),
        application=Application(
            context_statement="",
            context_factors=[],
            referrer_name="",
            declared_repo="tobi-k/celo-receipt-printer",
        ),
    )


def insider_low_shipper() -> ProfileSnapshot:
    """Well-connected, ships little of their own.

    Exists to prove invariant 1 empirically: a strong insider-network profile
    must not beat a genuine independent builder on this rubric.
    """
    repos = [
        RepoActivity(
            name="wellconnected/scratch",
            owner="wellconnected",
            is_fork=False,
            pushed_at=_iso(2026, 3, 8),
            created_at=_iso(2026, 3, 1),
            description="",
            language="JavaScript",
            topics=[],
            commits_in_window=4,
        ),
    ]
    merged = [
        PullRequestActivity(
            repo="celo-org/celo-monorepo",
            number=1000 + i,
            title=f"Small fix {i}",
            merged_at=_iso(2026, 3 + (i % 5), 10),
            created_at=_iso(2026, 3 + (i % 5), 8),
        )
        for i in range(14)
    ]
    reviews = [
        ReviewActivity(repo="celo-org/celo-monorepo", number=2000 + i, submitted_at=_iso(2026, 4, 5))
        for i in range(15)
    ]
    return ProfileSnapshot(
        handle="wellconnected",
        account_created_at=_iso(2019, 1, 1),
        collected_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        repos=repos,
        merged_prs=merged,
        reviews=reviews,
        active_weeks=_weeks_spread(10, start_week=8, step=2),
        application=Application(referrer_name="", declared_repo=""),
    )


# ---------------------------------------------------------------------------
# Red team.
#
# `gamed_profile` above is the attack of someone who has NOT read the rubric.
# The rubric is published on purpose, so the realistic adversary has read it
# and knows exactly which checks exist. These two profiles are what that person
# builds. They are here to be measured, not to pass.
# ---------------------------------------------------------------------------


def patient_farmer() -> ProfileSnapshot:
    """Low-and-slow manufacturing: the attack the burst check cannot see.

    Every anti-gaming check in `flags.py` keys on *concentration* — a fresh
    account, activity collapsed into a few weeks, implausible commits per week.
    All of them are defeated by the same cheap move: a scheduled job that makes
    a few real commits a week for a few months, from an account aged in
    advance.

    Cost to produce: one cron entry, plus an afternoon adding descriptions,
    licences, homepages and tagged releases to three thin repositories —
    because the rubric says finishing metadata is the strongest signal, and
    metadata is the one part of finishing that can be added without doing the
    work.
    """
    repos = [
        RepoActivity(
            name=f"steady-sam/{name}",
            owner="steady-sam",
            is_fork=False,
            pushed_at=_iso(2026, 7, 25),
            created_at=_iso(2026, 2, 10),
            description=desc,
            language=lang,
            topics=topics,
            has_releases=True,
            has_description=True,
            homepage=f"https://{name}.example",
            license="MIT",
            commits_in_window=commits,
        )
        for name, desc, lang, topics, commits in [
            (
                "celo-payments-kit",
                "Payment helpers for Celo stablecoin apps.",
                "TypeScript",
                ["celo", "minipay", "web3"],
                48,
            ),
            (
                "agent-tool-runtime",
                "A small runtime for agent tool calling.",
                "Rust",
                ["mcp", "ai-agents", "rust"],
                41,
            ),
            (
                "evm-index-lite",
                "Lightweight EVM log indexer.",
                "Go",
                ["ethereum", "infrastructure"],
                35,
            ),
        ]
    ]
    return ProfileSnapshot(
        handle="steady-sam",
        account_created_at=_iso(2024, 6, 1),  # aged past new_account_days
        collected_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        repos=repos,
        merged_prs=[],
        reviews=[],
        # 20 weeks, ~6 commits each: under the inflation threshold, spread
        # across all three thirds of the window.
        active_weeks=_weeks_spread(20, start_week=6),
        application=Application(
            context_statement=(
                "Self-taught, working from a region with no local funding for "
                "open source. Everything here was built in evenings."
            ),
            context_factors=["self-taught", "no institutional funding"],
            referrer_name="",
            declared_repo="steady-sam/celo-payments-kit",
        ),
    )


def sockpuppet_ring() -> ProfileSnapshot:
    """The same patient profile, plus merged PRs into repos the attacker owns.

    `external_validation` and `collaboration` are gated on `is_own_repo`, which
    means "not owned by this account". A second account is free, so PRs merged
    between two accounts the same person controls read as an independent
    reviewer clearing them — which is precisely the thing those dimensions
    claim to measure.

    Nothing in a snapshot currently distinguishes an independent repository
    from an alt's: not age, not contributor count, not whether anyone unrelated
    ever touched it.
    """
    base = patient_farmer()
    ring = ["sam-alt-one", "sam-labs-io", "samtools-dev", "sam-oss-collective"]
    merged = [
        PullRequestActivity(
            repo=f"{owner}/{repo}",
            number=10 + i,
            title=title,
            merged_at=_iso(2026, 3 + i, 12),
            created_at=_iso(2026, 3 + i, 5),
        )
        for i, (owner, repo, title) in enumerate(
            [
                (ring[0], "sdk", "Add retry helper"),
                (ring[1], "protocol-utils", "Support batch calls"),
                (ring[2], "cli", "Fix config precedence"),
                (ring[3], "runtime", "Add tool schema validation"),
            ]
        )
    ]
    reviews = [
        ReviewActivity(repo=f"{ring[i % 4]}/misc", number=50 + i, submitted_at=_iso(2026, 5, 6))
        for i in range(6)
    ]
    return ProfileSnapshot(
        handle="steady-sam",
        account_created_at=base.account_created_at,
        collected_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        repos=base.repos,
        merged_prs=merged,
        reviews=reviews,
        active_weeks=base.active_weeks,
        application=base.application,
    )


# ---------------------------------------------------------------------------
# Pools, for the cross-applicant check.
#
# The single-profile fixtures cannot exercise ring detection: it is a question
# about a group. These build two groups with deliberately similar shapes — both
# cluster, both review each other — differing only in whether anyone outside
# the group has ever accepted their work.
# ---------------------------------------------------------------------------


def _member(handle: str, merged: list[tuple[str, int]], reviews: list[tuple[str, int]],
            created: str) -> ProfileSnapshot:
    repos = [
        RepoActivity(
            name=f"{handle}/{name}",
            owner=handle,
            is_fork=False,
            pushed_at=_iso(2026, 7, 20),
            created_at=_iso(2026, 2, 15),
            description=f"{name} project",
            language="TypeScript",
            topics=["celo", "web3"],
            has_releases=True,
            has_description=True,
            license="MIT",
            commits_in_window=40,
        )
        for name in ("sdk", "tools")
    ]
    return ProfileSnapshot(
        handle=handle,
        account_created_at=created,
        collected_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        repos=repos,
        merged_prs=[
            PullRequestActivity(repo=r, number=n, title="patch",
                                merged_at=_iso(2026, 5, 10), created_at=_iso(2026, 5, 1))
            for r, n in merged
        ],
        reviews=[
            ReviewActivity(repo=r, number=n, submitted_at=_iso(2026, 5, 12))
            for r, n in reviews
        ],
        active_weeks=_weeks_spread(18),
        application=Application(declared_repo=f"{handle}/sdk"),
    )


def sockpuppet_pool() -> dict[str, ProfileSnapshot]:
    """Four accounts, one operator. Every merged PR lands inside the group.

    This is what a ring looks like once its members all apply — which they
    will, because several applications are several chances at a limited number
    of seats.
    """
    ring = ["ring-a", "ring-b", "ring-c", "ring-d"]
    pool = {}
    for i, h in enumerate(ring):
        others = [o for o in ring if o != h]
        pool[h] = _member(
            h,
            merged=[(f"{others[0]}/sdk", 10 + i), (f"{others[1]}/tools", 20 + i)],
            reviews=[(f"{others[2]}/sdk", 30 + i)],
            # Accounts stood up in the same week.
            created=_iso(2024, 6, 3 + i),
        )
    return pool


def genuine_pool() -> dict[str, ProfileSnapshot]:
    """Three real builders who know each other — the false positive to avoid.

    They review each other's work, exactly like the ring does. The difference
    is that most of what they have merged went to projects nobody in the group
    controls, and their accounts are years apart.
    """
    people = ["ada-builds", "kwame-dev", "lin-eth"]
    outside = [
        ("celo-org/celo-composer", 401),
        ("mento-protocol/mento-sdk", 88),
        ("modelcontextprotocol/servers", 1301),
        ("ethereum-optimism/optimism", 770),
    ]
    pool = {}
    for i, h in enumerate(people):
        peer = people[(i + 1) % len(people)]
        pool[h] = _member(
            h,
            # One PR to a peer, four to unrelated ecosystem projects.
            merged=[(f"{peer}/sdk", 50 + i)] + [(r, n + i) for r, n in outside],
            reviews=[(f"{peer}/tools", 60 + i), ("celo-org/celo-composer", 402 + i)],
            created=_iso(2019 + i * 2, 3, 11),
        )
    return pool


def metadata_maximiser() -> ProfileSnapshot:
    """Taxonomy-optimal metadata on thin repos, with no accomplices at all.

    The cheapest attack that is not obviously an attack.  Every field set here
    is one the applicant controls directly and can set through the API in
    minutes, and the exact strings that score are public: this program ships
    its taxonomy in `programs/*.json` and the rubric tells you to read it.

    No sockpuppets, no fake external validation, nothing a human would call
    fraud.  Five throwaway repositories, taxonomy keywords in every name,
    description and topic list, all five finishing marks set, a `homepage`
    string that nobody fetches, and a weekly cron spreading commits across
    fourteen distinct weeks in all three thirds of the window so neither
    `burst_activity` nor `metric_inflation` fires.  The repositories sit under
    an organisation rather than the user handle, which used to be enough on its
    own to restore full taxonomy credit.

    Against the live `prezenti-sponsorship-trial` weights this originally
    scored 67.52 clean, beating `patient_farmer` by nearly seven points, and
    74.97 once three typo-fix pull requests were added -- above the genuine
    builder, with no flag raised.
    """
    weeks = [f"2026-W{w:02d}" for w in (7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31, 32)]
    topics = ["celo", "minipay", "mcp", "x402"]
    repos = [
        RepoActivity(
            name=f"agentworks/agent-kit-{i}",
            owner="agentworks",  # an org the candidate controls, not the handle
            is_fork=False,
            pushed_at=_iso(2026, 8, 3),
            created_at=_iso(2026, 2, 10),
            description="MCP server for Celo MiniPay agent payments over x402",
            language="typescript",
            topics=topics,
            has_releases=True,
            has_description=True,
            homepage="https://example.invalid",
            homepage_verified=False,  # nothing answers there
            license="MIT",
            commits_in_window=c,
            commit_weeks=weeks[i::5],
        )
        for i, c in enumerate([14, 12, 10, 9, 7])
    ]
    return ProfileSnapshot(
        handle="maximiser",
        account_created_at=_iso(2019, 4, 2),
        collected_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        repos=repos,
        merged_prs=[],
        reviews=[],
        active_weeks=weeks,
        application=Application(),  # declares nothing, so nothing to flag
    )
