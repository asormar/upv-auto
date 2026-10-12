// Wall-clock time in the UPV's timezone, whatever the browser's is.
//
// `Date`'s local getters read the *browser's* zone, so a user outside Madrid
// would see the wrong countdown and the wrong booked week. Everything that
// reasons about "Saturday 10:01" or "today" goes through here instead.

/** Where the UPV (and so the booking window) lives; matches the backend default. */
export const DEFAULT_TIMEZONE = "Europe/Madrid";

export interface ZonedParts {
  year: number;
  /** 1 to 12. */
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
  /** 0 (Sunday) to 6 (Saturday), like `Date.getDay`. */
  weekday: number;
}

const WEEKDAY_INDEX: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatterFor(timeZone: string): Intl.DateTimeFormat {
  let formatter = formatters.get(timeZone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-US", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "numeric",
      second: "numeric",
      weekday: "short",
    });
    formatters.set(timeZone, formatter);
  }
  return formatter;
}

/** The calendar date and clock reading of an instant in `timeZone`. */
export function zonedParts(date: Date, timeZone: string = DEFAULT_TIMEZONE): ZonedParts {
  const read: Record<string, string> = {};
  for (const part of formatterFor(timeZone).formatToParts(date)) read[part.type] = part.value;
  return {
    year: Number(read.year),
    month: Number(read.month),
    day: Number(read.day),
    hour: Number(read.hour),
    minute: Number(read.minute),
    second: Number(read.second),
    weekday: WEEKDAY_INDEX[read.weekday] ?? 0,
  };
}

/** How far `timeZone` is ahead of UTC at this instant, in milliseconds. */
function offsetAt(instant: number, timeZone: string): number {
  const p = zonedParts(new Date(instant), timeZone);
  // Whole seconds only: the formatter drops the milliseconds.
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - Math.floor(instant / 1000) * 1000;
}

/**
 * The instant at which `timeZone`'s wall clock reads this date and time.
 * `day` may overflow the month (day 33 is the 2nd of the next one).
 *
 * The offset is resolved at the *target* moment, not now, so a target on the
 * other side of a DST change gets the right one. A reading that falls in the
 * skipped hour of a spring-forward lands just after the gap.
 */
export function zonedInstant(
  timeZone: string,
  year: number,
  month: number,
  day: number,
  hour = 0,
  minute = 0,
  seconds = 0,
): Date {
  const wall = Date.UTC(year, month - 1, day, hour, minute, seconds);
  // The offset at the wall reading taken as UTC can be off by the DST jump;
  // asking again at the instant that guess gives settles it.
  const guess = wall - offsetAt(wall, timeZone);
  return new Date(wall - offsetAt(guess, timeZone));
}

/** "YYYY-MM-DD" of an instant in `timeZone`. */
export function zonedIsoDate(date: Date, timeZone: string = DEFAULT_TIMEZONE): string {
  const p = zonedParts(date, timeZone);
  return `${p.year}-${String(p.month).padStart(2, "0")}-${String(p.day).padStart(2, "0")}`;
}
