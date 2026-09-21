// Supabase backend: the multi-user path (default `VITE_BACKEND`). Auth,
// sealed-credential upload, queue CRUD and the cached schedule all go
// through Supabase, under the RLS policies in
// `supabase/migrations/0001_multi_user.sql`.

import { createClient, type SupabaseClient, type Session } from "@supabase/supabase-js";
import type { Backend, Booking, Config, RawGroups, RefreshTrigger, Schedule } from "./types";

// `createClient` validates its URL/key eagerly (throws if either is empty),
// so the client is built lazily on first use rather than at module load.
// This file is still statically imported by the `api.ts` facade even under
// `VITE_BACKEND=local` (the facade re-exports its auth helpers), and local
// mode never configures `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` — only
// a call into one of this module's functions should ever require them.
let client: SupabaseClient | null = null;

function supabase(): SupabaseClient {
  if (client) return client;
  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
  const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error(
      "Faltan las variables VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY. " +
        "Configúralas en web/.env (ver web/.env.example) o usa VITE_BACKEND=local.",
    );
  }
  client = createClient(supabaseUrl, supabaseAnonKey);
  return client;
}

// ---------- auth ----------

function translateAuthError(message: string): string {
  const known: Record<string, string> = {
    "Invalid login credentials": "Correo o contraseña incorrectos.",
    "User already registered": "Ya existe una cuenta con ese correo.",
    "Password should be at least 6 characters": "La contraseña debe tener al menos 6 caracteres.",
    "Unable to validate email address: invalid format": "El correo no tiene un formato válido.",
  };
  return known[message] ?? `No se pudo completar la operación: ${message}`;
}

export async function signUp(email: string, password: string): Promise<void> {
  const { error } = await supabase().auth.signUp({ email, password });
  if (error) throw new Error(translateAuthError(error.message));
}

export async function signIn(email: string, password: string): Promise<void> {
  const { error } = await supabase().auth.signInWithPassword({ email, password });
  if (error) throw new Error(translateAuthError(error.message));
}

export async function signOut(): Promise<void> {
  await supabase().auth.signOut();
}

export async function getSession(): Promise<Session | null> {
  const { data } = await supabase().auth.getSession();
  return data.session;
}

/** Returns an unsubscribe function, mirroring `onAuthStateChange`'s own shape. */
export function onAuthStateChange(callback: (session: Session | null) => void): () => void {
  const {
    data: { subscription },
  } = supabase().auth.onAuthStateChange((_event, session) => callback(session));
  return () => subscription.unsubscribe();
}

export async function hasCredentials(): Promise<boolean> {
  const { data, error } = await supabase()
    .from("upv_credentials")
    .select("user_id")
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data !== null;
}

// ---------- credential custody, refresh, account ----------

export async function saveCredentials(username: string, password: string): Promise<void> {
  const { sealCredentials } = await import("../seal");
  const { sealed, key_id } = await sealCredentials(username, password);

  const {
    data: { user },
  } = await supabase().auth.getUser();
  if (!user) throw new Error("Sesión no iniciada.");

  const { error } = await supabase()
    .from("upv_credentials")
    .upsert({ user_id: user.id, sealed, key_id });
  if (error) throw new Error(error.message);
}

export async function deleteAccount(): Promise<void> {
  const { error } = await supabase().functions.invoke("delete-account", { method: "POST" });
  if (error) throw new Error(error.message);
  await supabase().auth.signOut();
}

// Spanish copy for the `refresh` Edge Function's known `{ error: "<code>" }`
// bodies (schedule-refresh spec: rate limit / throttle messages must reach
// the user in Spanish). `readErrorCode` reads that body from the SDK's
// error context; unrecognized codes fall back to a generic message.
const KNOWN_REFRESH_ERRORS: Record<string, string> = {
  rate_limited: "Has alcanzado el límite de actualizaciones manuales. Inténtalo de nuevo más tarde.",
  unauthorized: "Tu sesión ha caducado. Vuelve a iniciar sesión.",
  dispatch_failed: "No se pudo iniciar la actualización. Inténtalo de nuevo en unos minutos.",
  dispatch_not_configured: "La actualización no está disponible ahora mismo.",
  claim_failed: "No se pudo procesar la solicitud de actualización.",
  invalid_trigger: "No se pudo procesar la solicitud de actualización.",
};

async function readErrorCode(error: unknown): Promise<string | null> {
  const context = (error as { context?: { json?: () => Promise<unknown> } } | null)?.context;
  if (!context?.json) return null;
  try {
    const body = (await context.json()) as { error?: unknown };
    return typeof body.error === "string" ? body.error : null;
  } catch {
    return null;
  }
}

export async function requestRefresh(trigger: RefreshTrigger): Promise<void> {
  const { error } = await supabase().functions.invoke("refresh", { body: { trigger } });
  if (error) {
    const code = await readErrorCode(error);
    const message = (code && KNOWN_REFRESH_ERRORS[code]) ?? `No se pudo actualizar el horario: ${error.message}`;
    throw new Error(message);
  }
}

/** One row of `refresh_requests`, as delivered by Realtime (schedule-refresh
 * spec). Mirrors the table in `supabase/migrations/0001_multi_user.sql`. */
export interface RefreshRequestRow {
  id: string;
  status: "pending" | "done" | "failed";
  error_code: string | null;
  trigger: RefreshTrigger;
}

/**
 * Realtime feed for the signed-in user's own `refresh_requests` rows
 * (schedule-refresh spec's "Visible Loading State During Pending Refresh").
 * RLS already scopes every row to `auth.uid()` server-side; the `user_id`
 * filter here only narrows which changes wake this callback. Returns an
 * unsubscribe function, mirroring `onAuthStateChange`'s own shape.
 */
