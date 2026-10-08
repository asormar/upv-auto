import type { FriendsNotice } from "../api/useFriends";

/**
 * Reads a friends notice aloud wherever the user is in the app. Silent while
 * the dialog is open: the dialog shows (and announces) the same sentence itself.
 */
export function FriendsLive({ notice, silenced }: { notice: FriendsNotice | null; silenced: boolean }) {
  return (
    <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
      {/* Keyed, so a sentence repeated later is a new node and is read again. */}
      {notice && !silenced && <span key={notice.id}>{notice.text}</span>}
    </div>
  );
}
