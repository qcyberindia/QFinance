"use client";

/**
 * Research Library / Explore — MUST HAVE MVP feature (PRD §6 "Research
 * Library: browse/search company & industry research"). Calls two already-
 * existing, already-built backend endpoints only: `GET /research/library`
 * (default browse) and `GET /research/search?q=` (search box below) — no
 * new backend route, no new schema, no duplicate of `/research/mine`.
 * Tier gating (`preview: true` items) is decided entirely server-side
 * (`research/service.py`); this page only renders whichever shape it gets.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import type { LibraryItem, LibraryListResponse, LibraryPreviewItem } from "@/lib/types";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/states";

function isFullItem(item: LibraryItem | LibraryPreviewItem): item is LibraryItem {
  return item.preview !== true;
}

export default function ResearchExplorePage() {
  const [items, setItems] = useState<(LibraryItem | LibraryPreviewItem)[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadBrowse = useCallback(async () => {
    setError(null);
    try {
      const data = await api.get<LibraryListResponse>("/research/library?page_size=30");
      setItems(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the research library.");
    }
  }, []);

  const runSearch = useCallback(async (q: string) => {
    setError(null);
    try {
      const data = await api.get<LibraryListResponse>(`/research/search?q=${encodeURIComponent(q)}&page_size=30`);
      setItems(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed.");
    }
  }, []);

  useEffect(() => {
    loadBrowse();
  }, [loadBrowse]);

  function handleQueryChange(value: string) {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const trimmed = value.trim();
      if (trimmed.length === 0) {
        loadBrowse();
      } else {
        setItems(null);
        runSearch(trimmed);
      }
    }, 350);
  }

  function retry() {
    if (query.trim()) runSearch(query.trim());
    else loadBrowse();
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl">Explore Research</h1>
          <p className="text-sm text-ink-soft mt-1">Published research from across the community.</p>
        </div>
        <Link href="/research" className="text-xs text-ink-soft hover:underline">
          ← My Research
        </Link>
      </div>

      <input
        className="qf-input"
        placeholder="Search by title, business description, or tag…"
        value={query}
        onChange={(e) => handleQueryChange(e.target.value)}
        aria-label="Search research library"
      />

      {error && <ErrorState message={error} onRetry={retry} />}
      {!error && items === null && <LoadingState label={query.trim() ? "Searching…" : "Loading the research library…"} />}
      {!error && items !== null && items.length === 0 && (
        <EmptyState
          title={query.trim() ? "No matching research" : "No published research yet"}
          body={query.trim() ? "Try a different search term." : "Published research from members will appear here."}
        />
      )}
      {!error && items !== null && items.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {items.map((item) => {
            const full = isFullItem(item);
            const content = (
              <Card className="qf-clickable h-full flex flex-col">
                <div className="flex items-center justify-between mb-1 gap-2">
                  <span className="text-xs text-ink-soft truncate">
                    {full ? (item.company.name ?? "Unknown company") : "Core research"}
                  </span>
                  {item.access_tier === "core" && !full && (
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full shrink-0"
                      style={{ border: "1px solid var(--brass)", color: "var(--brass-dark)" }}
                    >
                      Core
                    </span>
                  )}
                </div>
                <div className="font-display text-base">{item.title}</div>
                <p className="text-sm text-ink-soft line-clamp-2 flex-1">{item.summary}</p>
                {full && (
                  <p className="text-xs text-ink-soft mt-2">
                    {item.author.username ?? "Member"} · {item.source_count} source{item.source_count === 1 ? "" : "s"}
                    {item.industry ? ` · ${item.industry}` : ""}
                  </p>
                )}
                {full && (
                  <p className="text-xs mt-2 font-semibold" style={{ color: "var(--brass-dark)" }}>Open →</p>
                )}
              </Card>
            );
            // A preview item has no route this viewer is entitled to open
            // (GET /research/{id} would 404/403 for them server-side) — it
            // renders as a non-interactive teaser, not a misleading link.
            return full ? (
              <Link key={item.id} href={`/research/${item.id}`} className="block">
                {content}
              </Link>
            ) : (
              <div key={item.id}>{content}</div>
            );
          })}
        </div>
      )}
    </div>
  );
}
