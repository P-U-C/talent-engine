"""Finding a way to reach someone must never mean guessing who they are.

Recon reads what a person published on their own GitHub profile. The tests that
matter are the ones about restraint: a share button is not a handle, a reserved
path is not a person, and a profile with nothing on it comes back empty rather
than plausible.
"""

from __future__ import annotations

import base64

from talent_engine.modes import recon


class FakeClient:
    """Answers the three endpoints recon knows about, and counts the calls."""

    def __init__(self, user=None, socials=None, readme=None):
        self.user = user or {}
        self.socials = socials
        self.readme = readme
        self.calls: list[str] = []

    def get(self, path, params=None):
        self.calls.append(path)
        if path.endswith("/social_accounts"):
            return self.socials
        if path.endswith("/readme"):
            return self.readme
        return self.user


def _readme(text: str) -> dict:
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


def test_the_stated_field_wins():
    c = FakeClient(user={"twitter_username": "amara_builds"})
    found = recon.find(c, "amara-dev")
    assert found["x_handle"] == "amara_builds"
    assert found["x_source"] == "profile field"


def test_a_linked_account_counts():
    c = FakeClient(socials=[{"provider": "twitter", "url": "https://x.com/amara_builds"}])
    found = recon.find(c, "amara-dev")
    assert (found["x_handle"], found["x_source"]) == ("amara_builds", "linked account")


def test_other_socials_are_kept_even_with_no_x():
    c = FakeClient(socials=[
        {"provider": "bluesky", "url": "https://bsky.app/profile/amara"},
        {"provider": "linkedin", "url": "https://linkedin.com/in/amara"},
    ])
    found = recon.find(c, "amara-dev")
    assert found["x_handle"] == ""          # nothing invented
    assert "bluesky: https://bsky.app/profile/amara" in found["socials"]
    assert "linkedin" in found["socials"]


def test_a_bio_link_counts():
    c = FakeClient(user={"bio": "building things · https://twitter.com/amara_builds"})
    found = recon.find(c, "amara-dev")
    assert (found["x_handle"], found["x_source"]) == ("amara_builds", "bio")


def test_the_readme_is_the_last_resort():
    c = FakeClient(readme=_readme("## hi\n[twitter](https://x.com/amara_builds)"))
    found = recon.find(c, "amara-dev")
    assert (found["x_handle"], found["x_source"]) == ("amara_builds", "profile README")


def test_the_readme_is_not_fetched_when_the_answer_is_already_known():
    c = FakeClient(user={"twitter_username": "amara_builds"}, readme=_readme("x.com/someone_else"))
    recon.find(c, "amara-dev")
    assert not any(p.endswith("/readme") for p in c.calls)


def test_a_share_button_is_not_a_person():
    c = FakeClient(readme=_readme(
        'tweet this: <a href="https://twitter.com/intent/tweet?text=hi">share</a>'
    ))
    assert recon.find(c, "amara-dev")["x_handle"] == ""


def test_an_empty_profile_stays_empty():
    found = recon.find(FakeClient(), "amara-dev")
    assert found["x_handle"] == "" and found["x_source"] == "" and found["socials"] == ""


def test_a_missing_profile_is_not_an_error():
    class Gone(FakeClient):
        def get(self, path, params=None):
            return None

    found = recon.find(Gone(), "deleted-account")
    assert found["handle"] == "deleted-account" and found["x_handle"] == ""
