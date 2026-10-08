import { useRef, type CSSProperties, type KeyboardEvent } from "react";

export interface TabItem {
  id: string;
  label: string;
  /** Shown as a small count on the tab when above zero. */
  badge?: number;
  /** What a screen reader hears for the count, after the label. */
  badgeLabel?: string;
}

export const tabDomId = (prefix: string, id: string) => `${prefix}-tab-${id}`;
export const panelDomId = (prefix: string, id: string) => `${prefix}-panel-${id}`;

/**
 * A segmented control that switches panels. Arrow keys move and select (the
 * panels are already rendered, so selecting is free), and only the selected
 * tab is in the Tab order: one stop for the whole control.
 */
export function FriendsTabs({
  tabs,
  value,
  prefix,
  label,
  onChange,
}: {
  tabs: TabItem[];
  value: string;
  /** Ties each tab to its panel's id; the panel side uses `panelDomId`. */
  prefix: string;
  label: string;
  onChange: (id: string) => void;
}) {
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const selected = Math.max(
    0,
    tabs.findIndex((tab) => tab.id === value),
  );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    let next: number;
    if (event.key === "ArrowRight") next = (selected + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (selected - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    const tab = tabs[next];
    onChange(tab.id);
    buttons.current.get(tab.id)?.focus();
  };

  return (
    <div
      className="fd-tabs"
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      style={{ "--n": tabs.length, "--i": selected } as CSSProperties}
    >
      <span className="fd-tabs-thumb" aria-hidden="true" />
      {tabs.map((tab) => (
        <button
          key={tab.id}
          ref={(node) => {
            if (node) buttons.current.set(tab.id, node);
            else buttons.current.delete(tab.id);
          }}
          className="fd-tab"
          type="button"
          role="tab"
          id={tabDomId(prefix, tab.id)}
          aria-selected={tab.id === value}
          aria-controls={panelDomId(prefix, tab.id)}
          tabIndex={tab.id === value ? 0 : -1}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {tab.badge ? (
            <>
              <span className="fd-tab-badge num" aria-hidden="true">
                {tab.badge}
              </span>
              <span className="visually-hidden">, {tab.badgeLabel ?? tab.badge}</span>
            </>
          ) : null}
        </button>
      ))}
    </div>
  );
}
