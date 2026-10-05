"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/session";
import type { CommunityPillar, Post, PostListResponse } from "@/lib/types";
import { EmptyState, ErrorState, FeedSkeleton } from "@/components/states";
import { MemberCharterModal } from "@/components/member-charter-modal";
import { Composer } from "@/components/composer";
import { PostCard } from "@/components/post-card";
import { ConfirmDialog } from "@/components/confirm-dialog";
import c from "@/components/community/community.module.css";

/**
 * Community — three pillars over ONE post model (posts.post_type):
 * Discussion (general/discussion), Q&A (question), Thesis (thesis, published
 * from Research). Reads the combined feed endpoint GET /community/posts,
 * which also includes thesis posts (they carry research_id, not a channel).
 */
type Tab = "all" | CommunityPillar;

const TABS: { value: Tab; label: string; intro: string }[] = [
  { value: "all", label: "All", intro: "Ideas, questions and published theses from the community — challenge the reasoning, not just the price." },
  { value: "discussion", label: "Discussion", intro: "Let's discuss an idea. Bring your reasoning and engage with others' arguments." },
  { value: "question", label: "Q&A", intro: "Have a question? Ask it here and get useful answers from other investors." },
  { value: "thesis", label: "Thesis", intro: "Investment theses published from Research. Read the reasoning, then try to prove it wrong." },
];

const EMPTY: Record<Tab, { title: string; body: string }> = {
  all: { title: "Nothing here yet", body: "Start a discussion or ask the first question." },
  discussion: { title: "No discussions yet", body: "Start one — share an idea worth challenging." },
  question: { title: "No questions yet", body: "Ask the first question." },
  thesis: { title: "No theses published yet", body: "Theses come from completed research. Publish yours from the Research Lab." },
};

const PAGE_SIZE = 20;