export function subscribeToRefreshRequests(
  userId: string,
  onChange: (row: RefreshRequestRow) => void,
): () => void {
  const channel = supabase()
    .channel(`refresh_requests:${userId}`)
    .on(
      "postgres_changes",
      { event: "*", schema: "public", table: "refresh_requests", filter: `user_id=eq.${userId}` },
      (payload) => onChange(payload.new as RefreshRequestRow),
    )
    .subscribe();

  return () => {
    void supabase().removeChannel(channel);
  };
}

/** The current user's most recent `refresh_requests` row, if any — used to
 * seed `useRefreshStatus`'s state for a refresh that was already pending
 * before the page loaded (Realtime only reports *changes* from the moment
 * of subscription). */
export async function getLatestRefreshRequest(): Promise<RefreshRequestRow | null> {
  const { data, error } = await supabase()
    .from("refresh_requests")
    .select("id, status, error_code, trigger")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle<RefreshRequestRow>();
  if (error) throw new Error(error.message);
  return data;
}

// ---------- queue + schedule ----------

interface AppSettingsRow {
  settings: Partial<
    Pick<Config, "activity" | "window" | "timezone" | "limits" | "email_notifications">
  >;
}

const DEFAULT_ACTIVITY: Config["activity"] = { name: "", campus: "", tipoact: "", codacti: "" };
const DEFAULT_WINDOW: Config["window"] = {
  weekday: "sabado",
  opens_at: "10:01",
  closes_at: "10:04",
  retry_interval_seconds: 5,
};
const DEFAULT_LIMITS: Config["limits"] = { max_sessions: 10, max_per_activity: 6 };

export async function getConfig(): Promise<Config> {
  const [{ data: settingsRow, error: settingsError }, { data: queueRow, error: queueError }] =
    await Promise.all([
      supabase().from("app_settings").select("settings").eq("id", 1).maybeSingle<AppSettingsRow>(),
      supabase().from("booking_queue").select("bookings").maybeSingle<{ bookings: Booking[] }>(),
    ]);
  if (settingsError) throw new Error(settingsError.message);
  if (queueError) throw new Error(queueError.message);

  const settings = settingsRow?.settings ?? {};
  return {
    activity: settings.activity ?? DEFAULT_ACTIVITY,
    window: settings.window ?? DEFAULT_WINDOW,
    timezone: settings.timezone ?? "Europe/Madrid",
    limits: settings.limits ?? DEFAULT_LIMITS,
    bookings: queueRow?.bookings ?? [],
    email_notifications: settings.email_notifications ?? true,
    demo: false,
  };
}

/** Maps `validate_queue()`'s Postgres exceptions (0001_multi_user.sql) to the
 * same Spanish copy the local FastAPI backend already uses for equivalent
 * checks (see `adapters/web/api.py`'s `write_bookings`). */
function translateQueueError(message: string, maxPerActivity: number): string {
  if (message.includes("exceeds the UPV limit")) {
    return `La UPV permite ${maxPerActivity} sesiones de esta actividad a la vez.`;
  }
  if (message.includes("Duplicate preferred group_code")) {
    return "Hay un grupo repetido en la cola.";
  }
  if (message.includes("Invalid group_code") || message.includes("Invalid alternative")) {
    return "Uno de los códigos de grupo no es válido.";
  }
  return `No se pudo guardar la cola: ${message}`;
}

export async function putBookings(bookings: Booking[]): Promise<{ bookings: Booking[] }> {
  const {
    data: { user },
  } = await supabase().auth.getUser();
  if (!user) throw new Error("Sesión no iniciada.");

  const { data, error } = await supabase()
    .from("booking_queue")
    .upsert({ user_id: user.id, bookings })
    .select("bookings")
    .single<{ bookings: Booking[] }>();

  if (error) {
    const { limits } = await getConfig();
    throw new Error(translateQueueError(error.message, limits.max_per_activity));
  }
  return { bookings: data.bookings };
}

export async function getSchedule(_refresh = false): Promise<Schedule> {
  // `_refresh` is part of the shared `Backend` interface (the local
  // FastAPI backend fetches synchronously with `?refresh=true`), but this
  // backend's refresh is Realtime-driven and 1-2 min long: triggering and
  // awaiting it belongs to `useRefreshStatus.ts` (schedule-refresh spec),
  // not to a schedule read. This always returns the current cached row.
  const [{ data: scheduleRow, error: scheduleError }, config] = await Promise.all([
    supabase()
      .from("schedules")
      .select("groups, fetched_at")
      .maybeSingle<{ groups: RawGroups; fetched_at: string | null }>(),
    getConfig(),
  ]);
  if (scheduleError) throw new Error(scheduleError.message);

  const groups = scheduleRow?.groups ?? {};
  return {
    demo: false,
    fetched_at: scheduleRow?.fetched_at ?? "",
    activity: config.activity,
    limits: {
      ...config.limits,
      queued: config.bookings.length,
      enrolled_this_week: countEnrolledThisWeek(groups),
    },
    // Phase 5 (task 5.3) ports `adapters/web/schedule_view.py`'s `build_days`
    // to `web/src/scheduleView.ts`; until then there is no cached-groups ->
    // day-view conversion here, so the agenda stays empty for the Supabase
    // backend (the queue panel and credential flow above it work today).
    days: [],
  };
}

function countEnrolledThisWeek(groups: RawGroups): number {
  return Object.values(groups).filter((group) => group.state === "ENROLLED").length;
}

// Structural check only: keeps this module's exports in sync with `Backend`.
const _backend: Backend = {
  getConfig,
  getSchedule,
  putBookings,
  requestRefresh,
  saveCredentials,
  deleteAccount,
};
void _backend;
