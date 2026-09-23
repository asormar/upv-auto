// Facade: every component keeps importing from "./api". Which backend
// actually runs is picked once, from `VITE_BACKEND` (design.md's "Front
// backend" decision): `"local"` talks to the FastAPI dev server
// (`python -m upv_auto serve[--demo]`); anything else (the default) talks
// to Supabase.

import * as local from "./api/local";
import * as supabaseBackend from "./api/supabase";
import type { Backend, Booking, RefreshTrigger } from "./api/types";

export type {
  Backend,
  Booking,
  Config,
  Day,
  Limits,
  RawGroup,
  RawGroups,
  RefreshTrigger,
  Schedule,
  Slot,
  SlotState,
} from "./api/types";

export const BACKEND: "local" | "supabase" =
  import.meta.env.VITE_BACKEND === "local" ? "local" : "supabase";

const backend: Backend = BACKEND === "local" ? local : supabaseBackend;

export const getConfig = () => backend.getConfig();
export const getSchedule = (refresh = false) => backend.getSchedule(refresh);
export const putBookings = (bookings: Booking[]) => backend.putBookings(bookings);
export const requestRefresh = (trigger: RefreshTrigger) => backend.requestRefresh(trigger);
export const saveCredentials = (username: string, password: string) =>
  backend.saveCredentials(username, password);
export const deleteAccount = () => backend.deleteAccount();

// Auth only exists under the Supabase backend; `AuthGate` never calls these
// when `BACKEND === "local"` (it skips the gate entirely).
export {
  getSession,
  hasCredentials,
  onAuthStateChange,
  signIn,
  signOut,
  signUp,
} from "./api/supabase";
