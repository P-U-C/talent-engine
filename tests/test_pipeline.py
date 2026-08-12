"""Pipeline tests: persistence, reproducibility, ingest, monitor, measure, scout."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from talent_engine.config import load_program
from talent_engine.ingest.normalize import normalize_handle, read_applications_report
from talent_engine.model import Application
from talent_engine.modes.monitor import ACTIVE, AT_RISK, INACTIVE, assess, measure
from talent_engine.modes.scout import Scout
from talent_engine.report import dossier, ranked_table, scores_to_csv
from talent_engine.scoring.engine import CODE_VERSION, rank, score_snapshot
from talent_engine.store.db import Store

from .fixtures.profiles import genuine_builder, gamed_profile, quiet_finisher


@pytest.fixture()
def cfg():
    return load_program("celo-trial")


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


# --------------------------------------------------------- reproducibility


def test_replay_reproduces_stored_score(store, cfg):
    snap = genuine_builder()
    run_id = store.start_run(cfg, "score", CODE_VERSION)
    store.save_snapshot(snap)
    original = score_snapshot(snap, cfg)
    store.save_score(run_id, original)

    replayed = store.replay(run_id, snap.handle)
    assert replayed.total == original.total
    assert replayed.snapshot_digest == original.snapshot_digest


def test_verify_reports_match(store, cfg):
    snap = genuine_builder()
    run_id = store.start_run(cfg, "score", CODE_VERSION)
    store.save_snapshot(snap)
    store.save_score(run_id, score_snapshot(snap, cfg))

    result = store.verify(run_id, snap.handle)
    assert result["matches"] is True
    assert result["recorded_total"] == result["replayed_total"]


def test_replay_uses_run_weights_not_current_ones(store, cfg):
    """A later rubric change must not silently rewrite an old score."""
    snap = genuine_builder()
    run_id = store.start_run(cfg, "score", CODE_VERSION)
    store.save_snapshot(snap)
    original = score_snapshot(snap, cfg)
    store.save_score(run_id, original)

    # Operator changes the live program config afterwards.
    cfg.weights["shipping_agency"] = 40.0
    assert store.replay(run_id, snap.handle).total == original.total


def test_config_survives_a_json_round_trip(cfg):
    """Regression: the audit log stores config as JSON and reloads it on replay.

    `to_dict()` emits each taxonomy's own `name`, which collided with the
    keyword on reload and broke every replay -- silently, and only for configs
    that had been persisted, which is all of them in production.
    """
    from talent_engine.config import ProgramConfig

    restored = ProgramConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))
    assert restored.weights_digest() == cfg.weights_digest()
    assert restored.ecosystem.topics == cfg.ecosystem.topics
    assert restored.frontier.keywords == cfg.frontier.keywords
    assert restored.referrers == cfg.referrers


def test_snapshot_digest_changes_when_inputs_change():
    a = genuine_builder()
    b = copy.deepcopy(a)
    b.repos[0].commits_in_window += 1
    assert a.digest() != b.digest()


# ---------------------------------------------------------------- ingest


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("octocat", "octocat"),
        ("@octocat", "octocat"),
        # Lower-cased: GitHub logins are case-insensitive, and preserving
        # case let one person hold two rows through to cohort selection.
        ("  OctoCat  ", "octocat"),
        ("github.com/octocat", "octocat"),
        ("https://github.com/octocat", "octocat"),
        ("https://github.com/octocat/", "octocat"),
        ("https://www.github.com/octocat/some-repo", "octocat"),
        ("https://github.com/octocat?tab=repositories", "octocat"),
        ("", None),
        ("not a handle", None),
        ("-leadinghyphen", None),
        ("a" * 40, None),
    ],
)
def test_handle_normalisation(raw, expected):
    assert normalize_handle(raw) == expected


def test_csv_ingest_reports_unusable_rows(tmp_path):
    path = tmp_path / "apps.csv"
    path.write_text(
        "GitHub URL,Access Barrier,Factors,Referrer,Project Repo\n"
        "https://github.com/amara-dev,No local funding network,self-taught;no degree,"
        "Celo Regional Scout - East Africa,amara-dev/x\n"
        "i dont have one,,,,\n"
    )
    good, bad = read_applications_report(path)
    assert [h for h, _, _ in good] == ["amara-dev"]
    assert len(bad) == 1  # surfaced, not silently dropped

    _, app, _ = good[0]
    assert app.context_factors == ["self-taught", "no degree"]
    assert app.referrer_name == "Celo Regional Scout - East Africa"


# --------------------------------------------------------------- monitor


def _now():
    return datetime(2026, 8, 5, tzinfo=timezone.utc)


def test_monitor_states(cfg):
    snap = genuine_builder()
    fresh = assess(snap, cfg, now=_now())
    assert fresh.state == ACTIVE

    stale = copy.deepcopy(snap)
    for r in stale.repos:
        r.pushed_at = "2026-07-15T00:00:00+00:00"
    stale.merged_prs = []
    stale.reviews = []
    assert assess(stale, cfg, now=_now()).state == AT_RISK

    dead = copy.deepcopy(stale)
    for r in dead.repos:
        r.pushed_at = "2026-05-01T00:00:00+00:00"
    assert assess(dead, cfg, now=_now()).state == INACTIVE


def test_monitor_flags_activity_away_from_declared_project(cfg):
    snap = genuine_builder()
    status = assess(snap, cfg, declared_repo="amara-dev/dotfiles", now=_now())
    assert status.declared_repo_active is True

    quiet = copy.deepcopy(snap)
    for r in quiet.repos:
        if r.name == "amara-dev/dotfiles":
            r.commits_in_window = 0
    status = assess(quiet, cfg, declared_repo="amara-dev/dotfiles", now=_now())
    assert status.declared_repo_active is False
    assert any("not on the funded project" in n for n in status.notes)
    # Busy elsewhere is the case a checkpoint exists to catch, so it downgrades.
    assert status.state == AT_RISK


def test_declared_repo_drift_never_upgrades_an_inactive_member(cfg):
    """The declared-repo rule may only downgrade."""
    dead = genuine_builder()
    for r in dead.repos:
        r.pushed_at = "2026-04-01T00:00:00+00:00"
        r.commits_in_window = 0
    dead.merged_prs = []
    dead.reviews = []
    status = assess(dead, cfg, declared_repo="amara-dev/dotfiles", now=_now())
    assert status.state == INACTIVE


def test_monitor_marks_partial_collection(cfg):
    snap = genuine_builder()
    snap.partial = True
    status = assess(snap, cfg, now=_now())
    assert any("unconfirmed" in n for n in status.notes)


# --------------------------------------------------------------- measure


def test_measure_reports_per_person_delta(cfg):
    before = [score_snapshot(quiet_finisher(), cfg)]

    grown = quiet_finisher()
    grown.repos[0].commits_in_window = 120
    grown.merged_prs = genuine_builder().merged_prs
    after = [score_snapshot(grown, cfg)]

    result = measure(before, after)
    assert result["cohort_size"] == 1
    assert result["improved"] == 1
    assert result["per_person"][0]["change"] > 0
    assert result["measured_on_same_rubric"] is True


def test_measure_notes_people_missing_from_endline(cfg):
    before = [score_snapshot(quiet_finisher(), cfg), score_snapshot(genuine_builder(), cfg)]
    after = [score_snapshot(quiet_finisher(), cfg)]
    assert measure(before, after)["missing_from_endline"] == ["amara-dev"]


# ----------------------------------------------------------------- report


def test_dossier_links_every_scored_claim(cfg):
    score = score_snapshot(genuine_builder(), cfg)
    text = dossier(score, cfg)
    assert score.handle in text
    assert "## Reproducing this score" in text
    assert score.snapshot_digest in text
    for d in score.dimensions:
        for e in d.evidence:
            assert e.url in text


def test_dossier_states_flags_do_not_subtract(cfg):
    text = dossier(score_snapshot(gamed_profile(), cfg), cfg)
    assert "Flags never add or subtract points" in text
    assert "burst_activity" in text


def test_csv_export_has_a_column_per_dimension(cfg):
    scores = rank([score_snapshot(f(), cfg) for f in (genuine_builder, gamed_profile)])
    header = scores_to_csv(scores).splitlines()[0]
    for key in cfg.weights:
        assert key in header


# ------------------------------------------------------------------ scout


class FakeClient:
    """Records requests and replays canned pages. No network."""

    def __init__(self, pages: dict[str, list[dict]]):
        self.pages = pages
        self.calls: list[tuple[str, dict]] = []
        self.stats = {"requests_spent": 0, "served_from_cache_304": 0}

    def paginate(self, path, params=None, max_pages=10):
        self.calls.append((path, dict(params or {})))
        key = f"{path}|{(params or {}).get('q', '')}"
        for item in self.pages.get(key, self.pages.get(path, [])):
            yield item

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        return self.pages.get(path, [])


def test_scout_prefers_corroborated_and_originators(cfg):
    client = FakeClient(
        {
            "/search/issues": [
                {"user": {"login": "insider", "type": "User"}, "html_url": "https://github.com/x/y/pull/1"},
                {"user": {"login": "both", "type": "User"}, "html_url": "https://github.com/x/y/pull/2"},
                {"user": {"login": "dependabot[bot]", "type": "Bot"}, "html_url": "https://github.com/x/y/pull/3"},
            ],
            "/search/repositories": [
                {
                    "full_name": "both/agent-thing",
                    "owner": {"login": "both", "type": "User"},
                    "html_url": "https://github.com/both/agent-thing",
                    "fork": False,
                },
                {
                    "full_name": "solo/mcp-thing",
                    "owner": {"login": "solo", "type": "User"},
                    "html_url": "https://github.com/solo/mcp-thing",
                    "fork": False,
                },
            ],
            "/repos/both/agent-thing/contributors": [],
            "/repos/solo/mcp-thing/contributors": [],
        }
    )
    scout = Scout(client, cfg, now=_now())
    ranked_candidates = scout.run(["celo-org/celo-composer"])
    handles = [c.handle for c in ranked_candidates]

    assert "dependabot[bot]" not in handles  # bots filtered
    assert handles[0] == "both"  # two channels beats one
    assert handles.index("solo") < handles.index("insider")  # originator > insider


def test_scout_queries_frontier_before_ecosystem(cfg):
    """Scarcer signal first: the search budget usually runs out early."""
    scout = Scout(FakeClient({}), cfg, now=_now())
    queries = scout._taxonomy_queries()
    first_frontier = next(i for i, q in enumerate(queries) if "mcp" in q)
    first_eco = next(i for i, q in enumerate(queries) if "celo" in q)
    assert first_frontier < first_eco


def test_scout_excludes_forks_from_originator_channel(cfg):
    client = FakeClient(
        {
            "/search/repositories": [
                {
                    "full_name": "forker/fork-of-thing",
                    "owner": {"login": "forker", "type": "User"},
                    "html_url": "https://github.com/forker/fork-of-thing",
                    "fork": True,
                }
            ]
        }
    )
    scout = Scout(client, cfg, now=_now())
    scout.from_originators()
    assert "forker" not in scout.candidates
