import type { ConnectionState } from "./use-live-channel";

export function LiveConnectionLabel({ state }: { state: ConnectionState }) {
  const label =
    state === "live"
      ? "Live updates on"
      : state === "connecting"
        ? "Connecting live updates…"
        : "Polling every 5 seconds";
  return (
    <p role="status" aria-live="polite" className="text-xs text-steel">
      {label}
    </p>
  );
}
