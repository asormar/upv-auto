import { useEffect, useState, type ReactNode } from "react";
import type { Friend } from "../api";
import { Avatar } from "./Avatar";

const CONFIRM_MS = 4000;

/**
 * One person with the actions that fit their relation to the user.
 *
 * `entering` is read once, when the row mounts: a row that was already there
 * when the list opened never animates, and one that shows up afterwards
 * (a remote request, the user's own action) rises into place.
 */
export function FriendRow({
  friend,
  entering,
  highlighted,
  stacked,
  children,
}: {
  friend: Friend;
  entering: boolean;
  highlighted: boolean;
  /** Two actions: on a narrow screen they take a line of their own. */
  stacked?: boolean;
  children: ReactNode;
}) {
  const [enter] = useState(entering);
  return (
    <li className={`fd-row${enter ? " enter" : ""}${highlighted ? " hl" : ""}${stacked ? " stacked" : ""}`}>
      <Avatar name={friend.alias} src={friend.avatar} size={36} />
      <span className="fd-alias" title={friend.alias}>
        {friend.alias}
      </span>
      <span className="fd-actions">{children}</span>
    </li>
  );
}

/** Accept (the likely answer) and decline an incoming request. */
export function RequestActions({
  alias,
  disabled,
  onAccept,
  onDecline,
}: {
  alias: string;
  disabled: boolean;
  onAccept: () => void;
  onDecline: () => void;
}) {
  return (
    <>
      <button
        className="cta sm press"
        type="button"
        disabled={disabled}
        onClick={onAccept}
        aria-label={`Aceptar a ${alias}`}
      >
        Aceptar
      </button>
      <button
        className="cta sm ghost press"
        type="button"
        disabled={disabled}
        onClick={onDecline}
        aria-label={`Rechazar a ${alias}`}
      >
        Rechazar
      </button>
    </>
  );
}

/** Withdraws a request the user sent. */
export function CancelButton({
  alias,
  disabled,
  onCancel,
}: {
  alias: string;
  disabled: boolean;
  onCancel: () => void;
}) {
  return (
    <button
      className="cta sm ghost press"
      type="button"
      disabled={disabled}
      onClick={onCancel}
      aria-label={`Cancelar la solicitud a ${alias}`}
    >
      Cancelar
    </button>
  );
}

/** Removing a friend cannot be undone, so the first press only asks. */
export function RemoveButton({
  alias,
  disabled,
  onConfirm,
}: {
  alias: string;
  disabled: boolean;
  onConfirm: () => void;
}) {
  const [asking, setAsking] = useState(false);

  // Walking away from the question cancels it. Touch browsers may not blur a
  // tapped button, hence the timer as well.
  useEffect(() => {
    if (!asking) return;
    const timer = window.setTimeout(() => setAsking(false), CONFIRM_MS);
    return () => window.clearTimeout(timer);
  }, [asking]);

  return (
    <>
      {/* The app has no separate danger colour; the filled style, against the
          ghost one it replaces, is what says this press is the real one. */}
      <button
        className={`cta sm press${asking ? "" : " ghost"}`}
        type="button"
        disabled={disabled}
        onBlur={() => setAsking(false)}
        onClick={() => (asking ? onConfirm() : setAsking(true))}
        aria-label={asking ? `Confirmar: eliminar a ${alias}` : `Eliminar a ${alias}`}
      >
        {asking ? "Sí, eliminar" : "Eliminar"}
      </button>
      <span className="visually-hidden" role="status">
        {asking ? `¿Seguro? Pulsa de nuevo para eliminar a ${alias}.` : ""}
      </span>
    </>
  );
}
