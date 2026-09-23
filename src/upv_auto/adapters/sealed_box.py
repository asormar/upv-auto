"""PyNaCl adapter: opens credentials sealed in the browser, and a keygen helper.

Mirrors `web/src/seal.ts`: the browser seals `JSON.stringify({v, username,
password})` with `crypto_box_seal` against the public key, base64-encoded
with the standard padded alphabet (libsodium's `base64_variants.ORIGINAL`,
the same alphabet as Python's `base64.b64encode`). `SealedBoxOpener` reverses
that with PyNaCl's `SealedBox`, using the private key for the sealed
payload's `key_id` (see design.md's "Key rotation").
"""

from __future__ import annotations

import base64
import json

from nacl.exceptions import CryptoError
from nacl.public import PrivateKey, SealedBox

from upv_auto.domain.errors import CredentialsUnavailable
from upv_auto.domain.models import Credentials


class SealedBoxOpener:
    """Unseals credentials for a known set of key ids.

    `private_keys` maps `key_id -> base64 private key`, mirroring the
    `SEAL_PRIVATE_KEYS` GitHub secret. A `key_id` not present here (rotated
    out, or never configured) raises `CredentialsUnavailable` rather than
    crashing: the caller records that one user's result and keeps going.
    """

    def __init__(self, private_keys: dict[str, str]) -> None:
        self._private_keys = private_keys

    def open(self, sealed: str, key_id: str) -> Credentials:
        private_key_b64 = self._private_keys.get(key_id)
        if private_key_b64 is None:
            raise CredentialsUnavailable(f"Unknown seal key id: {key_id!r}")

        try:
            private_key = PrivateKey(base64.b64decode(private_key_b64))
            ciphertext = base64.b64decode(sealed)
            plaintext = SealedBox(private_key).decrypt(ciphertext)
            payload = json.loads(plaintext)
        except (CryptoError, ValueError) as exc:
            raise CredentialsUnavailable(f"Could not unseal credentials: {exc}") from exc

        username = payload.get("username") if isinstance(payload, dict) else None
        password = payload.get("password") if isinstance(payload, dict) else None
        if not username or not password:
            raise CredentialsUnavailable("Unsealed payload is missing username or password")

        return Credentials(username=username, password=password)


def generate_keypair() -> tuple[str, str]:
    """Generate a fresh sealed-box key pair.

    Returns `(public_key_b64, private_key_b64)`, both base64 with the
    standard padded alphabet, ready for `VITE_SEAL_PUBLIC_KEY` and the
    `SEAL_PRIVATE_KEYS` secret respectively.
    """
    private_key = PrivateKey.generate()
    public_key_b64 = base64.b64encode(bytes(private_key.public_key)).decode("ascii")
    private_key_b64 = base64.b64encode(bytes(private_key)).decode("ascii")
    return public_key_b64, private_key_b64
