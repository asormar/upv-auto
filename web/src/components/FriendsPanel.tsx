import { useEffect, useState, type ReactNode } from "react";
import type { Friend } from "../api";
import type { FriendsState } from "../api/useFriends";
import { messageOf } from "../friendsMessages";
import { AddFriend } from "./AddFriend";
import { CancelButton, FriendRow, RemoveButton, RequestActions } from "./FriendRow";
import { ErrorBanner } from "./ErrorBanner";
import { YourCode } from "./YourCode";

type Section = "incoming" | "outgoing" | "friend";

function Block({
  title,
  count,
  className,
  error,
  children,
}: {
  title: string;
  count?: number;
  className?: string;
  error: string | null;
  children: ReactNode;
}) {
  return (
    <section className={`fd-section${className ? ` ${className}` : ""}`}>
      <h3 className="fd-heading">
        {title}
        {count !== undefined && <span className="num"> · {count}</span>}
      </h3>
      {children}
      <ErrorBanner message={error} />
    </section>
  );
}

/**
 * The "Amigos" tab, most urgent first: requests waiting for an answer, then
 * adding someone, then the friends, then what is still waiting on them.
 * Sections with nothing in them are left out; with nothing at all, the tab
 * explains what friends are for and the add field is the way forward.
 */
export function FriendsPanel({
  state,
  onFocusLost,
}: {
  state: FriendsState;
  /** A row's buttons disappear when its request is answered, taking the focus along. */
  onFocusLost: () => void;
}) {
  const { friends, profile, loading, highlightIds } = state;

  // Rows that exist when the tab opens do not animate; later ones do.
  const [settled, setSettled] = useState(false);
  useEffect(() => setSettled(true), []);

  // One row at a time is busy; its error shows under its section.
  const [pending, setPending] = useState<string | null>(null);
  const [listError, setListError] = useState<{ section: Section; message: string } | null>(null);

  const run = async (section: Section, friend: Friend, action: () => Promise<void>) => {
    setPending(friend.id);
    setListError(null);
    try {
      await action();
    } catch (cause) {
      setListError({ section, message: messageOf(cause) });
    } finally {
      setPending(null);
      // After React has committed the list without the row, not before.
      window.setTimeout(() => {
        if (!document.activeElement || document.activeElement === document.body) onFocusLost();
      }, 100);
    }
  };

  const incoming = friends.filter((friend) => friend.relation === "incoming");
  const outgoing = friends.filter((friend) => friend.relation === "outgoing");
  const accepted = friends.filter((friend) => friend.relation === "friend");
  const errorFor = (section: Section) => (listError?.section === section ? listError.message : null);
  const empty = friends.length === 0;

  const row = (friend: Friend, actions: ReactNode, stacked = false) => (
    <FriendRow
      key={friend.id}
      friend={friend}
      entering={settled}
      highlighted={highlightIds.has(friend.id)}
      stacked={stacked}
    >
      {actions}
    </FriendRow>
  );

  return (
    <>
      {incoming.length > 0 && (
        <Block title="Solicitudes" count={incoming.length} className="fd-requests" error={errorFor("incoming")}>
          <ul className="fd-list">
            {incoming.map((friend) =>
              row(
                friend,
                <RequestActions
                  alias={friend.alias}
                  disabled={pending === friend.id}
                  onAccept={() => void run("incoming", friend, () => state.respond(friend.id, true))}
                  onDecline={() => void run("incoming", friend, () => state.respond(friend.id, false))}
                />,
                true,
              ),
            )}
          </ul>
        </Block>
      )}

      <section className="fd-section">
        <h3 className="fd-heading">Añadir amigo</h3>
        {empty &&
          (loading ? (
            <div className="fd-skel fd-intro-skel" aria-hidden="true" />
          ) : (
            <p className="fd-intro">
              Añade a un amigo con su código y verás qué días reserva la semana que viene.
            </p>
          ))}
        <AddFriend ownCode={profile?.friend_code ?? null} onSend={state.sendRequest} />
        <YourCode code={profile?.friend_code ?? null} loading={loading} />
      </section>

      {accepted.length > 0 && (
        <Block title="Tus amigos" error={errorFor("friend")}>
          <ul className="fd-list">
            {accepted.map((friend) =>
              row(
                friend,
                <RemoveButton
                  alias={friend.alias}
                  disabled={pending === friend.id}
                  onConfirm={() => void run("friend", friend, () => state.remove(friend.id))}
                />,
              ),
            )}
          </ul>
        </Block>
      )}

      {outgoing.length > 0 && (
        <Block title="Enviadas" error={errorFor("outgoing")}>
          <ul className="fd-list">
            {outgoing.map((friend) =>
              row(
                friend,
                <CancelButton
                  alias={friend.alias}
                  disabled={pending === friend.id}
                  onCancel={() => void run("outgoing", friend, () => state.remove(friend.id))}
                />,
              ),
            )}
          </ul>
        </Block>
      )}
    </>
  );
}
