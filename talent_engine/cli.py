"""Command line interface.

    python3 -m talent_engine.cli score   --program celo-trial --handles a,b,c
    python3 -m talent_engine.cli score   --program celo-trial --csv applications.csv
    python3 -m talent_engine.cli scout   --program celo-trial --seeds celo-org/celo-composer
    python3 -m talent_engine.cli monitor --program celo-trial
    python3 -m talent_engine.cli measure --program celo-trial --baseline run_x --endline run_y
    python3 -m talent_engine.cli verify  --run run_x --handle octocat
    python3 -m talent_engine.cli dossier --run run_x --handle octocat
    python3 -m talent_engine.cli runs    --program celo-trial
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
from .modes.gates import HUMAN_GATES
from .store.db import LEDGER_TYPES
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


def cmd_decline(args) -> int:
    """Record a decline and produce the feedback the policy promises."""
    from .modes.decisions import feedback_letter

    cfg = load_program(args.program)
    store = Store(args.db)
    handle = normalize_handle(args.handle) or args.handle

    row = None
    for r in store.submissions(cfg.key, limit=1000):
        if r["handle"] == handle and r["status"] == "scored":
            row = r
            break
    if not row:
        print(
            f"no scored submission for {handle} in {cfg.key} — decline what was "
            "actually assessed, not a name",
            file=sys.stderr,
        )
        store.close()
        return 2

    store.record_decision(cfg.key, handle, "declined", note=args.note or "")
    score = store.replay(row["run_id"], handle)
    print(
        feedback_letter(
            handle, score, cfg, caveat=row["concerns"] or "",
            seats=args.seats, applicants=args.applicants, note=args.note or "",
        )
    )
    if args.mark_sent:
        store.mark_feedback_sent(cfg.key, handle)
        print("\n(marked as sent)", file=sys.stderr)
    else:
        print(
            "\n(not marked sent — pass --mark-sent once it has actually gone out)",
            file=sys.stderr,
        )
    store.close()
    return 0


def cmd_feedback_queue(args) -> int:
    """Who is still owed the feedback the policy promised them."""
    cfg = load_program(args.program)
    store = Store(args.db)
    pending = store.pending_feedback(cfg.key)
    if not pending:
        print("nobody is waiting on feedback")
    for row in pending:
        print(f"{row['decided_at']}  {row['handle']}  declined  (no feedback sent)")
    store.close()
    return 1 if pending else 0


def cmd_track(args) -> int:
    """Append an operating entry: receipts, reimbursements, checkpoints, KPIs."""
    from .programs.policy import load_overlay

    cfg = load_program(args.program)
    overlay = load_overlay(args.program)
    store = Store(args.db)
    handle = normalize_handle(args.handle) if args.handle else ""
    owner = args.owner or overlay.operating_owner
    if not owner:
        print(
            "no owner given and the policy sets no operating_owner. Every entry "
            "needs someone accountable for it.",
            file=sys.stderr,
        )
        store.close()
        return 2
    entry_id = store.record_ledger_entry(
        cfg.key,
        args.type,
        owner,
        handle=handle or "",
        period=args.period or "",
        amount_usd=args.amount,
        reference=args.reference or "",
        note=args.note or "",
    )
    print(f"recorded {args.type} for {handle or cfg.key} (owner: {owner})")
    print(f"  {entry_id}")
    store.close()
    return 0


def cmd_tracker(args) -> int:
    """What has been done for each recipient, and what has not."""
    import json as _json

    from .programs.policy import load_overlay
    from .store.db import programme_periods

    cfg = load_program(args.program)
    overlay = load_overlay(args.program)
    # The term's months, so an absent month-three receipt is visible rather
    # than being covered by a month-one one.
    periods = programme_periods(overlay.duration_months, args.start or overlay.term_start)
    store = Store(args.db)
    summary = store.ledger_summary(cfg.key, periods=periods)
    if args.format == "json":
        print(_json.dumps(summary, indent=2))
        store.close()
        return 0
    print(f"Operating tracker — {cfg.key}")
    if summary["totals"]:
        print("  totals: " + ", ".join(f"{k} ${v:,.2f}" for k, v in summary["totals"].items()))
    if not summary["recipients"]:
        print("  (no cohort yet)")
    for handle, r in summary["recipients"].items():
        owners = ", ".join(r["owners"]) or "nobody"
        print(f"\n  {handle}  ({r['entries']} entries, owners: {owners})")
        print(f"    reimbursed: ${r['reimbursed_usd']:,.2f}")
        if r["missing"]:
            print(f"    MISSING: {', '.join(r['missing'])}")
    store.close()
    return 0


def cmd_signoff(args) -> int:
    """Record that a named person checked a human gate."""
    from .modes.gates import GATE_LABELS

    cfg = load_program(args.program)
    store = Store(args.db)
    handle = normalize_handle(args.handle) or args.handle
    store.record_signoff(cfg.key, handle, args.gate, args.steward, args.note)
    print(f"{handle}: {GATE_LABELS[args.gate]} — signed off by {args.steward}")
    store.close()
    return 0


def cmd_gates(args) -> int:
    """Show every acceptance gate and whether it is met."""
    from .modes import gates as gate_checks
    from .programs.policy import load_overlay

    cfg = load_program(args.program)
    overlay = load_overlay(args.overlay or args.program)
    store = Store(args.db)
    handle = normalize_handle(args.handle) or args.handle
    checked = gate_checks.evaluate(
        store,
        cfg.key,
        handle,
        overlay.terms_digest(),
        overlay.terms_hash(),
    )
    print(gate_checks.render(checked))
    unmet = gate_checks.failing(checked)
    print(f"\n{len(checked) - len(unmet)}/{len(checked)} gates met.")
    for o in store.overrides(cfg.key, handle):
        print(f"  override: {o['gates']} by {o['steward']} — {o['reason']}")
    store.close()
    return 1 if unmet else 0


def cmd_legal_clearance(args) -> int:
    """Record counsel clearance for the exact current terms release."""
    from .programs.policy import load_overlay

    cfg = load_program(args.program)
    overlay = load_overlay(args.overlay or args.program)
    store = Store(args.db)
    digest = overlay.terms_digest()
    terms_hash = overlay.terms_hash()
    store.record_program_clearance(
        cfg.key,
        "legal",
        digest,
        terms_hash,
        args.steward,
        args.note or "",
    )
    print(
        f"legal clearance recorded for {cfg.key}: {digest} "
        f"({terms_hash}) by {args.steward}"
    )
    store.close()
    return 0


def cmd_accept(args) -> int:
    """Record an acceptance and produce the letter. Deploys nothing."""
    from .modes.acceptance import acceptance_letter
    from .programs.policy import load_overlay

    cfg = load_program(args.program)
    overlay = load_overlay(args.overlay or args.program)
    store = Store(args.db)

    from .modes import gates as gate_checks

    handle = normalize_handle(args.handle) or args.handle

    # Fail closed. `--select` used to be enough to accept an arbitrary handle
    # with no scored application, no recorded terms acceptance and none of the
    # programme's human checks -- and it printed the full acceptance letter.
    checked = gate_checks.evaluate(
        store,
        cfg.key,
        handle,
        overlay.terms_digest(),
        overlay.terms_hash(),
    )
    unmet = gate_checks.failing(checked)
    hard_unmet = gate_checks.non_bypassable_failures(checked)
    bypassable_unmet = [g for g in unmet if g.bypassable]
    override_event = None
    if unmet:
        print("--- acceptance gates -------------------------------------------")
        print(gate_checks.render(checked))
        if hard_unmet:
            print(
                f"\n{handle} does not clear {len(hard_unmet)} non-bypassable gate(s), "
                "so no acceptance was recorded and no letter was produced.\n"
                "Counsel clearance must be recorded for the exact current terms with:\n"
                "  python3 -m talent_engine.cli legal-clearance --program <program> "
                "--steward <who> --note <counsel memo/url>",
                file=sys.stderr,
            )
            store.close()
            return 2
        if not args.override:
            print(
                f"\n{handle} does not clear {len(bypassable_unmet)} candidate gate(s), "
                "so no acceptance was recorded and no letter was produced.\n"
                "Record the human checks with `python3 -m talent_engine.cli signoff`, "
                "or, if this is a deliberate candidate exception, re-run with:\n"
                "  --override --steward <who> --reason <why>\n"
                "An override is written atomically with acceptance after artefacts validate.",
                file=sys.stderr,
            )
            store.close()
            return 2
        if not (args.steward and args.reason):
            print(
                "--override requires --steward and --reason. An exception with no "
                "author and no stated reason is indistinguishable from a bug.",
                file=sys.stderr,
            )
            store.close()
            return 2
        override_event = ([g.key for g in bypassable_unmet], args.steward, args.reason)

    cohort_exists = any(m["handle"] == handle for m in store.cohort(cfg.key))
    if not cohort_exists and not args.select:
        print(
            f"{handle} is not in the {cfg.key} cohort. Selection is a human "
            "decision; pass --select to record it here at the same time.",
            file=sys.stderr,
        )
        store.close()
        return 2

    if args.split_address:
        print(
            "--split-address is obsolete for this trial. Use --payment-address "
            "with the verified Prezenti Safe; no 0xSplits collector is deployed.",
            file=sys.stderr,
        )
        store.close()
        return 2

    expected_payment = str(overlay.attestation.get("recipient", ""))
    payment_address = args.payment_address or ""
    if not payment_address:
        print(
            "--payment-address is required and must be the verified Prezenti Safe: "
            f"{expected_payment}",
            file=sys.stderr,
        )
        store.close()
        return 2
    if payment_address.lower() != expected_payment.lower():
        print(
            "payment address rejected: acceptance must use the verified Prezenti Safe "
            f"{expected_payment}",
            file=sys.stderr,
        )
        store.close()
        return 2

    attestation_uid = args.attestation_uid or ""
    if not (attestation_uid and args.attestation_signer):
        print(
            "--attestation-uid and --attestation-signer are required. The public "
            "pledge is mandatory for this trial and must be validated before acceptance.",
            file=sys.stderr,
        )
        store.close()
        return 2
    from .modes.attestations import AttestationValidationError, validate_attestation_uid

    try:
        validate_attestation_uid(
            attestation_uid,
            overlay,
            handle=handle,
            signer=args.attestation_signer,
            rpc_url=args.attestation_rpc,
        )
    except AttestationValidationError as exc:
        print(f"attestation rejected: {exc}", file=sys.stderr)
        store.close()
        return 2

    declared_repo = ""
    app_row = store.latest_application(cfg.key, handle)
    if app_row:
        try:
            declared_repo = json.loads(app_row["application_json"] or "{}").get("declared_repo", "")
        except (TypeError, ValueError):
            declared_repo = ""

    try:
        ok = store.accept_candidate(
            cfg.key,
            handle,
            selected=args.select and not cohort_exists,
            baseline_run_id=args.baseline or "",
            declared_repo=declared_repo,
            payment_address=payment_address,
            attestation_uid=attestation_uid,
            attestation_signer=args.attestation_signer,
            override=override_event,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        store.close()
        return 2
    if not ok:
        print(f"could not record acceptance for {handle}", file=sys.stderr)
        store.close()
        return 1

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
            payment_address=payment_address,
            score=score_row["total"] if score_row else None,
            caveat=score_row["concerns"] if score_row else "",
        )
    )
    store.close()
    return 0


def cmd_shortlist(args) -> int:
    """Deterministic shortlist across the whole scored applicant pool."""
    import json as _json

    store = Store(args.db)
    rows = store.shortlist(args.program, limit=args.limit)
    if args.format == "json":
        print(_json.dumps(rows, indent=2))
    else:
        for i, r in enumerate(rows, 1):
            total = "" if r["total"] is None else f"{r['total']:.2f}"
            print(f"{i:>2}. {r['handle']:<20} {total:>6}  {r['run_id']}  {r['received_at']}")
            if r["concerns"]:
                print(f"    {r['concerns']}")
    store.close()
    return 0


def cmd_quarantine(args) -> int:
    """Exclude a smoke-test or invalid handle from selection and reporting."""
    cfg = load_program(args.program)
    store = Store(args.db)
    handle = normalize_handle(args.handle) or args.handle
    store.quarantine_applicant(cfg.key, handle, args.reason)
    print(f"quarantined {handle}: {args.reason}")
    store.close()
    return 0


def _accepted_attestation_row(store: Store, program: str, handle: str) -> dict:
    cohort = {m["handle"]: m for m in store.cohort(program)}
    row = cohort.get(handle)
    if not row or not row.get("attestation_uid"):
        raise ValueError(f"{handle} has no original attestation UID recorded")
    if not row.get("attestation_signer"):
        raise ValueError(f"{handle} has no accepted attestation signer recorded")
    return row


def cmd_closeout_replace(args) -> int:
    """Record the builder-signed replacement pledge for close-out."""
    from .modes.attestations import AttestationValidationError, validate_replacement_uid
    from .programs.policy import load_overlay

    cfg = load_program(args.program)
    overlay = load_overlay(args.overlay or args.program)
    store = Store(args.db)
    handle = normalize_handle(args.handle) or args.handle
    try:
        row = _accepted_attestation_row(store, cfg.key, handle)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        store.close()
        return 2
    original_uid = row["attestation_uid"]
    signer = row["attestation_signer"]
    if args.months_funded < 0 or args.months_funded > overlay.duration_months:
        print(
            f"--months-funded must be between 0 and {overlay.duration_months}",
            file=sys.stderr,
        )
        store.close()
        return 2
    try:
        validate_replacement_uid(
            args.replacement_uid,
            overlay,
            handle=handle,
            signer=signer,
            previous_uid=original_uid,
            months_funded=args.months_funded,
            rpc_url=args.attestation_rpc,
        )
        event_id, created = store.record_closeout_replacement(
            cfg.key,
            handle,
            owner=args.owner or overlay.operating_owner,
            months_funded=args.months_funded,
            replacement_uid=args.replacement_uid,
            original_uid=original_uid,
            signer=signer,
            note=args.note or "",
        )
    except (AttestationValidationError, ValueError) as exc:
        print(f"close-out replacement rejected: {exc}", file=sys.stderr)
        store.close()
        return 2
    verb = "recorded" if created else "already recorded"
    print(
        f"close-out replacement {verb} for {handle}: {args.months_funded} "
        f"month(s) funded ({event_id})"
    )
    print(
        "replacement complete; builder still must revoke the original attestation "
        "with `python3 -m talent_engine.cli closeout-revoke`",
        file=sys.stderr,
    )
    store.close()
    return 0


def cmd_closeout_revoke(args) -> int:
    """Record revocation of the accepted original pledge after replacement."""
    from .modes.attestations import AttestationValidationError, validate_revoked_uid
    from .programs.policy import load_overlay

    cfg = load_program(args.program)
    overlay = load_overlay(args.overlay or args.program)
    store = Store(args.db)
    handle = normalize_handle(args.handle) or args.handle
    try:
        row = _accepted_attestation_row(store, cfg.key, handle)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        store.close()
        return 2
    original_uid = row["attestation_uid"]
    replacement = store.closeout_replacement_for(cfg.key, handle, original_uid)
    if not replacement:
        print(
            "record the close-out replacement before recording revocation",
            file=sys.stderr,
        )
        store.close()
        return 2
    try:
        validate_revoked_uid(original_uid, overlay, rpc_url=args.attestation_rpc)
        event_id, created = store.record_closeout_revocation(
            cfg.key,
            handle,
            owner=args.owner or overlay.operating_owner,
            original_uid=original_uid,
            replacement_uid=replacement["uid"],
            signer=row["attestation_signer"],
            revocation_tx=args.revocation_tx,
            months_funded=replacement.get("months_funded"),
            note=args.note or "",
        )
    except (AttestationValidationError, ValueError) as exc:
        print(f"close-out revocation rejected: {exc}", file=sys.stderr)
        store.close()
        return 2
    verb = "recorded" if created else "already recorded"
    print(f"close-out revocation {verb} for {handle}: {event_id}")
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

    from .programs.policy import load_overlay
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

    # Load and validate the programme policy before accepting a single
    # application. Previously the overlay was only read when someone was
    # accepted, which meant the service would happily take applications for
    # months under terms that violate the invariants and only fail at the
    # moment of accepting a person. Refusing to start is the enforcement.
    overlay = None
    try:
        overlay = load_overlay(args.overlay or args.program)
    except FileNotFoundError:
        print(
            f"note: no policy overlay for {cfg.key}; serving the form without "
            "programme terms. Add one in policies/ to state and enforce them.",
            file=sys.stderr,
        )
    except ValueError as exc:
        print(f"refusing to serve: the programme policy is invalid — {exc}", file=sys.stderr)
        return 2

    if overlay:
        logging.getLogger("talent_engine.intake").info(
            "serving under %s:\n  %s", overlay.name, "\n  ".join(overlay.terms_summary())
        )
        if not overlay.is_open:
            print(
                f"note: {overlay.key} is marked closed; the page will say so and "
                "will not show the form.",
                file=sys.stderr,
            )

    service = IntakeService(
        overlay=overlay,
        cfg=cfg,
        db_path=args.db,
        collector_factory=lambda: Collector(_client(args), window_days=cfg.window_days),
    )
    pages = (
        {}
        if args.no_page
        else routes(cfg.name, os.environ.get("TALLY_FORM_ID", ""), cfg.page, overlay)
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
    rows = store.submissions(
        args.program, limit=args.limit, include_quarantined=args.include_quarantined
    )
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
            app = json.loads(r["application_json"] or "{}")
            terms = "terms:ok" if app.get("accepted_terms") else "TERMS NOT ACCEPTED"
            print(
                f"{r['received_at']}  {r['status']:<10} {r['handle']:<20} {total:>6}  "
                f"{terms}  {note}"
            )
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

    s = sub.add_parser("decline", help="record a decline and print the feedback owed")
    s.add_argument("--program", required=True)
    s.add_argument("--handle", required=True)
    s.add_argument("--seats", type=int, help="places available, for context in the letter")
    s.add_argument("--applicants", type=int, help="how many applied")
    s.add_argument("--note", default="", help="anything specific to say to this person")
    s.add_argument("--mark-sent", action="store_true", help="record that it has gone out")
    s.set_defaults(func=cmd_decline)

    s = sub.add_parser(
        "feedback-queue", help="declined applicants still owed feedback (exit 1 if any)"
    )
    s.add_argument("--program", required=True)
    s.set_defaults(func=cmd_feedback_queue)

    s = sub.add_parser("accept", help="record an acceptance and print the letter")
    s.add_argument("--program", required=True)
    s.add_argument("--handle", required=True)
    s.add_argument("--overlay", help="policy key, if it differs from --program")
    s.add_argument("--payment-address", help="verified Prezenti Safe receiving direct give-back payments")
    s.add_argument("--split-address", help=argparse.SUPPRESS)
    s.add_argument("--attestation-uid", help="the signed public pledge attestation")
    s.add_argument("--attestation-signer", help="builder wallet that signed the attestation")
    s.add_argument(
        "--attestation-rpc",
        default="https://forno.celo.org",
        help="Celo JSON-RPC endpoint used to verify --attestation-uid",
    )
    s.add_argument("--baseline", help="run id to measure this person against later")
    s.add_argument(
        "--select",
        action="store_true",
        help="also add them to the cohort (selection is otherwise a separate decision)",
    )
    s.add_argument(
        "--override",
        action="store_true",
        help="proceed despite failing gates; requires --steward and --reason",
    )
    s.add_argument("--steward", help="who is taking responsibility for an override")
    s.add_argument("--reason", help="why the override is justified")
    s.set_defaults(func=cmd_accept)

    s = sub.add_parser(
        "signoff",
        help="record a human acceptance gate (access barrier, build plan, Celo fit, conflict)",
    )
    s.add_argument("--program", required=True)
    s.add_argument("--handle", required=True)
    s.add_argument("--gate", required=True, choices=list(HUMAN_GATES))
    s.add_argument("--steward", required=True, help="who checked it")
    s.add_argument("--note", default="", help="what they concluded")
    s.set_defaults(func=cmd_signoff)

    s = sub.add_parser("track", help="record an operating entry (receipt, KPI, ...)")
    s.add_argument("--program", required=True)
    s.add_argument("--type", required=True, choices=list(LEDGER_TYPES))
    s.add_argument("--owner", help="who is accountable (defaults to the policy operating_owner)")
    s.add_argument("--handle", help="recipient, if this is not programme-level")
    s.add_argument("--period", help="'YYYY-MM' or a milestone key")
    s.add_argument("--amount", type=float, help="USD, where the entry is financial")
    s.add_argument("--reference", help="receipt id, tx hash, or post URL")
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_track)

    s = sub.add_parser("tracker", help="what is done and what is outstanding")
    s.add_argument("--program", required=True)
    s.add_argument(
        "--start",
        help="override first programme month, YYYY-MM; defaults to policy term_start",
    )
    s.add_argument("--format", choices=["table", "json"], default="table")
    s.set_defaults(func=cmd_tracker)

    s = sub.add_parser("gates", help="show acceptance gate status for a candidate")
    s.add_argument("--program", required=True)
    s.add_argument("--handle", required=True)
    s.add_argument("--overlay", help="policy key, if it differs from --program")
    s.set_defaults(func=cmd_gates)

    s = sub.add_parser(
        "legal-clearance",
        help="record counsel clearance for the exact current terms release",
    )
    s.add_argument("--program", required=True)
    s.add_argument("--overlay", help="policy key, if it differs from --program")
    s.add_argument("--steward", required=True, help="who holds the counsel clearance")
    s.add_argument("--note", required=True, help="counsel memo, approval id, or URL")
    s.set_defaults(func=cmd_legal_clearance)

    s = sub.add_parser("shortlist", help="rank the whole scored applicant pool deterministically")
    s.add_argument("--program", required=True)
    s.add_argument("--limit", type=int)
    s.add_argument("--format", choices=["table", "json"], default="table")
    s.set_defaults(func=cmd_shortlist)

    s = sub.add_parser("quarantine", help="exclude a handle from selection/reporting")
    s.add_argument("--program", required=True)
    s.add_argument("--handle", required=True)
    s.add_argument("--reason", required=True)
    s.set_defaults(func=cmd_quarantine)

    s = sub.add_parser(
        "closeout-replace",
        help="record the builder-signed replacement pledge for close-out",
    )
    s.add_argument("--program", required=True)
    s.add_argument("--handle", required=True)
    s.add_argument("--overlay", help="policy key, if it differs from --program")
    s.add_argument("--months-funded", type=int, required=True)
    s.add_argument("--replacement-uid", required=True)
    s.add_argument("--attestation-rpc", default="https://forno.celo.org")
    s.add_argument("--owner", help="operator recording the close-out")
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_closeout_replace)

    s = sub.add_parser(
        "closeout-revoke",
        help="record revocation of the accepted original pledge",
    )
    s.add_argument("--program", required=True)
    s.add_argument("--handle", required=True)
    s.add_argument("--overlay", help="policy key, if it differs from --program")
    s.add_argument("--attestation-rpc", default="https://forno.celo.org")
    s.add_argument("--revocation-tx", required=True, help="transaction where the builder revoked the original UID")
    s.add_argument("--owner", help="operator recording the close-out")
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_closeout_revoke)

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
    s.add_argument("--overlay", help="policy key, if it differs from --program")
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
    s.add_argument(
        "--include-quarantined",
        action="store_true",
        help="include handles excluded from selection/reporting",
    )
    s.set_defaults(func=cmd_submissions)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
