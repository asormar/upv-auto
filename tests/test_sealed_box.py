"""Interop and error-path tests for `adapters.sealed_box.SealedBoxOpener`.

The interop fixture (`tests/fixtures/sealed_credentials_interop.json`) was
sealed with the real `libsodium-wrappers` package (the same one `web/src/seal.ts`
uses), not PyNaCl — this is what actually proves the browser and the runner
agree on the wire format, rather than PyNaCl round-tripping with itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from upv_auto.adapters.sealed_box import SealedBoxOpener, generate_keypair
from upv_auto.domain.errors import CredentialsUnavailable

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sealed_credentials_interop.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_opens_a_payload_sealed_by_libsodium_wrappers():
    fixture = load_fixture()
    opener = SealedBoxOpener({fixture["key_id"]: fixture["private_key"]})

    credentials = opener.open(fixture["sealed"], fixture["key_id"])

    assert credentials.username == fixture["username"]
    assert credentials.password == fixture["password"]


def test_unknown_key_id_raises_credentials_unavailable():
    fixture = load_fixture()
    opener = SealedBoxOpener({})  # no keys registered: as if the key was rotated out

    with pytest.raises(CredentialsUnavailable):
        opener.open(fixture["sealed"], fixture["key_id"])


def test_wrong_private_key_raises_credentials_unavailable():
    fixture = load_fixture()
    other_public, other_private = generate_keypair()
    assert other_public  # generated, unused here — only the mismatch matters
    opener = SealedBoxOpener({fixture["key_id"]: other_private})

    with pytest.raises(CredentialsUnavailable):
        opener.open(fixture["sealed"], fixture["key_id"])


def test_corrupt_ciphertext_raises_credentials_unavailable():
    fixture = load_fixture()
    opener = SealedBoxOpener({fixture["key_id"]: fixture["private_key"]})

    with pytest.raises(CredentialsUnavailable):
        opener.open("not-valid-base64!!!", fixture["key_id"])


def test_generate_keypair_round_trips_through_sealed_box_opener():
    """Exercises `generate_keypair` end to end using PyNaCl's own `crypto_box_seal`
    (not an interop concern — that's covered by the libsodium fixture above)."""
    from nacl.public import PublicKey, SealedBox
    import base64

    public_key_b64, private_key_b64 = generate_keypair()
    public_key = PublicKey(base64.b64decode(public_key_b64))
    payload = json.dumps({"v": 1, "username": "alice", "password": "hunter2"}).encode("utf-8")
    ciphertext = SealedBox(public_key).encrypt(payload)
    sealed = base64.b64encode(ciphertext).decode("ascii")

    opener = SealedBoxOpener({"kid": private_key_b64})
    credentials = opener.open(sealed, "kid")

    assert credentials.username == "alice"
    assert credentials.password == "hunter2"
