"""Form-webhook intake, on the standard library only.

Shape of the thing: the HTTP handler does no network work. It authenticates
the request, parses it, writes the submission down, and returns. Scoring —
which means dozens of GitHub calls and can take tens of seconds — happens on a
worker thread. Tally waits a few seconds for a webhook response and retries on
anything that is not a 2xx, so scoring inline would produce timeouts, retries,
duplicate scoring runs, and a doubled API spend on every applicant.

Durability comes from the store, not the queue: a submission is committed to
SQLite with status `queued` before it is handed to the worker, so a crash mid
scoring loses no applicant. `--drain` re-runs whatever was left queued.

Security posture:
  * Signature verification is mandatory. There is no "no secret configured, so
    accept everything" path — an open scoring endpoint is an open GitHub-API
    spend and an open way to inject applicants into a ranking.
  * The endpoint returns 202 for anything it accepted and a bare status code
    otherwise. It never echoes payload content back, which keeps it useless as
    an oracle for probing what the parser understood.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ..config import ProgramConfig
from ..github.collector import Collector
from ..ingest.tally import Submission, TallyPayloadError, parse_webhook, verify_signature
from ..model import Application, utc_now_iso
from ..notify import application_scored
from ..scoring.concerns import concerns
from ..scoring.engine import CODE_VERSION, score_snapshot
from ..store.db import Store

log = logging.getLogger("talent_engine.intake")

MAX_BODY = 1 << 20  # 1 MiB; real form responses are a few KiB


class IntakeService:
    """Accepts submissions, scores them off the request path.

    Not thread-safe by accident: the single worker thread owns the Store and
    the Collector, and the HTTP threads talk to it only through `accept()`,
    which takes the store lock for its one write. sqlite3 connections are not
    shareable across threads, so the handler gets its own.
    """

    def __init__(
        self,
        cfg: ProgramConfig,
        db_path: str,
        collector_factory,
        source: str = "tally",
    ) -> None:
        self.cfg = cfg
        self.db_path = db_path
        self.collector_factory = collector_factory
        self.source = source
        self._q: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()
        # sqlite3 connections are bound to the thread that created them, so the
        # worker opens its own inside `_run` rather than inheriting this one.
        self._store: Store | None = None
        # ThreadingHTTPServer serves each request on a new thread, so the
        # intake connection is shared and every use of it is taken under
        # `self._lock`.
        self._intake_store = Store(db_path, shared=True)
        self._run_ids: dict[str, str] = {}  # utc date -> run_id
        self._worker: threading.Thread | None = None
        self.accepted = 0
        self.duplicates = 0
        self.rejected = 0

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        self._worker = threading.Thread(target=self._run, name="scorer", daemon=True)
        self._worker.start()

    def stop(self, drain: bool = True) -> None:
        if not self._worker:
            return
        if drain:
            self._q.join()
        self._q.put(None)
        self._worker.join(timeout=30)

    # ---------------------------------------------------------------- intake

    def accept(self, sub: Submission) -> str:
        """Record a parsed submission and queue it. Returns a disposition."""
        if not sub.submission_id:
            self.rejected += 1
            return "no-submission-id"

        with self._lock:
            fresh = self._intake_store.record_submission(
                submission_id=sub.submission_id,
                program=self.cfg.key,
                source=self.source,
                handle=sub.handle,
                raw_handle=sub.raw_handle,
                application=sub.application,
                form_id=sub.form_id,
                status="queued" if sub.ok else "unparsable",
            )
            if fresh and not sub.contact.is_empty():
                self._intake_store.record_contact(sub.submission_id, sub.contact)
            if fresh and not sub.ok:
                self._intake_store.finish_submission(
                    sub.submission_id,
                    "unparsable",
                    error=f"no usable GitHub handle in {sub.raw_handle!r}",
                )

        if not fresh:
            self.duplicates += 1
            return "duplicate"
        if not sub.ok:
            # Deliberately still a 202: the response is stored and flagged for a
            # human, not dropped. Returning an error would make Tally retry a
            # submission that will never parse.
            self.rejected += 1
            return "unparsable"

        self.accepted += 1
        self._q.put(sub.submission_id)
        return "queued"

    def backlog(self) -> int:
        return self._q.qsize()

    def requeue_pending(self) -> int:
        """Push anything left in `queued` back onto the worker queue."""
        with self._lock:
            pending = self._intake_store.pending_submissions(self.cfg.key)
        for row in pending:
            self._q.put(row["submission_id"])
        return len(pending)

    # ---------------------------------------------------------------- worker

    def _run(self) -> None:
        self._store = Store(self.db_path)  # must be opened on this thread
        collector: Collector | None = None
        try:
            while True:
                item = self._q.get()
                if item is None:
                    self._q.task_done()
                    return
                try:
                    if collector is None:
                        collector = self.collector_factory()
                    self._score_one(item, collector)
                except Exception as exc:  # a bad applicant must not kill intake
                    log.exception("scoring %s failed", item)
                    try:
                        self._store.finish_submission(item, "error", error=repr(exc))
                    except Exception:
                        log.exception("could not record failure for %s", item)
                finally:
                    self._q.task_done()
        finally:
            self._store.close()

    def _score_one(self, submission_id: str, collector: Collector) -> None:
        assert self._store is not None  # only ever called on the worker thread
        row = self._store.get_submission(submission_id)
        if not row:
            log.warning("submission %s vanished before scoring", submission_id)
            return
        app = Application(**json.loads(row["application_json"]))

        run_id = self._run_for_today()
        snap = collector.collect(row["handle"], app)
        self._store.save_snapshot(snap)
        score = score_snapshot(snap, self.cfg)
        self._store.save_score(run_id, score)
        caveat = concerns(score, self.cfg, snap)
        self._store.finish_submission(
            submission_id, "scored", run_id=run_id, total=score.total, concerns=caveat
        )
        log.info("scored %s: %.2f (run %s) — %s", row["handle"], score.total, run_id, caveat)

        # Push, because nobody watches a table. Contact details deliberately
        # stay on this box — see notify.py.
        application_scored(
            handle=row["handle"],
            total=score.total,
            caveat=caveat,
            program=self.cfg.key,
            declared_repo=app.declared_repo,
            max_points=sum(self.cfg.weights.values()),
            contact=self._store.contact_for(submission_id),
        )

    def _run_for_today(self) -> str:
        """One run per UTC day, so a rolling intake still groups into cohorts.

        A single run for the server's whole lifetime would make `measure` and
        the ranked table meaningless after a few weeks; a run per submission
        would make them meaningless immediately.
        """
        assert self._store is not None
        day = utc_now_iso()[:10]
        if day not in self._run_ids:
            self._run_ids[day] = self._store.start_run(
                self.cfg, "intake", CODE_VERSION, note=f"{self.source} intake {day}"
            )
        return self._run_ids[day]


def build_handler(service: IntakeService, secret: str, pages: dict[str, tuple[str, bytes]]):
    class Handler(BaseHTTPRequestHandler):
        server_version = "talent-engine"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:  # route through logging
            log.info("%s %s", self.address_string(), fmt % args)

        def _send(self, code: int, content_type: str, payload: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            # The page embeds Tally in an iframe and loads nothing else, so the
            # policy can be this tight: no scripts of our own, no other origins.
            self.send_header(
                "Content-Security-Policy",
                # data: for the embedded brand fonts, which are inlined
                # rather than fetched so the page makes no external request.
                "default-src 'none'; style-src 'unsafe-inline'; font-src data:; "
                "img-src data:; frame-src https://tally.so; form-action 'none'; "
                "base-uri 'none'",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            if payload and self.command != "HEAD":
                self.wfile.write(payload)

        def _plain(self, code: int, body: str = "") -> None:
            self._send(code, "text/plain; charset=utf-8", body.encode())

        def do_GET(self) -> None:  # noqa: N802
            # Exact-match lookup only. No path is ever joined to a filesystem
            # root here, so traversal is not a thing that can be attempted.
            path = self.path.split("?", 1)[0]
            if path.rstrip("/") in ("/healthz", "/health"):
                self._plain(200, "ok\n")
                return
            page = pages.get(path) or (pages.get(path.rstrip("/")) if path != "/" else None)
            if page:
                self._send(200, page[0], page[1])
            else:
                self._plain(404)

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if self.path.rstrip("/") not in ("/webhook/tally", "/webhook"):
                self._plain(404)
                return

            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._plain(400)
                return
            if length <= 0 or length > MAX_BODY:
                self._plain(413 if length > MAX_BODY else 400)
                return

            raw = self.rfile.read(length)

            signature = self.headers.get("tally-signature") or self.headers.get(
                "Tally-Signature"
            )
            if not verify_signature(raw, signature, secret):
                log.warning("rejected unsigned/invalid webhook from %s", self.address_string())
                self._plain(401)
                return

            try:
                payload = json.loads(raw.decode("utf-8"))
                sub = parse_webhook(payload)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                log.warning("undecodable webhook body: %s", exc)
                self._plain(400)
                return
            except TallyPayloadError as exc:
                log.warning("unreadable webhook payload: %s", exc)
                self._plain(422)
                return

            disposition = service.accept(sub)
            self._plain(202, disposition + "\n")

    return Handler


def build_server(
    service: IntakeService,
    secret: str,
    host: str = "127.0.0.1",
    port: int = 8787,
    pages: dict[str, tuple[str, bytes]] | None = None,
) -> ThreadingHTTPServer:
    if not secret:
        raise ValueError(
            "a webhook signing secret is required — an unauthenticated scoring "
            "endpoint is an open GitHub-API spend and lets anyone inject "
            "applicants into the ranking"
        )
    return ThreadingHTTPServer(
        (host, port), build_handler(service, secret, pages or {})
    )


def run_server(
    service: IntakeService,
    secret: str,
    host: str,
    port: int,
    pages: dict[str, tuple[str, bytes]] | None = None,
) -> None:
    httpd = build_server(service, secret, host, port, pages)
    service.start()
    requeued = service.requeue_pending()
    if requeued:
        log.info("requeued %d submission(s) left from a previous run", requeued)
    log.info("listening on http://%s:%d/webhook/tally", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down; draining %d queued", service.backlog())
    finally:
        httpd.shutdown()
        service.stop()
