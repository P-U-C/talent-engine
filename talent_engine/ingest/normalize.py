"""Ingestion: CSV exports and handle normalisation.

Form builders produce GitHub "handles" in every shape a human can type. Getting
this wrong silently drops real applicants, so it is handled explicitly rather
than with a strip() at the call site.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Iterator

from ..model import Application

_HANDLE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")

# Field aliases seen in real form exports.
HANDLE_KEYS = ("github", "github_handle", "github_username", "handle", "username", "github url", "github_profile")
CONTEXT_KEYS = ("context_statement", "access_barrier", "barrier", "context", "statement")
FACTOR_KEYS = ("context_factors", "factors", "barriers")
REFERRER_KEYS = ("referrer", "referrer_name", "referred_by", "scout", "endorsed_by")
REPO_KEYS = ("declared_repo", "project_repo", "repository", "repo", "project")
PLAN_KEYS = ("build_plan", "plan", "proposal")


def normalize_handle(raw: str) -> str | None:
    """Reduce any common form of GitHub identity to a bare login.

    Accepts: 'octocat', '@octocat', 'github.com/octocat',
    'https://github.com/octocat/', 'https://github.com/octocat/some-repo'.
    Returns None for anything that is not a valid login, rather than guessing.
    """
    if not raw:
        return None
    value = raw.strip().strip('"').strip("'")
    if not value:
        return None

    value = re.sub(r"^https?://", "", value, flags=re.I)
    value = re.sub(r"^(www\.)?github\.com/", "", value, flags=re.I)
    value = value.lstrip("@").strip("/")
    if "/" in value:  # profile URL with a repo path attached
        value = value.split("/", 1)[0]
    if "?" in value:
        value = value.split("?", 1)[0]

    return value if _HANDLE_RE.match(value) else None


def _first(row: dict[str, str], keys: tuple[str, ...]) -> str:
    lowered = { (k or "").strip().lower(): (v or "") for k, v in row.items() }
    for key in keys:
        if lowered.get(key):
            return lowered[key].strip()
    return ""


def _split_factors(raw: str) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[;,|]", raw)
    return [p.strip() for p in parts if p.strip()]


def read_applications(path: str | Path) -> Iterator[tuple[str, Application, dict[str, Any]]]:
    """Yield (handle, Application, raw_row) for each parsable row.

    Rows whose handle cannot be normalised are yielded with handle=None by
    `read_applications_report` instead; this generator skips them.
    """
    for handle, app, row, ok in _read(path):
        if ok:
            yield handle, app, row


def read_applications_report(path: str | Path) -> tuple[list[tuple[str, Application, dict]], list[dict]]:
    """Parsed rows plus the rows that failed, so nobody is dropped silently."""
    good: list[tuple[str, Application, dict]] = []
    bad: list[dict] = []
    for handle, app, row, ok in _read(path):
        if ok:
            good.append((handle, app, row))
        else:
            bad.append(row)
    return good, bad


def _read(path: str | Path):
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            raw_handle = _first(row, HANDLE_KEYS)
            handle = normalize_handle(raw_handle)
            app = Application(
                context_statement=_first(row, CONTEXT_KEYS),
                context_factors=_split_factors(_first(row, FACTOR_KEYS)),
                referrer_name=_first(row, REFERRER_KEYS),
                declared_repo=_first(row, REPO_KEYS),
                build_plan=_first(row, PLAN_KEYS),
                extra={k: v for k, v in row.items() if v},
            )
            yield handle or "", app, row, bool(handle)
