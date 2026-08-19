"""The stewards' spreadsheet pulls scores; it must never pull a person's details.

The Tally sheet lives inside the Prezenti workspace and cannot be shared out, so
the scores travel to it through an IMPORTDATA endpoint instead. That endpoint is
fetched anonymously by Google, which makes "what can this URL ever return"
the whole of its security model. These tests pin the answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from talent_engine.model import Application
from talent_engine.server import scores_feed
from talent_engine.store.db import Store


@dataclass
class _Contact:
    email: str = ""
    name: str = ""
    telegram: str = ""
    x: str = ""
    discord: str = ""


def _seeded(tmp_path):
    db = tmp_path / "t.db"
    store = Store(db)
    store.record_submission(
        "sub1", "prog", "tally", "amara-dev", "Amara-Dev",
        Application(declared_repo="amara-dev/thing", region="Africa"),
    )
    store.record_contact(
        "sub1",
        _Contact(
            email="amara@example.org",
            name="Amara Okafor",
            telegram="@amara",
            x="amara_builds",
        ),
    )
    store.finish_submission("sub1", "scored", total=61.5)
    store.close()
    return str(db)


def test_the_feed_carries_the_score(tmp_path):
    out = scores_feed.csv_for(_seeded(tmp_path))
    assert out.startswith("Handle,Continent,Score,")
    assert "amara-dev" in out
    assert "61.50" in out
    assert "Africa" in out


def test_the_feed_carries_no_contact_detail(tmp_path):
    """Contact rows exist for this submission; none of them may appear."""
    out = scores_feed.csv_for(_seeded(tmp_path))
    for secret in ("amara@example.org", "Amara Okafor", "@amara", "amara_builds"):
        assert secret not in out, f"{secret!r} leaked into the scores feed"


def test_an_unscored_applicant_is_still_listed(tmp_path):
    """A stuck applicant that appears nowhere is how launch day went wrong."""
    db = tmp_path / "t.db"
    store = Store(db)
    store.record_submission(
        "sub2", "prog", "tally", "stuck-dev", "Stuck-Dev",
        Application(declared_repo="", region="Asia"),
    )
    store.close()
    out = scores_feed.csv_for(str(db))
    assert "stuck-dev" in out
    assert "stuck" in out.lower()
