import NumberFlow from "@number-flow/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getConfig,
  getSchedule,
  putBookings,
  type Booking,
  type Config,
  type Schedule,
  type Slot,
} from "./api";
import { DayRail } from "./components/DayRail";
import { QueuePanel } from "./components/QueuePanel";
import { QueuePanelSkeleton } from "./components/QueuePanelSkeleton";
import { ThemeToggle } from "./components/ThemeToggle";
import { WeekBar } from "./components/WeekBar";
import { Alert, Clock, Refresh, Shield } from "./components/icons";
import { describeActivity } from "./activity";
import { NextRun } from "./components/NextRun";

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [dayIndex, setDayIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justAdded, setJustAdded] = useState(false);
  const [justRemoved, setJustRemoved] = useState(false);

  const load = useCallback(async (refresh = false) => {
    setError(null);
    try {
      const [nextConfig, nextSchedule] = await Promise.all([getConfig(), getSchedule(refresh)]);
      setConfig(nextConfig);
      setSchedule(nextSchedule);
      return nextSchedule;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      return null;
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Start on the first day that already holds something of yours.
  useEffect(() => {
    if (!schedule) return;
    const mine = schedule.days.findIndex((day) => day.slots.some((slot) => slot.queued));
    setDayIndex(mine >= 0 ? mine : 0);
  }, [schedule?.fetched_at]);

  const bookings = config?.bookings ?? [];
  const queuedCodes = useMemo(
    () => new Set(bookings.flatMap((booking) => [booking.group_code, ...booking.alternatives])),
    [bookings],
  );

  const save = async (next: Booking[], added: boolean) => {
    setBusy(true);
    setError(null);
    const previous = config;
    if (config) setConfig({ ...config, bookings: next });
    try {
      const saved = await putBookings(next);
      setConfig((current) => (current ? { ...current, bookings: saved.bookings } : current));
      await load();
      // Long enough for the bubble's ring (10) or drain (10b) to finish.
      if (added) {
        setJustAdded(true);
        window.setTimeout(() => setJustAdded(false), 450);
      } else {
        setJustRemoved(true);
        window.setTimeout(() => setJustRemoved(false), 400);
      }
    } catch (cause) {
      setConfig(previous);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const toggleSlot = (slot: Slot) => {
    if (queuedCodes.has(slot.code)) {
      void save(
        bookings
          .filter((booking) => booking.group_code !== slot.code)
          .map((booking) => ({
            ...booking,
            alternatives: booking.alternatives.filter((code) => code !== slot.code),
          })),
        false,
      );
      return;
    }
    void save([...bookings, { group_code: slot.code, alternatives: [] }], true);
  };

  const removeBooking = (groupCode: string) =>
    void save(
      bookings.filter((booking) => booking.group_code !== groupCode),
      false,
    );

  const refresh = async () => {
    setRefreshing(true);
    await load(true);
    setRefreshing(false);
  };

  const day = schedule?.days[dayIndex];
  const limits = schedule?.limits;
  const limitReached = limits ? limits.queued >= limits.max_per_activity : false;
  const nextRun = config ? (
    <NextRun weekday={config.window.weekday} opensAt={config.window.opens_at} />
  ) : (
    "Cargando…"
  );

  return (
    <div className="shell">
      {schedule?.demo && (
        <div className="demobar">
          <Alert />
          <span>
            <strong>Datos de ejemplo.</strong> Esto es la tabla de prueba del proyecto, no tu
            cuenta de la UPV. Arranca sin <code>--demo</code> para ver tus grupos reales.
          </span>
        </div>
      )}
      <header className="topbar">
        <span className="brand">
          <span className="mark">
            <Clock />
          </span>
          upv-auto
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button className="cta ghost press desktop-only" onClick={refresh} disabled={refreshing}>
            <span className={refreshing ? "spin" : undefined}>
              <Refresh />
            </span>
            {refreshing ? "Actualizando…" : "Actualizar tabla"}
          </button>
          {error ? (
            <span className="status warn">
              <Alert /> {error}
            </span>
          ) : (
            <span className="status">
              <Shield /> Conectado a la UPV
            </span>
          )}
          <ThemeToggle />
        </span>
      </header>

      <section style={{ display: "flex", flexDirection: "column", gap: 20, minWidth: 0 }}>
        {/* The week bar already names the day, so the heading names the activity. */}
        <h1 className="page-title">
          {schedule ? describeActivity(schedule.activity) : "Cargando…"}
        </h1>

        <WeekBar days={schedule?.days ?? []} activeIndex={dayIndex} onSelect={setDayIndex} />

        {schedule ? (
          <DayRail
            slots={day?.slots ?? []}
            busy={busy}
            limitReached={limitReached}
            onToggle={toggleSlot}
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {Array.from({ length: 6 }, (_, index) => (
              <div className="skeleton" key={index} />
            ))}
          </div>
        )}
      </section>

      {limits && config ? (
        <QueuePanel
          bookings={bookings}
          days={schedule?.days ?? []}
          limits={limits}
          nextRun={nextRun}
          busy={busy}
          emailNotifications={config.email_notifications}
          justAdded={justAdded}
          justRemoved={justRemoved}
          onRemove={removeBooking}
        />
      ) : (
        <QueuePanelSkeleton />
      )}

      <div className="mobilebar">
        <span style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 15, fontWeight: 600 }}>
            {/* 8 · The count rolls to its new value. */}
            <NumberFlow value={bookings.length} />{" "}
            {bookings.length === 1 ? "reserva" : "reservas"}
          </span>
          <span style={{ fontSize: 12, color: "var(--muted)" }}>{nextRun}</span>
        </span>
        <button className="cta press" onClick={refresh} disabled={refreshing}>
          <span className={refreshing ? "spin" : undefined}>
            <Refresh />
          </span>
          Actualizar
        </button>
      </div>
    </div>
  );
}
