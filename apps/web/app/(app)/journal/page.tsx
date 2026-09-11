"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { JournalEntry, JournalEntryListResponse } from "@/lib/types";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/states";

const ENTRY_TYPES = ["decision", "reasoning", "observation", "note"] as const;

export default function JournalPage() {
  const [entries, setEntries] = useState<JournalEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [entryType, setEntryType] = useState<(typeof ENTRY_TYPES)[number]>("note");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await api.get<JournalEntryListResponse>("/journal");
      setEntries(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your journal.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    setSubmitting(true);
    try {
      await api.post("/journal", { content, entry_type: entryType });
      setContent("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save this entry.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.delete(`/journal/${id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete this entry.");
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-2xl">Investment Journal</h1>
        <p className="text-sm text-ink-soft">
          Private by default — journal entries are never shown in Community.
        </p>
      </div>

      <Card>
        <form onSubmit={handleCreate} className="space-y-3">
          <div className="flex gap-2 flex-wrap">
            {ENTRY_TYPES.map((t) => (
              <button
                type="button"
                key={t}
                onClick={() => setEntryType(t)}
                className="text-xs font-semibold px-3 py-1.5 rounded-full capitalize"
                style={{
                  border: "1px solid var(--line)",
                  background: entryType === t ? "var(--ink)" : "transparent",
                  color: entryType === t ? "var(--cream-0)" : "var(--ink-soft)",
                }}
              >
                {t}
              </button>
            ))}
          </div>
          <textarea
            className="qf-input min-h-[80px]"
            placeholder="What are you thinking about?"
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <button type="submit" disabled={submitting || !content.trim()} className="qf-btn-primary">
            {submitting ? "Saving…" : "Save Entry"}
          </button>
        </form>
      </Card>

      {error && <ErrorState message={error} onRetry={load} />}
      {!error && entries === null && <LoadingState label="Loading journal…" />}
      {!error && entries !== null && entries.length === 0 && (
        <EmptyState title="Your journal is empty" body="Start documenting your investment decisions and reasoning." />
      )}
      {!error && entries !== null && entries.length > 0 && (
        <div className="space-y-3">
          {entries.map((entry) => (
            <Card key={entry.id}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--brass-dark, var(--brass))" }}>
                  {entry.entry_type}
                </span>
                <button className="text-xs" style={{ color: "#9C4B3F" }} onClick={() => handleDelete(entry.id)}>
                  Delete
                </button>
              </div>
              <p className="text-sm whitespace-pre-wrap">{entry.content}</p>
              <p className="text-xs text-ink-soft mt-2">{new Date(entry.created_at).toLocaleString()}</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
