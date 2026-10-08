import { Alert } from "./icons";

/** The one place an error shows in the friends dialog: under the control that caused it. */
export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="authgate-banner error" role="alert">
      <Alert size={14} />
      <span>{message}</span>
    </p>
  );
}
