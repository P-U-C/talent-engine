"""Program configuration.

Everything a deployment can vary lives here: weights, window length, taxonomy
packs, referrer registry, thresholds.  Nothing program-specific is hardcoded in
the scorer.  That is what lets one engine serve both a grant program and a
recruiting pipeline without the two drifting apart (invariant 6).

Configs are JSON so the core stays stdlib-only -- a candidate must be able to
clone the repo and reproduce their score with no install step.  YAML is
accepted when PyYAML happens to be present.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

DEFAULT_WINDOW_MONTHS = 6

# Reference rubric: 80 automated + 20 application. Per-program overridable,
# but the split is validated so a program cannot accidentally ship a rubric
# where self-declared fields dominate measured output.
REFERENCE_WEIGHTS: dict[str, float] = {
    "shipping_agency": 25.0,
    "consistency": 15.0,
    "external_validation": 12.0,
    "collaboration": 8.0,
    "ecosystem_footprint": 10.0,
    "frontier_signal": 10.0,
    "context_statement": 10.0,
    "trusted_referral": 10.0,
}


@dataclass
class Taxonomy:
    """A named set of matchers for 'is this activity in our ecosystem'.

    Matching is deliberately explicit -- orgs, repos, topics, keywords,
    languages -- rather than an embedding or a classifier.  A candidate has to
    be able to read the list and see why they did or did not match.
    """

    name: str
    orgs: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.orgs = [o.lower() for o in self.orgs]
        self.repos = [r.lower() for r in self.repos]
        self.topics = [t.lower() for t in self.topics]
        self.keywords = [k.lower() for k in self.keywords]
        self.languages = [l.lower() for l in self.languages]

    def match_reasons(
        self,
        *,
        full_name: str = "",
        description: str = "",
        topics: list[str] | None = None,
        language: str | None = None,
    ) -> list[str]:
        """Why this activity matched. Empty list means no match."""
        reasons: list[str] = []
        name = (full_name or "").lower()
        owner = name.split("/")[0] if "/" in name else ""
        desc = (description or "").lower()
        tops = [t.lower() for t in (topics or [])]
        lang = (language or "").lower()

        if owner and owner in self.orgs:
            reasons.append(f"org:{owner}")
        if name and name in self.repos:
            reasons.append(f"repo:{name}")
        for t in tops:
            if t in self.topics:
                reasons.append(f"topic:{t}")
        if lang and lang in self.languages:
            reasons.append(f"language:{lang}")
        for kw in self.keywords:
            # Word-boundary match. Substring matching made "mcp" hit
            # "mcpherson" and inflated frontier scores on unrelated repos.
            pattern = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
            if re.search(pattern, desc) or re.search(pattern, name):
                reasons.append(f"keyword:{kw}")
        # Preserve order, drop duplicates.
        return list(dict.fromkeys(reasons))


@dataclass
class Thresholds:
    new_account_days: int = 180
    burst_week_threshold: int = 2  # activity in <= N weeks is a burst
    burst_commit_discount: float = 0.05  # gamed volume -> near-nothing
    inactivity_days: int = 30
    min_commits_for_volume_credit: int = 1
    metric_inflation_commits_per_week: int = 60


@dataclass
class ProgramConfig:
    key: str
    name: str
    window_months: int = DEFAULT_WINDOW_MONTHS
    weights: dict[str, float] = field(default_factory=lambda: dict(REFERENCE_WEIGHTS))
    ecosystem: Taxonomy = field(default_factory=lambda: Taxonomy("ecosystem"))
    frontier: Taxonomy = field(default_factory=lambda: Taxonomy("frontier"))
    referrers: list[str] = field(default_factory=list)
    thresholds: Thresholds = field(default_factory=Thresholds)
    # Recruitment mode turns the access-barrier field off by default; it is
    # only appropriate for an access-focused program.
    context_statement_enabled: bool = True
    score_free_text: bool = False  # optional pluggable LLM pass, off by default
    mode: str = "program"  # "program" | "recruitment"
    # Copy for the public application page. Lives here rather than in the
    # server because the words are the running organisation's to write and
    # sign off, and they should be editable without touching Python. Unset
    # keys fall back to the generic defaults in server/pages.py.
    page: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = set(self.weights) - set(REFERENCE_WEIGHTS)
        if unknown:
            raise ValueError(f"{self.key}: unknown rubric dimensions {sorted(unknown)}")
        missing = set(REFERENCE_WEIGHTS) - set(self.weights)
        for m in missing:
            self.weights[m] = 0.0
        if not self.context_statement_enabled:
            self.weights["context_statement"] = 0.0

        total = sum(self.weights.values())
        if total <= 0:
            raise ValueError(f"{self.key}: rubric weights sum to zero")

        # Invariant 1: agency over pedigree. external_validation and
        # collaboration are insider-network proxies -- a program that weights
        # them above measured shipping selects for people who already have
        # access, which is the exact failure this product exists to avoid.
        insider = self.weights.get("external_validation", 0) + self.weights.get(
            "collaboration", 0
        )
        agency = self.weights.get("shipping_agency", 0) + self.weights.get(
            "consistency", 0
        )
        if insider >= agency:
            raise ValueError(
                f"{self.key}: insider-network weight ({insider}) >= agency weight "
                f"({agency}). Supporting evidence must not dominate measured "
                "shipping (design invariant 1)."
            )

        self_declared = self.weights.get("context_statement", 0) + self.weights.get(
            "trusted_referral", 0
        )
        if self_declared > total / 2:
            raise ValueError(
                f"{self.key}: self-declared weight ({self_declared}) exceeds half of "
                f"the rubric ({total})."
            )

    @property
    def window_days(self) -> int:
        return int(self.window_months * 30.44)

    def max_points(self, dimension: str) -> float:
        return float(self.weights.get(dimension, 0.0))

    def is_verified_referrer(self, name: str) -> bool:
        """Exact-ish match against the registry.

        Normalised for case and internal whitespace only.  No fuzzy matching:
        a near-match on a referrer name is precisely the attack this check
        exists to stop, so anything not on the list scores zero and flags.
        """
        if not name:
            return False
        needle = " ".join(name.lower().split())
        return any(" ".join(r.lower().split()) == needle for r in self.referrers)

    def weights_digest(self) -> str:
        payload = json.dumps(
            {
                "weights": self.weights,
                "window_months": self.window_months,
                "thresholds": asdict(self.thresholds),
                "ecosystem": asdict(self.ecosystem),
                "frontier": asdict(self.frontier),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ---------------------------------------------------------------- loading

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProgramConfig":
        data = dict(data)
        thresholds = Thresholds(**(data.pop("thresholds", None) or {}))
        # Copy and drop `name`: a config that has been round-tripped through
        # to_dict() carries the taxonomy's own name, which would collide with
        # the keyword below. This path is the audit-log replay path, so getting
        # it wrong breaks reproducing historical scores rather than anything
        # loud and immediate.
        eco = {k: v for k, v in (data.pop("ecosystem", None) or {}).items() if k != "name"}
        fro = {k: v for k, v in (data.pop("frontier", None) or {}).items() if k != "name"}
        referrers = data.pop("referrers", None) or []

        # Referrer registries hold real names; allow keeping them out of the
        # repo via an env pointer to a separate file.
        env_key = data.pop("referrers_env", None)
        if env_key and os.environ.get(env_key):
            path = Path(os.environ[env_key])
            if path.exists():
                referrers = [
                    line.strip()
                    for line in path.read_text().splitlines()
                    if line.strip() and not line.startswith("#")
                ]

        return cls(
            ecosystem=Taxonomy(name="ecosystem", **eco),
            frontier=Taxonomy(name="frontier", **fro),
            thresholds=thresholds,
            referrers=referrers,
            **data,
        )

    @classmethod
    def load(cls, path: str | Path) -> "ProgramConfig":
        p = Path(path)
        text = p.read_text()
        if p.suffix in (".yaml", ".yml"):
            try:
                import yaml  # optional
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    f"{p} is YAML but PyYAML is not installed; use JSON to keep "
                    "the core dependency-free"
                ) from exc
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        return cls.from_dict(data)


def load_program(name_or_path: str, search_dir: str | Path | None = None) -> ProgramConfig:
    """Load by explicit path, or by program key from the programs/ directory."""
    p = Path(name_or_path)
    if p.exists():
        return ProgramConfig.load(p)
    base = Path(search_dir) if search_dir else Path(__file__).resolve().parent.parent / "programs"
    for suffix in (".json", ".yaml", ".yml"):
        candidate = base / f"{name_or_path}{suffix}"
        if candidate.exists():
            return ProgramConfig.load(candidate)
    available = sorted(f.stem for f in base.glob("*.json")) if base.exists() else []
    raise FileNotFoundError(
        f"no program config {name_or_path!r} in {base} (available: {available})"
    )
