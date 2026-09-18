import { deriveAvatarIdentity } from "@/lib/avatar";

export function Avatar({ username, size = 36 }: { username: string | null; size?: number }) {
  const { hue, pattern, glyph } = deriveAvatarIdentity(username || "?");
  const bg = `hsl(${hue}, 42%, 88%)`;
  const fg = `hsl(${hue}, 45%, 32%)`;
  const radius = pattern === "circle" ? "9999px" : pattern === "diamond" ? "22%" : pattern === "hex" ? "30%" : "28%";
  const rotate = pattern === "diamond" ? "rotate(45deg)" : "none";

  return (
    <div
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        minWidth: size,
        borderRadius: radius,
        background: bg,
        color: fg,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "'Fraunces', serif",
        fontWeight: 600,
        fontSize: size * 0.42,
        transform: rotate,
        flexShrink: 0,
      }}
    >
      <span style={{ transform: rotate === "none" ? "none" : "rotate(-45deg)" }}>{glyph}</span>
    </div>
  );
}
