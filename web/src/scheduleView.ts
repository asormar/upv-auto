// Shapes the cached raw groups into the day-grouped view `App.tsx` renders.
//
// Behavior-identical port (task 5.3) of `adapters/web/schedule_view.py`'s
// `build_days`/`count_queued`/`count_enrolled_now`: same day/time ordering,
// the same queue-position rule (a booking's preferred code counts as
// position N; its alternatives share that position and are marked
// `is_alternative`; alternatives never add to the count), and the same
// "current week" enrolled count. Pure: no I/O, no framework.

import type { Booking, Day, RawGroups, Slot } from "./api/types";

// Weekday order of the UPV table, in both languages it is served in.
const DAY_ORDER: Record<string, number> = {
  lunes: 0,
  dilluns: 0,
  martes: 1,
  dimarts: 1,
  miercoles: 2,
  "miércoles": 2,
  dimecres: 2,
  jueves: 3,
  dijous: 3,
  viernes: 4,
  divendres: 4,
  sabado: 5,
  "sábado": 5,
  dissabte: 5,
  domingo: 6,
  diumenge: 6,
};

export const UNKNOWN_DAY = "Sin día";

function compareStrings(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function dayRank(name: string): number {
  return DAY_ORDER[name.trim().toLowerCase()] ?? 99;
}

function timeRank(time: string | null | undefined): [number, number] {
  if (!time) return [99, 99];
  const start = (time.split("-")[0] ?? "").trim();
  const [hoursText, minutesText] = start.split(":");
  const hours = Number(hoursText);
  const minutes = Number(minutesText);
  if (!Number.isInteger(hours) || !Number.isInteger(minutes)) return [99, 99];
  return [hours, minutes];
}

function compareRanks(a: [number, number], b: [number, number]): number {
  return a[0] - b[0] || a[1] - b[1];
}

/** Where `code` sits in the configured queue: [booking number, is alternative]. */
function queuePosition(code: string, bookings: Booking[]): [number, boolean] | null {
  for (let index = 0; index < bookings.length; index += 1) {
    const target = bookings[index];
    const optionIndex = [target.group_code, ...target.alternatives].indexOf(code);
    if (optionIndex !== -1) return [index + 1, optionIndex > 0];
  }
  return null;
}

/** Group the cached raw table into ordered days of ordered slots. */
export function buildDays(groups: RawGroups, bookings: Booking[]): Day[] {
  const byDay = new Map<string, Slot[]>();
  for (const code of Object.keys(groups).sort(compareStrings)) {
    const group = groups[code];
    const day = group.day || UNKNOWN_DAY;
    const position = queuePosition(code, bookings);
    const slot: Slot = {
      code,
      time: group.time ?? "",
      state: group.state,
      free_places: group.free_places,
      queued: position !== null,
      priority: position ? position[0] : null,
      is_alternative: position ? position[1] : false,
    };
    const slots = byDay.get(day);
    if (slots) slots.push(slot);
    else byDay.set(day, [slot]);
  }

  return [...byDay.keys()]
    .sort((a, b) => dayRank(a) - dayRank(b) || compareStrings(a, b))
    .map((day) => ({
      name: day,
      slots: [...(byDay.get(day) ?? [])].sort(
        (a, b) => compareRanks(timeRank(a.time), timeRank(b.time)) || compareStrings(a.code, b.code),
      ),
    }));
}

/** How many places next Saturday's run would secure: one per booking.
 *
 * Alternatives do not add up: within a booking only one of them is taken.
 */
export function countQueued(bookings: Booking[]): number {
  return bookings.length;
}

/** How many groups the cached table already shows as enrolled.
 *
 * That is the *current* week — the UPV page has no week marker — so it
 * never counts towards what Saturday will book.
 */
export function countEnrolledNow(groups: RawGroups): number {
  return Object.values(groups).filter((group) => group.state === "ENROLLED").length;
}
