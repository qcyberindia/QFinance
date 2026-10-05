"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api-client";
import type { MyProfile, PublicProfile } from "@/lib/types";
import { ErrorState } from "@/components/states";
import s from "@/components/profile/profile.module.css";

const EXPERIENCE: Record<string, string> = { beginner: "Beginner", intermediate: "Intermediate", advanced: "Advanced" };
const dateFmt = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }) : "—");

/**
 * Overview — what other members see (public profile, GET /profile/{username})
 * kept visibly separate from private account details only the member sees
 * (GET /users/me/profile). Includes the account summary: Q-Points are the
 * only "balance" in Qfinera and have no monetary value.
 */
export default function ProfileOverviewPage() {
  const [me, setMe] = useState<MyProfile | null>(null);
  const [pub, setPub] = useState<PublicProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const mine = await api.get<MyProfile>("/users/me/profile");
      setMe(mine);
      setPub(await api.get<PublicProfile>(`/profile/${encodeURIComponent(mine.username)}`));
    } catch {
      setError("We couldn't load your profile. Try again.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (error) return <div className="mt-4"><ErrorState message={error} onRetry={load} /></div>;
  if (!me || !pub) {
    return (
      <div aria-busy="true" aria-label="Loading profile" className="mt-4 space-y-3">
        <div className="qf-skeleton" style={{ height: 72, width: "100%" }} />
        <div className="qf-skeleton" style={{ height: 120, width: "100%" }} />
      </div>
    );
  }

  return (
    <>
      <section className={s.section} aria-labelledby="public-title">
        <div className={s.sectionHead}>
          <h2 id="public-title" className="qf-section-title">Public profile</h2>
          <span className={s.privateTag}>Visible to other members</span>
        </div>
        {pub.bio ? <p className="qf-body">{pub.bio}</p> : (
          <p className="qf-secondary">No bio yet. <Link href="/profile/edit" className="underline">Add one</Link> so others know what you research.</p>
        )}
        <div className={`${s.stats} mt-4`}>
          <div className={s.stat}><div className={s.statValue}>{pub.published_posts_count}</div><div className={s.statLabel}>Posts</div></div>
          <div className={s.stat}><div className={s.statValue}>{pub.published_theses_count}</div><div className={s.statLabel}>Theses</div></div>
          <div className={s.stat}><div className={s.statValue}>{pub.contribution_points}</div><div className={s.statLabel}>Q-Points</div></div>
        </div>
        <p className="qf-secondary mt-3" style={{ fontSize: 12.5 }}>
          Joined {dateFmt(pub.joined_at)}. Other members see your username, bio, activity and Q-Points — never your
          name, email, portfolio or private research.
        </p>
      </section>

      <section className={s.section} aria-labelledby="account-title">
        <div className={s.sectionHead}>
          <h2 id="account-title" className="qf-section-title">Private account details</h2>
          <span className={s.privateTag}>Only you can see this</span>
        </div>
        <dl className={s.facts}>
          <dt>Name</dt><dd>{me.name}</dd>
          <dt>Email</dt><dd>{me.email} {me.email_verified ? <span className="qf-secondary">· verified</span> : <span style={{ color: "var(--down)" }}>· not verified</span>}</dd>
          <dt>Experience</dt><dd>{me.experience_level ? EXPERIENCE[me.experience_level] : <span className="qf-secondary">Not set</span>}</dd>
          <dt>Member since</dt><dd>{dateFmt(me.joined_at)}</dd>
        </dl>
        <Link href="/profile/edit" className="qf-btn-ghost mt-4" style={{ textDecoration: "none" }}>Edit profile</Link>
      </section>

      <section className={s.section} aria-labelledby="summary-title">
        <div className={s.sectionHead}>
          <h2 id="summary-title" className="qf-section-title">Account summary</h2>
        </div>
        <dl className={s.facts}>
          <dt>Q-Points</dt><dd><strong>{me.contribution_points}</strong> <Link href="/profile/q-points" className="underline qf-secondary">History</Link></dd>
          <dt>Monetary balance</dt><dd>None — Qfinera has no wallet, no withdrawable funds and no paid plans.</dd>
        </dl>
        <p className="qf-secondary mt-3" style={{ fontSize: 12.5 }}>
          Q-Points reflect your contribution and reputation in Qfinera. They have no monetary value.
        </p>
      </section>

      <section className={s.section} aria-labelledby="activity-title">
        <div className={s.sectionHead}>
          <h2 id="activity-title" className="qf-section-title">Recent public activity</h2>
        </div>
        {pub.recent_posts.length === 0 ? (
          <p className="qf-secondary">No public posts yet. <Link href="/community" className="underline">Visit Community</Link></p>
        ) : (
          <ul className={s.list}>
            {pub.recent_posts.map((p) => (
              <li key={p.id} className={s.item}>
                <div className={s.itemBody}>
                  <span className={`${s.typeTag} ${p.post_type === "thesis" ? s.typeThesis : p.post_type === "question" ? s.typeQuestion : ""}`}>
                    {p.post_type === "question" ? "Question" : p.post_type === "thesis" ? "Thesis" : "Discussion"}
                  </span>
                  <Link href={`/community/${p.id}`} className={`${s.itemTitle} block mt-1`}>
                    {p.content.length > 160 ? `${p.content.slice(0, 160)}…` : p.content}
                  </Link>
                  <div className={s.itemMeta}>{dateFmt(p.created_at)}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
