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

# A question is a TITLE block followed by its input block, each with its OWN
# groupUuid — the API rejects a TITLE that shares a group with an input
# ("TITLE block must not share groupUuid with an input block"). The label the
# webhook reports is taken from the preceding TITLE, so the association is
# positional. That is why the spec's question order is also the block order.
INPUT_TYPES = {"INPUT_TEXT", "INPUT_EMAIL", "TEXTAREA"}


def _uuid() -> str:
    return str(uuid.uuid4())


def build_blocks(spec: dict, terms_digest: str = "") -> list[dict]:
    """Blocks for the whole form.

    `terms_digest` is substituted into any `{terms_digest}` placeholder. The
    acceptance option carries it because Tally exposes no API for hidden
    fields, and a ticked checkbox is submitted as its own option text — so the
    applicant transmits the version of the terms they actually saw, rather than
    the server stamping whatever it considers current when the webhook lands.
    """
    blocks: list[dict] = []

    title_uuid = _uuid()
    blocks.append(
        {
            "uuid": title_uuid,
            "type": "FORM_TITLE",
            "groupUuid": title_uuid,
            "groupType": "TEXT",
            "payload": {"title": spec["title"], "safeHTMLSchema": [[spec["title"]]]},
        }
    )

    for q in spec["questions"]:
        # The label block. This is what arrives as `label` in the webhook and
        # what the parser matches on — see forms/*.json for why it is fixed.
        label_uuid = _uuid()
        blocks.append(
            {
                "uuid": label_uuid,
                "type": "TITLE",
                "groupUuid": label_uuid,
                "groupType": "QUESTION",
                "payload": {"safeHTMLSchema": [[q["label"]]]},
            }
        )

        if q["type"] == "CHECKBOX":
            # Tally has no distinct checkbox block: it is a multiple choice
            # with allowMultiple, one block per option, all sharing a group.
            options = [
                o.replace("{terms_digest}", terms_digest)
                for o in q.get("options", [])
            ]
            group = _uuid()
            for i, option in enumerate(options):
                blocks.append(
                    {
                        "uuid": _uuid(),
                        "type": "MULTIPLE_CHOICE_OPTION",
                        "groupUuid": group,
                        "groupType": "MULTIPLE_CHOICE",
                        "payload": {
                            "index": i,
                            "text": option,
                            "isRequired": bool(q.get("required")),
                            "isFirst": i == 0,
                            "isLast": i == len(options) - 1,
                            "allowMultiple": True,
                        },
                    }
                )
        elif q["type"] in INPUT_TYPES:
            input_uuid = _uuid()
            blocks.append(
                {
                    "uuid": input_uuid,
                    "type": q["type"],
                    "groupUuid": input_uuid,
                    "groupType": q["type"],
                    "payload": {
                        "isRequired": bool(q.get("required")),
                        "placeholder": q.get("placeholder", ""),
                    },
                }
            )
        else:
            raise ValueError(f"unknown question type {q['type']!r} in {q['label']!r}")

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
            # api.tally.so sits behind Cloudflare, which rejects the default
            # Python-urllib agent with a 403 / error 1010 before the request
            # reaches Tally at all. The failure looks exactly like a bad API
            # key, so it is worth the explicit header and this comment.
            "User-Agent": "talent-engine/0.1 (+https://github.com/P-U-C/talent-engine)",
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
    ap.add_argument(
        "--program",
        default="prezenti-sponsorship-trial",
        help="policy whose terms digest is written into the acceptance option",
    )
    args = ap.parse_args()

    spec = json.loads(args.spec.read_text())

    # The digest of the terms this form is being built against. It is written
    # into the acceptance option so the applicant submits the version they saw.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from talent_engine.programs.policy import load_overlay

    terms_digest = load_overlay(args.program).terms_digest()
    payload: dict = {
        "blocks": build_blocks(spec, terms_digest),
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
