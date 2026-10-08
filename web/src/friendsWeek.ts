// Lays friends' preferred groups out on the week table, and finds which of
// them share an hour with the user. Pure: no I/O, no framework.
//
// A friend's queue is just group codes; the day and time of each come from the
// same `Day[]` the agenda renders, so the table can never disagree with it.

import type { Booking, Day, Friend } from "./api/types";
import { dayRank } from "./scheduleView";

/** Monday to Friday: the only columns the table has. */
export const WEEKDAYS = 5;

/** A stretch of the day, in minutes since midnight. */
export interface Range {
  start: number;
  end: number;
}

export interface FriendRow {
  id: string;
  alias: string;
  avatar: string | null;
  /** One list of ranges per weekday, Monday first. */
  cells: Range[][];
}

interface Placement extends Range {
  weekday: number;
}

const TIME = /^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$/;

function parseTime(time: string): Range | null {
  const match = TIME.exec(time.trim());
  if (!match) return null;
  const start = Number(match[1]) * 60 + Number(match[2]);
  const end = Number(match[3]) * 60 + Number(match[4]);
  return end > start ? { start, end } : null;
}

/** "12:30" for 750. */
export function formatTime(minutes: number): string {
  const hours = String(Math.floor(minutes / 60)).padStart(2, "0");
  return `${hours}:${String(minutes % 60).padStart(2, "0")}`;
}

/** Where each group code falls in the week; weekend and unreadable slots are left out. */
function placements(days: Day[]): Map<string, Placement> {
  const byCode = new Map<string, Placement>();
  for (const day of days) {
    const weekday = dayRank(day.name);
    if (weekday >= WEEKDAYS) continue;
    for (const slot of day.slots) {
      const range = parseTime(slot.time);
      if (range && !byCode.has(slot.code)) byCode.set(slot.code, { ...range, weekday });
    }
  }
  return byCode;
}

/** Sorts and joins ranges that touch or overlap: 12:30-13:30 + 13:30-14:30 is one stretch. */
function merge(ranges: Range[]): Range[] {
  const merged: Range[] = [];
  for (const range of [...ranges].sort((a, b) => a.start - b.start)) {
    const last = merged[merged.length - 1];
    if (last && range.start <= last.end) last.end = Math.max(last.end, range.end);
    else merged.push({ ...range });
  }
  return merged;
}

function weekOf(codes: string[], where: Map<string, Placement>): Range[][] {
  const perDay: Range[][] = Array.from({ length: WEEKDAYS }, () => []);
  for (const code of codes) {
    const found = where.get(code);
    if (found) perDay[found.weekday].push({ start: found.start, end: found.end });
  }
  return perDay.map(merge);
}

/** The accepted friends, each with the hours their queue holds, per weekday. */
export function buildFriendRows(friends: Friend[], days: Day[]): FriendRow[] {
  const where = placements(days);
  return friends
    .filter((friend) => friend.relation === "friend")
    .map((friend) => ({
      id: friend.id,
      alias: friend.alias,
      avatar: friend.avatar,
      cells: weekOf(friend.group_codes, where),
    }));
}

/** Whether the row holds at least one hour. */
export function hasBookings(row: FriendRow): boolean {
  return row.cells.some((ranges) => ranges.length > 0);
}

/**
 * The friends who share a weekday and an overlapping time with the user's own
 * preferred groups. Alternatives are ignored: they are a fallback, not a plan.
 */
export function coincidingFriends(rows: FriendRow[], days: Day[], bookings: Booking[]): FriendRow[] {
  const mine = weekOf(
    bookings.map((booking) => booking.group_code),
    placements(days),
  );
  return rows.filter((row) =>
    row.cells.some((theirs, weekday) =>
      theirs.some((a) => mine[weekday].some((b) => a.start < b.end && b.start < a.end)),
    ),
  );
}
