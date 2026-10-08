import { useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import type { FriendsState } from "../api/useFriends";
import { ErrorBanner } from "./ErrorBanner";
import { FriendsPanel } from "./FriendsPanel";
import { FriendsProfile } from "./FriendsProfile";
import { FriendsTabs, panelDomId, tabDomId } from "./FriendsTabs";
import { Bell, Close } from "./icons";

type TabId = "friends" | "profile";

// Visible controls only: the hidden tab's panel is still in the DOM, and the
// tabs other than the selected one are reached with the arrow keys.
const FOCUSABLE = 'button:not([disabled]):not([tabindex="-1"]), input:not([disabled]):not([tabindex="-1"])';

/**
 * Where friends are managed. Two tabs: the people (requests, adding, the
 * list) and the user's own profile, which changes rarely. The week table
 * itself is read-only and lives in `FriendsWeek`.
 */
export function FriendsDialog({ state, onClose }: { state: FriendsState; onClose: () => void }) {
  const { friends, notice } = state;
  const titleId = useId();
  const prefix = useId();
  const card = useRef<HTMLDivElement>(null);
  // Closing on a click would also fire after a drag that began inside a field.
  const pressedBackdrop = useRef(false);
  const [tab, setTab] = useState<TabId>("friends");
  // The first panel is just there; only a switch the user asks for cross-fades.
  const [switched, setSwitched] = useState(false);

  const incoming = friends.filter((friend) => friend.relation === "incoming").length;

  // Focus moves in on open and goes back to the trigger on close.
  useEffect(() => {
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    card.current?.focus();
    return () => trigger?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Keeps Tab inside the dialog: behind it the page is inert in spirit only.
  const trapTab = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Tab" || !card.current) return;
    const items = [...card.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
      (item) => !item.closest("[hidden]"),
    );
    // The selected tab is a stop too, but it is `tabindex=0`, not excluded above.
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === card.current)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const select = (id: string) => {
    setSwitched(true);
    setTab(id as TabId);
  };

  return (
    <div
      className="sheet-backdrop"
      onMouseDown={(event) => {
        pressedBackdrop.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        if (pressedBackdrop.current && event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="sheet-card friends-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        ref={card}
        onKeyDown={trapTab}
      >
        <div className="fd-head">
          <div className="fd-titlebar">
            <h2 className="fd-title" id={titleId}>
              Amigos
            </h2>
            <button className="fd-close press" type="button" aria-label="Cerrar" onClick={onClose}>
              <Close />
            </button>
          </div>
          <FriendsTabs
            label="Secciones de amigos"
            prefix={prefix}
            value={tab}
            onChange={select}
            tabs={[
              {
                id: "friends",
                label: "Amigos",
                badge: incoming,
                badgeLabel: `${incoming} ${incoming === 1 ? "solicitud pendiente" : "solicitudes pendientes"}`,
              },
              { id: "profile", label: "Mi perfil" },
            ]}
          />
        </div>

        <div className="fd-body">
          <ErrorBanner message={state.error} />

          {/* Mounted even when empty so the screen reader has a region to watch;
              the app-level one stays quiet while this dialog is open. */}
          <div className="fd-live" role="status">
            {notice && (
              <p className="authgate-banner info" key={notice.id}>
                <Bell size={14} />
                <span>{notice.text}</span>
              </p>
            )}
          </div>

          <div
            className={`fd-panel${switched ? " swap" : ""}`}
            role="tabpanel"
            id={panelDomId(prefix, "friends")}
            aria-labelledby={tabDomId(prefix, "friends")}
            hidden={tab !== "friends"}
          >
            <FriendsPanel state={state} onFocusLost={() => card.current?.focus()} />
          </div>
          <div
            className={`fd-panel${switched ? " swap" : ""}`}
            role="tabpanel"
            id={panelDomId(prefix, "profile")}
            aria-labelledby={tabDomId(prefix, "profile")}
            hidden={tab !== "profile"}
          >
            <FriendsProfile state={state} />
          </div>
        </div>
      </div>
    </div>
  );
}
