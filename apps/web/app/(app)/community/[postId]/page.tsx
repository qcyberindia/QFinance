"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/session";
import type { Comment, CommentListResponse, Post } from "@/lib/types";
import { Card, ErrorState, LoadingState } from "@/components/states";

interface CommentNode extends Comment {
  children: CommentNode[];
}

function buildCommentTree(flat: Comment[]): CommentNode[] {
  const byId = new Map<string, CommentNode>();
  flat.forEach((c) => byId.set(c.id, { ...c, children: [] }));
  const roots: CommentNode[] = [];
  byId.forEach((node) => {
    if (node.parent_comment_id && byId.has(node.parent_comment_id)) {
      byId.get(node.parent_comment_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  });
  return roots;
}

function CommentThread({
  node,
  depth,
  canComment,
  onReply,
}: {
  node: CommentNode;
  depth: number;
  canComment: boolean;
  onReply: (commentId: string, content: string) => Promise<void>;
}) {
  const [replying, setReplying] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submitReply(e: React.FormEvent) {
    e.preventDefault();
    if (!replyText.trim()) return;
    setSubmitting(true);
    try {
      await onReply(node.id, replyText);
      setReplyText("");
      setReplying(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ marginLeft: depth > 0 ? 20 : 0 }} className={depth > 0 ? "border-l pl-3 mt-2" : ""}>
      <Card className={depth > 0 ? "!p-3" : undefined}>
        <div className="text-xs text-ink-soft mb-1 font-semibold" style={{ color: "var(--ink)" }}>
          {node.author.username ? `@${node.author.username}` : "Member"}
        </div>
        <p className="text-sm whitespace-pre-wrap">{node.content}</p>
        {canComment && (
          <button
            className="text-xs mt-2 font-semibold"
            style={{ color: "var(--brass)" }}
            onClick={() => setReplying((v) => !v)}
          >
            Reply
          </button>
        )}
        {replying && (
          <form onSubmit={submitReply} className="mt-2 space-y-2">
            <textarea
              className="qf-input min-h-[50px] text-sm"
              placeholder="Write a reply…"
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
            />
            <button type="submit" disabled={submitting || !replyText.trim()} className="qf-btn-ghost text-xs">
              {submitting ? "Posting…" : "Post Reply"}
            </button>
          </form>
        )}
      </Card>
      {node.children.map((child) => (
        <CommentThread key={child.id} node={child} depth={depth + 1} canComment={canComment} onReply={onReply} />
      ))}
    </div>
  );
}

export default function PostDetailPage() {
  const { postId } = useParams<{ postId: string }>();
  const { session } = useSession();
  const canComment = session !== null;
  const [post, setPost] = useState<Post | null>(null);
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newComment, setNewComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [liked, setLiked] = useState(false);

  // NOTE: there's no GET /community/posts/{id} single-post-fetch endpoint in
  // the current backend — only list-by-channel and list-comments exist. The
  // post's own content/post_type/author (needed for a full Thesis Card
  // presentation) can't be fetched directly on this page. This is a genuine,
  // documented backend gap (see work_memory.md), not a frontend oversight —
  // this page shows the discussion thread, which IS fully real, without a
  // post header.
  // GET /community/posts/{id} — NEW this pass (see work_memory.md); the post
  // header (content/author/post_type) was previously unreachable from this page.
  const load = useCallback(async () => {
    setError(null);
    try {
      const [postData, commentsData] = await Promise.all([
        api.get<Post>(`/community/posts/${postId}`),
        api.get<CommentListResponse>(`/community/posts/${postId}/comments`),
      ]);
      setPost(postData);
      setComments(commentsData.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this post.");
    }
  }, [postId]);

  useEffect(() => {
    load();
  }, [load]);

  const tree = useMemo(() => (comments ? buildCommentTree(comments) : []), [comments]);

  async function handleNewComment(e: React.FormEvent) {
    e.preventDefault();
    if (!newComment.trim() || !canComment) return;
    setSubmitting(true);
    try {
      await api.post(`/community/posts/${postId}/comments`, { content: newComment });
      setNewComment("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not post your comment.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReply(commentId: string, content: string) {
    // Real endpoint: POST /community/comments/{comment_id}/replies (API Spec V2 §3).
    await api.post(`/community/comments/${commentId}/replies`, { content });
    await load();
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
      {post && (
        <Card>
          <div className="flex items-center gap-2 mb-2">
            {post.post_type === "question" && (
              <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: "var(--brass)", color: "var(--cream-0)" }}>
                Question
              </span>
            )}
            {post.post_type === "thesis" && (
              <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: "var(--ink)", color: "var(--cream-0)" }}>
                Thesis
              </span>
            )}
            <span className="font-semibold text-sm">{post.author.username ? `@${post.author.username}` : "Member"}</span>
            <span className="text-xs text-ink-soft">· {new Date(post.created_at).toLocaleDateString()}</span>
          </div>
          <p className="text-sm whitespace-pre-wrap">{post.content}</p>
          {post.research_id && (
            <a href={`/research/${post.research_id}`} className="qf-btn-ghost text-xs inline-block mt-3">
              View full thesis →
            </a>
          )}
          <div className="flex items-center gap-3 mt-3">
            <button className="qf-btn-ghost text-xs" onClick={handleLike}>
              {liked ? "♥ Liked" : "♡ Like"}
            </button>
            <span className="text-xs text-ink-soft">{post.comment_count} comments</span>
          </div>
        </Card>
      )}

      <Card>
        {canComment ? (
          <form onSubmit={handleNewComment} className="space-y-3">
            <textarea
              className="qf-input min-h-[60px]"
              placeholder="Write a comment…"
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
            />
            <button type="submit" disabled={submitting || !newComment.trim()} className="qf-btn-primary">
              {submitting ? "Posting…" : "Comment"}
            </button>
          </form>
        ) : (
          <p className="text-sm text-ink-soft">Sign in to join the discussion.</p>
        )}
      </Card>

      <div>
        {tree.length === 0 && <p className="text-sm text-ink-soft">No comments yet.</p>}
        {tree.map((node) => (
          <CommentThread key={node.id} node={node} depth={0} canComment={canComment} onReply={handleReply} />
        ))}
      </div>
    </div>
  );
}
