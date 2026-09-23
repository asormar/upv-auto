// Realtime-driven refresh state (schedule-refresh spec). Subscribes to the
// signed-in user's own `refresh_requests` rows so the existing `refreshing`
// loading UI (`App.tsx`) can stay accurate for the ~1-2 min `refresh.yml`
// takes, without polling. Also fires the sign-in throttled refresh once per
// session and exposes the manual, rate-limited trigger the "Actualizar
// tabla" button already calls. The loading state's visual design is out of
// scope for this change (a later pass); this hook only owns whether a
// refresh is pending and why the last one failed or was rejected.

import { useCallback, useEffect, useRef, useState } from "react";
import { BACKEND } from "../api";
import {
  getLatestRefreshRequest,
  onAuthStateChange,
  requestRefresh,
  subscribeToRefreshRequests,
  type RefreshRequestRow,
} from "./supabase";

export interface RefreshStatus {
  /** True while a refresh is pending for the current user; drives the
   * existing `refreshing` loading UI in `App.tsx`. */
  pending: boolean;
  /** Spanish message for the last rate-limit/throttle rejection or failure, if any. */
  message: string | null;
  /** The manual "Actualizar tabla" button: rate-limited server-side (schedule-refresh
   * spec's "Manual Refresh Rate Limiting"). */
  triggerManualRefresh: () => Promise<void>;
}

/** Spanish copy for a `refresh_requests.error_code` a finished request may
 * carry (`app.refresh_user`'s `finish_request` codes and `claim_refresh`'s
 * own `expired`). Unrecognized codes fall back to a generic message. */
const DONE_ERRORS: Record<string, string> = {
  credentials_unavailable: "No se pudieron leer tus credenciales guardadas. Vuelve a introducirlas.",
  fetch_failed: "No se pudo obtener tu horario de la UPV. Se volverá a intentar más tarde.",
  error: "Ha ocurrido un error inesperado al actualizar tu horario.",
  expired: "La solicitud de actualización caducó. Pulsa Actualizar de nuevo.",
  dispatch_failed: "No se pudo iniciar la actualización. Inténtalo de nuevo en unos minutos.",
};

/**
 * @param onRefreshed called every time a pending refresh finishes
 * successfully, so the caller can reload the cached schedule.
 */
export function useRefreshStatus(onRefreshed: () => void): RefreshStatus {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const onRefreshedRef = useRef(onRefreshed);
  onRefreshedRef.current = onRefreshed;
  const signInFiredRef = useRef(false);

  const handleRow = useCallback((row: RefreshRequestRow) => {
    if (row.status === "pending") {
      setPending(true);
      return;
    }
    setPending(false);
    if (row.status === "failed") {
      setMessage(DONE_ERRORS[row.error_code ?? ""] ?? "No se pudo actualizar tu horario.");
      return;
    }
    setMessage(null);
    onRefreshedRef.current();
  }, []);

  useEffect(() => {
    if (BACKEND === "local") return;
    let cancelled = false;
    let unsubscribeChannel: (() => void) | null = null;

    // `onAuthStateChange` fires immediately with the current session (or
    // `null`), so this both seeds the initial state and reacts to sign-out.
    const unsubscribeAuth = onAuthStateChange((session) => {
      unsubscribeChannel?.();
      unsubscribeChannel = null;

      if (!session) {
        signInFiredRef.current = false;
        setPending(false);
        return;
      }

      unsubscribeChannel = subscribeToRefreshRequests(session.user.id, handleRow);

      // A refresh may already have been pending before this page loaded
      // (e.g. the manual button was clicked, then the tab was closed) —
      // the Realtime subscription above only sees *changes* from now on,
      // so seed the current state with one read.
      void getLatestRefreshRequest()
        .then((row) => {
          if (!cancelled && row) handleRow(row);
        })
        .catch(() => {
          // Best-effort seed only; the subscription above still catches
          // the next change regardless.
        });

      // Sign-in triggered refresh (schedule-refresh spec's "Sign-In
      // Triggered Refresh"), fired once per signed-in session.
      // `claim_refresh` throttles this server-side (6h since the last
      // successful refresh), so a throttled response is silent, not an
      // error — the cached schedule is served as-is either way.
      if (!signInFiredRef.current) {
        signInFiredRef.current = true;
        // Optimistic: the loading state starts with the click-equivalent
        // (signing in), not when the Edge Function answers a second later.
        setPending(true);
        void requestRefresh("signin")
          .then(({ dispatched }) => {
            // Throttled sign-in: no run will ever report back, so stop
            // showing a load that is not happening.
            if (!dispatched) setPending(false);
          })
          .catch(() => {
            // Offline or the Edge Function is unreachable: keep the cached
            // schedule (schedule-refresh spec's "Cached Schedule Served").
            setPending(false);
          });
      }
    });

    return () => {
      cancelled = true;
      unsubscribeChannel?.();
      unsubscribeAuth();
    };
  }, [handleRow]);

  const triggerManualRefresh = useCallback(async () => {
    setMessage(null);
    // Feedback belongs to the click, not to the round trip: invoking the
    // Edge Function (which calls GitHub) takes a noticeable moment, and a
    // button that does nothing meanwhile reads as broken.
    setPending(true);
    try {
      await requestRefresh("manual");
    } catch (cause) {
      setPending(false);
      setMessage(cause instanceof Error ? cause.message : String(cause));
    }
  }, []);

  return { pending, message, triggerManualRefresh };
}
