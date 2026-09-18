/**
 * Deterministic pseudonymous avatar — Community Phase 1.
 *
 * Pure function of the username string: same username always produces the
 * same avatar, no randomness, no external service, no network call, no way
 * to reconstruct a real photo/appearance. A small FNV-1a-style hash picks a
 * hue and a simple abstract geometric pattern; the rendered mark is the
 * user's own first letter/symbol, never their real name (this component
 * never receives a real name — only `username`, which is all the backend's
 * PublicProfileResponse/AuthorRef ever expose).
 */

const PATTERNS = ["circle", "triangle", "diamond", "hex"] as const;
type Pattern = (typeof PATTERNS)[number];

function hashString(input: string): number {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash);
}

export interface AvatarIdentity {
  hue: number;
  pattern: Pattern;
  glyph: string;
}

export function deriveAvatarIdentity(seed: string): AvatarIdentity {
  const h = hashString(seed || "?");
  const hue = h % 360;
  const pattern = PATTERNS[h % PATTERNS.length];
  const glyph = (seed || "?").replace(/^@/, "").charAt(0).toUpperCase() || "?";
  return { hue, pattern, glyph };
}
