import { useEffect, useState, type ReactNode } from "react";
import type { Booking, Day, Limits } from "../api";
import { LimitBubbles } from "./LimitBubbles";
import { Check, Clock, Minus } from "./icons";

interface Props {
  bookings: Booking[];
  days: Day[];
  limits: Limits;
  nextRun: ReactNode;
  busy: boolean;
  emailNotifications: boolean;
  justAdded: boolean;
  justRemoved: boolean;
  onRemove: (groupCode: string) => void;
}

const EXIT_MS = 260;

interface QueueRow {
  booking: Booking;
  rank: number;
  exiting: boolean;
}

/**
 * The rows to draw: current bookings, plus any just removed, kept in place
 * for the length of their exit animation. Removal can come from this panel
 * or from the agenda, so it is derived from the props rather than the click.
 */
function useQueueRows(bookings: Booking[]): QueueRow[] {
  const [rows, setRows] = useState<QueueRow[]>(() =>
    bookings.map((booking, index) => ({ booking, rank: index + 1, exiting: false })),
  );

  useEffect(() => {
    setRows((previous) => {
      const current = new Set(bookings.map((booking) => booking.group_code));
      const next: QueueRow[] = bookings.map((booking, index) => ({
        booking,
        rank: index + 1,
        exiting: false,
      }));
      previous.forEach((row, index) => {
        // Rows already leaving are kept too: the save reply re-sends the
        // bookings while the exit is still playing.
        if (!current.has(row.booking.group_code)) {
          next.splice(Math.min(index, next.length), 0, { ...row, exiting: true });
        }
      });
      return next;
    });
  }, [bookings]);

  useEffect(() => {
    if (!rows.some((row) => row.exiting)) return;
    const timer = window.setTimeout(
      () => setRows((current) => current.filter((row) => !row.exiting)),
      EXIT_MS,
    );
    return () => window.clearTimeout(timer);
  }, [rows]);

  return rows;
}

/** Where a group sits in the week, for showing "Martes · 12:30-13:30". */
function locate(days: Day[], code: string): string {
  for (const day of days) {
    const slot = day.slots.find((candidate) => candidate.code === code);
    if (slot) return `${day.name} · ${slot.time}`;
  }
  return code;
}

export function QueuePanel({
  bookings,
  days,
  limits,
  nextRun,
  busy,
  emailNotifications,
  justAdded,
  justRemoved,
  onRemove,
}: Props) {
  const left = limits.max_per_activity - limits.queued;
  const rows = useQueueRows(bookings);

  return (
    <aside className="panel">
      <div className="card accent">
        <span
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: 14,
            fontWeight: 600,
            color: "var(--accent-ink)",
          }}
        >
          <Clock size={16} /> {nextRun}
        </span>
        <p style={{ margin: "10px 0 0", fontSize: 15, color: "var(--body)", lineHeight: 1.5 }}>
          {bookings.length === 0
            ? "Aún no hay nada en la cola."
            : bookings.length === 1
              ? "Se reservará 1 sesión"
              : `Se reservarán ${bookings.length} sesiones`}
          {emailNotifications ? " Te avisamos por correo del resultado." : ""}
        </p>
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <span style={{ fontSize: 13, color: "var(--muted)" }}>Límite UPV</span>
        <LimitBubbles
          label={limits.max_per_activity === 6 ? "Musculación" : "Esta actividad"}
          used={limits.queued}
          max={limits.max_per_activity}
          highlight={justAdded}
          removed={justRemoved}
        />
        <LimitBubbles
          label="Todas las actividades"
          used={limits.queued}
          max={limits.max_sessions}
          highlight={justAdded}
          removed={justRemoved}
        />
        {left <= 0 && (
          <span style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>
            Has llegado al máximo de esta actividad: quita una para añadir otra.
          </span>
        )}
        {limits.enrolled_this_week > 0 && (
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 12,
              color: "var(--ok)",
              background: "var(--ok-bg)",
              borderRadius: 12,
              padding: "10px 12px",
              lineHeight: 1.45,
            }}
          >
            <Check size={14} />
            <span>
              Esta semana ya estás inscrito en {limits.enrolled_this_week}{" "}
              {limits.enrolled_this_week === 1 ? "sesión" : "sesiones"}
            </span>
          </span>
        )}
      </div>
      <div className="card">
        <h2 style={{ fontSize: 17, fontWeight: 600, paddingBottom: 6 }}>Tu cola</h2>
        {rows.map(({ booking, rank, exiting }) => (
          <div
            className={`queue-row ${exiting ? "exiting" : ""}`.trim()}
            key={booking.group_code}
            aria-hidden={exiting || undefined}
          >
            <div className="queue-clip">
              <div className="queue-item">
                <span className="rank num">{rank}</span>
                <span
                  style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, minWidth: 0 }}
                >
                  <span style={{ fontSize: 15, fontWeight: 600 }}>
                    {locate(days, booking.group_code)}
                  </span>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>
                    {booking.group_code}
                    {booking.alternatives.length > 0
                      ? ` · si está completo: ${booking.alternatives
                          .map((code) => locate(days, code))
                          .join(", ")}`
                      : ""}
                  </span>
                </span>
                <button
                  className="iconbtn press"
                  onClick={() => onRemove(booking.group_code)}
                  disabled={busy || exiting}
                  aria-label={`Quitar ${booking.group_code} de la cola`}
                >
                  <Minus />
                </button>
              </div>
            </div>
          </div>
        ))}
        {rows.length === 0 && (
          <p style={{ margin: 0, fontSize: 14, color: "var(--muted)" }}>
            La cola está vacía.
          </p>
        )}
      </div>

    </aside>
  );
}
