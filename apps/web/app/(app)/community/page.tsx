"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/session";
import type { Post, PostListResponse } from "@/lib/types";
import { EmptyState, ErrorState, FeedSkeleton } from "@/components/states";
import { MemberCharterModal } from "@/components/member-charter-modal";
import { Composer } from "@/components/composer";
import { PostCard } from "@/components/post-card";
import { ConfirmDialog } from "@/components/confirm-dialog";

// "All" merges these existing channels client-side — no new backend API.
// (announcements/learning/off_topic excluded: low post volume, and
// announcements is staff-only to post in, so it rarely carries the kind of
// content the tab filters below are meant to surface.)
const FEED_CHANNELS = ["general_discussion", "research_discussion", "market_discussion", "help_questions"];

type FilterTab = "all" | "discussions" | "questions" | "theses";

const TABS: { value: FilterTab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "discussions", label: "Discussions" },
  { value: "questions", label: "Questions" },
  { value: "theses", label: "Theses" },
];

function matchesTab(post: Post, tab: FilterTab): boolean {
  if (tab === "all") return true;
  if (tab === "discussions") return post.post_type === "general" || post.post_type === "discussion";
  if (tab === "questions") return post.post_type === "question";
  if (tab === "theses") return post.post_type === "thesis";
  return true;
}

export default function CommunityPage() {
  const { session } = useSession();
  const canPost = session !== null;

  const [allPosts, setAllPosts] = useState<Post[] | null>(null);
  const [tab, setTab] = useState<FilterTab>("all");
  const [error, setError] = useState<string | null>(null);
  const [showCharterModal, setShowCharterModal] = useState(false);
  const [pendingSubmit, setPendingSubmit] = useState<{ content: string; postType: Post["post_type"] } | null>(null);
  const [likedIds, setLikedIds] = useState<Set<string>>(new Set());
  const [bookmarkedIds, setBookmarkedIds] = useState<Set<string>>(new Set());
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setAllPosts(null);
    try {
      const results = await Promise.all(
        FEED_CHANNELS.map((c) =>
          api.get<PostListResponse>(`/community/channels/${c}/posts`).catch(() => ({ page: 1, page_size: 0, total: 0, items: [] } as PostListResponse))
        )
      );
      const merged = results.flatMap((r) => r.items);
      merged.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      setAllPosts(merged);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the feed.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function doSubmitPost(content: string, postType: Post["post_type"]) {
    try {
      await api.post(`/community/channels/general_discussion/posts`, { content, post_type: postType });
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.code === "CHARTER_NOT_ACKNOWLEDGED") {
        setPendingSubmit({ content, postType });
        setShowCharterModal(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not publish your post.");
        throw err;
      }
    }
  }

  async function toggleLike(post: Post) {
    const isLiked = likedIds.has(post.id);
    setLikedIds((prev) => {
      const next = new Set(prev);
      isLiked ? next.delete(post.id) : next.add(post.id);
      return next;
    });
    try {
      if (isLiked) {
        await api.delete(`/community/post/${post.id}/reactions`);
      } else {
        await api.post(`/community/post/${post.id}/reactions`, { reaction_type: "like" });
      }
    } catch {
      // Revert optimistic update on failure.
      setLikedIds((prev) => {
        const next = new Set(prev);
        isLiked ? next.add(post.id) : next.delete(post.id);
        return next;
      });
    }
  }

  async function toggleBookmark(post: Post) {
    const isSaved = bookmarkedIds.has(post.id);
    setBookmarkedIds((prev) => {
      const next = new Set(prev);
      isSaved ? next.delete(post.id) : next.add(post.id);
      return next;
    });
    try {
      if (isSaved) {
        await api.delete(`/community/bookmarks/${post.id}`);
      } else {
        await api.post(`/community/bookmarks`, { post_id: post.id });
      }
    } catch {
      setBookmarkedIds((prev) => {
        const next = new Set(prev);
        isSaved ? next.add(post.id) : next.delete(post.id);
        return next;
      });
    }
  }

  async function handleEdit(post: Post, newContent: string) {
    await api.patch(`/community/posts/${post.id}`, { content: newContent });
    await load();
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    const id = deleteTarget;
    setDeleteTarget(null);
    try {
      await api.delete(`/community/posts/${id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete this post.");
    }
  }

  async function handleReport(post: Post) {
    try {
      // Real endpoint: POST /moderation/reports (§5.1) — surfaced honestly;
      // if the backend rejects it (e.g. role requirement), the real error
      // message is shown, not a fake success.
      await api.post("/moderation/reports", { target_type: "post", target_id: post.id, reason: "Reported from Community feed" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit your report.");
    }
  }

  const posts = allPosts?.filter((p) => matchesTab(p, tab)) ?? null;

  return (
    <div className="max-w-2xl mx-auto">
      {deleteTarget && (
        <ConfirmDialog
          message="Delete this discussion?"
          onCancel={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
        />
      )}
      {showCharterModal && (
        <MemberCharterModal
          onCancel={() => { setShowCharterModal(false); setPendingSubmit(null); }}
          onAcknowledged={async () => {
            setShowCharterModal(false);
            if (pendingSubmit) {
              await doSubmitPost(pendingSubmit.content, pendingSubmit.postType).catch(() => {});
              setPendingSubmit(null);
            }
          }}
        />
      )}

      <div className="mb-1">
        <h1 className="font-display text-2xl">Community</h1>
      </div>

      {canPost && (
        <div className="border-b" style={{ borderColor: "var(--line)" }}>
          <Composer username={session?.username ?? null} onSubmit={doSubmitPost} />
        </div>
      )}

      <div
        role="tablist"
        aria-label="Filter posts"
        className="flex gap-1 py-3 overflow-x-auto"
        style={{ WebkitOverflowScrolling: "touch" }}
      >
        {TABS.map((t) => (
          <button
            key={t.value}
            role="tab"
            aria-selected={tab === t.value}
            onClick={() => setTab(t.value)}
            className="text-sm px-3 py-1.5 rounded-full whitespace-nowrap focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            style={{
              fontWeight: tab === t.value ? 600 : 400,
              color: tab === t.value ? "var(--ink)" : "var(--ink-soft)",
              background: tab === t.value ? "var(--cream-1)" : "transparent",
              outlineColor: "var(--brass)",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <ErrorState message={error} onRetry={load} />}
      {!error && posts === null && <FeedSkeleton />}
      {!error && posts !== null && posts.length === 0 && (
        <EmptyState title="Nothing here yet" body="Be the first to start a thread." />
      )}
      {!error && posts !== null && posts.length > 0 && (
        <div>
          {posts.map((post) => (
            <PostCard
              key={post.id}
              post={post}
              href={`/community/${post.id}`}
              isOwn={session?.user_id === post.author.id}
              liked={likedIds.has(post.id)}
              onToggleLike={() => toggleLike(post)}
              bookmarked={bookmarkedIds.has(post.id)}
              onToggleBookmark={() => toggleBookmark(post)}
              onEdit={(content) => handleEdit(post, content)}
              onDelete={() => setDeleteTarget(post.id)}
              onReport={() => handleReport(post)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
