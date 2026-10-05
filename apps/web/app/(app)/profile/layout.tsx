"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Avatar } from "@/components/avatar";
import { useSession } from "@/lib/session";
import s from "@/components/profile/profile.module.css";

/**
 * Profile — the member's personal control center. One shell with its own
 * sub-navigation; each section is a route so it can be linked and the
 * browser back button works. Portfolio, Research and Community stay in the
 * primary navigation.
 */
const SECTIONS = [
  { href: "/profile", label: "Overview" },
  { href: "/profile/edit", label: "Edit profile" },
  { href: "/profile/saved", label: "Saved" },
  { href: "/profile/q-points", label: "Q-Points" },
  { href: "/profile/settings", label: "Settings" },
];

export default function ProfileLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { session } = useSession();
  return (
    <div className={s.touch}>
      <header className={s.header}>
        <Avatar username={session?.username ?? null} size={44} />
        <div className="min-w-0">
          <h1 className={s.handle}>{session?.username ? `@${session.username}` : "Profile"}</h1>
          <p className="qf-secondary">Your personal control center</p>
        </div>
      </header>
      <nav aria-label="Profile sections" className={s.subnav}>
        {SECTIONS.map((sec) => {
          const active = sec.href === "/profile" ? pathname === "/profile" : pathname?.startsWith(sec.href);
          return (
            <Link key={sec.href} href={sec.href} aria-current={active ? "page" : undefined}
              className={`${s.subnavLink} ${active ? s.subnavActive : ""}`}>
              {sec.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-2">{children}</div>
    </div>
  );
}
