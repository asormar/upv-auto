import { useEffect, useState } from "react";

const MINUTE_MS = 60_000;

/**
 * The current time, refreshed once a minute on the minute and the moment the
 * tab becomes visible again (a hidden tab's timers are throttled, so a page
 * left open overnight would otherwise wake up with yesterday's clock).
 * Coarse on purpose: for what changes by day or by weekly run, not a countdown.
 */
export function useClock(): Date {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    let timer: number | undefined;
    const schedule = () => {
      window.clearTimeout(timer);
      // A beat past the boundary, so the minute has really turned.
      timer = window.setTimeout(() => {
        setNow(new Date());
        schedule();
      }, MINUTE_MS - (Date.now() % MINUTE_MS) + 50);
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        setNow(new Date());
        schedule();
      } else {
        window.clearTimeout(timer);
      }
    };
    if (document.visibilityState === "visible") schedule();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return now;
}
