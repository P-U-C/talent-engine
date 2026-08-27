"""The lead list the stewards work from, and the one promise it has to keep.

An outreach tab is typed beside this feed by hand. If a row ever moved, every
note beside it would come to describe the wrong person -- so discovery order is
a contract here, not a detail, and a new name can only appear at the bottom.
"""

from __future__ import annotations

from dataclasses import dataclass

from talent_engine.model import Application
from talent_engine.server import scouted_feed
from talent_engine.store.db import Store

PROGRAM = "prog"


@dataclass
class _Contact:
    email: str = ""
    name: str = ""
    telegram: str = ""
    x: str = ""
    discord: str = ""


def _scout(store, handle, first_seen, total=None):
    store.conn.execute(
        "CREATE TABLE IF NOT EXISTS scouted (program TEXT, handle TEXT, "
        "first_seen TEXT, channels TEXT DEFAULT '', PRIMARY KEY (program, handle))"
    )
    store.conn.execute(
        "INSERT OR IGNORE INTO scouted (program, handle, first_seen, channels) "
        "VALUES (?, ?, ?, 'adjacent')",
        (PROGRAM, handle, first_seen),
    )
    if total is not None:
        store.conn.execute(
            "INSERT INTO scores (run_id, handle, total, snapshot_digest, payload, scored_at) "
            "VALUES ('r1', ?, ?, 'd1', '{}', ?)",
            (handle, total, first_seen),
        )
    store.conn.commit()


def _seeded(tmp_path):
    store = Store(tmp_path / "t.db")
    _scout(store, "zara", "2026-08-01T00:00:00+00:00", total=70.0)
    _scout(store, "amara", "2026-08-02T00:00:00+00:00", total=60.0)
    _scout(store, "quiet-one", "2026-08-03T00:00:00+00:00")  # never scored
    store.save_recon({"handle": "zara", "x_handle": "zara_dev", "x_source": "profile field",
                      "name": "Zara", "blog": "https://zara.dev", "location": "Nairobi"})
    return store


def _rows(store):
    return scouted_feed.csv_for(str(store.path), PROGRAM).splitlines()


def test_discovery_order_is_the_contract(tmp_path):
    store = _seeded(tmp_path)
    body = _rows(store)
    assert body[1].startswith("zara,")     # found first, listed first
    assert body[2].startswith("amara,")
    # A newly discovered candidate lands at the bottom, never between the two
    # rows a steward has already written notes beside.
    _scout(store, "new-today", "2026-08-20T00:00:00+00:00", total=99.0)
    after = _rows(store)
    assert after[1:3] == body[1:3]
    assert after[-1].startswith("new-today,")
    store.close()


def test_the_handle_leads(tmp_path):
    store = _seeded(tmp_path)
    assert _rows(store)[0].split(",", 1)[0] == "Handle"
    store.close()


def test_unscored_candidates_are_left_out_by_default(tmp_path):
    store = _seeded(tmp_path)
    assert "quiet-one" not in "\n".join(_rows(store))
    assert "quiet-one" in scouted_feed.csv_for(str(store.path), PROGRAM, scored_only=False)
    store.close()


def test_someone_who_has_since_applied_is_marked(tmp_path):
    store = _seeded(tmp_path)
    store.record_submission("s1", PROGRAM, "tally", "amara", "Amara", Application())
    row = [r for r in _rows(store) if r.startswith("amara,")][0]
    assert "applied" in row
    store.close()


def test_an_applicants_own_details_never_reach_this_feed(tmp_path):
    store = _seeded(tmp_path)
    store.record_submission("s1", PROGRAM, "tally", "amara", "Amara", Application())
    store.record_contact("s1", _Contact(email="amara@example.org", telegram="@amara"))
    body = scouted_feed.csv_for(str(store.path), PROGRAM, scored_only=False)
    assert "amara@example.org" not in body and "@amara" not in body
    store.close()


def test_a_handle_nobody_has_looked_up_says_so(tmp_path):
    store = _seeded(tmp_path)
    row = [r for r in _rows(store) if r.startswith("amara,")][0]
    assert "not looked up yet" in row
    store.close()
