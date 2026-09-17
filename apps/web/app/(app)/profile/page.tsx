"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "@/lib/session";
import { api, ApiError } from "@/lib/api-client";
import type { PublicProfile } from "@/lib/types";
import { Card, ErrorState, LoadingState } from "@/components/states";

export default function ProfilePage() {
  const { session } = useSession();
  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!session?.username) return;
    setError(null);
    try {
      // Real endpoint: GET /profile/{username} (API Spec V2 §6), public/read-only.
      // Never returns journal/drafts/broker/portfolio data — those fields
      // don't exist on this response at all.
      const data = await api.get<PublicProfile>(`/profile/${session.username}`);
      setProfile(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your profile.");
    }
  }, [session?.username]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-2xl">Profile</h1>
        <p className="text-sm text-ink-soft">Your public identity in the community.</p>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}
      {!error && profile === null && <LoadingState label="Loading profile…" />}

      {!error && profile && (
        <>
          <Card>
            <div className="font-display text-xl">@{profile.username}</div>
            <div className="text-sm text-ink-soft">Qfinera community identity — your real name is never shown here.</div>
            {profile.bio && <p className="text-sm mt-3">{profile.bio}</p>}
          </Card>

          <div className="grid grid-cols-3 gap-3">
            <Card className="text-center">
              <div className="font-display text-2xl">{profile.published_posts_count}</div>
              <div className="text-xs text-ink-soft uppercase tracking-wide mt-1">Posts</div>
            </Card>
            <Card className="text-center">
              <div className="font-display text-2xl">{profile.published_theses_count}</div>
              <div className="text-xs text-ink-soft uppercase tracking-wide mt-1">Theses</div>
            </Card>
            <Card className="text-center">
              <div className="font-display text-2xl">{profile.contribution_points}</div>
              <div className="text-xs text-ink-soft uppercase tracking-wide mt-1">Q-Points</div>
            </Card>
          </div>

          <div>
            <h2 className="font-display text-lg mb-3">Recent activity</h2>
            {profile.recent_posts.length === 0 ? (
              <p className="text-sm text-ink-soft">No public posts yet.</p>
            ) : (
              <div className="space-y-3">
                {profile.recent_posts.map((p) => (
                  <Card key={p.id}>
                    <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--brass)" }}>
                      {p.post_type}
                    </span>
                    <p className="text-sm mt-1 whitespace-pre-wrap">{p.content}</p>
                    <p className="text-xs text-ink-soft mt-2">{new Date(p.created_at).toLocaleDateString()}</p>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
