"""Test-suite guards.

The suite exercises the real IntakeService, which notifies on every scored
submission. Before this file existed, running `pytest` delivered a burst of
"New application — octocat" messages to a real person's phone, because the
notifier fell back to reading a bot token off disk when the environment had
none. That fallback is gone; this is the second lock on the same door.
"""

from __future__ import annotations

import pytest

from talent_engine.notify import DISABLE_ENV


@pytest.fixture(autouse=True, scope="session")
def _never_notify_from_tests():
    import os

    os.environ[DISABLE_ENV] = "1"
    yield
