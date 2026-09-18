import NumberFlow from "@number-flow/react";

/** The UPV limit as bubbles, counting only what next Saturday would book. */
interface Props {
  label: string;
  used: number;
  max: number;
  highlight?: boolean;
  /** A place was just freed: the bubble at `used` drains away. */
  removed?: boolean;
}

export function LimitBubbles({ label, used, max, highlight = false, removed = false }: Props) {
  const left = Math.max(0, max - used);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span className="num" style={{ color: "var(--muted)" }}>
          {/* 8 · The number rolls instead of swapping. */}
          <NumberFlow value={used} /> de {max}
        </span>
      </div>
      <div
        className="bubbles"
        role="img"
        aria-label={`${label}: ${used} de ${max} plazas en la cola del sábado, quedan ${left}`}
      >
        {Array.from({ length: max }, (_, index) => {
          const filled = index < used;
          const justAdded = highlight && index === used - 1;
          const justRemoved = removed && index === used;
          const classes = ["bubble", filled && "held", justAdded && "just-added", justRemoved && "just-removed"];
          return <span key={index} className={classes.filter(Boolean).join(" ")} />;
        })}
      </div>
    </div>
  );
}
