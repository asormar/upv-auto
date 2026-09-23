import { useEffect, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { BACKEND, getSession, hasCredentials, onAuthStateChange } from "../api";
import { Clock, Refresh } from "./icons";
import { SignIn } from "./SignIn";
import { CredentialsForm } from "./CredentialsForm";
import { ThemeToggle } from "./ThemeToggle";

type GateState =
  | { phase: "loading" }
  | { phase: "signed-out" }
  | { phase: "needs-credentials" }
  | { phase: "ready" };

/**
 * Gates the app behind Supabase auth + a saved UPV credential (user-accounts
 * and credential-custody specs). Under `VITE_BACKEND=local` there is no
 * account system at all — `serve --demo`/local dev render the app directly.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [state, setState] = useState<GateState>({ phase: "loading" });

  useEffect(() => {
    if (BACKEND === "local") return;
    let cancelled = false;
    void getSession().then((current) => {
      if (!cancelled) setSession(current);
    });
    const unsubscribe = onAuthStateChange((next) => setSession(next));
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (BACKEND === "local" || session === undefined) return;
    if (!session) {
      setState({ phase: "signed-out" });
      return;
    }
    let cancelled = false;
    setState({ phase: "loading" });
    void hasCredentials()
      .then((present) => {
        if (!cancelled) setState({ phase: present ? "ready" : "needs-credentials" });
      })
      .catch(() => {
        // RLS gives an authenticated user nothing to fail on for their own
        // row; treat any read failure as "not saved yet" rather than
        // stalling the gate on a transient error.
        if (!cancelled) setState({ phase: "needs-credentials" });
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  if (BACKEND === "local" || state.phase === "ready") return <>{children}</>;

  return (
    <div className="authgate">
      <div className="authgate-card card">
        <span className="brand authgate-brand">
          <span className="mark">
            <Clock />
          </span>
          upv-auto
        </span>
        {/* Keyed by phase so each step (loading → sign-in → credentials) gets
            its own short settle instead of jumping straight to the next. */}
        <div className="authgate-step" key={state.phase}>
          {state.phase === "loading" && (
            <p className="authgate-hint authgate-loading">
              <span className="spin">
                <Refresh size={14} />
              </span>
              Cargando…
            </p>
          )}
          {state.phase === "signed-out" && <SignIn />}
          {state.phase === "needs-credentials" && (
            <CredentialsForm onSaved={() => setState({ phase: "ready" })} />
          )}
        </div>
      </div>
      <div className="authgate-theme">
        <ThemeToggle />
      </div>
    </div>
  );
}
