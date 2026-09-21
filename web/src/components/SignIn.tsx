import { useState, type FormEvent } from "react";
import { signIn, signUp } from "../api";

type Mode = "sign-in" | "sign-up";

/** Email + password sign-in/sign-up (user-accounts spec). Toggles between
 * the two modes in place rather than as separate routes/screens. */
export function SignIn() {
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="authgate-form" onSubmit={submit}>
      <h1 className="authgate-title">{mode === "sign-in" ? "Inicia sesión" : "Crea tu cuenta"}</h1>
      <p className="authgate-hint">
        {mode === "sign-in"
          ? "Usa el correo con el que te registraste."
          : "Solo hacen falta un correo y una contraseña."}
      </p>
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
        <input
          type="password"
          autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
          minLength={6}
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
      {info && <p className="authgate-info">{info}</p>}
      <button className="cta press" type="submit" disabled={busy}>
        {busy ? "Un momento…" : mode === "sign-in" ? "Entrar" : "Crear cuenta"}
      </button>
      <button className="authgate-switch" type="button" onClick={switchMode}>
        {mode === "sign-in" ? "¿No tienes cuenta? Regístrate" : "¿Ya tienes cuenta? Inicia sesión"}
      </button>
    </form>
  );
}
