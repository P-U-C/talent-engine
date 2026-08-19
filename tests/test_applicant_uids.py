"""Applicant references are allocated once and never move.

Chad, 2026-08-19: "We also like to do a UID. We will have this as the first
column in review and format like PRE-S3-S-001."

The temptation is to compute it from row position, which needs no storage and
is wrong: deleting one row silently renumbers everyone below it, and a
reference a steward has already quoted in an email cannot be allowed to change
meaning. So it is allocated on arrival and stored.
"""

from __future__ import annotations

from talent_engine.model import Application
from talent_engine.store.db import Store


def _store(tmp_path):
    return Store(tmp_path / "t.db")


def _submit(store, sid, handle):
    store.record_submission(
        sid, "prog", "tally", handle, handle,
        Application(declared_repo="", region="Africa"),
    )


def test_references_are_allocated_in_order(tmp_path):
    store = _store(tmp_path)
    for sid, handle in (("s1", "first"), ("s2", "second"), ("s3", "third")):
        _submit(store, sid, handle)
        store.assign_uid(sid, "PRE-S3-S-")
    assert store.uid_for("s1") == "PRE-S3-S-001"
    assert store.uid_for("s2") == "PRE-S3-S-002"
    assert store.uid_for("s3") == "PRE-S3-S-003"
    store.close()


def test_allocating_twice_returns_the_same_reference(tmp_path):
    """Tally retries webhooks; a retry must not consume a second number."""
    store = _store(tmp_path)
    _submit(store, "s1", "someone")
    first = store.assign_uid("s1", "PRE-S3-S-")
    again = store.assign_uid("s1", "PRE-S3-S-")
    assert first == again == "PRE-S3-S-001"
    store.close()


def test_a_removed_row_leaves_a_gap_rather_than_renumbering(tmp_path):
    """The whole reason this is stored: reuse would point an old reference at a
    different person."""
    store = _store(tmp_path)
    for sid in ("s1", "s2"):
        _submit(store, sid, sid)
        store.assign_uid(sid, "PRE-S3-S-")
    store.conn.execute("DELETE FROM applicant_uids WHERE submission_id = 's2'")
    store.conn.commit()

    _submit(store, "s3", "later")
    assert store.assign_uid("s3", "PRE-S3-S-") == "PRE-S3-S-003"
    assert store.uid_for("s1") == "PRE-S3-S-001"  # untouched
    store.close()


def test_a_new_prefix_starts_its_own_sequence(tmp_path):
    """Next season counts from one rather than continuing this season's run."""
    store = _store(tmp_path)
    _submit(store, "s1", "a")
    _submit(store, "s2", "b")
    assert store.assign_uid("s1", "PRE-S3-S-") == "PRE-S3-S-001"
    assert store.assign_uid("s2", "PRE-S4-S-") == "PRE-S4-S-001"
    store.close()


def test_an_unscored_applicant_still_has_a_reference(tmp_path):
    """Launch day's two stranded applicants needed something to be called by."""
    store = _store(tmp_path)
    _submit(store, "stuck", "stuck-dev")
    assert store.assign_uid("stuck", "PRE-S3-S-") == "PRE-S3-S-001"
    store.close()


def test_adopting_the_counter_on_a_live_database_does_not_re_issue(tmp_path):
    """References were already issued before the counter table existed. The
    first allocation after it appears must continue the run, not restart it."""
    store = _store(tmp_path)
    for sid in ("s1", "s2"):
        _submit(store, sid, sid)
        store.assign_uid(sid, "PRE-S3-S-")
    # Simulate the pre-counter world: references exist, no high-water mark does.
    store.conn.execute("DELETE FROM uid_counters")
    store.conn.commit()

    _submit(store, "s3", "next-one")
    assert store.assign_uid("s3", "PRE-S3-S-") == "PRE-S3-S-003"
    store.close()
