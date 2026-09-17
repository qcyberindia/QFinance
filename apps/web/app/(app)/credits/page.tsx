"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { CreditsSummary } from "@/lib/types";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/states";

function formatPaise(paise: number): string {
  return `₹${(paise / 100).toFixed(0)}`;
}

export default function CreditsPage() {
  const [summary, setSummary] = useState<CreditsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      // Real endpoint: GET /credits/me (API Spec V2 §8).
      const data = await api.get<CreditsSummary>("/credits/me");
      setSummary(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your credits.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-2xl">Credits &amp; Premium</h1>
        <p className="text-sm text-ink-soft">
          Community contribution earns Q-Points toward your next Premium period.
        </p>
      </div>

      <Card>
        <div className="text-xs text-ink-soft uppercase tracking-wide">Current balance</div>
        <div className="font-display text-3xl mt-1">
          {summary ? formatPaise(summary.balance_paise) : "—"}
        </div>
      </Card>

      <div>
        <h2 className="font-display text-lg mb-3">Contribution history</h2>
        {error && <ErrorState message={error} onRetry={load} />}
        {!error && summary === null && <LoadingState label="Loading credit history…" />}
        {!error && summary !== null && summary.entries.length === 0 && (
          <EmptyState
            title="No contributions yet"
            body="Publish a thesis, get engagement, or receive a rating to start earning Q-Points."
          />
        )}
        {!error && summary !== null && summary.entries.length > 0 && (
          <Card className="!p-0 overflow-hidden">
            <table className="w-full text-sm">
              <tbody>
                {summary.entries.map((entry, i) => (
                  <tr key={i} className="border-b" style={{ borderColor: "var(--line)" }}>
                    <td className="px-4 py-3">
                      <div>{entry.reason}</div>
                      <div className="text-xs text-ink-soft">{new Date(entry.created_at).toLocaleDateString()}</div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono">+{formatPaise(entry.amount_paise)}</td>
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
