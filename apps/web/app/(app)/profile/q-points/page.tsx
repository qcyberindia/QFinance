"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type { QPointsSummary } from "@/lib/types";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/states";

/**
 * Q-Points — a reputation/contribution score earned from useful Community
 * participation. Not money: no currency value, no balance to spend, no
 * redemption or transfer. Reads GET /credits/me (points only).
 */
export default function QPointsPage() {
  const [summary, setSummary] = useState<QPointsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setSummary(await api.get<QPointsSummary>("/credits/me"));
    } catch {
      setError("We couldn't load your Q-Points. Try again.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-5 mt-4">
      <div>
        <h2 className="qf-section-title">Q-Points</h2>
        <p className="qf-secondary mt-1">
          Q-Points represent your contribution and reputation within Qfinera — earned when you publish a thesis
          and when other members engage with your posts. They have no monetary value and cannot be spent,
          redeemed, transferred, withdrawn, or converted to rupees.
        </p>
      </div>

      <Card>
        <div className="qf-caption">Your Q-Points</div>
        <div className="font-display text-3xl mt-1" aria-live="polite">
          {summary ? summary.points.toLocaleString() : "—"}
        </div>
      </Card>

      <div>
        <h3 className="font-display text-lg mb-3">Contribution history</h3>
        {error && <ErrorState message={error} onRetry={load} />}
        {!error && summary === null && <LoadingState label="Loading your contributions…" />}
        {!error && summary !== null && summary.entries.length === 0 && (
          <EmptyState
            title="No contributions yet"
            body="Publish a thesis or get engagement on your posts to start earning Q-Points."
          />
        )}
        {!error && summary !== null && summary.entries.length > 0 && (
          <Card className="!p-0 overflow-hidden">
            <table className="w-full text-sm">
              <caption className="sr-only">Q-Point contribution history</caption>
              <tbody>
                {summary.entries.map((entry, i) => (
                  <tr key={i} className="border-b" style={{ borderColor: "var(--line)" }}>
                    <td className="px-4 py-3">
                      <div>{entry.reason}</div>
                      <div className="qf-secondary" style={{ fontSize: 12 }}>{new Date(entry.created_at).toLocaleDateString()}</div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono whitespace-nowrap">
                      +{entry.points} <span className="qf-secondary">pts</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  );
}
