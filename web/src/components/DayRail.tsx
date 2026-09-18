import type { Slot } from "../api";
import { Check, Minus, Plus } from "./icons";

interface Props {
  slots: Slot[];
  busy: boolean;
  limitReached: boolean;
  onToggle: (slot: Slot) => void;
}

function describe(slot: Slot): string {
  if (slot.queued) {
    const base = slot.is_alternative
      ? `Alternativa de la reserva ${slot.priority} · ${slot.code}`
      : `En la cola del sábado · ${slot.code}`;
    // The UPV table has no week marker, so an enrolment shown here is the
    // current week's, never next week's.
    return slot.state === "ENROLLED" ? `${base} · ya la tienes esta semana` : base;
  }
  if (slot.state === "ENROLLED") return `Inscrito esta semana · ${slot.code}`;
  if (slot.state === "BOOKABLE") {
    const places = slot.free_places ?? 0;
    return `${slot.code} · ${places} ${places === 1 ? "plaza libre" : "plazas libres"}`;
  }
  if (slot.state === "FULL") return `${slot.code} · completo ahora mismo`;
  return `${slot.code} · sin plazo abierto`;
}

export function DayRail({ slots, busy, limitReached, onToggle }: Props) {
  if (slots.length === 0) {
    return (
      <p style={{ color: "var(--muted)", fontSize: 15 }}>
        Este día no tiene grupos en la tabla de la UPV.
      </p>
    );
  }

  return (
    <div className="rail">
      {slots.map((slot) => {
        const open = slot.state === "BOOKABLE";
        const mine = slot.queued;
        const tone = mine
          ? "mine"
          : slot.state === "ENROLLED"
            ? "enrolled"
            : open
              ? "open"
              : "dim";
        const blocked = !mine && limitReached;

        return (
          <div className={`slot ${tone}`} key={slot.code}>
            <span className="hour num">{slot.time.split("-")[0]}</span>
            <span className="node" />
            <div className="block">
              <span style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
                <span className="when num">{slot.time}</span>
                <span className="detail">{describe(slot)}</span>
              </span>
              <span className="actions">
                {slot.state === "ENROLLED" && (
                  <span
                    className="tag-enrolled"
                    title="Es tu plaza de la semana en curso: la UPV no distingue semanas"
                  >
                    <Check size={14} /> Inscrito esta semana
                  </span>
                )}
                {open && !mine && (
                  // Not built yet: enrolling for the *current* week goes
                  // through UPV's own booking link, which the bot only
                  // follows on Saturday. Shown disabled so the button never
                  // promises something it does not do.
                  <button className="cta ghost" disabled title="Próximamente">
                    Inscribirse ya
                  </button>
                )}
                <button
                  // The strong accent is for hours you can actually take now;
                  // queueing a full hour is still allowed, just quieter.
                  className={`cta press ${mine || !open ? "ghost" : ""}`.trim()}
                  onClick={() => onToggle(slot)}
                  disabled={busy || blocked}
                  title={
                    blocked ? "Has llegado al límite de la UPV para esta actividad" : undefined
                  }
                >
                  {mine ? <Minus /> : <Plus />}
                  {mine
                    ? "Quitar"
                    : slot.state === "ENROLLED"
                      ? "Reservar de nuevo"
                      : "Reservar"}
                </button>
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
