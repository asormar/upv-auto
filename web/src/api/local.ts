// Local backend: the original single-user FastAPI adapter (`python -m
// upv_auto serve`). Kept working so `serve --demo` and local dev never need
// Supabase configured (`VITE_BACKEND=local`, see design.md's "Front backend"
// decision).

import type { Backend, Booking, Config, RefreshTrigger, Schedule } from "./types";

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

// Local mode has no accounts, so the multi-user-only actions have nothing to
// do. `AuthGate` never renders their UI under `VITE_BACKEND=local` (it skips
// the gate entirely), so these only guard against an unexpected direct call.

export async function requestRefresh(_trigger: RefreshTrigger): Promise<{ dispatched: boolean }> {
  throw new Error("El refresco desde la nube no está disponible en modo local.");
}

export async function saveCredentials(_username: string, _password: string): Promise<void> {
  throw new Error("Guardar credenciales no está disponible en modo local.");
}

export async function deleteAccount(): Promise<void> {
  throw new Error("Eliminar la cuenta no está disponible en modo local.");
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
