// The usual groups of a weekday, for when the UPV table hides it.
//
// A holiday weekday vanishes from the UPV table, and the groups are not kept
// anywhere else, yet they do not change from week to week. Captured on
// 2026-09-15 (tests/fixtures/activities_musculacion.html): every weekday has
// the same 15 hourly slots, and the group codes run on from day to day, so a
// day is its first code plus the slot number.

import type { RawGroups } from "./api/types";

const MUSCULACION_VERA = "21948";

const TIMES = [
  "07:35-08:30",
  "08:30-09:30",
  "09:30-10:30",
  "10:30-11:30",
  "11:30-12:30",
  "12:30-13:30",
  "13:30-14:30",
  "14:30-15:30",
  "15:30-16:30",
  "16:30-17:30",
  "17:30-18:30",
  "18:30-19:30",
  "19:30-20:30",
  "20:30-21:30",
  "21:30-22:30",
];

/** Number of the first group of Monday to Friday (MUS001, MUS016, …). */
const FIRST_GROUP = [1, 16, 31, 46, 61];

/**
 * The usual groups of weekday `index` (0 = Monday) as raw table rows, or null
 * when this activity has no captured template.
 *
 * They carry no live state: nothing is bookable until the week they belong to
 * opens, so they all read as not open yet.
 */
export function typicalGroups(codacti: string, index: number, day: string): RawGroups | null {
  const first = FIRST_GROUP[index];
  if (codacti !== MUSCULACION_VERA || first === undefined) return null;
  return Object.fromEntries(
    TIMES.map((time, slot) => {
      const code = `MUS${String(first + slot).padStart(3, "0")}`;
      return [code, { code, state: "UNAVAILABLE", free_places: null, day, time }];
    }),
  );
}
