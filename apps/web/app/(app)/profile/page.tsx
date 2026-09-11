"use client";

import { useSession } from "@/lib/session";
import { Card, NotAvailableYet } from "@/components/states";

export default function ProfilePage() {
  const { session } = useSession();

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-2xl">Profile</h1>
        <p className="text-sm text-ink-soft">Your public identity in the community.</p>
      </div>

      <Card>
        <div className="text-sm text-ink-soft">Signed in as</div>
        <div className="font-display text-lg">{session?.email}</div>
        <div className="text-xs text-ink-soft mt-1">{session?.effective_tier} tier</div>
      </Card>

      {/* GENUINE BACKEND GAP: API Specification V2 §6 (GET /profile/{username})
          is specified but not yet implemented in the backend — see
          work_memory.md. Once it ships, this page should fetch it and show
          published posts/theses/contribution summary, never journal/drafts/
          broker/portfolio data (PRD V2 §4.7). */}
      <NotAvailableYet feature="Public profile (published posts, theses, contribution summary)" />
    </div>
  );
}
