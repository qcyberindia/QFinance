"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import { useSession } from "@/lib/session";
import type { ConnectionStatusResponse, MyProfile } from "@/lib/types";
import { AiConnectionSettings } from "@/components/ai-connection-settings";
import s from "@/components/profile/profile.module.css";

const BROKER_STATUS: Record<string, string> = {
  connected: "Connected (read-only)",
  error: "Session expired — reconnect from Portfolio",
  disconnected: "Not connected",
  not_connected: "Not connected",
};

/**
 * Settings — only settings the product actually supports. No payment,
 * subscription or trading settings exist in Qfinera. Theme follows the
 * device setting (there is no in-app theme override).
 */
export default function SettingsPage() {
  const { logout } = useSession();
  const router = useRouter();
  const [me, setMe] = useState<MyProfile | null>(null);
  const [broker, setBroker] = useState<ConnectionStatusResponse | null | undefined>(undefined);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    api.get<MyProfile>("/users/me/profile").then(setMe).catch(() => setMe(null));
    api.get<ConnectionStatusResponse>("/portfolio/connection").then(setBroker).catch(() => setBroker(null));
  }, []);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <>
      <section className={s.section} aria-labelledby="set-account">
        <h2 id="set-account" className="qf-section-title mb-3">Account</h2>
        <dl className={s.facts}>
          <dt>Email</dt>
          <dd>{me ? <>{me.email} <span className="qf-secondary">· {me.email_verified ? "verified" : "not verified"}</span></> : "—"}</dd>
          <dt>Profile details</dt>
          <dd><Link href="/profile/edit" className="underline">Edit username, bio and name</Link></dd>
        </dl>
        <p className={s.hint}>Email changes aren&apos;t available in Qfinera yet.</p>
      </section>

      <section className={s.section} aria-labelledby="set-ai">
        <h2 id="set-ai" className="qf-section-title mb-3">AI provider</h2>
        <p className="qf-secondary mb-3">Your own AI key powers the Research Assistant. It&apos;s stored encrypted and never shown again.</p>
        <AiConnectionSettings />
      </section>

      <section className={s.section} aria-labelledby="set-broker">
        <h2 id="set-broker" className="qf-section-title mb-3">Connected broker</h2>
        <dl className={s.facts}>
          <dt>Zerodha</dt>
          <dd aria-live="polite">
            {broker === undefined ? "Checking…" : broker === null ? "Status unavailable" : BROKER_STATUS[broker.status] ?? broker.status}
          </dd>
        </dl>
        <p className={s.hint}>Read-only — Qfinera can view holdings but can never place trades or change your account.</p>
        <Link href="/portfolio" className="qf-btn-ghost mt-3" style={{ textDecoration: "none" }}>Manage in Portfolio</Link>
      </section>

      <section className={s.section} aria-labelledby="set-privacy">
        <h2 id="set-privacy" className="qf-section-title mb-3">Privacy</h2>
        <div className={s.notice}>
          Other members can see your username, bio, public posts, theses and Q-Points. They can never see:
          <ul>
            <li>your name or email</li>
            <li>your portfolio, holdings or broker connection</li>
            <li>your research drafts, Journal or Saved items</li>
          </ul>
        </div>
      </section>

      <section className={s.section} aria-labelledby="set-appearance">
        <h2 id="set-appearance" className="qf-section-title mb-3">Appearance</h2>
        <p className="qf-secondary">Qfinera follows your device&apos;s light or dark mode setting.</p>
      </section>

      <section className={s.section} aria-labelledby="set-session">
        <h2 id="set-session" className="qf-section-title mb-3">Session</h2>
        <button type="button" className="qf-btn-ghost" onClick={handleLogout} disabled={loggingOut} aria-busy={loggingOut}>
          {loggingOut ? "Logging out…" : "Log out"}
        </button>
      </section>
    </>
  );
}
