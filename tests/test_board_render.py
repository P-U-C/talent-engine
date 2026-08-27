"""The board a steward opens by URL must never carry a person's details.

The board is served rather than published because a published snapshot is
correct only until the next application lands. Serving it means the URL is the
whole access control, exactly as with the scores feed -- so the question that
matters is not who holds the link but what the page can ever contain. These
tests pin that answer, and pin the reference format the stewards quote.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from talent_engine.model import Application
from talent_engine.store.db import Store

TOOL = Path(__file__).resolve().parents[1] / "tools" / "crm_report.py"


@dataclass
class _Contact:
    email: str = ""
    name: str = ""
    telegram: str = ""
    x: str = ""
    discord: str = ""


def _seeded(tmp_path) -> str:
    db = tmp_path / "t.db"
    store = Store(db)
    store.record_submission(
        "sub1", "prog", "tally", "amara-dev", "Amara-Dev",
        Application(declared_repo="amara-dev/thing", region="Africa"),
    )
    store.record_contact(
        "sub1",
        _Contact(email="amara@example.org", name="Amara Okafor",
                 telegram="@amara", x="amara_builds"),
    )
    store.assign_uid("sub1", "PRE-S3-S-")
    store.finish_submission("sub1", "scored", total=61.5)
    store.close()
    return str(db)


def _render(tmp_path, *flags) -> str:
    out = tmp_path / "board.html"
    subprocess.run(
        [sys.executable, str(TOOL), "--db", _seeded(tmp_path), "--out", str(out), *flags],
        check=True, capture_output=True,
    )
    return out.read_text()


def test_the_served_board_names_nobody(tmp_path):
    page = _render(tmp_path, "--standalone")
    for private in ("amara@example.org", "Amara Okafor", "@amara", "amara_builds"):
        assert private not in page
    # The public GitHub handle is not a contact detail and is the whole point.
    assert "amara-dev" in page


def test_the_local_copy_may_carry_contacts(tmp_path):
    page = _render(tmp_path, "--contacts")
    assert "amara@example.org" in page


def test_the_board_shows_the_reference(tmp_path):
    assert "PRE-S3-S-001" in _render(tmp_path, "--standalone")


def test_standalone_is_a_real_document(tmp_path):
    page = _render(tmp_path, "--standalone")
    assert page.startswith("<!doctype html>")
    # Stylesheet in the head, page in the body: a <link> stranded in the body
    # is the failure this split exists to prevent.
    head = page[: page.index("</head>")]
    assert "fonts.googleapis.com" in head and "</style>" in head
    assert "noindex" in head


def test_the_fragment_stays_a_fragment(tmp_path):
    # Without --standalone the artefact publisher wraps it, and a doctype of
    # our own would end up nested inside theirs.
    assert not _render(tmp_path).startswith("<!doctype")
