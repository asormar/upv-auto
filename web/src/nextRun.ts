import { DEFAULT_TIMEZONE, zonedInstant, zonedParts } from "./zone";

const WEEKDAYS: Record<string, number> = {
  sunday: 0,
  monday: 1,
  tuesday: 2,
  wednesday: 3,
  thursday: 4,
  friday: 5,
  saturday: 6,
};

const DAY_NAMES = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/**
 * The next moment the booking window opens, or null if the config can't be
 * read. `weekday` and `opensAt` are wall-clock in `timeZone` (the UPV's), not
 * the browser's.
 */
export function nextRunAt(
  weekday: string,
  opensAt: string,
  now: Date = new Date(),
  timeZone: string = DEFAULT_TIMEZONE,
): Date | null {
  const target = WEEKDAYS[weekday.toLowerCase()];
  const [hours, minutes = 0, seconds = 0] = opensAt.split(":").map(Number);
  if (target === undefined || Number.isNaN(hours)) return null;

  const today = zonedParts(now, timeZone);
  const at = (ahead: number) =>
    zonedInstant(timeZone, today.year, today.month, today.day + ahead, hours, minutes, seconds);

  const ahead = (target - today.weekday + 7) % 7;
  const next = at(ahead);
  return ahead === 0 && next <= now ? at(7) : next;
}

/** "Sábado 19 sep, 10:01", read in `timeZone` (the UPV's). */
export function formatRunDay(date: Date, timeZone: string = DEFAULT_TIMEZONE): string {
  const p = zonedParts(date, timeZone);
  const time = `${String(p.hour).padStart(2, "0")}:${String(p.minute).padStart(2, "0")}`;
  return `${DAY_NAMES[p.weekday]} ${p.day} ${MONTHS[p.month - 1]}, ${time}`;
}

export interface Remaining {
  hours: number;
  minutes: number;
  seconds: number;
}

/** Hours are not folded into days, so it reads as one countdown: 70:45:53. */
export function splitRemaining(milliseconds: number): Remaining {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  return {
    hours: Math.floor(total / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60,
  };
}