export default function CommunityPage() {
  const { session } = useSession();
  const canPost = session !== null;

  const [tab, setTab] = useState<Tab>("all");
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showCharterModal, setShowCharterModal] = useState(false);
  const [pendingSubmit, setPendingSubmit] = useState<{ content: string; postType: Post["post_type"] } | null>(null);
  const [likedIds, setLikedIds] = useState<Set<string>>(new Set());
  const [bookmarkedIds, setBookmarkedIds] = useState<Set<string>>(new Set());
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Deep link: /community?pillar=thesis
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("pillar");
    if (p && TABS.some((t) => t.value === p)) setTab(p as Tab);
  }, []);

  const fetchPage = useCallback(async (t: Tab, n: number) => {
    const q = new URLSearchParams({ page: String(n), page_size: String(PAGE_SIZE) });
    if (t !== "all") q.set("pillar", t);
    return api.get<PostListResponse>(`/community/posts?${q}`);
  }, []);

  const absorbFlags = (items: Post[], reset: boolean) => {
    setLikedIds((prev) => {
      const next = reset ? new Set<string>() : new Set(prev);
      items.forEach((p) => p.viewer_reacted && next.add(p.id));
      return next;
    });
    setBookmarkedIds((prev) => {
      const next = reset ? new Set<string>() : new Set(prev);
      items.forEach((p) => p.viewer_bookmarked && next.add(p.id));
      return next;
    });
  };

  // Only the latest request may update the list — switching tabs quickly
  // (or the ?pillar= deep link) must not let an older response win.
  const requestSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++requestSeq.current;
    setError(null);
    setPosts(null);
    try {
      const data = await fetchPage(tab, 1);
      if (seq !== requestSeq.current) return;
      setPosts(data.items);
      setTotal(data.total);
      setPage(1);
      absorbFlags(data.items, true);
    } catch {
      if (seq !== requestSeq.current) return;
      setError("We couldn't load the community feed. Check your connection and try again.");
    }
  }, [tab, fetchPage]);

  useEffect(() => { load(); }, [load]);

  async function loadMore() {
    setLoadingMore(true);
    const seq = requestSeq.current;
    try {
      const data = await fetchPage(tab, page + 1);
      if (seq !== requestSeq.current) return;
      setPosts((prev) => {
        const seen = new Set((prev ?? []).map((p) => p.id));
        return [...(prev ?? []), ...data.items.filter((p) => !seen.has(p.id))];
      });
      setTotal(data.total);
      setPage(page + 1);
      absorbFlags(data.items, false);
    } catch {
      setNotice("Couldn't load more posts. Try again.");
    } finally {
      setLoadingMore(false);
    }
  }

  function selectTab(t: Tab) {
    setTab(t);
    const url = t === "all" ? "/community" : `/community?pillar=${t}`;
    window.history.replaceState(null, "", url);
  }

  function onTabKey(e: React.KeyboardEvent, i: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const next = (i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length;
    selectTab(TABS[next].value);
    tabRefs.current[next]?.focus();
  }

  async function doSubmitPost(content: string, postType: Post["post_type"]) {
    try {
      await api.post(`/community/channels/general_discussion/posts`, { content, post_type: postType });
      setNotice(postType === "question" ? "Your question is live." : "Your discussion is live.");
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.code === "CHARTER_NOT_ACKNOWLEDGED") {
        setPendingSubmit({ content, postType });
        setShowCharterModal(true);
      } else {
        throw err;
      }
    }
  }

  async function toggle(post: Post, kind: "like" | "save") {
    const set = kind === "like" ? likedIds : bookmarkedIds;
    const setSet = kind === "like" ? setLikedIds : setBookmarkedIds;
    const on = set.has(post.id);
    const flip = (value: boolean) => setSet((prev) => {
      const next = new Set(prev);
      value ? next.add(post.id) : next.delete(post.id);
      return next;
    });
    flip(!on);
    if (kind === "like") {
      setPosts((prev) => prev?.map((p) => p.id === post.id ? { ...p, reaction_count: p.reaction_count + (on ? -1 : 1) } : p) ?? prev);
    }
    try {
      if (kind === "like") {
        if (on) await api.delete(`/community/post/${post.id}/reactions`);
        else await api.post(`/community/post/${post.id}/reactions`, { reaction_type: "like" });
      } else if (on) {
        await api.delete(`/community/bookmarks/${post.id}`);
      } else {
        await api.post(`/community/bookmarks`, { post_id: post.id });
      }
    } catch {
      flip(on);
      if (kind === "like") {
        setPosts((prev) => prev?.map((p) => p.id === post.id ? { ...p, reaction_count: p.reaction_count + (on ? 1 : -1) } : p) ?? prev);
      }
      setNotice(kind === "like" ? "Couldn't update your like." : "Couldn't update Saved.");
    }
  }

  async function handleEdit(post: Post, newContent: string) {
    await api.patch(`/community/posts/${post.id}`, { content: newContent });
    setPosts((prev) => prev?.map((p) => p.id === post.id ? { ...p, content: newContent, is_edited: true } : p) ?? prev);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    const id = deleteTarget;
    setDeleteTarget(null);
    try {
      await api.delete(`/community/posts/${id}`);
      setPosts((prev) => prev?.filter((p) => p.id !== id) ?? prev);
      setTotal((t) => Math.max(0, t - 1));
      setNotice("Post deleted.");
    } catch {
      setNotice("Couldn't delete this post. Try again.");
    }
  }

  async function handleReport(post: Post) {
    try {
      await api.post("/moderation/reports", { target_type: "post", target_id: post.id, reason: "Reported from Community feed" });
      setNotice("Thanks — the moderators will review this post.");
    } catch {
      setNotice("Couldn't submit your report. Try again.");
    }
  }

  const active = TABS.find((t) => t.value === tab)!;
  const composerTypes: ("discussion" | "question")[] | null =
    tab === "all" ? ["discussion", "question"] : tab === "discussion" ? ["discussion"] : tab === "question" ? ["question"] : null;

  return (
    <div className={`${c.page} ${c.touch}`}>
      {deleteTarget && (
        <ConfirmDialog message="Delete this post?" onCancel={() => setDeleteTarget(null)} onConfirm={confirmDelete} />
      )}
      {showCharterModal && (
        <MemberCharterModal
          onCancel={() => { setShowCharterModal(false); setPendingSubmit(null); }}
          onAcknowledged={async () => {
            setShowCharterModal(false);
            if (pendingSubmit) {
              await doSubmitPost(pendingSubmit.content, pendingSubmit.postType).catch(() => setNotice("Couldn't publish your post. Try again."));
              setPendingSubmit(null);
            }
          }}
        />
      )}

      <header className="mb-4">
        <h1 className="qf-page-title">Community</h1>
        <p className="qf-secondary mt-1">Where investors challenge ideas, not just prices.</p>
      </header>

      <div role="tablist" aria-label="Community sections" className={c.tabs}>
        {TABS.map((t, i) => (
          <button
            key={t.value}
            ref={(el) => { tabRefs.current[i] = el; }}
            id={`tab-${t.value}`}
            role="tab"
            aria-selected={tab === t.value}
            aria-controls="community-panel"
            tabIndex={tab === t.value ? 0 : -1}
            onClick={() => selectTab(t.value)}
            onKeyDown={(e) => onTabKey(e, i)}
            className={`${c.tab} ${tab === t.value ? c.tabActive : ""}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <section id="community-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        <p className={c.pillarIntro}>{active.intro}</p>

        {canPost && composerTypes && (
          <Composer username={session?.username ?? null} onSubmit={doSubmitPost} types={composerTypes} />
        )}
        {tab === "thesis" && (
          <div className={c.composer}>
            <p className="text-sm">
              A thesis starts as research. Complete your research, publish it from <strong>Review</strong>, then
              publish it as a thesis to Community.
            </p>
            <Link href="/research" className="qf-btn-ghost mt-3" style={{ textDecoration: "none" }}>
              Open Research Lab →
            </Link>
          </div>
        )}

        <div aria-live="polite" className={c.srOnly}>{posts === null && !error ? "Loading posts" : ""}</div>
        {notice && (
          <p className="text-sm py-2" role="status" style={{ color: "var(--ink-soft)" }}>
            {notice}{" "}
            <button type="button" className="underline" onClick={() => setNotice(null)}>Dismiss</button>
          </p>
        )}

        {error && <div className="mt-4"><ErrorState message={error} onRetry={load} /></div>}
        {!error && posts === null && <FeedSkeleton />}
        {!error && posts !== null && posts.length === 0 && (
          <div className="mt-4"><EmptyState title={EMPTY[tab].title} body={EMPTY[tab].body} /></div>
        )}
        {!error && posts !== null && posts.length > 0 && (
          <>
            {posts.map((post) => (
              <PostCard
                key={post.id}
                post={post}
                href={`/community/${post.id}`}
                isOwn={session?.user_id === post.author.id}
                liked={likedIds.has(post.id)}
                onToggleLike={() => toggle(post, "like")}
                bookmarked={bookmarkedIds.has(post.id)}
                onToggleBookmark={() => toggle(post, "save")}
                onEdit={(content) => handleEdit(post, content)}
                onDelete={() => setDeleteTarget(post.id)}
                onReport={() => handleReport(post)}
              />
            ))}
            {posts.length < total && (
              <div className={c.loadMore}>
                <button type="button" className="qf-btn-ghost" onClick={loadMore} disabled={loadingMore} aria-busy={loadingMore}>
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
