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
"""


class Store:
    def __init__(self, path: str | Path = "talent_engine.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
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
