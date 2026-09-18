/**
 * Relative/absolute timestamp formatting — Community thread-redesign Phase 1/5.
 * No backend dependency; works off the existing created_at ISO string every
 * Post/Comment already returns. User's local timezone (Date parses ISO UTC,
 * toLocaleString renders in the browser's own timezone automatically).
 */
export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 30) return "Just now";
  if (diffMin < 1) return `${diffSec}s ago`;
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  if (diffDay === 1) return "Yesterday";
  if (diffDay < 7) return `${diffDay}d ago`;

  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

/** Full, exact timestamp for a hover/title attribute — never hides anything
 * private (just the same created_at, rendered in full, in the viewer's own
 * local timezone — no server-side/account timezone info is involved). */
export function formatExactTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}
