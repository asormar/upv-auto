import { useEffect, useRef, useState } from "react";
import { People } from "./icons";

/**
 * The topbar's way into the friends dialog. Its badge counts requests waiting
 * for an answer and pops once each time that number goes up.
 */
export function FriendsButton({
  incoming,
  loading,
  onOpen,
}: {
  incoming: number;
  loading: boolean;
  onOpen: () => void;
}) {
  const [pops, setPops] = useState(0);
  const previous = useRef<number | null>(null);

  useEffect(() => {
    // What the first read finds is not news.
    if (loading) return;
    if (previous.current !== null && incoming > previous.current) setPops((count) => count + 1);
    previous.current = incoming;
  }, [incoming, loading]);

  return (
    <button
      className="icon-button press"
      type="button"
      onClick={onOpen}
      title="Amigos"
      aria-label={
        incoming > 0
          ? `Amigos, ${incoming} ${incoming === 1 ? "solicitud pendiente" : "solicitudes pendientes"}`
          : "Amigos"
      }
    >
      <People />
      {incoming > 0 && (
        // Keyed by the pop count so every increase starts the animation again.
        <span className={`icon-badge num${pops > 0 ? " pop" : ""}`} key={pops} aria-hidden="true">
          {incoming}
        </span>
      )}
    </button>
  );
}
