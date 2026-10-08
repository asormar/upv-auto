// Friends and the user's own profile. Requests and removals arrive through
// Realtime on the `friendships` table. A friend's queue, alias and photo do
// not (row-level security hides them), so the list is also re-read on mount,
// when the tab comes back to the foreground, and every `POLL_MS` while it is
// visible. Supabase only: under `VITE_BACKEND=local` there are no accounts and
// nothing is ever fetched.

import { useCallback, useEffect, useRef, useState } from "react";
import {
  BACKEND,
  getProfile,
  listFriends,
  removeFriendship,
  respondFriendRequest,
  sendFriendRequest,
  setAlias,
  setAvatar,
  subscribeToFriendships,
  type Friend,
  type Profile,
} from "../api";
import { describeChanges, type FriendChanges } from "../friendsChanges";

/** What a send did, and who it was for when the refreshed list shows it. */
export interface SendOutcome {
  result: "requested" | "accepted";
  friend: Friend | null;
}

export interface FriendsNotice {
  /** Changes for every announcement, so the same sentence twice still reads twice. */
  id: number;
  text: string;
}

export interface FriendsState {
  friends: Friend[];
  profile: Profile | null;
  /** True until the first read settles; later refetches never set it. */
  loading: boolean;
  /** Why the last read failed. The data from the last good one stays on screen. */
  error: string | null;
  /** The latest request that arrived or was accepted without the user doing it; clears itself. */
  notice: FriendsNotice | null;
  /** Friendships behind `notice`, for the list to point at; clears itself sooner. */
  highlightIds: ReadonlySet<string>;
  reload: () => Promise<void>;
  /** The actions below throw the API's Spanish message, for the caller to show
   * next to what the user was doing, and re-read the list when they succeed. */
  sendRequest: (code: string) => Promise<SendOutcome>;
  respond: (friendshipId: string, accept: boolean) => Promise<void>;
  remove: (friendshipId: string) => Promise<void>;
  saveAlias: (alias: string) => Promise<void>;
  /** A data URL from `fileToAvatar`, or null to remove the photo. */
  saveAvatar: (avatar: string | null) => Promise<void>;
}

const ENABLED = BACKEND === "supabase";

/** Safety net for what Realtime cannot carry. */
const POLL_MS = 90_000;
/** A burst of events (accept = update + insert) is one read. */
const DEBOUNCE_MS = 250;
const NOTICE_MS = 5000;
const HIGHLIGHT_MS = 2000;

const NO_IDS: ReadonlySet<string> = new Set();

export function useFriends(): FriendsState {
  const [friends, setFriends] = useState<Friend[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(ENABLED);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<FriendsNotice | null>(null);
  const [highlightIds, setHighlightIds] = useState<ReadonlySet<string>>(NO_IDS);
  const alive = useRef(true);
  // Only the newest read may write: a slow one must not undo a fresher one.
  const latest = useRef(0);
  // The list last put on screen; null until a read has worked, so the first
  // one is never announced as news.
  const committed = useRef<Friend[] | null>(null);
  const noticeId = useRef(0);
  const noticeTimer = useRef<number>();
  const highlightTimer = useRef<number>();

  const announce = useCallback((changes: FriendChanges) => {
    setNotice({ id: ++noticeId.current, text: changes.text });
    window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), NOTICE_MS);

    setHighlightIds((current) => new Set([...current, ...changes.ids]));
    window.clearTimeout(highlightTimer.current);
    highlightTimer.current = window.setTimeout(() => setHighlightIds(NO_IDS), HIGHLIGHT_MS);
  }, []);

  const reload = useCallback(async () => {
    if (!ENABLED) return;
    const ticket = ++latest.current;
    // Each half is kept on its own: losing the profile must not hide the friends.
    const [list, mine] = await Promise.allSettled([listFriends(), getProfile()]);
    if (!alive.current || ticket !== latest.current) return;
    if (list.status === "fulfilled") {
      const changes = committed.current && describeChanges(committed.current, list.value);
      committed.current = list.value;
      setFriends(list.value);
      if (changes) announce(changes);
    }
    if (mine.status === "fulfilled") setProfile(mine.value);
    const failure = list.status === "rejected" ? list.reason : mine.status === "rejected" ? mine.reason : null;
    setError(failure ? (failure instanceof Error ? failure.message : String(failure)) : null);
    setLoading(false);
  }, [announce]);

  // First read, foreground reads, and the slow poll while the tab is visible.
  useEffect(() => {
    alive.current = true;
    void reload();

    let poll: number | undefined;
    const stop = () => window.clearInterval(poll);
    const start = () => {
      stop();
      poll = window.setInterval(() => void reload(), POLL_MS);
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void reload();
        start();
      } else {
        stop();
      }
    };
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      alive.current = false;
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
      window.clearTimeout(noticeTimer.current);
      window.clearTimeout(highlightTimer.current);
    };
  }, [reload]);

  // Realtime: the friendships themselves. The channel is created per mount, so
  // StrictMode's second mount replaces the first instead of doubling it.
  useEffect(() => {
    if (!ENABLED) return;
    let debounce: number | undefined;
    let status: string | null = null;
    let active = true;
    const schedule = () => {
      window.clearTimeout(debounce);
      debounce = window.setTimeout(() => active && void reload(), DEBOUNCE_MS);
    };

    let unsubscribe = () => {};
    try {
      unsubscribe = subscribeToFriendships(schedule, (next) => {
        // Joining again after a drop: whatever happened meanwhile was never delivered.
        if (next === "SUBSCRIBED" && status !== null && status !== "SUBSCRIBED") schedule();
        status = next;
      });
    } catch {
      // No client (missing env) is already reported by the read itself; the poll covers the rest.
    }

    return () => {
      active = false;
      window.clearTimeout(debounce);
      unsubscribe();
    };
  }, [reload]);

  const sendRequest = useCallback(
    async (code: string): Promise<SendOutcome> => {
      const before = new Map((committed.current ?? []).map((friend) => [friend.id, friend.relation]));
      const result = await sendFriendRequest(code);
      await reload();
      // The API does not say who it was; the row that is new (or just became a friend) does.
      const relation = result === "accepted" ? "friend" : "outgoing";
      const friend =
        (committed.current ?? []).find(
          (row) => row.relation === relation && before.get(row.id) !== relation,
        ) ?? null;
      return { result, friend };
    },
    [reload],
  );

  const respond = useCallback(
    async (friendshipId: string, accept: boolean) => {
      await respondFriendRequest(friendshipId, accept);
      await reload();
    },
    [reload],
  );

  const remove = useCallback(
    async (friendshipId: string) => {
      await removeFriendship(friendshipId);
      await reload();
    },
    [reload],
  );

  const saveAlias = useCallback(async (alias: string) => {
    const saved = await setAlias(alias);
    if (alive.current) setProfile(saved);
  }, []);

  const saveAvatar = useCallback(async (avatar: string | null) => {
    const saved = await setAvatar(avatar);
    if (alive.current) setProfile(saved);
  }, []);

  return {
    friends,
    profile,
    loading,
    error,
    notice,
    highlightIds,
    reload,
    sendRequest,
    respond,
    remove,
    saveAlias,
    saveAvatar,
  };
}
