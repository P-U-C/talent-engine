"""GitHub authentication.

Three modes, in the order a deployment grows into them:

  AnonymousAuth  -- 60 req/hr. Unusable past a handful of profiles; present so
                    the tool runs at all with no setup, and it says so loudly.
  TokenAuth      -- a PAT. 5,000 req/hr. Fine for a single program run.
  AppAuth        -- a GitHub App installation. 5,000 req/hr *per installation*,
                    short-lived tokens, no human's personal credential in the
                    loop. This is the one to run in production.

The RS256 JWT for App auth is signed directly with `cryptography` rather than
pulling in PyJWT -- it is about twenty lines and keeps the dependency surface
at one library that was already present.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API_ROOT = "https://api.github.com"


class Auth:
    """Supplies an Authorization header value, or None."""

    def header(self) -> str | None:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def label(self) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def hourly_budget(self) -> int:
        return 5000


class AnonymousAuth(Auth):
    def header(self) -> str | None:
        return None

    @property
    def label(self) -> str:
        return "anonymous"

    @property
    def hourly_budget(self) -> int:
        return 60


@dataclass
class TokenAuth(Auth):
    token: str

    def header(self) -> str | None:
        return f"Bearer {self.token}"

    @property
    def label(self) -> str:
        return "token"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass
class AppAuth(Auth):
    """GitHub App installation auth with automatic token refresh."""

    app_id: str
    private_key_pem: str
    installation_id: str
    _token: str = field(default="", repr=False)
    _expires_at: float = field(default=0.0, repr=False)

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "AppAuth":
        key = env.get("GITHUB_APP_PRIVATE_KEY", "")
        key_path = env.get("GITHUB_APP_PRIVATE_KEY_PATH", "")
        if not key and key_path:
            key = Path(key_path).read_text()
        missing = [
            name
            for name, val in (
                ("GITHUB_APP_ID", env.get("GITHUB_APP_ID")),
                ("GITHUB_APP_INSTALLATION_ID", env.get("GITHUB_APP_INSTALLATION_ID")),
                ("GITHUB_APP_PRIVATE_KEY(_PATH)", key),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(f"GitHub App auth requires: {', '.join(missing)}")
        return cls(
            app_id=env["GITHUB_APP_ID"],
            private_key_pem=key,
            installation_id=env["GITHUB_APP_INSTALLATION_ID"],
        )

    def _app_jwt(self) -> str:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "GitHub App auth needs the `cryptography` package; use TokenAuth "
                "if you cannot install it"
            ) from exc

        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        # 60s of backdating absorbs clock skew; GitHub caps expiry at 10 min.
        payload = {"iat": now - 60, "exp": now + 540, "iss": self.app_id}
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(json.dumps(payload, separators=(",", ":")).encode())
        ).encode()

        key = serialization.load_pem_private_key(
            self.private_key_pem.encode(), password=None
        )
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        return signing_input.decode() + "." + _b64url(signature)

    def _refresh(self) -> None:
        req = urllib.request.Request(
            f"{API_ROOT}/app/installations/{self.installation_id}/access_tokens",
            method="POST",
            headers={
                "Authorization": f"Bearer {self._app_jwt()}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "talent-engine",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            raise RuntimeError(
                f"installation token request failed ({exc.code}): {exc.read()[:200]!r}"
            ) from exc
        self._token = data["token"]
        # Refresh a minute early rather than racing the expiry.
        self._expires_at = time.time() + 3540

    def header(self) -> str | None:
        if not self._token or time.time() >= self._expires_at:
            self._refresh()
        return f"Bearer {self._token}"

    @property
    def label(self) -> str:
        return f"app:{self.app_id}"


def auth_from_env(env: dict[str, str]) -> Auth:
    """Best available auth for the environment, strongest first."""
    if env.get("GITHUB_APP_ID") and env.get("GITHUB_APP_INSTALLATION_ID"):
        return AppAuth.from_env(env)
    for key in ("GITHUB_TOKEN", "GH_TOKEN", "TALENT_ENGINE_GITHUB_TOKEN"):
        if env.get(key):
            return TokenAuth(env[key])
    return AnonymousAuth()
