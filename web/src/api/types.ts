// Shared types for both backends (`local.ts`, `supabase.ts`) and the
// `api.ts` facade that picks between them via `VITE_BACKEND`.

export type SlotState = "BOOKABLE" | "FULL" | "ENROLLED" | "UNAVAILABLE";

export interface Slot {
  code: string;
  time: string;
  state: SlotState;
  free_places: number | null;
  queued: boolean;
  priority: number | null;
  is_alternative: boolean;
}

export interface Day {
  name: string;
  slots: Slot[];
}

export interface Limits {
  max_sessions: number;
  max_per_activity: number;
  /** Places next Saturday's run would secure. */
  queued: number;
  /** Groups the UPV table already shows as enrolled: the current week. */
  enrolled_this_week: number;
}

export interface Schedule {
  demo: boolean;
  fetched_at: string;
  activity: { name: string; campus: string; tipoact: string; codacti: string };
  limits: Limits;
  days: Day[];
}

export interface Booking {
  group_code: string;
  alternatives: string[];
}

export interface Config {
  activity: { name: string; campus: string; tipoact: string; codacti: string };
  window: { weekday: string; opens_at: string; closes_at: string; retry_interval_seconds: number };
  timezone: string;
  limits: { max_sessions: number; max_per_activity: number };
  bookings: Booking[];
  email_notifications: boolean;
  demo: boolean;
}

/** What triggered a schedule refresh; mirrors `refresh_requests.trigger` (design.md). */
/** "credentials" is the re-check right after saving new UPV credentials:
 * exempt from the manual 5-minute limit, since it is the only way a user can
 * fix a rejected login. */
export type RefreshTrigger = "signin" | "manual" | "credentials";

/**
 * One parsed UPV activity-table cell, as cached in `schedules.groups`
 * (raw, keyed by group code, no `booking_path` — see design.md's Schema
 * section). Mirrors `upv_auto.domain.models.GroupAvailability` minus the
 * `booking_path` field the client never needs.
 */
export interface RawGroup {
  code: string;
  state: SlotState;
  free_places: number | null;
  day: string | null;
  time: string | null;
}

export type RawGroups = Record<string, RawGroup>;

/** Every backend (`local.ts`, `supabase.ts`) implements this shape; `api.ts` dispatches to it. */
export interface Backend {
  getConfig(): Promise<Config>;
  getSchedule(refresh?: boolean): Promise<Schedule>;
  putBookings(bookings: Booking[]): Promise<{ bookings: Booking[] }>;
  /** Resolves to whether a refresh run was actually dispatched: a sign-in
   * inside the throttle window is accepted but dispatches nothing, and the
   * loading state must not linger for a run that will never happen. */
  requestRefresh(trigger: RefreshTrigger): Promise<{ dispatched: boolean }>;
  saveCredentials(username: string, password: string): Promise<void>;
  deleteAccount(): Promise<void>;
}
