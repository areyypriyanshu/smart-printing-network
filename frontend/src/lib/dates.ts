const istDateTime = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Kolkata",
});

/** Format an ISO timestamp in the shop's timezone. */
export function formatIstDateTime(iso: string): string {
  return `${istDateTime.format(new Date(iso))} IST`;
}

/** Whole minutes since an ISO timestamp, never negative. */
export function minutesSince(iso: string, now: Date): number {
  const elapsed = now.getTime() - new Date(iso).getTime();
  return Math.max(0, Math.floor(elapsed / 60_000));
}

/** "3 minutes ago", "1 hour ago", "just now". */
export function relativeTime(iso: string, now: Date): string {
  const minutes = minutesSince(iso, now);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
