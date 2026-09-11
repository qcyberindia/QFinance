"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import type { BookmarkItem, BookmarkListResponse } from "@/lib/types";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/states";

export default function SavedPage() {
  const [items, setItems] = useState<BookmarkItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await api.get<BookmarkListResponse>("/community/bookmarks");
      setItems(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your saved posts.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRemove(postId: string) {
    try {
      await api.delete(`/community/bookmarks/${postId}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove this bookmark.");
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-2xl">Saved</h1>
        <p className="text-sm text-ink-soft">Posts you&apos;ve bookmarked — private to you.</p>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}
      {!error && items === null && <LoadingState label="Loading saved posts…" />}
      {!error && items !== null && items.length === 0 && (
        <EmptyState title="Nothing saved yet" body="Bookmark posts from Community to find them here later." />
      )}
      {!error && items !== null && items.length > 0 && (
        <div className="space-y-3">
          {items.map((item) => (
            <Card key={item.post_id}>
              <Link href={`/community/${item.post_id}`} className="text-sm block mb-2">{item.post_summary}</Link>
              <div className="flex items-center justify-between">
                <span className="text-xs text-ink-soft">
                  Saved {new Date(item.bookmarked_at).toLocaleDateString()}
                </span>
                <button className="text-xs" style={{ color: "#9C4B3F" }} onClick={() => handleRemove(item.post_id)}>
                  Remove
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
