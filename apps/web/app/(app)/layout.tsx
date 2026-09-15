"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useSession } from "@/lib/session";
import { LoadingState } from "@/components/states";

const NAV_ITEMS = [
  { href: "/community", label: "Community" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/journal", label: "Journal" },
  { href: "/research", label: "My Research" },
  { href: "/saved", label: "Saved" },
  { href: "/profile", label: "Profile" },
  { href: "/credits", label: "Credits" },
];

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

  return (
    <div className="min-h-screen md:flex">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex md:flex-col md:w-60 md:shrink-0 border-r" style={{ borderColor: "var(--line)", background: "var(--cream-1)" }}>
        <div className="font-display text-lg px-5 py-5 border-b" style={{ borderColor: "var(--line)" }}>
          Qfinera
        </div>
        <nav className="flex-1 py-3">
          {NAV_ITEMS.map((item) => {
            const active = pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className="block px-5 py-2.5 text-sm"
                style={{
                  fontWeight: active ? 600 : 400,
                  color: active ? "var(--ink)" : "var(--ink-soft)",
                  borderLeft: active ? "2px solid var(--brass)" : "2px solid transparent",
                  background: active ? "rgba(168,134,62,.06)" : "transparent",
                }}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="px-5 py-4 border-t text-sm" style={{ borderColor: "var(--line)" }}>
          <div className="text-ink-soft mb-2 truncate">{session.email}</div>
          <button className="qf-btn-ghost w-full text-xs" onClick={() => logout().then(() => router.replace("/login"))}>
            Log out
          </button>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="md:hidden flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--line)", background: "var(--cream-1)" }}>
        <div className="font-display text-lg">
          Qfinera
        </div>
        <button className="qf-btn-ghost text-xs" onClick={() => logout().then(() => router.replace("/login"))}>
          Log out
        </button>
      </div>

      <main className="flex-1 min-w-0">
        <div className="max-w-3xl mx-auto px-4 py-6">{children}</div>

        {/* Mobile bottom nav */}
        <nav
          className="md:hidden fixed bottom-0 left-0 right-0 flex justify-around border-t py-2"
          style={{ borderColor: "var(--line)", background: "var(--cream-0)" }}
        >
          {NAV_ITEMS.slice(0, 5).map((item) => {
            const active = pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className="text-[11px] px-2 py-1 text-center"
                style={{ color: active ? "var(--brass)" : "var(--ink-soft)", fontWeight: active ? 600 : 400 }}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="md:hidden h-14" /> {/* spacer so content isn't hidden behind fixed bottom nav */}
      </main>
    </div>
  );
}
