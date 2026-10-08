import { useEffect, useId, useState } from "react";
import { groupCode } from "../friendsMessages";
import { Check } from "./icons";

const FEEDBACK_MS = 2000;

type Feedback = "code" | "message" | "failed" | null;

const FEEDBACK_TEXT = {
  code: "Copiado",
  message: "Mensaje copiado",
  failed: "No se pudo copiar",
} as const;

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * The user's own code, ready to hand over: copy the bare code, or copy a
 * message that also carries the link to the web, to paste into any chat.
 */
export function YourCode({ code, loading }: { code: string | null; loading: boolean }) {
  const labelId = useId();
  const [feedback, setFeedback] = useState<Feedback>(null);

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(null), FEEDBACK_MS);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  const copy = async () => {
    if (!code) return;
    setFeedback((await copyText(code)) ? "code" : "failed");
  };

  const share = async () => {
    if (!code) return;
    // The grouped code is easier to read in a chat, and the add field strips
    // the space when it is pasted back.
    const message = `¿Quieres ser mi amigo? Este es mi código: ${groupCode(code)}\n${location.origin}${location.pathname}`;
    setFeedback((await copyText(message)) ? "message" : "failed");
  };

  return (
    <div className="fd-yourcode" aria-busy={loading}>
      <div className="fd-yourcode-head">
        <span className="fd-yourcode-label" id={labelId}>
          Tu código
        </span>
        {/* Up here, not next to the buttons, so the card never changes height. */}
        <span className={`fd-note ${feedback === "failed" ? "bad" : "ok"}`} role="status">
          {feedback && (
            <>
              {feedback !== "failed" && <Check size={13} />} {FEEDBACK_TEXT[feedback]}
            </>
          )}
        </span>
      </div>
      {code ? (
        <span className="fd-code" aria-labelledby={labelId}>
          {groupCode(code)}
        </span>
      ) : loading ? (
        <span className="fd-skel fd-code-skel" aria-hidden="true" />
      ) : (
        <span className="fd-code-missing">No disponible por ahora</span>
      )}
      <div className="fd-yourcode-actions">
        <button className="cta sm ghost press" type="button" disabled={!code} onClick={() => void copy()}>
          Copiar
        </button>
        <button className="cta sm ghost press" type="button" disabled={!code} onClick={() => void share()}>
          Compartir
        </button>
      </div>
    </div>
  );
}
