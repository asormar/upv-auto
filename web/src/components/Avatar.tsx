import { useState, type CSSProperties } from "react";

// With no animation `animationend` never fires, so the fade must not start.
function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * A person's circle: their photo, or their initial while they have none, the
 * photo has not loaded yet, or it failed to. Decorative (the name always sits
 * next to it), so it is hidden from screen readers.
 *
 * A photo that arrives later than the first paint (the user just changed it)
 * fades in over what was there. One that was already there never animates.
 */
export function Avatar({
  name,
  src,
  size = 28,
  className,
}: {
  name: string;
  src?: string | null;
  /** Diameter in px. The box is fixed, so a photo loading never moves anything. */
  size?: number;
  className?: string;
}) {
  const photo = src ?? null;
  const [seen, setSeen] = useState(photo);
  const [loaded, setLoaded] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  // The photo being faded over, and whether the new one is still fading in.
  const [under, setUnder] = useState<string | null>(null);
  const [fading, setFading] = useState(false);

  // Adjusting state while rendering: it lands before anything is painted.
  if (photo !== seen) {
    setSeen(photo);
    setUnder(seen !== null && loaded === seen ? seen : null);
    setFading(photo !== null && !prefersReducedMotion());
  }

  const visible = photo !== null && failed !== photo ? photo : null;
  const ready = visible !== null && loaded === visible;
  const initial = name.trim().charAt(0).toUpperCase() || "?";

  return (
    <span
      className={`avatar${className ? ` ${className}` : ""}`}
      style={{ "--size": `${size}px` } as CSSProperties}
      aria-hidden="true"
    >
      {(!ready || (fading && under === null)) && initial}
      {fading && under && visible && <img className="avatar-img" src={under} alt="" draggable={false} />}
      {visible && (
        <img
          key={visible}
          className={`avatar-img${fading && ready ? " fade" : ""}`}
          src={visible}
          alt=""
          draggable={false}
          loading="lazy"
          decoding="async"
          onLoad={() => setLoaded(visible)}
          onError={() => setFailed(visible)}
          onAnimationEnd={() => {
            setFading(false);
            setUnder(null);
          }}
        />
      )}
    </span>
  );
}
