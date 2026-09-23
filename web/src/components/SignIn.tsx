import { useState, type FormEvent } from "react";
import { signIn, signUp } from "../api";
import { Alert, Eye, EyeOff, Refresh } from "./icons";

type Mode = "sign-in" | "sign-up";

/** Turns a thrown error into human Spanish. `signIn`/`signUp` (api/supabase.ts)
 * already translate known Supabase auth error shapes; this only catches the
 * raw, browser-worded failures that slip past that layer (a dropped
 * connection, a stalled request) before they reach the screen. */
function describeAuthError(cause: unknown): string {
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

/** Email + password sign-in/sign-up (user-accounts spec). Toggles between
 * the two modes in place rather than as separate routes/screens. */
export function SignIn() {
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const switchMode = () => {
    setMode((current) => (current === "sign-in" ? "sign-up" : "sign-in"));
    setError(null);
    setInfo(null);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      if (mode === "sign-up") {
        await signUp(email, password);
        setInfo("Cuenta creada. Ya tienes la sesión iniciada.");
      } else {
        await signIn(email, password);
      }
    } catch (cause) {
      setError(describeAuthError(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="authgate-form" onSubmit={submit}>
      {/* Remounts on mode change so the copy swap gets a short settle
          instead of teleporting between sign-in and sign-up text. */}
      <div className="authgate-switchable" key={mode}>
        <h1 className="authgate-title">{mode === "sign-in" ? "Inicia sesión" : "Crea tu cuenta"}</h1>
        <p className="authgate-hint">
          {mode === "sign-in"
            ? "Usa el correo con el que te registraste."
            : "Solo hacen falta un correo y una contraseña. No hay correo de confirmación: podrás continuar enseguida."}
        </p>
      </div>
      <label className="field">
        <span>Correo</span>
        <input
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>
      <label className="field">
        <span>Contraseña</span>
        <div className="field-control">
          <input
            type={reveal ? "text" : "password"}
            autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
            minLength={6}
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
      {info && (
        <p className="authgate-banner info" role="status" aria-live="polite">
          <span>{info}</span>
        </p>
      )}
      <button className="cta press" type="submit" disabled={busy} aria-busy={busy}>
        {busy && (
          <span className="spin">
            <Refresh size={14} />
          </span>
        )}
        {busy
          ? mode === "sign-up"
            ? "Creando cuenta…"
            : "Entrando…"
          : mode === "sign-in"
            ? "Entrar"
            : "Crear cuenta"}
      </button>
      <button className="authgate-switch" type="button" onClick={switchMode}>
        {mode === "sign-in" ? "¿No tienes cuenta? Regístrate" : "¿Ya tienes cuenta? Inicia sesión"}
      </button>
    </form>
  );
}
