import { useId, useMemo, useState, type CSSProperties } from "react";
import type { Booking, Day, Friend } from "../api";
import {
  buildFriendRows,
  coincidingFriends,
  formatTime,
  hasBookings,
  type FriendRow,
} from "../friendsWeek";
import { Avatar } from "./Avatar";
import { Chevron } from "./icons";

const STORAGE_KEY = "upv-auto-friends-open";
const MAX_AVATARS = 3;

// Column headers, and the day names a screen reader gets in their place.
const COLUMNS = [
  { short: "L", name: "lunes" },
  { short: "MA", name: "martes" },
  { short: "MI", name: "miércoles" },
  { short: "J", name: "jueves" },
  { short: "V", name: "viernes" },
] as const;

function readOpen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "0";
  } catch {
    return true;
  }
}

function writeOpen(open: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, open ? "1" : "0");
  } catch {
    // Private mode or blocked storage: the choice just is not remembered.
  }
}

/** "Marta", "Marta y Lucía", "Marta, Lucía y 1 más". */
function nameList(rows: FriendRow[]): string {
  const names = rows.map((row) => row.alias);
  if (names.length <= 2) return names.join(" y ");
  const rest = names.length - 2;
  return `${names[0]}, ${names[1]} y ${rest} más`;
}

/**
 * Where the user's accepted friends have booked next week, one row each.
 * Read-only: friends are managed in `FriendsDialog`. Renders nothing until
 * there is at least one.
 */
export function FriendsWeek({
  friends,
  days,
  bookings,
}: {
  friends: Friend[];
  days: Day[];
  bookings: Booking[];
}) {
  const [open, setOpen] = useState(readOpen);
  const bodyId = useId();

  const rows = useMemo(() => buildFriendRows(friends, days), [friends, days]);
  const together = useMemo(() => coincidingFriends(rows, days, bookings), [rows, days, bookings]);

  if (rows.length === 0) return null;

  const booked = rows.filter(hasBookings);
  const shown = (booked.length > 0 ? booked : rows).slice(0, MAX_AVATARS);
  const hidden = (booked.length > 0 ? booked : rows).length - shown.length;

  const toggle = () => {
    writeOpen(!open);
    setOpen(!open);
  };

  return (
    <div className={`card friends${open ? " open" : ""}`}>
      <button
        className="friends-head press"
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={bodyId}
      >
        <span className="fw-avatars">
          {shown.map((row) => (
            <Avatar key={row.id} name={row.alias} src={row.avatar} />
          ))}
          {hidden > 0 && (
            <span className="avatar fw-more" aria-hidden="true">
              +{hidden}
            </span>
          )}
        </span>
        <span className="friends-summary">
          <span className="friends-title">
            {booked.length === 0
              ? "Tus amigos aún no tienen reservas"
              : `${booked.length} ${booked.length === 1 ? "amigo" : "amigos"} con reservas la semana que viene`}
          </span>
          {together.length > 0 && (
            <span className="friends-sub">Coincides con {nameList(together)}</span>
          )}
        </span>
        <span className="friends-chevron">
          <Chevron />
        </span>
      </button>

      <div className="friends-body" id={bodyId}>
        <div className="friends-clip">
          <div
            className="fw-table"
            role="table"
            aria-label="Reservas de tus amigos la semana que viene"
          >
            <div className="fw-row fw-head" role="row">
              {/* Holds the name column's place; absolutely positioned text would not. */}
              <span role="columnheader">
                <span className="visually-hidden">Amigo</span>
              </span>
              {COLUMNS.map((column) => (
                <span key={column.name} role="columnheader" aria-label={column.name}>
                  {column.short}
                </span>
              ))}
            </div>
            {rows.map((row, index) => (
              <div
                className="fw-row fw-friend"
                role="row"
                key={row.id}
                style={{ "--i": Math.min(index, 8) } as CSSProperties}
              >
                <span className="fw-name" role="rowheader" title={row.alias}>
                  <Avatar name={row.alias} src={row.avatar} size={24} />
                  <span className="fw-alias">{row.alias}</span>
                </span>
                {row.cells.map((ranges, weekday) => (
                  <span className="fw-cell" role="cell" key={COLUMNS[weekday].name}>
                    {ranges.length === 0 ? (
                      <span className="fw-bubble empty" aria-hidden="true" />
                    ) : (
                      ranges.map((range) => (
                        <span
                          className="fw-bubble num"
                          role="img"
                          key={range.start}
                          aria-label={`${row.alias}, ${COLUMNS[weekday].name}, de ${formatTime(range.start)} a ${formatTime(range.end)}`}
                        >
                          <span>{formatTime(range.start)}</span>
                          <span>{formatTime(range.end)}</span>
                        </span>
                      ))
                    )}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
