import { useState, type FormEvent } from "react";
import { saveCredentials } from "../api";
import { Shield } from "./icons";

/** Collects UPV credentials once per account and seals them in the browser
 * before they ever leave it (credential-custody spec's "Browser-Side
 * Sealing"). Shown by `AuthGate` right after sign-in/sign-up, before the
 * queue is usable. */
export function CredentialsForm({ onSaved }: { onSaved: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await saveCredentials(username, password);
      onSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="authgate-form" onSubmit={submit}>
      <h1 className="authgate-title">Tus credenciales de la UPV</h1>
      <p className="authgate-hint authgate-hint-seal">
        <Shield size={14} />
        Se sellan en tu navegador antes de enviarse: nadie salvo el proceso que reserva el sábado
        puede leerlas.
      </p>
      <label className="field">
        <span>Usuario UPV</span>
        <input
          type="text"
          autoComplete="username"
          required
          value={username}
          onChange={(event) => setUsername(event.target.value)}
        />
      </label>
      <label className="field">
        <span>Contraseña UPV</span>
        <input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      {error && (
        <p className="authgate-error" role="alert">
          {error}
        </p>
      )}
      <button className="cta press" type="submit" disabled={busy}>
        {busy ? "Sellando…" : "Guardar credenciales"}
      </button>
    </form>
  );
}
