// Completes the UPV table's days into the week the queue will actually book.
//
// The UPV table is the *current* week and drops a weekday that is a holiday,
// so it can neither show next week's holiday nor keep the empty weekday. The
// calendar below fills both gaps.

import type { Booking, Day } from "./api/types";
import { buildDays, dayRank } from "./scheduleView";
import { typicalGroups } from "./typicalWeek";
import { DEFAULT_TIMEZONE, zonedParts } from "./zone";

const WEEKDAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"];

/**
 * Holidays that close the sports service, keyed by calendar date (YYYY-MM-DD).
 *
 * Valencian public holidays only: UPV-specific closures are not listed. Add
 * the next year's once its calendar is published.
 */
const HOLIDAYS: Record<string, string> = {
  "2026-10-09": "Día de la Comunitat Valenciana",
  "2026-10-12": "Fiesta Nacional de España",
  "2026-12-08": "Inmaculada Concepción",
  "2026-12-25": "Navidad",
  "2027-01-01": "Año Nuevo",
  "2027-01-06": "Epifanía del Señor",
};

// Calendar dates are handled as midnight UTC of that date ("floating": the
// instant means nothing, only year/month/day do), so neither the browser's
// timezone nor its DST changes can shift them. Hence the UTC getters and the
// UTC formatter.
const LONG_DATE = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "long", timeZone: "UTC" });

function isoDate(date: Date): string {
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${date.getUTCFullYear()}-${month}-${day}`;
}

function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setUTCDate(result.getUTCDate() + days);
  return result;
}

/** The calendar date `instant` falls on in `timeZone`, as a floating date. */
function calendarDay(instant: Date, timeZone: string): Date {
  const { year, month, day } = zonedParts(instant, timeZone);
  return new Date(Date.UTC(year, month - 1, day));
}

function mondayOf(instant: Date, timeZone: string): Date {
  const day = calendarDay(instant, timeZone);
  return addDays(day, -((day.getUTCDay() + 6) % 7));
}

/** The Monday after the run: the week the queue books. */
function bookedMonday(nextRun: Date, timeZone: string): Date {
  const day = calendarDay(nextRun, timeZone);
  return addDays(day, (8 - day.getUTCDay()) % 7 || 7);
}

/**
 * Monday to Friday of the booked week, in order, then any weekend day the
 * table carries.
 *
 * A weekday is kept when it has groups, and added when the calendar explains
 * it: it is a holiday of the booked week (`closed`, empty), or it is a
 * holiday of the week the table shows, so the UPV left it out and its usual
 * groups stand in (`typical`).
 *
 * "Today" and the run day are read in `timeZone` (the UPV's), not the browser's.
 */
export function completeWeek(
  days: Day[],
  nextRun: Date | null,
  codacti: string,
  bookings: Booking[],
  now: Date = new Date(),
  timeZone: string = DEFAULT_TIMEZONE,
): Day[] {
  if (!nextRun) return days;
  const booked = bookedMonday(nextRun, timeZone);
  const shown = mondayOf(now, timeZone);

  const weekdays = WEEKDAY_NAMES.flatMap((name, index): Day[] => {
    const found = days.find((day) => dayRank(day.name) === index);
    const bookedDate = addDays(booked, index);
    const closedBy = HOLIDAYS[isoDate(bookedDate)];
    const hiddenBy = HOLIDAYS[isoDate(addDays(shown, index))];
    const base: Day = found ?? { name, slots: [] };

    if (closedBy) {
      return [
        {
          ...base,
          closed: true,
          notice: `El ${name.toLowerCase()} ${LONG_DATE.format(bookedDate)} es festivo (${closedBy}): no hay sesiones y no se puede reservar.`,
        },
      ];
    }
    if (!found && hiddenBy) {
      const raw = typicalGroups(codacti, index, name);
      const usual = raw ? (buildDays(raw, bookings)[0]?.slots ?? []) : [];
      const why = `la UPV oculta este ${name.toLowerCase()} por el festivo (${hiddenBy})`;
      return [
        {
          ...base,
          slots: usual,
          typical: usual.length > 0,
          notice:
            usual.length > 0
              ? `Horarios habituales del ${name.toLowerCase()}: ${why}. Las plazas se abren el sábado, así que aún no se puede ver su disponibilidad.`
              : `Aún no hay grupos del ${name.toLowerCase()}: ${why} y no vuelven a su tabla hasta que cambie de semana.`,
        },
      ];
    }
    return found ? [base] : [];
  });

  return [...weekdays, ...days.filter((day) => dayRank(day.name) >= 5)];
}
