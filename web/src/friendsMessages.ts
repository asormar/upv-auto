// Wording the friends dialog adds on top of what the API says. Kept out of
// the API layer on purpose: these are UI decisions, the API strings stay as
// they are.

import type { SendOutcome } from "./api/useFriends";

export const CODE_LENGTH = 8;
export const OWN_CODE_MESSAGE = "Ese es tu propio código.";

export function messageOf(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

/** A second, muted line telling the user what to do about an error, if there is something. */
export function guidanceFor(message: string): string | null {
  return message.includes("No existe ningún usuario")
    ? "Revisa que no falte ninguna letra o pídele el código otra vez."
    : null;
}

/** Names the person when the list showed who the request went to. */
export function sentText({ result, friend }: SendOutcome): string {
  if (result === "accepted") return friend ? `Ya sois amigos: ${friend.alias}` : "Ya sois amigos";
  return friend ? `Solicitud enviada a ${friend.alias}` : "Solicitud enviada";
}

/** "K7M2QXAB" as "K7M2 QXAB": easier to read out and to compare by eye. */
export function groupCode(code: string): string {
  return code.replace(/(.{4})(?=.)/g, "$1 ");
}
