// What changed in the friends list between two reads, as a sentence to
// announce. Pure: no I/O, no framework.
//
// Only what the user did not do themselves is worth interrupting for, and
// that is exactly two things: somebody asked to be their friend, or somebody
// accepted theirs. Everything else (accepting, declining, removing, sending)
// is the user's own action and already has its own feedback.

import type { Friend } from "./api/types";

export interface FriendChanges {
  text: string;
  /** Friendship ids behind the sentence, for the list to point at. */
  ids: string[];
}

export function describeChanges(previous: Friend[], next: Friend[]): FriendChanges | null {
  const before = new Map(previous.map((friend) => [friend.id, friend.relation]));
  const asked = next.filter((friend) => friend.relation === "incoming" && !before.has(friend.id));
  const accepted = next.filter(
    (friend) => friend.relation === "friend" && before.get(friend.id) === "outgoing",
  );

  const parts: string[] = [];
  if (asked.length === 1) parts.push(`${asked[0].alias} te ha enviado una solicitud de amistad`);
  else if (asked.length > 1) parts.push(`${asked.length} solicitudes de amistad nuevas`);
  if (accepted.length === 1) parts.push(`${accepted[0].alias} ha aceptado tu solicitud`);
  else if (accepted.length > 1) parts.push(`${accepted.length} personas han aceptado tus solicitudes`);

  if (parts.length === 0) return null;
  return { text: parts.join(". "), ids: [...asked, ...accepted].map((friend) => friend.id) };
}
