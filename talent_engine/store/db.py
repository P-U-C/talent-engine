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
    error TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_handle ON submissions(handle);

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
        self.conn.row_factory = sqlite3.Row
        # Intake and scoring hold separate connections to the same file, so a
        # writer must not lock the other out: WAL lets them overlap, and the
        # busy timeout turns the remaining contention into a wait instead of an
        # immediate "database is locked" that would drop a submission.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

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
        error: str = "",
    ) -> None:
        self.conn.execute(
            "UPDATE submissions SET status = ?, run_id = ?, total = ?, error = ? "
            "WHERE submission_id = ?",
            (status, run_id, total, error[:500], submission_id),
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
