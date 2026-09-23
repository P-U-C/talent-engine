#!/usr/bin/env bash
# Close the public Prezenti sponsorship intake without changing programme terms.
#
# The policy's `status` is part of the terms digest accepted by applicants.
# Do not flip that just to hide the form; use the runtime page flag instead.
set -euo pipefail

REPO="${TALENT_ENGINE_REPO:-/home/ubuntu/talent-engine}"
RUNTIME="${TALENT_ENGINE_RUNTIME:-/home/ubuntu/talent-engine-runtime}"
ENV_FILE="$RUNTIME/intake.env"
OPERATOR_ENV="$RUNTIME/operator.env"
CLOSED_AT="${1:-2026-09-24 00:00 America/Los_Angeles}"

umask 077
mkdir -p "$RUNTIME/form-snapshots"

if [ ! -f "$ENV_FILE" ]; then
  echo "missing $ENV_FILE" >&2
  exit 2
fi

backup="$RUNTIME/form-snapshots/intake.env.before-close-$(date -u +%Y%m%dT%H%M%SZ)"
cp "$ENV_FILE" "$backup"

python3 - "$ENV_FILE" "$CLOSED_AT" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
closed_at = sys.argv[2]
updates = {
    "TE_APPLICATIONS_CLOSED": "1",
    "TE_APPLICATIONS_CLOSE_AT": closed_at,
    "TE_APPLICATIONS_CLOSED_AT": closed_at,
}
lines = path.read_text().splitlines()
seen = set()
out = []
for line in lines:
    key, sep, _value = line.partition("=")
    if sep and key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n")
PY
chmod 600 "$ENV_FILE"

if [ -f "$OPERATOR_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$OPERATOR_ENV"
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  if [ -n "${TALLY_API_KEY:-}" ] && [ -n "${TALLY_FORM_ID:-}" ]; then
    python3 - <<'PY'
import json
import os
import urllib.request

api = "https://api.tally.so"
form = os.environ["TALLY_FORM_ID"]
key = os.environ["TALLY_API_KEY"]
payload = {
    "settings": {
        "isClosed": True,
        "closeTimezone": "America/Los_Angeles",
        "closeDate": "2026-09-24",
        "closeTime": "00:00",
        "closeMessageTitle": "Applications are closed",
        "closeMessageDescription": (
            "This sponsorship round closed at 12:00 AM Pacific on September 24, "
            "2026. The rubric and code remain public so applicants can still "
            "reproduce scores."
        ),
    }
}
req = urllib.request.Request(
    f"{api}/forms/{form}",
    method="PATCH",
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "tally-version": "2025-02-01",
        "User-Agent": "talent-engine/0.1 (+https://github.com/prezenti/talent-engine)",
    },
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode() or "{}")
settings = data.get("settings") or {}
print(json.dumps({"tally_form": data.get("id") or form, "isClosed": settings.get("isClosed")}))
PY
  else
    echo "Tally close skipped: TALLY_API_KEY or TALLY_FORM_ID unset" >&2
  fi
else
  echo "Tally close skipped: missing $OPERATOR_ENV" >&2
fi

sudo systemctl restart talent-engine-intake.service
curl -fsS http://127.0.0.1:8787/healthz >/dev/null
echo "sponsorship intake closed; env backup: $backup"
