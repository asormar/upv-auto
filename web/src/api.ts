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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body) => body.detail as string)
      .catch(() => null);
    throw new Error(detail ?? `Error ${response.status} al hablar con el servidor`);
  }
  return (await response.json()) as T;
}

export const getConfig = () => request<Config>("/api/config");

export const getSchedule = (refresh = false) =>
  request<Schedule>(`/api/schedule${refresh ? "?refresh=true" : ""}`);

export const putBookings = (bookings: Booking[]) =>
  request<{ bookings: Booking[] }>("/api/bookings", {
    method: "PUT",
    body: JSON.stringify({ bookings }),
  });
