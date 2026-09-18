"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/session";
import { Avatar } from "@/components/avatar";
import { PostCard, Timestamp } from "@/components/post-card";
import { ConfirmDialog } from "@/components/confirm-dialog";
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
  node, depth, canComment, currentUserId, onReply, onEdit, onDelete,
}: {
  node: CommentNode;
  depth: number;
  canComment: boolean;
  currentUserId: string | undefined;
  onReply: (commentId: string, content: string) => Promise<void>;
  onEdit: (commentId: string, content: string) => Promise<void>;
  onDelete: (commentId: string) => void;
}) {
  const [replying, setReplying] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(node.content);
  const [saving, setSaving] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const isOwn = currentUserId === node.author.id;

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

  async function saveEdit() {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      await onEdit(node.id, draft);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ marginLeft: depth > 0 ? 20 : 0 }} className={depth > 0 ? "border-l pl-3 mt-3" : "mt-3"}>
      <div className="flex gap-2.5">
        <Avatar username={node.author.username} size={28} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs font-semibold" style={{ color: "var(--ink)" }}>
              {node.author.username ? `@${node.author.username}` : "Member"}
            </span>
            <Timestamp iso={node.created_at} />
            {node.is_edited && <span className="text-xs text-ink-soft">· edited</span>}
          </div>

          {editing ? (
            <div className="mt-1 space-y-2">
              <textarea className="qf-input min-h-[50px] text-sm" value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
              <div className="flex gap-2">
                <button className="qf-btn-primary text-xs" disabled={saving || !draft.trim()} onClick={saveEdit}>
                  {saving ? "Saving…" : "Save"}
                </button>
                <button className="qf-btn-ghost text-xs" onClick={() => { setEditing(false); setDraft(node.content); }}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm mt-0.5 whitespace-pre-wrap leading-relaxed">{node.content}</p>
          )}

          <div className="flex items-center gap-4 mt-1.5">
            {canComment && !editing && (
              <button
                type="button"
                className="text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded"
                style={{ color: "var(--brass)", outlineColor: "var(--brass)" }}
                onClick={() => setReplying((v) => !v)}
              >
                Reply
              </button>
            )}
            {isOwn && !editing && (
              <div className="relative">
                <button
                  type="button"
                  aria-label="More actions"
                  aria-expanded={menuOpen}
                  className="text-xs text-ink-soft px-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded"
                  style={{ outlineColor: "var(--brass)" }}
                  onClick={() => setMenuOpen((v) => !v)}
                >
                  ⋯
                </button>
                {menuOpen && (
                  <div role="menu" className="absolute left-0 top-5 z-10 qf-card py-1 min-w-[100px]">
                    <button role="menuitem" className="block w-full text-left text-xs px-3 py-1.5 hover:bg-black/5" onClick={() => { setEditing(true); setMenuOpen(false); }}>
                      Edit
                    </button>
                    <button role="menuitem" className="block w-full text-left text-xs px-3 py-1.5 hover:bg-black/5" style={{ color: "#9C4B3F" }} onClick={() => { onDelete(node.id); setMenuOpen(false); }}>
                      Delete
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {replying && (
            <form onSubmit={submitReply} className="mt-2 space-y-2">
              <textarea
                className="qf-input min-h-[50px] text-sm"
                placeholder="Write a reply…"
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                autoFocus
              />
              <button type="submit" disabled={submitting || !replyText.trim()} className="qf-btn-ghost text-xs">
                {submitting ? "Posting…" : "Post Reply"}
              </button>
            </form>
          )}
        </div>
      </div>
      {node.children.map((child) => (
        <CommentThread key={child.id} node={child} depth={depth + 1} canComment={canComment} currentUserId={currentUserId} onReply={onReply} onEdit={onEdit} onDelete={onDelete} />
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
  const [bookmarked, setBookmarked] = useState(false);
  const [deleteCommentTarget, setDeleteCommentTarget] = useState<string | null>(null);
  const [postDeleted, setPostDeleted] = useState(false);

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
    await api.post(`/community/comments/${commentId}/replies`, { content });
    await load();
  }

  async function handleCommentEdit(commentId: string, content: string) {
    await api.patch(`/community/comments/${commentId}`, { content });
    await load();
  }

  async function confirmDeleteComment() {
    if (!deleteCommentTarget) return;
    const id = deleteCommentTarget;
    setDeleteCommentTarget(null);
    try {
      await api.delete(`/community/comments/${id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete this comment.");
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

  async function handleBookmark() {
    const wasBookmarked = bookmarked;
    setBookmarked(!wasBookmarked);
    try {
      if (wasBookmarked) {
        await api.delete(`/community/bookmarks/${postId}`);
      } else {
        await api.post(`/community/bookmarks`, { post_id: postId });
      }
    } catch {
      setBookmarked(wasBookmarked);
    }
  }

  async function handlePostEdit(content: string) {
    await api.patch(`/community/posts/${postId}`, { content });
    await load();
  }

  async function handlePostDelete() {
    try {
      await api.delete(`/community/posts/${postId}`);
      setPostDeleted(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete this post.");
    }
  }

  async function handleReport() {
    if (!post) return;
    try {
      await api.post("/moderation/reports", { target_type: "post", target_id: post.id, reason: "Reported from thread view" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit your report.");
    }
  }

  if (postDeleted) {
    return <p className="text-sm text-ink-soft">This post has been deleted.</p>;
  }
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (comments === null || post === null) return <LoadingState label="Loading discussion…" />;

  return (
    <div className="space-y-5 max-w-2xl mx-auto">
      {deleteCommentTarget && (
        <ConfirmDialog
          message="Delete this comment?"
          onCancel={() => setDeleteCommentTarget(null)}
          onConfirm={confirmDeleteComment}
        />
      )}

      <div className="border-b" style={{ borderColor: "var(--line)" }}>
        <PostCard
          post={post}
          isOwn={session?.user_id === post.author.id}
          liked={liked}
          onToggleLike={handleLike}
          bookmarked={bookmarked}
          onToggleBookmark={handleBookmark}
          onEdit={handlePostEdit}
          onDelete={handlePostDelete}
          onReport={session?.user_id !== post.author.id ? handleReport : undefined}
        />
        {post.research_id && (
          <a href={`/research/${post.research_id}`} className="qf-btn-ghost text-xs inline-block mb-3">
            View full thesis →
          </a>
        )}
      </div>

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
        <p className="text-xs font-semibold text-ink-soft mb-1">
          {comments.length} {comments.length === 1 ? "reply" : "replies"}
        </p>
        {tree.length === 0 && <p className="text-sm text-ink-soft">No comments yet.</p>}
        {tree.map((node) => (
          <CommentThread
            key={node.id}
            node={node}
            depth={0}
            canComment={canComment}
            currentUserId={session?.user_id}
            onReply={handleReply}
            onEdit={handleCommentEdit}
            onDelete={(id) => setDeleteCommentTarget(id)}
          />
        ))}
      </div>
    </div>
  );
}
