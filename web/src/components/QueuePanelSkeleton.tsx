/**
 * Placeholder for the side panel while the schedule loads.
 *
 * Same plain shimmering blocks as the agenda skeleton, one per real card and
 * roughly its height, so both columns load the same way and nothing jumps
 * when the data arrives.
 */
const CARD_HEIGHTS = [106, 220, 228];

export function QueuePanelSkeleton() {
  return (
    <aside className="panel" aria-busy="true" aria-label="Cargando tu cola">
      {CARD_HEIGHTS.map((height) => (
        <div key={height} className="skeleton skeleton-panel" style={{ height }} />
      ))}
    </aside>
  );
}
