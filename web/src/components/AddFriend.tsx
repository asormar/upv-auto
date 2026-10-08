import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import type { SendOutcome } from "../api/useFriends";
import { CODE_LENGTH, OWN_CODE_MESSAGE, guidanceFor, messageOf, sentText } from "../friendsMessages";
import { Alert, Check, Refresh } from "./icons";

const SENT_MS = 6000;

/**
 * Typing a friend's code and sending the request. The button only wakes up
 * with a full code, and the one code that can never work (your own) is
 * refused as soon as it is complete rather than after a round trip.
 */
export function AddFriend({
  ownCode,
  onSend,
}: {
  ownCode: string | null;
  onSend: (code: string) => Promise<SendOutcome>;
}) {
  const inputId = useId();
  const errorId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [code, setCode] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  useEffect(() => {
    if (!sent) return;
    const timer = window.setTimeout(() => setSent(null), SENT_MS);
    return () => window.clearTimeout(timer);
  }, [sent]);

  const complete = code.length === CODE_LENGTH;
  const isOwn = complete && ownCode !== null && code === ownCode.toUpperCase();
  const shown = isOwn ? OWN_CODE_MESSAGE : error;
  const guidance = shown && !isOwn ? guidanceFor(shown) : null;

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (!complete || isOwn || sending) return;
    setSending(true);
    setError(null);
    setSent(null);
    try {
      setSent(sentText(await onSend(code)));
      setCode("");
      // The button is disabled again with the field empty: keep the focus on
      // the field instead of letting it fall to the page. Not on a phone,
      // where that would pop the keyboard up over the confirmation.
      if (window.matchMedia("(pointer: fine)").matches) input.current?.focus();
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setSending(false);
    }
  };

  return (
    <form className="field" onSubmit={send}>
      <label htmlFor={inputId}>Código de tu amigo</label>
      <div className="fd-inline">
        {/* Phone keyboards capitalise, autocorrect and suggest by default,
            which silently mangles a code that has to match exactly. */}
        <input
          ref={input}
          id={inputId}
          className="fd-codeinput"
          type="text"
          inputMode="text"
          autoCapitalize="characters"
          autoCorrect="off"
          autoComplete="off"
          spellCheck={false}
          value={code}
          aria-invalid={shown ? true : undefined}
          aria-describedby={shown ? errorId : undefined}
          onChange={(event) => {
            // Sliced here, not with `maxLength`, so a pasted "ABCD EFGH"
            // loses its space before it is cut to length.
            setCode(event.target.value.toUpperCase().replace(/\s+/g, "").slice(0, CODE_LENGTH));
            setError(null);
            setSent(null);
          }}
        />
        <button
          className="cta sm press"
          type="submit"
          // Stays enabled while sending (the handler ignores a second press), so
          // the focus it holds is not dropped mid-request.
          disabled={!complete || isOwn}
          aria-busy={sending}
        >
          {sending && (
            <span className="spin">
              <Refresh size={14} />
            </span>
          )}
          Enviar solicitud
        </button>
      </div>
      {shown && (
        <p className="authgate-banner error" role="alert" id={errorId}>
          <Alert size={14} />
          <span>
            {shown}
            {guidance && <span className="fd-hint">{guidance}</span>}
          </span>
        </p>
      )}
      <span className="fd-note ok" role="status">
        {sent && (
          <>
            <Check size={13} /> {sent}
          </>
        )}
      </span>
    </form>
  );
}
