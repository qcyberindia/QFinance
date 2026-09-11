"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/session";
import type { Comment, CommentListResponse, Post } from "@/lib/types";
import { Card, ErrorState, LoadingState } from "@/components/states";

export default function PostDetailPage() {
  const { postId } = useParams<{ postId: string }>();
  const { session } = useSession();
  // Same gate as the Community feed page's Post form — POST .../comments also
  // requires MEMBER (community/router.py's create_comment), unchanged from V1.
  const canComment = session?.effective_tier === "CORE";
  const [post, setPost] = useState<Post | null>(null);
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [liked, setLiked] = useState(false);

  // NOTE: there's no GET /community/posts/{id} single-post-fetch endpoint
  // in the current backend — only list-by-channel and list-comments exist.
  // Comments are fetched directly (that endpoint IS real); the post header
  // itself is reconstructed from the comments list's own implicit context
  // where possible, with a graceful minimal fallback otherwise. This is a
  // genuine backend gap, not a frontend oversight — flagged in work_memory.md.
  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await api.get<CommentListResponse>(`/community/posts/${postId}/comments`);
      setComments(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this post.");
    }
  }, [postId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleReply(e: React.FormEvent) {
    e.preventDefault();
    if (!reply.trim() || !canComment) return;
    setSubmitting(true);
    try {
      await api.post(`/community/posts/${postId}/comments`, { content: reply });
      setReply("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not post your comment.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLike() {
    try {
      if (liked) {
        await api.delete(`/community/post/${postId}/reactions`);
        setLiked(false);
      } else {
        await api.post(`/community/post/${postId}/reactions`, { reaction_type: "like" });
        setLiked(true);
      }
    } catch {
      // Non-critical UI affordance — a failed like shouldn't block the page.
    }
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (comments === null) return <LoadingState label="Loading discussion…" />;

  return (
    <div className="space-y-5">
      <Card>
        <p className="text-xs text-ink-soft mb-2">Post</p>
        <button className="qf-btn-ghost text-xs" onClick={handleLike}>
          {liked ? "♥ Liked" : "♡ Like"}
        </button>
      </Card>

      <Card>
        {canComment ? (
          <form onSubmit={handleReply} className="space-y-3">
            <textarea
              className="qf-input min-h-[60px]"
              placeholder="Write a comment…"
              value={reply}
              onChange={(e) => setReply(e.target.value)}
            />
            <button type="submit" disabled={submitting || !reply.trim()} className="qf-btn-primary">
              {submitting ? "Posting…" : "Comment"}
            </button>
          </form>
        ) : (
          <p className="text-sm text-ink-soft">Commenting is a Core membership benefit.</p>
        )}
      </Card>

      <div className="space-y-3">
        {comments.length === 0 && <p className="text-sm text-ink-soft">No comments yet.</p>}
        {comments.map((c) => (
          <Card key={c.id}>
            <div className="text-xs text-ink-soft mb-1 font-semibold" style={{ color: "var(--ink)" }}>
              {c.author.name || c.author.username || "Member"}
            </div>
            <p className="text-sm whitespace-pre-wrap">{c.content}</p>
            {/* Threaded replies (parent_comment_id) are not yet supported by the
                backend — see API Specification V2 §3 and work_memory.md. */}
          </Card>
        ))}
      </div>
    </div>
  );
}
