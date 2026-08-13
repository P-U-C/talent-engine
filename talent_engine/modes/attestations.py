"""Validate EAS pledge attestations before storing their UID.

`accept --attestation-uid` is an acceptance artefact, not a note field. If a UID
is recorded, it must be the current trial pledge: same schema, recipient,
signer, handle, native expiry and canonical terms hash.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..programs.policy import ProgramOverlay

GET_ATTESTATION_SELECTOR = "0xa3112a64"
FORNO_RPC = "https://forno.celo.org"
ZERO_UID = "0x" + "0" * 64


class AttestationValidationError(ValueError):
    """The supplied UID exists but is not the current accepted pledge."""


@dataclass(frozen=True)
class Attestation:
    uid: str
    schema: str
    time: int
    expiration_time: int
    revocation_time: int
    ref_uid: str
    recipient: str
    attester: str
    revocable: bool
    data: bytes


@dataclass(frozen=True)
class TrialPledgeData:
    program_id: str
    recipient_handle: str
    sponsorship_value_usd: int
    giveback_basis_points: int
    prezenti_recipient: str
    prezenti_basis_points: int
    community_fund_recipient: str
    community_fund_basis_points: int
    cap_usd: int
    expires_at: int
    months_funded_at_signing: int
    covered_income: str
    rofo_notice_days: int
    terms_uri: str
    terms_hash: str


def validate_attestation_uid(
    uid: str,
    overlay: ProgramOverlay,
    *,
    handle: str,
    signer: str = "",
    rpc_url: str = FORNO_RPC,
) -> Attestation:
    """Fetch and validate a trial pledge attestation UID.

    `signer` is optional only so historical UIDs can be inspected. First
    acceptance should pass `--attestation-signer`; otherwise the attestation can
    prove terms were signed, but not who signed them.
    """
    uid = _normalise_uid(uid)
    att = get_attestation(uid, overlay.attestation["eas_contract"], rpc_url=rpc_url)
    expected = overlay.attestation

    _expect(att.uid == uid, "attestation UID did not round-trip from EAS")
    _expect(att.schema.lower() == expected["schema_uid"].lower(), "wrong EAS schema")
    _expect(att.recipient.lower() == expected["recipient"].lower(), "wrong attestation recipient")
    _expect(att.expiration_time == overlay.attestation_expiration, "wrong native EAS expiry")
    _expect(att.revocable, "attestation is not revocable")
    _expect(att.revocation_time == 0, "attestation has already been revoked")
    if signer:
        _expect(att.attester.lower() == signer.lower(), "attestation signer does not match")

    data = decode_trial_pledge_data(att.data)
    _expect(data.program_id == overlay.key, "wrong program id")
    _expect(data.recipient_handle.lower().lstrip("@") == handle.lower(), "wrong recipient handle")
    _expect(data.sponsorship_value_usd == int(overlay.per_person_usd), "wrong sponsorship value")
    _expect(data.giveback_basis_points == int(overlay.giveback["total_bps"]), "wrong give-back bps")
    _expect(data.prezenti_recipient.lower() == expected["recipient"].lower(), "wrong Prezenti recipient")
    _expect(data.prezenti_basis_points == int(overlay.giveback["total_bps"]), "wrong Prezenti bps")
    _expect(
        data.community_fund_recipient.lower() == expected["community_fund_recipient"].lower(),
        "wrong community fund recipient",
    )
    onward = overlay.giveback.get("prezenti_onward_commitment") or {}
    _expect(
        data.community_fund_basis_points == int(onward.get("bps_of_covered_income", 0)),
        "wrong community fund bps",
    )
    _expect(data.cap_usd == int(overlay.giveback_cap_usd), "wrong cap")
    _expect(data.expires_at == overlay.attestation_expiration, "wrong schema expiry")
    _expect(data.months_funded_at_signing == 0, "initial pledge must not set months funded")
    _expect(data.covered_income == _covered_income(overlay), "wrong covered-income text")
    _expect(data.rofo_notice_days == int(overlay.upside.get("rofo_notice_days", 0)), "wrong ROFO notice")
    _expect(data.terms_uri == overlay.terms_uri, "wrong terms URI")
    _expect(data.terms_hash.lower() == overlay.terms_hash().lower(), "wrong terms hash")
    return att


def get_attestation(uid: str, eas_contract: str, *, rpc_url: str = FORNO_RPC) -> Attestation:
    uid = _normalise_uid(uid)
    result = _eth_call(rpc_url, eas_contract, GET_ATTESTATION_SELECTOR + uid[2:])
    raw = bytes.fromhex(result[2:] if result.startswith("0x") else result)
    if len(raw) < 10 * 32:
        raise AttestationValidationError("EAS returned no attestation for that UID")
    words = [_word(raw, i) for i in range(10)]
    data_offset = _uint(words[9])
    data = _dynamic_bytes(raw, data_offset)
    return Attestation(
        uid=_hex_word(words[0]),
        schema=_hex_word(words[1]),
        time=_uint(words[2]),
        expiration_time=_uint(words[3]),
        revocation_time=_uint(words[4]),
        ref_uid=_hex_word(words[5]),
        recipient=_address(words[6]),
        attester=_address(words[7]),
        revocable=bool(_uint(words[8])),
        data=data,
    )


def decode_trial_pledge_data(data: bytes) -> TrialPledgeData:
    if len(data) < 15 * 32:
        raise AttestationValidationError("attestation data is too short for the trial schema")
    words = [_word(data, i) for i in range(15)]
    return TrialPledgeData(
        program_id=_dynamic_string(data, _uint(words[0])),
        recipient_handle=_dynamic_string(data, _uint(words[1])),
        sponsorship_value_usd=_uint(words[2]),
        giveback_basis_points=_uint(words[3]),
        prezenti_recipient=_address(words[4]),
        prezenti_basis_points=_uint(words[5]),
        community_fund_recipient=_address(words[6]),
        community_fund_basis_points=_uint(words[7]),
        cap_usd=_uint(words[8]),
        expires_at=_uint(words[9]),
        months_funded_at_signing=_uint(words[10]),
        covered_income=_dynamic_string(data, _uint(words[11])),
        rofo_notice_days=_uint(words[12]),
        terms_uri=_dynamic_string(data, _uint(words[13])),
        terms_hash=_hex_word(words[14]),
    )


def _eth_call(rpc_url: str, to: str, data: str) -> str:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": to, "data": data}, "latest"]}
    ).encode()
    req = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"content-type": "application/json", "user-agent": "talent-engine/attestation-validator"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode())
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise AttestationValidationError(f"could not read attestation from EAS: {exc}") from exc
    if body.get("error"):
        raise AttestationValidationError(f"EAS RPC error: {body['error']}")
    result = body.get("result")
    if not isinstance(result, str) or result in ("0x", "0x0"):
        raise AttestationValidationError("EAS returned no attestation for that UID")
    return result


def _covered_income(overlay: ProgramOverlay) -> str:
    g = overlay.giveback
    return f"{g.get('onchain_base')}, and any {g.get('also_applies_to')}."


def _normalise_uid(uid: str) -> str:
    uid = (uid or "").strip()
    if not uid.startswith("0x"):
        uid = "0x" + uid
    if len(uid) != 66:
        raise AttestationValidationError("attestation UID must be bytes32")
    try:
        int(uid[2:], 16)
    except ValueError as exc:
        raise AttestationValidationError("attestation UID must be hex bytes32") from exc
    return uid


def _word(blob: bytes, i: int) -> bytes:
    return blob[i * 32 : (i + 1) * 32]


def _uint(word: bytes) -> int:
    return int.from_bytes(word, "big")


def _hex_word(word: bytes) -> str:
    return "0x" + word.hex()


def _address(word: bytes) -> str:
    return "0x" + word[-20:].hex()


def _dynamic_bytes(blob: bytes, offset: int) -> bytes:
    if offset + 32 > len(blob):
        raise AttestationValidationError("dynamic data offset outside attestation payload")
    length = _uint(blob[offset : offset + 32])
    start = offset + 32
    end = start + length
    if end > len(blob):
        raise AttestationValidationError("dynamic data length outside attestation payload")
    return blob[start:end]


def _dynamic_string(blob: bytes, offset: int) -> str:
    try:
        return _dynamic_bytes(blob, offset).decode()
    except UnicodeDecodeError as exc:
        raise AttestationValidationError("attestation string field is not UTF-8") from exc


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AttestationValidationError(message)
