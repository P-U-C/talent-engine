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
