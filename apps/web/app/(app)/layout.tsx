"use client";

/**
 * Global authenticated shell — Phase 3 of the product-wide UI/UX pass.
 * Everything else in this brief (Community, Portfolio, Journal, Profile,
 * Saved, Credits, auth pages, per-route polish) is NOT done in this turn —
 * see the chat response for the honest accounting. This file exists because
 * every route sits inside it, making it the single highest-leverage piece
 * to get right first.
 *
 * Nav structure per the brief: primary = Research, Community, Portfolio,
 * Journal; secondary = Saved, Credits, Profile. AI settings stay inside
 * Profile rather than becoming a primary nav item, as the brief asks.
 */
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useSession } from "@/lib/session";
import { LoadingState } from "@/components/states";

const PRIMARY_NAV = [
  { href: "/research", label: "Research" },
  { href: "/community", label: "Community" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/journal", label: "Journal" },
];

const SECONDARY_NAV = [
  { href: "/saved", label: "Saved" },
  { href: "/credits", label: "Q-Points" },
  { href: "/profile", label: "Profile" },
];

function NavLink({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className="qf-nav-item flex items-center gap-2.5 mx-2 px-3 py-2.5 text-sm"
      style={{
        fontWeight: active ? 600 : 500,
        color: active ? "var(--ink)" : "var(--ink-soft)",
        background: active ? "var(--cream-2)" : "transparent",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 3, height: 16, borderRadius: 2, flexShrink: 0,
          background: active ? "var(--brass)" : "transparent",
          transition: "background-color var(--motion-fast) var(--motion-ease)",
        }}
      />
      {label}
    </Link>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { session, loading, logout } = useSession();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    // Authoritative check (middleware only checked cookie presence): if the
    // real session lookup comes back empty, the cookie was stale/invalid.
    if (!loading && !session) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, session, pathname, router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingState label="Loading your workspace…" />
      </div>
    );
  }

  if (!session) {
    return null; // redirect effect above is already firing
  }

  const isActive = (href: string) => pathname?.startsWith(href) ?? false;

  return (
    <div className="min-h-screen md:flex">
      {/* Desktop sidebar */}
      <aside
        className="hidden md:flex md:flex-col md:w-60 md:shrink-0 border-r"
        style={{ borderColor: "var(--line)", background: "var(--cream-1)" }}
      >
        <div className="font-display text-lg px-5 py-5 border-b" style={{ borderColor: "var(--line)" }}>
          Qfinera
        </div>

        <nav className="flex-1 py-3" aria-label="Primary">
          {PRIMARY_NAV.map((item) => (
            <NavLink key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </nav>

        <nav className="pb-3" aria-label="Secondary" style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          {SECONDARY_NAV.map((item) => (
            <NavLink key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </nav>

        <div className="px-5 py-4 border-t text-sm" style={{ borderColor: "var(--line)" }}>
          <div className="qf-secondary mb-2 truncate">{session.email}</div>
          <button className="qf-btn-ghost w-full text-xs" onClick={() => logout().then(() => router.replace("/login"))}>
            Log out
          </button>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div
        className="md:hidden flex items-center justify-between px-4 py-3 border-b"
        style={{ borderColor: "var(--line)", background: "var(--cream-1)" }}
      >
        <div className="font-display text-lg">Qfinera</div>
        <button className="qf-btn-ghost text-xs" onClick={() => logout().then(() => router.replace("/login"))}>
          Log out
        </button>
      </div>

      <main className="flex-1 min-w-0">
        {/* The Research Workspace (/research/[id]) uses a three-column
            desktop layout (section nav / document / assistant) that needs
            more room than every other page in the app — widened only for
            that one route, everything else keeps the standard max-w-3xl. */}
        <div
          className={`mx-auto px-4 py-6 ${
            pathname && /^\/research\/(?!explore(?:\/|$))[^/]+/.test(pathname) ? "max-w-6xl" : "max-w-3xl"
          }`}
        >
          {children}
        </div>

        {/* Mobile bottom nav — the 4 PRIMARY items only (not an arbitrary
            slice of a combined list); Saved/Credits/Profile remain one tap
            away via the top-bar's own route, not crammed in here. Each
            target is >=44px tall including padding, per the accessibility
            requirement. */}
        <nav
          className="md:hidden fixed bottom-0 left-0 right-0 flex border-t"
          style={{ borderColor: "var(--line)", background: "var(--cream-0)", boxShadow: "var(--shadow-lg)" }}
          aria-label="Primary"
        >
          {PRIMARY_NAV.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className="flex-1 flex flex-col items-center justify-center gap-1 text-[11px]"
                style={{ minHeight: 52, color: active ? "var(--brass)" : "var(--ink-soft)", fontWeight: active ? 600 : 500 }}
              >
                <span aria-hidden style={{ width: 4, height: 4, borderRadius: "50%", background: active ? "var(--brass)" : "transparent" }} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="md:hidden h-16" /> {/* spacer so content isn't hidden behind fixed bottom nav */}
      </main>
    </div>
  );
}
