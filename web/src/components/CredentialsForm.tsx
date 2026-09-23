import { useState, type FormEvent } from "react";
import { saveCredentials } from "../api";
import { Alert, Eye, EyeOff, Refresh, Shield } from "./icons";

/** Turns a thrown error into human Spanish. `saveCredentials` (api/supabase.ts)
 * already translates known Postgres/auth error shapes; this only catches the
 * raw, browser-worded failures that slip past that layer (a dropped
 * connection, a stalled request) before they reach the screen. */
function describeSaveError(cause: unknown): string {
  const message = cause instanceof Error ? cause.message : String(cause);
  const lower = message.toLowerCase();
  if (
    lower.includes("networkerror") ||
    lower.includes("failed to fetch") ||
    lower.includes("load failed") ||
    lower.includes("network request failed")
  ) {
    return "No hay conexión con el servidor. Revisa tu internet e inténtalo de nuevo.";
  }
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return "La operación ha tardado demasiado. Inténtalo de nuevo.";
  }
  return message;
}

/** Collects UPV credentials once per account and seals them in the browser
 * before they ever leave it (credential-custody spec's "Browser-Side
 * Sealing"). Shown by `AuthGate` right after sign-in/sign-up, before the
 * queue is usable. */
export function CredentialsForm({ onSaved }: { onSaved: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
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
      setError(describeSaveError(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="authgate-form" onSubmit={submit}>
      <h1 className="authgate-title">Tus credenciales de la UPV</h1>
      <p className="authgate-hint authgate-hint-seal">
        <Shield size={14} />
        Se sellan en tu navegador con una clave pública antes de enviarse. Solo la clave privada
        guardada en GitHub Actions puede abrirlas, el sábado, para reservarte la plaza.
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
        <div className="field-control">
          <input
            type={reveal ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button
            type="button"
            className="field-toggle"
            onClick={() => setReveal((current) => !current)}
            aria-pressed={reveal}
            aria-label={reveal ? "Ocultar contraseña" : "Mostrar contraseña"}
          >
            {reveal ? <EyeOff /> : <Eye />}
          </button>
        </div>
      </label>
      {error && (
        <p className="authgate-banner error" role="alert" aria-live="assertive">
          <Alert size={14} />
          <span>{error}</span>
        </p>
      )}
      <button className="cta press" type="submit" disabled={busy} aria-busy={busy}>
        {busy && (
          <span className="spin">
            <Refresh size={14} />
          </span>
        )}
        {busy ? "Sellando…" : "Guardar credenciales"}
      </button>
    </form>
  );
}
