#!/usr/bin/env python3
"""Create or update a Tally form from a spec in `forms/`.

The spec is the source of truth, not Tally's editor. Question labels are the
wire format between the form and the webhook parser, so a label edited in the
Tally UI can silently stop a field being read with nothing raising anywhere —
`tests/test_form_spec.py` only guards the file.

Usage:
  export TALLY_API_KEY=...        # or put it in the env file the service reads
  create_tally_form.py forms/sponsorship-application.json --dry-run
  create_tally_form.py forms/sponsorship-application.json
  create_tally_form.py forms/sponsorship-application.json --update <form-id>

Prints the form id and public URL. Forms are created as DRAFT: publishing is a
deliberate act, not a side effect of running a script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API_ROOT = "https://api.tally.so"
API_VERSION = "2025-02-01"  # pinned: the API is versioned by date

# Spec type -> (Tally block type, group type). A question is two blocks sharing
# a groupUuid: the visible label, then the input.
BLOCK_TYPES = {
    "INPUT_TEXT": "INPUT_TEXT",
    "INPUT_EMAIL": "INPUT_EMAIL",
    "TEXTAREA": "TEXTAREA",
    "CHECKBOX": "CHECKBOX",
    "MULTIPLE_CHOICE_OPTION": "MULTIPLE_CHOICE_OPTION",
}


def _uuid() -> str:
    return str(uuid.uuid4())


def build_blocks(spec: dict) -> list[dict]:
    blocks: list[dict] = []

    title_uuid = _uuid()
    blocks.append(
        {
            "uuid": title_uuid,
            "type": "FORM_TITLE",
            "groupUuid": title_uuid,
            "groupType": "TEXT",
            "payload": {"title": spec["title"], "html": f"<h1>{spec['title']}</h1>"},
        }
    )

    for q in spec["questions"]:
        block_type = BLOCK_TYPES.get(q["type"])
        if not block_type:
            raise ValueError(f"unknown question type {q['type']!r} in {q['label']!r}")

        group = _uuid()
        # The label block. This is what arrives as `label` in the webhook, and
        # what the parser matches on — see forms/*.json for why it is fixed.
        blocks.append(
            {
                "uuid": _uuid(),
                "type": "TITLE",
                "groupUuid": group,
                "groupType": "QUESTION",
                "payload": {"title": q["label"], "html": q["label"]},
            }
        )

        if q["type"] == "CHECKBOX":
            # Checkboxes are one block per option, all sharing the group.
            for option in q.get("options", []):
                blocks.append(
                    {
                        "uuid": _uuid(),
                        "type": "CHECKBOX",
                        "groupUuid": group,
                        "groupType": "CHECKBOXES",
                        "payload": {
                            "index": len(blocks),
                            "text": option,
                            "isRequired": bool(q.get("required")),
                        },
                    }
                )
        else:
            blocks.append(
                {
                    "uuid": _uuid(),
                    "type": block_type,
                    "groupUuid": group,
                    "groupType": block_type,
                    "payload": {"isRequired": bool(q.get("required"))},
                }
            )

    return blocks


def call(method: str, path: str, key: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{API_ROOT}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "tally-version": API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:800]
        raise SystemExit(f"Tally API {exc.code} on {method} {path}:\n{detail}") from exc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--update", metavar="FORM_ID", help="update an existing form in place")
    ap.add_argument("--publish", action="store_true", help="create as PUBLISHED, not DRAFT")
    ap.add_argument("--workspace", help="workspace id")
    ap.add_argument("--dry-run", action="store_true", help="print the payload, send nothing")
    args = ap.parse_args()

    spec = json.loads(args.spec.read_text())
    payload: dict = {
        "blocks": build_blocks(spec),
        "status": "PUBLISHED" if args.publish else "DRAFT",
    }
    if args.workspace:
        payload["workspaceId"] = args.workspace

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        print(
            f"\n{len(spec['questions'])} questions, {len(payload['blocks'])} blocks. "
            "Nothing sent.",
            file=sys.stderr,
        )
        return 0

    key = os.environ.get("TALLY_API_KEY", "")
    if not key:
        print(
            "TALLY_API_KEY is not set. Create one at https://tally.so/settings/api "
            "and export it, or add it to the intake env file — never paste it into "
            "a chat window.",
            file=sys.stderr,
        )
        return 2

    if args.update:
        result = call("PATCH", f"/forms/{args.update}", key, payload)
    else:
        result = call("POST", "/forms", key, payload)

    form_id = result.get("id") or args.update or "?"
    print(f"form id:  {form_id}")
    print(f"public:   https://tally.so/r/{form_id}")
    print(f"embed id: {form_id}   -> set TALLY_FORM_ID to this")
    print(
        "\nNext: turn on the webhook in the form's Integrations tab, point it at\n"
        "  https://sponsorships.prezenti.xyz/webhook/tally\n"
        "and copy the signing secret into the intake env file.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
