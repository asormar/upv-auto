// Friends and the user's own profile. A friend changes their queue whenever
// they like and there is no Realtime for it, so the list is re-read on mount
// and each time the tab comes back to the foreground. Supabase only: under
// `VITE_BACKEND=local` there are no accounts and nothing is ever fetched.

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
  type Friend,
  type Profile,
} from "../api";

export interface FriendsState {
  friends: Friend[];
  profile: Profile | null;
  /** True until the first read settles; later refetches never set it. */
  loading: boolean;
  /** Why the last read failed. The data from the last good one stays on screen. */
  error: string | null;
  reload: () => Promise<void>;
  /** The actions below throw the API's Spanish message, for the caller to show
   * next to what the user was doing, and re-read the list when they succeed. */
  sendRequest: (code: string) => Promise<"requested" | "accepted">;
  respond: (friendshipId: string, accept: boolean) => Promise<void>;
  remove: (friendshipId: string) => Promise<void>;
  saveAlias: (alias: string) => Promise<void>;
  /** A data URL from `fileToAvatar`, or null to remove the photo. */
  saveAvatar: (avatar: string | null) => Promise<void>;
}

const ENABLED = BACKEND === "supabase";

export function useFriends(): FriendsState {
  const [friends, setFriends] = useState<Friend[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(ENABLED);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  // Only the newest read may write: a slow one must not undo a fresher one.
  const latest = useRef(0);

  const reload = useCallback(async () => {
    if (!ENABLED) return;
    const ticket = ++latest.current;
    // Each half is kept on its own: losing the profile must not hide the friends.
    const [list, mine] = await Promise.allSettled([listFriends(), getProfile()]);
    if (!alive.current || ticket !== latest.current) return;
    if (list.status === "fulfilled") setFriends(list.value);
    if (mine.status === "fulfilled") setProfile(mine.value);
    const failure = list.status === "rejected" ? list.reason : mine.status === "rejected" ? mine.reason : null;
    setError(failure ? (failure instanceof Error ? failure.message : String(failure)) : null);
    setLoading(false);
  }, []);

  useEffect(() => {
    alive.current = true;
    void reload();
    const onVisible = () => {
      if (document.visibilityState === "visible") void reload();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive.current = false;
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [reload]);

  const sendRequest = useCallback(
    async (code: string) => {
      const result = await sendFriendRequest(code);
      await reload();
      return result;
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

  return { friends, profile, loading, error, reload, sendRequest, respond, remove, saveAlias, saveAvatar };
}
