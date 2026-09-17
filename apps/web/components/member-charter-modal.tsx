"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api-client";

const CHARTER_PRINCIPLES = [
  "Share your own reasoning, not unverified tips or guaranteed-return claims.",
  "Disclose your position or conflict of interest when it's relevant to what you post.",
  "Cite sources for factual claims wherever practical.",
  "Treat other members' theses as ideas to challenge respectfully, not attacks.",
  "This community does not provide personalized investment advice — nothing here is a buy/sell/hold instruction.",
];

export function MemberCharterModal({
  onAcknowledged,
  onCancel,
}: {
  onAcknowledged: () => void;
  onCancel: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAcknowledge() {
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/users/me/acknowledge-charter");
      onAcknowledged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record your acknowledgment. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(43,38,33,.45)" }}
    >
      <div className="qf-card w-full max-w-md p-6">
        <h2 className="font-display text-xl mb-1">Member Charter</h2>
        <p className="text-sm text-ink-soft mb-4">
          Before you post for the first time, please read and acknowledge the community's ground rules.
        </p>
        <ul className="text-sm space-y-2 mb-5 list-disc pl-5">
          {CHARTER_PRINCIPLES.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
        {error && <p className="text-sm mb-3" style={{ color: "#9C4B3F" }}>{error}</p>}
        <div className="flex gap-3">
          <button className="qf-btn-ghost" onClick={onCancel} disabled={submitting}>
            Not now
          </button>
          <button className="qf-btn-primary" onClick={handleAcknowledge} disabled={submitting}>
            {submitting ? "Saving…" : "I Acknowledge — Continue"}
          </button>
        </div>
      </div>
    </div>
  );
}
