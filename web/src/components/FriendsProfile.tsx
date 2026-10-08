import { useEffect, useId, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import type { FriendsState } from "../api/useFriends";
import { fileToAvatar } from "../avatarImage";
import { messageOf } from "../friendsMessages";
import { Avatar } from "./Avatar";
import { ErrorBanner } from "./ErrorBanner";
import { Check, Refresh } from "./icons";

const NOTE_MS = 1500;
const ALIAS_MAX = 24;

function Spinner() {
  return (
    <span className="spin">
      <Refresh size={14} />
    </span>
  );
}

/** What the user's friends see of them: a photo and an alias. */
export function FriendsProfile({ state }: { state: FriendsState }) {
  const { profile } = state;
  const aliasId = useId();

  const [aliasDraft, setAliasDraft] = useState<string | null>(null);
  const [aliasBusy, setAliasBusy] = useState(false);
  const [aliasError, setAliasError] = useState<string | null>(null);
  const [aliasSaved, setAliasSaved] = useState(false);

  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [photoNote, setPhotoNote] = useState<"saved" | "removed" | null>(null);
  const pickButton = useRef<HTMLButtonElement>(null);
  const pickInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!aliasSaved) return;
    const timer = window.setTimeout(() => setAliasSaved(false), NOTE_MS);
    return () => window.clearTimeout(timer);
  }, [aliasSaved]);

  useEffect(() => {
    if (!photoNote) return;
    const timer = window.setTimeout(() => setPhotoNote(null), NOTE_MS);
    return () => window.clearTimeout(timer);
  }, [photoNote]);

  const aliasValue = aliasDraft ?? profile?.alias ?? "";
  const aliasChanged = aliasValue.trim() !== (profile?.alias ?? "");

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
      // "Eliminar foto" is disabled meanwhile and leaves once it worked: either
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

  return (
    <>
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
                {photoBusy && <Spinner />}
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
                  Eliminar foto
                </button>
              )}
            </div>
            <span className="fd-note ok" role="status">
              {photoNote && (
                <>
                  <Check size={13} /> {photoNote === "saved" ? "Foto guardada" : "Foto eliminada"}
                </>
              )}
            </span>
          </div>
        </div>
        <ErrorBanner message={photoError} />
      </section>

      <form className="fd-section field" onSubmit={saveAlias}>
        <label htmlFor={aliasId}>Tu alias</label>
        <div className="fd-inline">
          <input
            id={aliasId}
            type="text"
            maxLength={ALIAS_MAX}
            autoComplete="nickname"
            required
            disabled={!profile}
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
            {aliasBusy && <Spinner />}
            Guardar
          </button>
        </div>
        <span className="fd-note ok" role="status">
          {aliasSaved && (
            <>
              <Check size={13} /> Alias guardado
            </>
          )}
        </span>
        <ErrorBanner message={aliasError} />
      </form>

      <p className="fd-footnote">Tus amigos ven tu foto y tu alias.</p>
    </>
  );
}
