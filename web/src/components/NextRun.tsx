import NumberFlow, { NumberFlowGroup } from "@number-flow/react";
import { useEffect, useState } from "react";
import { formatRunDay, nextRunAt, splitRemaining } from "../nextRun";

interface Props {
  weekday: string;
  opensAt: string;
}

const TWO_DIGITS = { minimumIntegerDigits: 2 } as const;
// The tens of minutes and seconds only reach 5, so 00 → 59 rolls one step
// instead of spinning through 6, 7, 8 and 9.
const SIXTY = { 1: { max: 5 } };

/**
 * "Sábado 19 sep, 10:01 · faltan 70:45:53", ticking every second with the
 * same rolling digits as the booking counters.
 *
 * The tick lives here, not in the page, so only this line re-renders each
 * second. The group keeps the three numbers animating as one.
 */
export function NextRun({ weekday, opensAt }: Props) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const at = nextRunAt(weekday, opensAt, now);
  if (!at) return <>Próxima ejecución: {weekday} {opensAt}</>;

  const { hours, minutes, seconds } = splitRemaining(at.getTime() - now.getTime());

  return (
    <>
      {formatRunDay(at)} · faltan{" "}
      <span
        className="num countdown"
        role="timer"
        aria-label={`${hours} horas, ${minutes} minutos y ${seconds} segundos`}
      >
        <NumberFlowGroup>
          {/* Counting down: every digit rolls the same way. */}
          <NumberFlow value={hours} trend={-1} format={TWO_DIGITS} />
          <NumberFlow value={minutes} trend={-1} format={TWO_DIGITS} digits={SIXTY} prefix=":" />
          <NumberFlow value={seconds} trend={-1} format={TWO_DIGITS} digits={SIXTY} prefix=":" />
        </NumberFlowGroup>
      </span>
    </>
  );
}
