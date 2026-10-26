import { formatClock, type RunPhase } from "../nextRun";
import { Alert, Clock } from "./icons";

/**
 * Tells the user when their edits stop counting for today's run: the batch
 * reads every queue a minute before the window opens, so anything saved after
 * that books next week. Editing stays allowed throughout.
 */
export function RunNotice({ phase, timeZone }: { phase: RunPhase; timeZone: string }) {
  if (phase.kind === "idle") return null;

  if (phase.kind === "frozen") {
    return (
      <p className="authgate-banner run-notice warn" role="status">
        <Alert size={14} />
        <span>
          La reserva de hoy ya está en marcha: los cambios que hagas ahora cuentan para la semana
          que viene.
        </span>
      </p>
    );
  }

  return (
    <p className="authgate-banner run-notice" role="status">
      <Clock size={14} />
      <span>Los cambios hasta las {formatClock(phase.cutoff, timeZone)} cuentan para la reserva de hoy.</span>
    </p>
  );
}
