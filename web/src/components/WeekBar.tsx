import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import type { Day } from "../api";

interface Props {
  days: Day[];
  activeIndex: number;
  onSelect: (index: number) => void;
}

/** How far the dark copy is clipped from each side, in px. */
interface Clip {
  left: number;
  right: number;
}

// Leading edge leaves first, trailing edge follows: the pill stretches across
// both days, then gathers into the new one.
const EDGE_MS = 340;
const TRAIL_DELAY_MS = 120;

function note(day: Day): string {
  const mine = day.slots.filter((slot) => slot.queued).length;
  if (mine > 0) return `${mine} ${mine === 1 ? "reserva" : "reservas"}`;
  const open = day.slots.filter((slot) => slot.state === "BOOKABLE").length;
  return `${open} ${open === 1 ? "hueco" : "huecos"}`;
}

/**
 * Day selector with an elastic active pill.
 *
 * A second, fully "active" copy of the strip sits on top and is clipped down
 * to the selected day. Moving the clip's two edges on different timings makes
 * the pill slide out of the current day while it fills the next one, and the
 * label colours change exactly where the clip passes — something separate
 * colour transitions cannot line up.
 */
export function WeekBar({ days, activeIndex, onSelect }: Props) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [clip, setClip] = useState<Clip | null>(null);
  const [direction, setDirection] = useState<"right" | "left">("right");
  const [ready, setReady] = useState(false);
  const previousIndex = useRef(activeIndex);

  useLayoutEffect(() => {
    const measure = () => {
      const track = trackRef.current;
      const button = track?.querySelectorAll<HTMLButtonElement>(".weekbar-base button")[
        activeIndex
      ];
      if (!track || !button) return;
      setClip({
        left: button.offsetLeft,
        right: track.offsetWidth - (button.offsetLeft + button.offsetWidth),
      });
    };
    setDirection(activeIndex >= previousIndex.current ? "right" : "left");
    previousIndex.current = activeIndex;
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [activeIndex, days.length]);

  // Only animate once the pill has been placed, so it never grows in from 0.
  useEffect(() => {
    if (!clip || ready) return;
    const frame = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(frame);
  }, [clip, ready]);

  const leading = `${EDGE_MS}ms`;
  const trailing = `${EDGE_MS}ms`;
  const overlayStyle = clip
    ? ({
        "--clip-left": `${clip.left}px`,
        "--clip-right": `${clip.right}px`,
        // Timings only once placed, so the first paint never animates.
        ...(ready && {
          // Moving right, the right edge leads; moving left, the left edge leads.
          transitionDuration: `${leading}, ${trailing}`,
          transitionDelay:
            direction === "right" ? `${TRAIL_DELAY_MS}ms, 0ms` : `0ms, ${TRAIL_DELAY_MS}ms`,
        }),
      } as CSSProperties)
    : undefined;

  return (
    <div className="weekbar">
      <div className={`weekbar-track ${clip ? "has-overlay" : ""}`.trim()} ref={trackRef}>
        <div className="weekbar-base">
          {days.map((day, index) => (
            <button
              key={day.name}
              className={`press ${index === activeIndex ? "on" : ""}`.trim()}
              onClick={() => onSelect(index)}
              aria-pressed={index === activeIndex}
            >
              <span className="name">{day.name}</span>
              <span className="note num">{note(day)}</span>
            </button>
          ))}
        </div>
        {clip && (
          <div
            className={`weekbar-active ${ready ? "ready" : ""}`.trim()}
            style={overlayStyle}
            aria-hidden="true"
          >
            {days.map((day) => (
              <span className="day" key={day.name}>
                <span className="name">{day.name}</span>
                <span className="note num">{note(day)}</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
