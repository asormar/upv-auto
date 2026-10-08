import {
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import type { Friend } from "../api";
import type { FriendsState } from "../api/useFriends";
import { fileToAvatar } from "../avatarImage";
import { Avatar } from "./Avatar";
import { Alert, Check, Refresh } from "./icons";

const COPIED_MS = 1500;
const CONFIRM_MS = 4000;
const ALIAS_MAX = 24;
const CODE_LENGTH = 8;

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

function messageOf(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

/** Removing a friend cannot be undone, so the first press only asks. */
function RemoveButton({
  alias,
  disabled,
  onConfirm,
}: {
  alias: string;
  disabled: boolean;
  onConfirm: () => void;
}) {
  const [asking, setAsking] = useState(false);

  // Walking away from the question cancels it. Touch browsers may not blur a
  // tapped button, hence the timer as well.
  useEffect(() => {
    if (!asking) return;
    const timer = window.setTimeout(() => setAsking(false), CONFIRM_MS);
    return () => window.clearTimeout(timer);
  }, [asking]);

  return (
    <>
      <button
        className={`cta sm press${asking ? "" : " ghost"}`}
        type="button"
        disabled={disabled}
        onBlur={() => setAsking(false)}
        onClick={() => (asking ? onConfirm() : setAsking(true))}
        aria-label={asking ? `Confirmar: eliminar a ${alias}` : `Eliminar a ${alias}`}
      >
        {asking ? "¿Seguro?" : "Eliminar"}
      </button>
      <span className="visually-hidden" role="status">
        {asking ? `¿Seguro? Pulsa de nuevo para eliminar a ${alias}.` : ""}
      </span>
    </>
  );
}

function Section({
  title,
  error,
  children,
}: {
  title: string;
  error: string | null;
  children: ReactNode;
}) {
  return (
    <section className="fd-section">
      <h3 className="fd-heading">{title}</h3>
      {children}
      {error && (
        <p className="authgate-banner error" role="alert">
          <Alert size={14} />
          <span>{error}</span>
        </p>
      )}
    </section>
  );
}

/**
 * Where friends are managed: your code, adding someone, answering and
 * withdrawing requests, removing friends. The week table itself is read-only.
 */
export function FriendsDialog({ state, onClose }: { state: FriendsState; onClose: () => void }) {
  const { friends, profile } = state;
  const titleId = useId();
  const aliasId = useId();
  const codeId = useId();
  const card = useRef<HTMLDivElement>(null);
  // Closing on a click would also fire after a drag that began inside a field.
  const pressedBackdrop = useRef(false);

  // Your own code and alias.
  const [aliasDraft, setAliasDraft] = useState<string | null>(null);
  const [aliasBusy, setAliasBusy] = useState(false);
  const [aliasError, setAliasError] = useState<string | null>(null);
  const [aliasSaved, setAliasSaved] = useState(false);
  const [copy, setCopy] = useState<"idle" | "done" | "failed">("idle");

  // Your photo.
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [photoNote, setPhotoNote] = useState<"saved" | "removed" | null>(null);
  const pickButton = useRef<HTMLButtonElement>(null);
  const pickInput = useRef<HTMLInputElement>(null);

  // Adding someone.
  const [code, setCode] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendNotice, setSendNotice] = useState<string | null>(null);

  // Requests and friends: one row at a time is busy; its error shows under its section.
  const [pending, setPending] = useState<string | null>(null);
  const [listError, setListError] = useState<{ section: string; message: string } | null>(null);

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

  useEffect(() => {
    if (copy === "idle") return;
    const timer = window.setTimeout(() => setCopy("idle"), COPIED_MS);
    return () => window.clearTimeout(timer);
  }, [copy]);

  useEffect(() => {
    if (!aliasSaved) return;
    const timer = window.setTimeout(() => setAliasSaved(false), COPIED_MS);
    return () => window.clearTimeout(timer);
  }, [aliasSaved]);

  useEffect(() => {
    if (!photoNote) return;
    const timer = window.setTimeout(() => setPhotoNote(null), COPIED_MS);
    return () => window.clearTimeout(timer);
  }, [photoNote]);

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

  const aliasValue = aliasDraft ?? profile?.alias ?? "";
  const aliasChanged = aliasValue.trim() !== (profile?.alias ?? "");

  const copyCode = async () => {
    if (!profile) return;
    try {
      await navigator.clipboard.writeText(profile.friend_code);
      setCopy("done");
    } catch {
      setCopy("failed");
    }
  };

  const saveAlias = async (event: FormEvent) => {
    event.preventDefault();
    setAliasBusy(true);
    setAliasError(null);
    try {
      await state.saveAlias(aliasValue);
      setAliasDraft(null);
      setAliasSaved(true);
    } catch (cause) {
      setAliasError(messageOf(cause));
    } finally {
      setAliasBusy(false);
    }
  };

  const changePhoto = async (avatar: File | null) => {
    setPhotoBusy(true);
    setPhotoError(null);
    setPhotoNote(null);
    try {
      await state.saveAvatar(avatar && (await fileToAvatar(avatar)));
      setPhotoNote(avatar ? "saved" : "removed");
    } catch (cause) {
      setPhotoError(messageOf(cause));
    } finally {
      setPhotoBusy(false);
      // "Quitar foto" is disabled meanwhile and leaves once it worked: either
      // way the focus it held would be lost.
      pickButton.current?.focus();
    }
  };

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    // Cleared right away, or picking the same file again would not fire `change`.
    event.currentTarget.value = "";
    if (file) void changePhoto(file);
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    setSending(true);
    setSendError(null);
    setSendNotice(null);
    try {
      const result = await state.sendRequest(code.trim());
      setSendNotice(result === "accepted" ? "Ya sois amigos" : "Solicitud enviada");
      setCode("");
    } catch (cause) {
      setSendError(messageOf(cause));
    } finally {
      setSending(false);
    }
  };

  const run = async (section: string, friend: Friend, action: () => Promise<void>) => {
    setPending(friend.id);
    setListError(null);
    try {
      await action();
    } catch (cause) {
      setListError({ section, message: messageOf(cause) });
    } finally {
      setPending(null);
    }
  };

  const incoming = friends.filter((friend) => friend.relation === "incoming");
  const outgoing = friends.filter((friend) => friend.relation === "outgoing");
  const accepted = friends.filter((friend) => friend.relation === "friend");
  const errorFor = (section: string) => (listError?.section === section ? listError.message : null);

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
        <h2 className="fd-title" id={titleId}>
          Amigos
        </h2>

        {state.error && (
          <p className="authgate-banner error" role="alert">
            <Alert size={14} />
            <span>{state.error}</span>
          </p>
        )}

        <section className="fd-section">
          <h3 className="fd-heading">Tu foto</h3>
          <div className="fd-photo">
            <Avatar name={profile?.alias ?? ""} src={profile?.avatar} size={72} />
            <div className="fd-photo-side">
              <div className="fd-photo-actions">
                {/* The picker is the hidden input; this is the control people reach. */}
                <button
                  ref={pickButton}
                  className="cta sm ghost press"
                  type="button"
                  disabled={!profile}
                  aria-busy={photoBusy}
                  aria-label="Cambiar foto de perfil"
                  onClick={() => !photoBusy && pickInput.current?.click()}
                >
                  {photoBusy && (
                    <span className="spin">
                      <Refresh size={14} />
                    </span>
                  )}
                  Cambiar foto
                </button>
                <input
                  ref={pickInput}
                  className="visually-hidden"
                  type="file"
                  accept="image/*"
                  tabIndex={-1}
                  aria-hidden="true"
                  onChange={onPick}
                />
                {profile?.avatar && (
                  <button
                    className="cta sm ghost press"
                    type="button"
                    disabled={photoBusy}
                    onClick={() => void changePhoto(null)}
                  >
                    Quitar foto
                  </button>
                )}
              </div>
              <span className="fd-note" role="status">
                {photoNote ? (
                  <>
                    <Check size={13} /> {photoNote === "saved" ? "Foto guardada" : "Foto quitada"}
                  </>
                ) : (
                  "Es la que ven tus amigos."
                )}
              </span>
            </div>
          </div>
          {photoError && (
            <p className="authgate-banner error" role="alert">
              <Alert size={14} />
              <span>{photoError}</span>
            </p>
          )}
        </section>

        <section className="fd-section">
          <h3 className="fd-heading">Tu código</h3>
          <div className="fd-codebar">
            <span className="fd-code" id={codeId}>
              {profile?.friend_code ?? "········"}
            </span>
            <button
              className="cta sm ghost press"
              type="button"
              onClick={() => void copyCode()}
              disabled={!profile}
              aria-describedby={codeId}
            >
              {copy === "done" ? "Copiado" : copy === "failed" ? "No se pudo" : "Copiar"}
            </button>
          </div>
          <form className="field" onSubmit={saveAlias}>
            <label htmlFor={aliasId}>Tu alias</label>
            <div className="fd-inline">
              <input
                id={aliasId}
                type="text"
                maxLength={ALIAS_MAX}
                autoComplete="nickname"
                required
                value={aliasValue}
                onChange={(event) => {
                  setAliasDraft(event.target.value);
                  setAliasSaved(false);
                }}
              />
              <button
                className="cta sm ghost press"
                type="submit"
                disabled={aliasBusy || !aliasChanged || aliasValue.trim() === ""}
                aria-busy={aliasBusy}
              >
                {aliasBusy && (
                  <span className="spin">
                    <Refresh size={14} />
                  </span>
                )}
                Guardar
              </button>
            </div>
            <span className="fd-note" role="status">
              {aliasSaved ? (
                <>
                  <Check size={13} /> Alias guardado
                </>
              ) : (
                "Es lo que ven tus amigos."
              )}
            </span>
            {aliasError && (
              <p className="authgate-banner error" role="alert">
                <Alert size={14} />
                <span>{aliasError}</span>
              </p>
            )}
          </form>
        </section>

        <section className="fd-section">
          <h3 className="fd-heading">Añadir amigo</h3>
          <form className="field" onSubmit={send}>
            <label htmlFor={`${codeId}-add`}>Código de tu amigo</label>
            <div className="fd-inline">
              {/* Phone keyboards capitalise, autocorrect and suggest by default,
                  which silently mangles a code that has to match exactly. */}
              <input
                id={`${codeId}-add`}
                className="fd-codeinput"
                type="text"
                inputMode="text"
                autoCapitalize="characters"
                autoCorrect="off"
                autoComplete="off"
                spellCheck={false}
                required
                value={code}
                onChange={(event) => {
                  // Sliced here, not with `maxLength`, so a pasted "ABCD EFGH"
                  // loses its space before it is cut to length.
                  setCode(event.target.value.toUpperCase().replace(/\s+/g, "").slice(0, CODE_LENGTH));
                  setSendError(null);
                  setSendNotice(null);
                }}
              />
              <button
                className="cta sm press"
                type="submit"
                disabled={sending || code.trim().length === 0}
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
            {sendError && (
              <p className="authgate-banner error" role="alert">
                <Alert size={14} />
                <span>{sendError}</span>
              </p>
            )}
            {sendNotice && (
              <p className="authgate-banner info" role="status">
                <Check size={14} />
                <span>{sendNotice}</span>
              </p>
            )}
          </form>
        </section>

        {incoming.length > 0 && (
          <Section title="Solicitudes" error={errorFor("incoming")}>
            {incoming.map((friend) => (
              <div className="fd-row" key={friend.id}>
                <Avatar name={friend.alias} src={friend.avatar} size={32} />
                <span className="fd-alias" title={friend.alias}>
                  {friend.alias}
                </span>
                <button
                  className="cta sm press"
                  type="button"
                  disabled={pending === friend.id}
                  onClick={() => void run("incoming", friend, () => state.respond(friend.id, true))}
                  aria-label={`Aceptar a ${friend.alias}`}
                >
                  Aceptar
                </button>
                <button
                  className="cta sm ghost press"
                  type="button"
                  disabled={pending === friend.id}
                  onClick={() => void run("incoming", friend, () => state.respond(friend.id, false))}
                  aria-label={`Rechazar a ${friend.alias}`}
                >
                  Rechazar
                </button>
              </div>
            ))}
          </Section>
        )}

        {outgoing.length > 0 && (
          <Section title="Enviadas" error={errorFor("outgoing")}>
            {outgoing.map((friend) => (
              <div className="fd-row" key={friend.id}>
                <Avatar name={friend.alias} src={friend.avatar} size={32} />
                <span className="fd-alias" title={friend.alias}>
                  {friend.alias}
                </span>
                <button
                  className="cta sm ghost press"
                  type="button"
                  disabled={pending === friend.id}
                  onClick={() => void run("outgoing", friend, () => state.remove(friend.id))}
                  aria-label={`Cancelar la solicitud a ${friend.alias}`}
                >
                  Cancelar
                </button>
              </div>
            ))}
          </Section>
        )}

        {accepted.length > 0 && (
          <Section title="Tus amigos" error={errorFor("friend")}>
            {accepted.map((friend) => (
              <div className="fd-row" key={friend.id}>
                <Avatar name={friend.alias} src={friend.avatar} size={32} />
                <span className="fd-alias" title={friend.alias}>
                  {friend.alias}
                </span>
                <RemoveButton
                  alias={friend.alias}
                  disabled={pending === friend.id}
                  onConfirm={() => void run("friend", friend, () => state.remove(friend.id))}
                />
              </div>
            ))}
          </Section>
        )}

        <button className="authgate-switch" type="button" onClick={onClose}>
          Cerrar
        </button>
      </div>
    </div>
  );
}
