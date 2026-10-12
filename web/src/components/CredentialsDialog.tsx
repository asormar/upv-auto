import { useEffect, useId, useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { CredentialsForm } from "./CredentialsForm";

const FOCUSABLE = "button:not([disabled]), input:not([disabled])";

/**
 * The form to replace stored UPV credentials, as a modal. Same keyboard
 * contract as `FriendsDialog`: focus moves in on open and returns to the
 * trigger on close, Tab stays inside, Escape closes.
 */
export function CredentialsDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const titleId = useId();
  const card = useRef<HTMLDivElement>(null);

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
    const items = [...card.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
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

  return (
    <div className="sheet-backdrop">
      <div
        className="sheet-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        ref={card}
        onKeyDown={trapTab}
      >
        <CredentialsForm
          title="Cambiar tus credenciales"
          submitLabel="Guardar y actualizar"
          headingLevel="h2"
          headingId={titleId}
          onCancel={onClose}
          onSaved={onSaved}
        />
      </div>
    </div>
  );
}
