"""The acceptance UID is checked against the on-chain pledge shape."""

from __future__ import annotations

import pytest

from talent_engine.modes import attestations
from talent_engine.modes.attestations import Attestation, AttestationValidationError
from talent_engine.programs.policy import load_overlay

UID = "0x" + "ab" * 32
SIGNER = "0x1111111111111111111111111111111111111111"


def test_decode_trial_pledge_data_round_trips_current_terms():
    overlay = load_overlay("prezenti-sponsorship-trial")
    data = attestations.decode_trial_pledge_data(_encoded_trial_data(overlay, "amara"))
    assert data.program_id == overlay.key
    assert data.recipient_handle == "amara"
    assert data.giveback_basis_points == 200
    assert data.community_fund_basis_points == 100
    assert data.months_funded_at_signing == 0
    assert data.terms_hash == overlay.terms_hash()


def test_validate_attestation_rejects_wrong_terms_hash(monkeypatch):
    overlay = load_overlay("prezenti-sponsorship-trial")
    monkeypatch.setattr(
        attestations,
        "get_attestation",
        lambda uid, eas, rpc_url: _attestation(
            overlay,
            "amara",
            terms_hash="0x" + "12" * 32,
        ),
    )
    with pytest.raises(AttestationValidationError, match="terms hash"):
        attestations.validate_attestation_uid(UID, overlay, handle="amara", signer=SIGNER)


def test_validate_attestation_rejects_wrong_handle(monkeypatch):
    overlay = load_overlay("prezenti-sponsorship-trial")
    monkeypatch.setattr(
        attestations,
        "get_attestation",
        lambda uid, eas, rpc_url: _attestation(overlay, "someone-else"),
    )
    with pytest.raises(AttestationValidationError, match="recipient handle"):
        attestations.validate_attestation_uid(UID, overlay, handle="amara", signer=SIGNER)


def test_validate_attestation_rejects_wrong_signer(monkeypatch):
    overlay = load_overlay("prezenti-sponsorship-trial")
    monkeypatch.setattr(
        attestations,
        "get_attestation",
        lambda uid, eas, rpc_url: _attestation(overlay, "amara"),
    )
    with pytest.raises(AttestationValidationError, match="signer"):
        attestations.validate_attestation_uid(
            UID,
            overlay,
            handle="amara",
            signer="0x2222222222222222222222222222222222222222",
        )


def test_validate_attestation_accepts_the_current_trial_pledge(monkeypatch):
    overlay = load_overlay("prezenti-sponsorship-trial")
    monkeypatch.setattr(
        attestations,
        "get_attestation",
        lambda uid, eas, rpc_url: _attestation(overlay, "amara"),
    )
    got = attestations.validate_attestation_uid(UID, overlay, handle="amara", signer=SIGNER)
    assert got.uid == UID


def _attestation(
    overlay,
    handle: str,
    *,
    terms_hash: str | None = None,
    months_funded: int = 0,
) -> Attestation:
    return Attestation(
        uid=UID,
        schema=overlay.attestation["schema_uid"],
        time=1,
        expiration_time=overlay.attestation_expiration,
        revocation_time=0,
        ref_uid=attestations.ZERO_UID,
        recipient=overlay.attestation["recipient"].lower(),
        attester=SIGNER.lower(),
        revocable=True,
        data=_encoded_trial_data(
            overlay,
            handle,
            terms_hash=terms_hash,
            months_funded=months_funded,
        ),
    )


def _encoded_trial_data(
    overlay,
    handle: str,
    *,
    terms_hash: str | None = None,
    months_funded: int = 0,
) -> bytes:
    strings = [
        overlay.key,
        handle,
        _covered_income(overlay),
        overlay.terms_uri,
    ]
    heads: list[bytes] = []
    tails: list[bytes] = []

    def dyn(value: str) -> bytes:
        offset = 32 * 15 + sum(len(t) for t in tails)
        heads.append(_uint(offset))
        data = value.encode()
        padded = data + b"\x00" * ((32 - len(data) % 32) % 32)
        tails.append(_uint(len(data)) + padded)
        return b""

    dyn(strings[0])
    dyn(strings[1])
    heads.extend(
        [
            _uint(int(overlay.per_person_usd)),
            _uint(overlay.giveback["total_bps"]),
            _address(overlay.attestation["recipient"]),
            _uint(overlay.giveback["total_bps"]),
            _address(overlay.attestation["community_fund_recipient"]),
            _uint(overlay.giveback["prezenti_onward_commitment"]["bps_of_covered_income"]),
            _uint(int(overlay.giveback_cap_usd)),
            _uint(overlay.attestation_expiration),
            _uint(months_funded),
        ]
    )
    dyn(strings[2])
    heads.append(_uint(overlay.upside["rofo_notice_days"]))
    dyn(strings[3])
    heads.append(bytes.fromhex((terms_hash or overlay.terms_hash())[2:]))
    return b"".join(heads + tails)


def _covered_income(overlay) -> str:
    g = overlay.giveback
    return f"{g.get('onchain_base')}, and any {g.get('also_applies_to')}."


def _uint(value: int) -> bytes:
    return int(value).to_bytes(32, "big")


def _address(value: str) -> bytes:
    return b"\x00" * 12 + bytes.fromhex(value[2:])
