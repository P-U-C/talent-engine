"""Persistence and the audit log.

The reproducibility requirement is that any historical score can be regenerated
exactly.  That needs three things stored together, and storing only the score
satisfies none of them:

  * the snapshot   -- the exact inputs the scorer saw
  * the weights    -- the rubric as configured at the time
  * the code version -- which scorer produced it

`replay()` reconstitutes a stored snapshot and re-scores it under the stored
weights.  If the result differs from what was recorded, the scorer changed
behaviour between then and now, and `verify()` reports that as a mismatch
rather than quietly returning the new number.  Silent re-scoring would make the
audit log actively misleading.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from ..config import ProgramConfig
from ..model import (
    Application,
    CandidateScore,
    ProfileSnapshot,
    PullRequestActivity,
    RepoActivity,
    ReviewActivity,
    utc_now_iso,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    program TEXT NOT NULL,
    mode TEXT NOT NULL,
    code_version TEXT NOT NULL,
    weights_digest TEXT NOT NULL,
    config_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS snapshots (
    digest TEXT PRIMARY KEY,
    handle TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scores (
    run_id TEXT NOT NULL,
    handle TEXT NOT NULL,
    total REAL NOT NULL,
    snapshot_digest TEXT NOT NULL,
    payload TEXT NOT NULL,
    scored_at TEXT NOT NULL,
    PRIMARY KEY (run_id, handle)
);
CREATE TABLE IF NOT EXISTS cohort (
    program TEXT NOT NULL,
    handle TEXT NOT NULL,
    declared_repo TEXT DEFAULT '',
    baseline_run_id TEXT DEFAULT '',
    selected_at TEXT NOT NULL,
    -- Acceptance artefacts. The split address and attestation UID are the two
    -- public objects the terms depend on, so they live next to the cohort row
    -- rather than in someone's notes: `monitor` and `measure` need to reach
    -- them, and so does anyone auditing what was actually agreed.
    accepted_at TEXT DEFAULT '',
    split_address TEXT DEFAULT '',
    attestation_uid TEXT DEFAULT '',
    months_received INTEGER DEFAULT 0,
    PRIMARY KEY (program, handle)
);
CREATE INDEX IF NOT EXISTS idx_scores_handle ON scores(handle);

-- Inbound form submissions. `submission_id` is the form's own id, so a webhook
-- redelivery is a no-op rather than a second score for the same person.
CREATE TABLE IF NOT EXISTS submissions (
    submission_id TEXT PRIMARY KEY,
    program TEXT NOT NULL,
    source TEXT NOT NULL,
    form_id TEXT DEFAULT '',
    handle TEXT DEFAULT '',
    raw_handle TEXT DEFAULT '',
    application_json TEXT NOT NULL,
    received_at TEXT NOT NULL,
    status TEXT NOT NULL,          -- queued | scored | unparsable | error
    run_id TEXT DEFAULT '',
    total REAL,
    concerns TEXT DEFAULT '',
    error TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_handle ON submissions(handle);

-- Decisions, and the feedback owed because of them. The policy commits the
-- programme to giving feedback to unsuccessful applicants; an obligation with
-- no queue gets honoured for the first three people and dropped at scale, so
-- it is tracked rather than remembered.
CREATE TABLE IF NOT EXISTS decisions (
    program TEXT NOT NULL,
    handle TEXT NOT NULL,
    decision TEXT NOT NULL,          -- accepted | declined
    decided_at TEXT NOT NULL,
    note TEXT DEFAULT '',
    feedback_sent_at TEXT DEFAULT '',
    PRIMARY KEY (program, handle)
);
CREATE INDEX IF NOT EXISTS idx_decisions_feedback ON decisions(feedback_sent_at);

-- Human sign-offs that acceptance depends on. Some programme gates are not
-- machine-checkable -- whether an access barrier was verified, whether the
-- build plan was reviewed, whether the Celo fit holds, whether a conflict was
-- cleared. Before this table, `accept --select` would take an arbitrary handle
-- with no scored application and none of these, and produce a full acceptance
-- letter. A judgement nobody signed is not a judgement, so each one is
-- recorded against a named steward and acceptance fails closed without them.
CREATE TABLE IF NOT EXISTS gate_signoffs (
    program TEXT NOT NULL,
    handle TEXT NOT NULL,
    gate TEXT NOT NULL,
    steward TEXT NOT NULL,
    note TEXT DEFAULT '',
    signed_at TEXT NOT NULL,
    PRIMARY KEY (program, handle, gate)
);

-- Overrides of a failed gate. Deliberately a separate table rather than a
-- column: an override is an event with an author and a reason, and it must be
-- as easy to audit as it was to perform.
CREATE TABLE IF NOT EXISTS gate_overrides (
    program TEXT NOT NULL,
    handle TEXT NOT NULL,
    gates TEXT NOT NULL,             -- comma-separated keys that were failing
    steward TEXT NOT NULL,
    reason TEXT NOT NULL,
    overridden_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_overrides_handle ON gate_overrides(program, handle);

-- What happens after acceptance. The engine scored people, accepted them, and
-- then had nothing to say about whether the money actually moved: receipts,
-- reimbursements, the month-two Celo result, months funded, vendor offsets,
-- Reserve returns and the final KPIs lived nowhere. For five people a shared
-- manual tracker is enough, but it needs a defined shape and a named owner per
-- entry, or "we track that" means whoever remembers.
--
-- Deliberately an append-only ledger of typed entries rather than a wide row
-- per recipient: the obligations arrive at different times, from different
-- people, and a correction should be visible as a correction.
CREATE TABLE IF NOT EXISTS operating_ledger (
    entry_id TEXT PRIMARY KEY,
    program TEXT NOT NULL,
    handle TEXT DEFAULT '',          -- blank for programme-level entries
    entry_type TEXT NOT NULL,
    period TEXT DEFAULT '',          -- 'YYYY-MM' or a milestone key
    amount_usd REAL,                 -- NULL where the entry is not financial
    owner TEXT NOT NULL,             -- who is accountable for this line
    reference TEXT DEFAULT '',       -- receipt id, tx hash, post URL
    note TEXT DEFAULT '',
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_program ON operating_ledger(program, handle);
CREATE INDEX IF NOT EXISTS idx_ledger_type ON operating_ledger(entry_type);

-- Contact details live here and ONLY here: never in a snapshot, never in a
-- score, never in a dossier. Joined to a submission by id when a human needs
-- to reach someone, and separable from everything publishable by dropping
-- this one table.
CREATE TABLE IF NOT EXISTS contacts (
    submission_id TEXT PRIMARY KEY,
    email TEXT DEFAULT '',
    name TEXT DEFAULT '',
    telegram TEXT DEFAULT '',
    x TEXT DEFAULT '',
    discord TEXT DEFAULT '',
    recorded_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path = "talent_engine.db", *, shared: bool = False) -> None:
        """`shared=True` permits use from more than one thread.

        Only pass it when the caller serialises its own access — the HTTP
        intake path does, under a single lock, because ThreadingHTTPServer
        hands every request to a fresh thread and sqlite3 otherwise binds a
        connection to whichever thread opened it.
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=not shared)
        # The contacts table holds applicant PII, so the quarantine has to be a
        # filesystem boundary as well as a schema convention. sqlite creates its
        # database and WAL with the process umask, which left them world
        # readable on the live host; every process on the box could read
        # applicant emails despite the code-level separation.
        self._restrict_permissions()
        self.conn.row_factory = sqlite3.Row
        # Intake and scoring hold separate connections to the same file, so a
        # writer must not lock the other out: WAL lets them overlap, and the
        # busy timeout turns the remaining contention into a wait instead of an
        # immediate "database is locked" that would drop a submission.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _restrict_permissions(self) -> None:
        """0600 on the database and its sidecars. Best effort, never fatal."""
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            try:
                if candidate.exists():
                    candidate.chmod(0o600)
            except OSError:  # a read-only mount or foreign owner must not stop a run
                pass

    # ------------------------------------------------------------------ runs

    def start_run(self, cfg: ProgramConfig, mode: str, code_version: str, note: str = "") -> str:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        self.conn.execute(
            "INSERT INTO runs (run_id, program, mode, code_version, weights_digest, "
            "config_json, started_at, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                cfg.key,
                mode,
                code_version,
                cfg.weights_digest(),
                json.dumps(cfg.to_dict(), sort_keys=True),
                utc_now_iso(),
                note,
            ),
        )
        self.conn.commit()
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self, program: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if program:
            rows = self.conn.execute(
                "SELECT * FROM runs WHERE program = ? ORDER BY started_at DESC LIMIT ?",
                (program, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------- snapshots/scores

    def save_snapshot(self, snap: ProfileSnapshot) -> str:
        digest = snap.digest()
        self.conn.execute(
            "INSERT OR REPLACE INTO snapshots (digest, handle, collected_at, payload) "
            "VALUES (?, ?, ?, ?)",
            (digest, snap.handle, snap.collected_at, json.dumps(snap.to_dict(), sort_keys=True)),
        )
        self.conn.commit()
        return digest

    def load_snapshot(self, digest: str) -> ProfileSnapshot | None:
        row = self.conn.execute(
            "SELECT payload FROM snapshots WHERE digest = ?", (digest,)
        ).fetchone()
        return _snapshot_from_dict(json.loads(row["payload"])) if row else None

    def save_score(self, run_id: str, score: CandidateScore) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO scores (run_id, handle, total, snapshot_digest, "
            "payload, scored_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                score.handle,
                score.total,
                score.snapshot_digest,
                json.dumps(score.to_dict(), sort_keys=True),
                score.scored_at,
            ),
        )
        self.conn.commit()

    def scores_for_run(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM scores WHERE run_id = ? ORDER BY total DESC", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def score_for(self, run_id: str, handle: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM scores WHERE run_id = ? AND handle = ?", (run_id, handle)
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------ reproduce

    def replay(self, run_id: str, handle: str) -> CandidateScore:
        """Re-score a stored snapshot under the run's stored weights."""
        from ..scoring.engine import score_snapshot

        rec = self.score_for(run_id, handle)
        if not rec:
            raise KeyError(f"no score for {handle} in {run_id}")
        run = self.get_run(run_id)
        if not run:
            raise KeyError(f"no such run {run_id}")
        snap = self.load_snapshot(rec["snapshot_digest"])
        if snap is None:
            raise KeyError(f"snapshot {rec['snapshot_digest']} missing")
        cfg = ProgramConfig.from_dict(json.loads(run["config_json"]))
        return score_snapshot(snap, cfg)

    def verify(self, run_id: str, handle: str) -> dict[str, Any]:
        """Did the recorded score survive a replay? Reports drift, never hides it."""
        recorded = self.score_for(run_id, handle)
        if not recorded:
            raise KeyError(f"no score for {handle} in {run_id}")
        replayed = self.replay(run_id, handle)
        run = self.get_run(run_id) or {}
        matches = abs(replayed.total - recorded["total"]) < 1e-6
        return {
            "handle": handle,
            "run_id": run_id,
            "recorded_total": recorded["total"],
            "replayed_total": replayed.total,
            "matches": matches,
            "recorded_code_version": run.get("code_version"),
            "replay_code_version": replayed.code_version,
            "explanation": (
                "reproduced exactly"
                if matches
                else "scorer behaviour changed since this run; the recorded value "
                "stands as the score of record"
            ),
        }

    # ----------------------------------------------------------------- cohort

    def select_cohort(
        self, program: str, handles: Iterable[str], baseline_run_id: str,
        declared_repos: dict[str, str] | None = None,
    ) -> None:
        declared_repos = declared_repos or {}
        for h in handles:
            self.conn.execute(
                "INSERT OR REPLACE INTO cohort (program, handle, declared_repo, "
                "baseline_run_id, selected_at) VALUES (?, ?, ?, ?, ?)",
                (program, h, declared_repos.get(h, ""), baseline_run_id, utc_now_iso()),
            )
        self.conn.commit()

    def record_acceptance(
        self,
        program: str,
        handle: str,
        *,
        split_address: str = "",
        attestation_uid: str = "",
        months_received: int | None = None,
    ) -> bool:
        """Attach acceptance artefacts to an existing cohort row.

        Returns False if the handle is not in the cohort — accepting someone
        who was never selected should fail loudly rather than create a row
        that no selection decision stands behind.
        """
        row = self.conn.execute(
            "SELECT 1 FROM cohort WHERE program = ? AND handle = ?", (program, handle)
        ).fetchone()
        if not row:
            return False
        sets, params = ["accepted_at = ?"], [utc_now_iso()]
        if split_address:
            sets.append("split_address = ?")
            params.append(split_address)
        if attestation_uid:
            sets.append("attestation_uid = ?")
            params.append(attestation_uid)
        if months_received is not None:
            sets.append("months_received = ?")
            params.append(months_received)
        params += [program, handle]
        self.conn.execute(
            f"UPDATE cohort SET {', '.join(sets)} WHERE program = ? AND handle = ?",
            params,
        )
        self.conn.commit()
        return True

    def cohort(self, program: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM cohort WHERE program = ? ORDER BY handle", (program,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ submissions

    def record_submission(
        self,
        submission_id: str,
        program: str,
        source: str,
        handle: str,
        raw_handle: str,
        application: Application,
        form_id: str = "",
        status: str = "queued",
    ) -> bool:
        """Insert a submission. Returns False if this id was already seen.

        Idempotency is the point: form platforms retry webhooks on any non-2xx
        and sometimes on a slow 2xx, and a retry must not produce a second
        score, a second API spend, or a duplicate row in the ranking.
        """
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO submissions (submission_id, program, source, form_id, "
            "handle, raw_handle, application_json, received_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                submission_id,
                program,
                source,
                form_id,
                handle,
                raw_handle,
                json.dumps(asdict(application), sort_keys=True),
                utc_now_iso(),
                status,
            ),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def record_contact(self, submission_id: str, contact: Any) -> None:
        """Store contact details in the quarantined table.

        Takes the dataclass rather than a dict so a caller cannot casually pass
        the whole form payload in here.
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO contacts (submission_id, email, name, telegram, x, "
            "discord, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                submission_id,
                getattr(contact, "email", ""),
                getattr(contact, "name", ""),
                getattr(contact, "telegram", ""),
                getattr(contact, "x", ""),
                getattr(contact, "discord", ""),
                utc_now_iso(),
            ),
        )
        self.conn.commit()

    def finish_submission(
        self, submission_id: str, status: str, run_id: str = "", total: float | None = None,
        error: str = "", concerns: str = "",
    ) -> None:
        """Record the outcome. `concerns` travels with the number by design.

        A score stored on its own gets read as a verdict; the caveat sentence
        is stored alongside it so no consumer of this table can show one
        without the other.
        """
        self.conn.execute(
            "UPDATE submissions SET status = ?, run_id = ?, total = ?, concerns = ?, "
            "error = ? WHERE submission_id = ?",
            (status, run_id, total, concerns, error[:500], submission_id),
        )
        self.conn.commit()

    def pending_submissions(self, program: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM submissions WHERE status = 'queued'"
        params: list[Any] = []
        if program:
            sql += " AND program = ?"
            params.append(program)
        sql += " ORDER BY received_at"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def submissions(self, program: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM submissions"
        params: list[Any] = []
        if program:
            sql += " WHERE program = ?"
            params.append(program)
        sql += " ORDER BY received_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM submissions WHERE submission_id = ?", (submission_id,)
        ).fetchone()
        return dict(row) if row else None

    def latest_snapshots(self, program: str) -> dict[str, ProfileSnapshot]:
        """Most recent snapshot per handle across every run of a program.

        Ring detection is a question about the applicant *pool*, not about any
        single run, so it reads across runs — someone who applied in March and
        someone who applied in August can still be the same person.
        """
        rows = self.conn.execute(
            "SELECT s.handle, s.snapshot_digest, s.scored_at FROM scores s "
            "JOIN runs r ON r.run_id = s.run_id WHERE r.program = ? "
            "ORDER BY s.scored_at",
            (program,),
        ).fetchall()
        latest: dict[str, str] = {}
        for row in rows:
            latest[row["handle"]] = row["snapshot_digest"]  # later rows win
        out: dict[str, ProfileSnapshot] = {}
        for handle, digest in latest.items():
            snap = self.load_snapshot(digest)
            if snap is not None:
                out[handle] = snap
        return out

    # ------------------------------------------------------------- decisions

    def record_decision(
        self, program: str, handle: str, decision: str, note: str = ""
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO decisions (program, handle, decision, decided_at, "
            "note, feedback_sent_at) VALUES (?, ?, ?, ?, ?, "
            "COALESCE((SELECT feedback_sent_at FROM decisions WHERE program = ? "
            "AND handle = ?), ''))",
            (program, handle, decision, utc_now_iso(), note, program, handle),
        )
        self.conn.commit()

    def mark_feedback_sent(self, program: str, handle: str) -> None:
        self.conn.execute(
            "UPDATE decisions SET feedback_sent_at = ? WHERE program = ? AND handle = ?",
            (utc_now_iso(), program, handle),
        )
        self.conn.commit()

    def pending_feedback(self, program: str) -> list[dict[str, Any]]:
        """Declined applicants who have not yet been told anything."""
        rows = self.conn.execute(
            "SELECT * FROM decisions WHERE program = ? AND decision = 'declined' "
            "AND feedback_sent_at = '' ORDER BY decided_at",
            (program,),
        ).fetchall()
        return [dict(r) for r in rows]

    def decisions(self, program: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM decisions WHERE program = ? ORDER BY decided_at DESC",
            (program,),
        ).fetchall()
        return [dict(r) for r in rows]

    def contact_for(self, submission_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM contacts WHERE submission_id = ?", (submission_id,)
        ).fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self.conn.close()


# ---------------------------------------------------------------- rehydration


def _snapshot_from_dict(data: dict[str, Any]) -> ProfileSnapshot:
    app = Application(**data.get("application", {}))
    return ProfileSnapshot(
        handle=data["handle"],
        account_created_at=data.get("account_created_at"),
        collected_at=data["collected_at"],
        window_start=data["window_start"],
        window_end=data["window_end"],
        repos=[RepoActivity(**r) for r in data.get("repos", [])],
        merged_prs=[PullRequestActivity(**p) for p in data.get("merged_prs", [])],
        reviews=[ReviewActivity(**r) for r in data.get("reviews", [])],
        active_weeks=data.get("active_weeks", []),
        application=app,
        collection_notes=data.get("collection_notes", []),
        partial=data.get("partial", False),
    )


# --------------------------------------------------------------------------
# Acceptance gates
# --------------------------------------------------------------------------


def _gate_methods():  # pragma: no cover - wiring only
    """Attached below; kept out of the class body for readability."""


def record_signoff(
    self,
    program: str,
    handle: str,
    gate: str,
    steward: str,
    note: str = "",
) -> None:
    """Record that a named person checked a gate. Idempotent per gate."""
    self.conn.execute(
        "INSERT INTO gate_signoffs (program, handle, gate, steward, note, signed_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(program, handle, gate) DO UPDATE SET "
        "steward = excluded.steward, note = excluded.note, signed_at = excluded.signed_at",
        (program, handle, gate, steward, note, utc_now_iso()),
    )
    self.conn.commit()


def signoffs(self, program: str, handle: str) -> dict[str, dict[str, Any]]:
    rows = self.conn.execute(
        "SELECT gate, steward, note, signed_at FROM gate_signoffs "
        "WHERE program = ? AND handle = ?",
        (program, handle),
    ).fetchall()
    return {r["gate"]: dict(r) for r in rows}


def record_override(
    self, program: str, handle: str, gates: list[str], steward: str, reason: str
) -> None:
    self.conn.execute(
        "INSERT INTO gate_overrides (program, handle, gates, steward, reason, "
        "overridden_at) VALUES (?, ?, ?, ?, ?, ?)",
        (program, handle, ",".join(sorted(gates)), steward, reason, utc_now_iso()),
    )
    self.conn.commit()


def overrides(self, program: str, handle: str = "") -> list[dict[str, Any]]:
    sql = "SELECT * FROM gate_overrides WHERE program = ?"
    params: list[Any] = [program]
    if handle:
        sql += " AND handle = ?"
        params.append(handle)
    return [dict(r) for r in self.conn.execute(sql + " ORDER BY overridden_at", params)]


def has_scored_application(self, program: str, handle: str) -> bool:
    """Did this person actually apply and get scored under this programme?"""
    row = self.conn.execute(
        "SELECT 1 FROM submissions WHERE program = ? AND handle = ? "
        "AND status = 'scored' LIMIT 1",
        (program, handle),
    ).fetchone()
    return bool(row)


def latest_application(self, program: str, handle: str) -> dict[str, Any] | None:
    row = self.conn.execute(
        "SELECT application_json, received_at FROM submissions WHERE program = ? "
        "AND handle = ? ORDER BY received_at DESC LIMIT 1",
        (program, handle),
    ).fetchone()
    return dict(row) if row else None


for _fn in (
    record_signoff,
    signoffs,
    record_override,
    overrides,
    has_scored_application,
    latest_application,
):
    setattr(Store, _fn.__name__, _fn)


# --------------------------------------------------------------------------
# Operating ledger
# --------------------------------------------------------------------------

# The obligations a programme takes on once it accepts someone. Named here so
# that "what do we owe and what have we done" is answerable from the database
# rather than from memory.
LEDGER_TYPES = (
    "receipt",           # a tooling invoice the recipient paid
    "reimbursement",     # money we sent back to them
    "vendor_offset",     # credit or discount a vendor gave us instead of cash
    "reserve_return",    # give-back income actually received
    "public_update",     # the public record we promised, with a URL
    "celo_checkpoint",   # the month-two Celo result
    "months_funded",     # how many months this person actually took
    "kpi",               # a final outcome measure
)


def record_ledger_entry(
    self,
    program: str,
    entry_type: str,
    owner: str,
    *,
    handle: str = "",
    period: str = "",
    amount_usd: float | None = None,
    reference: str = "",
    note: str = "",
) -> str:
    """Append one operating entry. Returns its id.

    `owner` is required and not defaulted: an obligation with no named person
    behind it is the thing this table exists to prevent.
    """
    if entry_type not in LEDGER_TYPES:
        raise ValueError(f"unknown entry type {entry_type!r}; expected one of {LEDGER_TYPES}")
    if not owner:
        raise ValueError("every ledger entry needs an owner")
    entry_id = f"{program}:{entry_type}:{handle or '-'}:{period or '-'}:{utc_now_iso()}"
    self.conn.execute(
        "INSERT INTO operating_ledger (entry_id, program, handle, entry_type, period, "
        "amount_usd, owner, reference, note, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry_id, program, handle, entry_type, period,
            amount_usd, owner, reference, note, utc_now_iso(),
        ),
    )
    self.conn.commit()
    return entry_id


def ledger(
    self, program: str, handle: str = "", entry_type: str = ""
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM operating_ledger WHERE program = ?"
    params: list[Any] = [program]
    if handle:
        sql += " AND handle = ?"
        params.append(handle)
    if entry_type:
        sql += " AND entry_type = ?"
        params.append(entry_type)
    return [dict(r) for r in self.conn.execute(sql + " ORDER BY recorded_at", params)]


def programme_periods(duration_months: int, start: str) -> list[str]:
    """The 'YYYY-MM' keys a term of this length covers, from its start month."""
    if not start or duration_months <= 0:
        return []
    year, month = int(start[:4]), int(start[5:7])
    out = []
    for _ in range(duration_months):
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return out


def ledger_summary(
    self, program: str, *, periods: list[str] | None = None
) -> dict[str, Any]:
    """Per-recipient totals and what is still missing.

    The 'missing' list is the useful part: it is the difference between a
    tracker and a filing cabinet. It is period-aware on purpose. Checking only
    that a type had *ever* been recorded meant one receipt in month one
    satisfied the tracker for the whole four-month term, and `public_update`
    -- a monthly obligation the policy actually commits to -- was not checked
    at all. Absence in month three is exactly what this is for.
    """
    rows = self.ledger(program)
    people = sorted(
        {r["handle"] for r in rows if r["handle"]}
        | {m["handle"] for m in self.cohort(program)}
    )
    periods = periods or []
    out: dict[str, Any] = {
        "program": program,
        "periods": periods,
        "recipients": {},
        "totals": {},
    }
    for t in LEDGER_TYPES:
        total = sum(r["amount_usd"] or 0 for r in rows if r["entry_type"] == t)
        if total:
            out["totals"][t] = round(total, 2)

    # Once per term.
    ONCE = ("celo_checkpoint", "months_funded", "kpi")
    # Once per programme month.
    MONTHLY = ("receipt", "reimbursement", "public_update")

    for h in people:
        mine = [r for r in rows if r["handle"] == h]
        seen = {r["entry_type"] for r in mine}
        by_period = {(r["entry_type"], r["period"]) for r in mine}
        missing = [t for t in ONCE if t not in seen]
        for t in MONTHLY:
            gaps = [p for p in periods if (t, p) not in by_period]
            if not periods and t not in seen:
                missing.append(t)
            missing.extend(f"{t}:{p}" for p in gaps)
        out["recipients"][h] = {
            "entries": len(mine),
            "reimbursed_usd": round(
                sum(r["amount_usd"] or 0 for r in mine if r["entry_type"] == "reimbursement"), 2
            ),
            "missing": missing,
            "owners": sorted({r["owner"] for r in mine}),
        }
    return out


for _fn in (record_ledger_entry, ledger, ledger_summary):
    setattr(Store, _fn.__name__, _fn)
