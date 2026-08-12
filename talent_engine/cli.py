"""Command line interface.

    talent-engine score   --program celo-trial --handles a,b,c
    talent-engine score   --program celo-trial --csv applications.csv
    talent-engine scout   --program celo-trial --seeds celo-org/celo-composer
    talent-engine monitor --program celo-trial
    talent-engine measure --program celo-trial --baseline run_x --endline run_y
    talent-engine verify  --run run_x --handle octocat
    talent-engine dossier --run run_x --handle octocat
    talent-engine runs    --program celo-trial
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import load_program
from .github.auth import AnonymousAuth, auth_from_env
from .github.client import GitHubClient, ResponseCache
from .github.collector import Collector
from .ingest.normalize import normalize_handle, read_applications_report
from .model import Application
from .modes.monitor import assess, measure as measure_deltas
from .modes.scout import Scout
from .report import dossier, ranked_table, scores_to_csv, scores_to_json
from .scoring.concerns import concerns
from .scoring.engine import CODE_VERSION, rank, score_snapshot
from .store.db import Store

DEFAULT_DB = "talent_engine.db"
DEFAULT_CACHE = ".cache/github.sqlite"


def _client(args) -> GitHubClient:
    auth = auth_from_env(dict(os.environ))
    if isinstance(auth, AnonymousAuth):
        print(
            "warning: no GitHub credentials found (GITHUB_TOKEN or GITHUB_APP_*).\n"
            "         Anonymous access is 60 requests/hour and will produce partial\n"
            "         snapshots for all but the smallest runs.",
            file=sys.stderr,
        )
    cache = None if args.no_cache else ResponseCache(args.cache)
    return GitHubClient(auth=auth, cache=cache, budget=args.budget)


# ------------------------------------------------------------------- score


def cmd_score(args) -> int:
    cfg = load_program(args.program)
    store = Store(args.db)
    client = _client(args)
    collector = Collector(client, window_days=cfg.window_days)

    targets: list[tuple[str, Application]] = []
    if args.csv:
        good, bad = read_applications_report(args.csv)
        targets = [(h, app) for h, app, _ in good]
        if bad:
            print(
                f"warning: {len(bad)} row(s) had no usable GitHub handle and were "
                f"skipped (they are not scored, not zero-scored)",
                file=sys.stderr,
            )
    if args.handles:
        for raw in args.handles.split(","):
            handle = normalize_handle(raw)
            if handle:
                targets.append((handle, Application()))
            else:
                print(f"warning: {raw!r} is not a valid GitHub handle", file=sys.stderr)

    if not targets:
        print("nothing to score: pass --handles or --csv", file=sys.stderr)
        return 2

    run_id = store.start_run(cfg, "score", CODE_VERSION, note=args.note)
    scores = []
    for handle, app in targets:
        snap = collector.collect(handle, app)
        store.save_snapshot(snap)
        score = score_snapshot(snap, cfg)
        store.save_score(run_id, score)
        scores.append(score)
        print(f"  scored {handle}: {score.total:.2f}", file=sys.stderr)

    ordered = rank(scores)
    _emit(ordered, cfg, args)
    print(f"\nrun_id: {run_id}   ({client.stats})", file=sys.stderr)
    store.close()
    return 0


def _emit(ordered, cfg, args) -> None:
    if args.format == "json":
        print(scores_to_json(ordered, cfg))
    elif args.format == "csv":
        print(scores_to_csv(ordered))
    else:
        print(ranked_table(ordered, limit=args.limit))
        print()
        for s in ordered[: args.limit or None]:
            print(f"  {s.handle}: {concerns(s, cfg)}")
    if args.dossier_dir:
        out = Path(args.dossier_dir)
        out.mkdir(parents=True, exist_ok=True)
        for s in ordered:
            (out / f"{s.handle}.md").write_text(dossier(s, cfg))
        print(f"\nwrote {len(ordered)} dossiers to {out}/", file=sys.stderr)


# ------------------------------------------------------------------- scout


def cmd_scout(args) -> int:
    cfg = load_program(args.program)
    client = _client(args)
    scout = Scout(client, cfg, window_days=cfg.window_days)
    seeds = [s.strip() for s in (args.seeds or "").split(",") if s.strip()]

    candidates = scout.run(seeds)
    if args.format == "json":
        print(json.dumps([c.to_dict() for c in candidates], indent=2))
    else:
        print(f"{'handle':<28} {'ch':>2}  channels / why")
        print("-" * 78)
        for c in candidates[: args.limit or 50]:
            print(
                f"{c.handle:<28} {c.corroboration:>2}  "
                f"{','.join(sorted(c.channels))}: {c.reasons[0] if c.reasons else ''}"
            )
    for note in scout.notes:
        print(f"note: {note}", file=sys.stderr)
    print(f"\n{len(candidates)} candidates   ({client.stats})", file=sys.stderr)
    return 0


# ----------------------------------------------------------------- monitor


def cmd_monitor(args) -> int:
    cfg = load_program(args.program)
    store = Store(args.db)
    client = _client(args)
    collector = Collector(client, window_days=cfg.thresholds.inactivity_days * 2)

    members = store.cohort(cfg.key)
    if not members:
        print(f"no cohort selected for {cfg.key}", file=sys.stderr)
        return 2

    statuses = []
    for m in members:
        snap = collector.collect(m["handle"])
        statuses.append(assess(snap, cfg, declared_repo=m["declared_repo"] or ""))

    if args.format == "json":
        print(json.dumps([s.to_dict() for s in statuses], indent=2))
    else:
        for s in statuses:
            days = "never" if s.days_since_activity is None else f"{s.days_since_activity}d"
            repo = ""
            if s.declared_repo:
                repo = f"  declared_repo={'active' if s.declared_repo_active else 'QUIET'}"
            print(f"{s.state:<9} {s.handle:<24} last activity {days}{repo}")
            for n in s.notes:
                print(f"          note: {n}")
    store.close()
    return 0


# ----------------------------------------------------------------- measure


def cmd_measure(args) -> int:
    from .model import CandidateScore

    store = Store(args.db)

    def load(run_id: str) -> list[CandidateScore]:
        out = []
        for row in store.scores_for_run(run_id):
            out.append(store.replay(run_id, row["handle"]))
        return out

    result = measure_deltas(load(args.baseline), load(args.endline))
    print(json.dumps(result, indent=2))
    store.close()
    return 0


# ------------------------------------------------------------------ verify


def cmd_verify(args) -> int:
    store = Store(args.db)
    result = store.verify(args.run, args.handle)
    print(json.dumps(result, indent=2))
    store.close()
    return 0 if result["matches"] else 1


def cmd_dossier(args) -> int:
    store = Store(args.db)
    run = store.get_run(args.run)
    if not run:
        print(f"no such run {args.run}", file=sys.stderr)
        return 2
    from .config import ProgramConfig

    cfg = ProgramConfig.from_dict(json.loads(run["config_json"]))
    print(dossier(store.replay(args.run, args.handle), cfg))
    store.close()
    return 0


def cmd_accept(args) -> int:
    """Record an acceptance and produce the letter. Deploys nothing."""
    from .modes.acceptance import acceptance_letter, split_plan
    from .programs.policy import load_overlay

    cfg = load_program(args.program)
    overlay = load_overlay(args.overlay or args.program)
    store = Store(args.db)

    handle = normalize_handle(args.handle) or args.handle
    if not any(m["handle"] == handle for m in store.cohort(cfg.key)):
        if not args.select:
            print(
                f"{handle} is not in the {cfg.key} cohort. Selection is a human "
                "decision; pass --select to record it here at the same time.",
                file=sys.stderr,
            )
            store.close()
            return 2
        store.select_cohort(cfg.key, [handle], baseline_run_id=args.baseline or "")

    ok = store.record_acceptance(
        cfg.key,
        handle,
        split_address=args.split_address or "",
        attestation_uid=args.attestation_uid or "",
    )
    if not ok:
        print(f"could not record acceptance for {handle}", file=sys.stderr)
        store.close()
        return 1

    plan = split_plan(overlay, dict(os.environ))
    if not args.split_address:
        print("--- split to create -------------------------------------------")
        print(plan.render())
        if not plan.resolved:
            print(
                "\nSome recipient addresses are unset; export them before creating "
                "the split.",
                file=sys.stderr,
            )
        print()

    score_row = None
    for row in store.submissions(cfg.key, limit=500):
        if row["handle"] == handle and row["status"] == "scored":
            score_row = row
            break

    print("--- acceptance letter -----------------------------------------")
    print(
        acceptance_letter(
            handle,
            overlay,
            split_address=args.split_address or "",
            score=score_row["total"] if score_row else None,
            caveat=score_row["concerns"] if score_row else "",
        )
    )
    store.close()
    return 0


def cmd_rings(args) -> int:
    from .modes.rings import find_clusters, report

    cfg = load_program(args.program)
    store = Store(args.db)
    snapshots = store.latest_snapshots(cfg.key)
    store.close()

    if not snapshots:
        print(f"no scored applicants for {cfg.key} yet", file=sys.stderr)
        return 2

    known = set(cfg.ecosystem.orgs) | set(cfg.frontier.orgs)
    clusters = find_clusters(snapshots, known)
    if args.format == "json":
        print(json.dumps([c.to_dict() for c in clusters], indent=2))
    else:
        print(f"{len(snapshots)} scored applicants in the pool\n")
        print(report(clusters))
    return 0


def cmd_runs(args) -> int:
    store = Store(args.db)
    for r in store.list_runs(args.program):
        print(
            f"{r['run_id']}  {r['started_at']}  {r['program']:<16} {r['mode']:<8} "
            f"{r['code_version']}  {r['note']}"
        )
    store.close()
    return 0


# -------------------------------------------------------------------- serve


def cmd_serve(args) -> int:
    import logging

    from .server import IntakeService, routes, run_server

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )

    secret = os.environ.get("TALLY_SIGNING_SECRET", "")
    if not secret:
        print(
            "TALLY_SIGNING_SECRET is not set.\n"
            "Take it from the Tally form's webhook settings and export it — the\n"
            "endpoint refuses to start without it, because an unauthenticated\n"
            "scoring endpoint is an open GitHub-API spend and lets anyone push\n"
            "applicants into the ranking.",
            file=sys.stderr,
        )
        return 2

    cfg = load_program(args.program)
    service = IntakeService(
        cfg=cfg,
        db_path=args.db,
        collector_factory=lambda: Collector(_client(args), window_days=cfg.window_days),
    )
    pages = (
        {}
        if args.no_page
        else routes(cfg.name, os.environ.get("TALLY_FORM_ID", ""), cfg.page)
    )
    if pages and not os.environ.get("TALLY_FORM_ID"):
        print(
            "note: TALLY_FORM_ID is not set, so the landing page renders without "
            "the embedded form.",
            file=sys.stderr,
        )
    run_server(service, secret, args.host, args.port, pages)
    return 0


def cmd_submissions(args) -> int:
    store = Store(args.db)
    rows = store.submissions(args.program, limit=args.limit)
    if args.with_contact:
        # Opt-in, and never part of the default view: this is the one command
        # that reads the quarantined contacts table.
        for r in rows:
            c = store.contact_for(r["submission_id"]) or {}
            total = "" if r["total"] is None else f"{r['total']:.2f}"
            print(
                f"{r['received_at']}  {r['status']:<10} {r['handle']:<20} {total:>6}  "
                f"{c.get('email', '')} {c.get('telegram', '')} {c.get('x', '')}".rstrip()
            )
    else:
        for r in rows:
            total = "" if r["total"] is None else f"{r['total']:.2f}"
            note = r["error"] or r["run_id"]
            print(f"{r['received_at']}  {r['status']:<10} {r['handle']:<20} {total:>6}  {note}")
            if r["concerns"]:
                print(f"{'':<26} {r['concerns']}")
    store.close()
    return 0


# -------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="talent-engine", description=__doc__)
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--budget", type=int, default=4000, help="max API requests this run")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("score")
    s.add_argument("--program", required=True)
    s.add_argument("--handles")
    s.add_argument("--csv")
    s.add_argument("--format", choices=["table", "json", "csv"], default="table")
    s.add_argument("--limit", type=int)
    s.add_argument("--dossier-dir")
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_score)

    s = sub.add_parser("scout")
    s.add_argument("--program", required=True)
    s.add_argument("--seeds", help="comma-separated owner/repo seeds")
    s.add_argument("--format", choices=["table", "json"], default="table")
    s.add_argument("--limit", type=int)
    s.set_defaults(func=cmd_scout)

    s = sub.add_parser("monitor")
    s.add_argument("--program", required=True)
    s.add_argument("--format", choices=["table", "json"], default="table")
    s.set_defaults(func=cmd_monitor)

    s = sub.add_parser("measure")
    s.add_argument("--program", required=True)
    s.add_argument("--baseline", required=True)
    s.add_argument("--endline", required=True)
    s.set_defaults(func=cmd_measure)

    s = sub.add_parser("verify")
    s.add_argument("--run", required=True)
    s.add_argument("--handle", required=True)
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("dossier")
    s.add_argument("--run", required=True)
    s.add_argument("--handle", required=True)
    s.set_defaults(func=cmd_dossier)

    s = sub.add_parser("runs")
    s.add_argument("--program")
    s.set_defaults(func=cmd_runs)

    s = sub.add_parser("accept", help="record an acceptance and print the letter")
    s.add_argument("--program", required=True)
    s.add_argument("--handle", required=True)
    s.add_argument("--overlay", help="policy key, if it differs from --program")
    s.add_argument("--split-address", help="the 0xSplits address, once it exists")
    s.add_argument("--attestation-uid", help="the signed pledge attestation")
    s.add_argument("--baseline", help="run id to measure this person against later")
    s.add_argument(
        "--select",
        action="store_true",
        help="also add them to the cohort (selection is otherwise a separate decision)",
    )
    s.set_defaults(func=cmd_accept)

    s = sub.add_parser(
        "rings", help="relationships between applicants (needs a pool, not one profile)"
    )
    s.add_argument("--program", required=True)
    s.add_argument("--format", choices=["table", "json"], default="table")
    s.set_defaults(func=cmd_rings)

    s = sub.add_parser("serve", help="receive form webhooks and score submissions")
    s.add_argument("--program", required=True)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)
    s.add_argument(
        "--no-page",
        action="store_true",
        help="serve only the webhook endpoint, no public landing page",
    )
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("submissions", help="what has come in through the form")
    s.add_argument("--program")
    s.add_argument("--limit", type=int, default=100)
    s.add_argument(
        "--with-contact",
        action="store_true",
        help="include contact details (reads the quarantined contacts table)",
    )
    s.set_defaults(func=cmd_submissions)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
