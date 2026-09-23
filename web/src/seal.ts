// Browser-side sealing (credential-custody spec: "Browser-Side Sealing").
// `libsodium-wrappers` ships a WASM payload, so this module is only ever
// imported lazily — from `api/supabase.ts`'s `saveCredentials` — the moment
// a user actually submits UPV credentials. Sign-in/sign-up never pay for it.

import sodium from "libsodium-wrappers";

export interface SealedCredentials {
  /** base64 (standard alphabet, padded) `crypto_box_seal` ciphertext. */
  sealed: string;
  key_id: string;
}

/** Bumped only if the sealed payload's JSON shape ever changes. */
const SEAL_VERSION = 1;

/**
 * Seals `{ v, username, password }` against `VITE_SEAL_PUBLIC_KEY` (base64,
 * standard alphabet) with `crypto_box_seal`, so only the holder of the
 * matching private key — the GitHub Actions runner, per design.md's "Key
 * rotation" decision — can ever recover the plaintext. Rejects if the public
 * key or key id are not configured, rather than silently sending nothing.
 */
export async function sealCredentials(
  username: string,
  password: string,
): Promise<SealedCredentials> {
  const publicKeyB64 = import.meta.env.VITE_SEAL_PUBLIC_KEY;
  const keyId = import.meta.env.VITE_SEAL_KEY_ID;
  if (!publicKeyB64 || !keyId) {
    throw new Error(
      "Falta configurar la clave pública de sellado (VITE_SEAL_PUBLIC_KEY / VITE_SEAL_KEY_ID).",
    );
  }

  await sodium.ready;
  const publicKey = sodium.from_base64(publicKeyB64, sodium.base64_variants.ORIGINAL);
  const payload = JSON.stringify({ v: SEAL_VERSION, username, password });
  const ciphertext = sodium.crypto_box_seal(sodium.from_string(payload), publicKey);

  return {
    sealed: sodium.to_base64(ciphertext, sodium.base64_variants.ORIGINAL),
    key_id: keyId,
  };
}
