"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api-client";
import type { BookmarkItem, BookmarkListResponse } from "@/lib/types";
import { ErrorState } from "@/components/states";
import s from "@/components/profile/profile.module.css";

const PAGE_SIZE = 20;
const TYPE: Record<string, { label: string; cls: string }> = {
  thesis: { label: "Thesis", cls: s.typeThesis },
  question: { label: "Question", cls: s.typeQuestion },
  discussion: { label: "Discussion", cls: "" },
  general: { label: "Discussion", cls: "" },
};

/** Saved — the member's own Community bookmarks (GET /community/bookmarks,
 * always scoped to the session's user). Removed/restricted posts show no
 * content, only that they're unavailable. */
export default function SavedPage() {
  const [items, setItems] = useState<BookmarkItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(false);
    try {
      const data = await api.get<BookmarkListResponse>(`/community/bookmarks?page=1&page_size=${PAGE_SIZE}`);
      setItems(data.items);
      setTotal(data.total);
      setPage(1);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const data = await api.get<BookmarkListResponse>(`/community/bookmarks?page=${page + 1}&page_size=${PAGE_SIZE}`);
      setItems((prev) => [...(prev ?? []), ...data.items.filter((i) => !prev?.some((p) => p.post_id === i.post_id))]);
      setTotal(data.total);
      setPage(page + 1);
    } catch {
      setNotice("Couldn't load more. Try again.");
    } finally {
      setLoadingMore(false);
    }
  }

  async function remove(postId: string) {
    try {
      await api.delete(`/community/bookmarks/${postId}`);
      setItems((prev) => prev?.filter((i) => i.post_id !== postId) ?? prev);
      setTotal((t) => Math.max(0, t - 1));
      setNotice("Removed from Saved.");
    } catch {
      setNotice("Couldn't remove that item. Try again.");
    }
  }

  if (error) return <div className="mt-4"><ErrorState message="We couldn't load your saved posts. Try again." onRetry={load} /></div>;
  if (items === null) return <div className="qf-skeleton mt-4" style={{ height: 200 }} aria-busy="true" aria-label="Loading saved posts" />;

  return (
    <section className="mt-2" aria-labelledby="saved-title">
      <h2 id="saved-title" className={s.srOnly}>Saved</h2>
      <p className="qf-secondary mt-3">Discussions, questions and theses you&apos;ve saved from Community. Only you can see this list.</p>
      <p aria-live="polite" className="text-sm mt-2">{notice}</p>
      {items.length === 0 ? (
        <div className={s.empty}>
          <p className="qf-section-title">Nothing saved yet</p>
          <p className="qf-secondary mt-1">Use <strong>Save</strong> on any Community post to keep it here.</p>
          <Link href="/community" className="qf-btn-ghost mt-4" style={{ textDecoration: "none" }}>Browse Community</Link>
        </div>
      ) : (
        <>
          <ul className={s.list}>
            {items.map((item) => {
              const t = item.post_type ? TYPE[item.post_type] ?? TYPE.general : null;
              return (
                <li key={item.post_id} className={s.item}>
                  <div className={s.itemBody}>
                    {t ? <span className={`${s.typeTag} ${t.cls}`}>{t.label}</span> : <span className={s.typeTag}>Unavailable</span>}
                    {item.available ? (
                      <Link href={`/community/${item.post_id}`} className={`${s.itemTitle} block mt-1`}>{item.post_summary}</Link>
                    ) : (
                      <p className="qf-secondary mt-1">This post is no longer available.</p>
                    )}
                    <div className={s.itemMeta}>Saved {new Date(item.bookmarked_at).toLocaleDateString()}</div>
                  </div>
                  <button type="button" className={s.linkBtn} onClick={() => remove(item.post_id)}>
                    Remove<span className={s.srOnly}> from Saved</span>
                  </button>
                </li>
              );
            })}
          </ul>
          {items.length < total && (
            <div className="flex justify-center py-5">
              <button type="button" className="qf-btn-ghost" onClick={loadMore} disabled={loadingMore} aria-busy={loadingMore}>
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
