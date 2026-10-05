"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/session";
import { Avatar } from "@/components/avatar";
import { PostCard, Timestamp, replyNoun } from "@/components/post-card";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { Comment, CommentListResponse, Post, ThesisSnapshot } from "@/lib/types";
import { ErrorState } from "@/components/states";
import c from "@/components/community/community.module.css";

interface CommentNode extends Comment {
  children: CommentNode[];
}

function buildCommentTree(flat: Comment[]): CommentNode[] {
  const byId = new Map<string, CommentNode>();
  flat.forEach((cm) => byId.set(cm.id, { ...cm, children: [] }));
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

// Beyond this depth replies stop indenting further so threads stay readable on phones.
const MAX_INDENT_DEPTH = 3;

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
  const [failed, setFailed] = useState<string | null>(null);
  const isOwn = currentUserId === node.author.id;
  const name = node.author.username ? `@${node.author.username}` : "Member";

  async function submitReply(e: React.FormEvent) {
    e.preventDefault();
    if (!replyText.trim()) return;
    setSubmitting(true);
    setFailed(null);
    try {
      await onReply(node.id, replyText);
      setReplyText("");
      setReplying(false);
    } catch {
      setFailed("Couldn't post your reply. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function saveEdit() {
    if (!draft.trim()) return;
    setSaving(true);
    setFailed(null);
    try {
      await onEdit(node.id, draft);
      setEditing(false);
    } catch {
      setFailed("Couldn't save your edit. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`${c.comment} ${depth > 0 && depth <= MAX_INDENT_DEPTH ? c.nested : ""}`}>
      <article aria-label={`Reply by ${name}`} className="flex gap-2.5">
        <Avatar username={node.author.username} size={28} />
        <div className="min-w-0 flex-1">
          <div className={c.meta}>
            <span className={c.author}>{name}</span>
            <Timestamp iso={node.created_at} />
            {node.is_edited && <span>· edited</span>}
          </div>

          {editing ? (
            <div className="mt-1 space-y-2">
              <label htmlFor={`edit-${node.id}`} className={c.srOnly}>Edit reply</label>
              <textarea id={`edit-${node.id}`} className="qf-input min-h-[70px]" value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
              <div className="flex gap-2">
                <button className="qf-btn-primary" disabled={saving || !draft.trim()} onClick={saveEdit}>
                  {saving ? "Saving…" : "Save"}
                </button>
                <button className="qf-btn-ghost" onClick={() => { setEditing(false); setDraft(node.content); }}>Cancel</button>
              </div>
            </div>
          ) : (
            <p className="text-sm mt-1 whitespace-pre-wrap leading-relaxed" style={{ overflowWrap: "anywhere" }}>{node.content}</p>
          )}

          {!editing && (
            <div className="flex items-center gap-2 mt-1">
              {canComment && (
                <button type="button" className={c.replyBtn} aria-expanded={replying} onClick={() => setReplying((v) => !v)}>
                  Reply<span className={c.srOnly}> to {name}</span>
                </button>
              )}
              {isOwn && (
                <>
                  <button type="button" className={c.replyBtn} style={{ color: "var(--ink-soft)" }} onClick={() => setEditing(true)}>
                    Edit
                  </button>
                  <button type="button" className={c.replyBtn} style={{ color: "var(--down)" }} onClick={() => onDelete(node.id)}>
                    Delete
                  </button>
                </>
              )}
            </div>
          )}
          {failed && <p className="text-xs mt-1" style={{ color: "var(--down)" }} role="alert">{failed}</p>}

          {replying && (
            <form onSubmit={submitReply} className="mt-2 space-y-2">
              <label htmlFor={`reply-${node.id}`} className={c.srOnly}>Reply to {name}</label>
              <textarea
                id={`reply-${node.id}`}
                className="qf-input min-h-[70px]"
                placeholder="Write a reply…"
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                autoFocus
              />
              <div className="flex gap-2">
                <button type="submit" disabled={submitting || !replyText.trim()} className="qf-btn-primary">
                  {submitting ? "Posting…" : "Post Reply"}
                </button>
                <button type="button" className="qf-btn-ghost" onClick={() => { setReplying(false); setReplyText(""); }}>Cancel</button>
              </div>
            </form>
          )}
        </div>
      </article>
      {node.children.map((child) => (
        <CommentThread key={child.id} node={child} depth={depth + 1} canComment={canComment} currentUserId={currentUserId}
          onReply={onReply} onEdit={onEdit} onDelete={onDelete} />
      ))}
    </div>
  );
}

const REASONING: { key: string; label: string }[] = [
  { key: "business_model", label: "Business" },
  { key: "business_quality", label: "Business quality" },
  { key: "competitive_position", label: "Industry & competition" },
  { key: "financial_snapshot", label: "Financial health" },
  { key: "catalysts", label: "Growth" },
  { key: "management_notes", label: "Management" },
  { key: "assumptions_outlook", label: "Assumptions & outlook" },
  { key: "valuation_range", label: "Valuation reasoning" },
];
const SCENARIOS: { key: string; label: string }[] = [
  { key: "bull_case", label: "Bull case" },
  { key: "base_case", label: "Base case" },
  { key: "bear_case", label: "Bear case" },
];

function text(v: string | boolean | null | undefined): string {
  return typeof v === "string" ? v.trim() : "";
}

function ThesisDocument({ snap, postContent, onChallenge }: { snap: ThesisSnapshot; postContent: string; onChallenge: () => void }) {
  const s = snap.sections;
  const reasoning = REASONING.filter((r) => text(s[r.key]));
  const scenarios = SCENARIOS.filter((r) => text(s[r.key]));
  const disclosure = (flag: string | boolean | null, detail: string | boolean | null, yes: string, no: string) =>
    flag === true ? `${yes}${text(detail) ? ` — ${text(detail)}` : ""}` : flag === false ? no : "Not stated";

  return (
    <div>
      {/* The post body already shows the summary; repeat it only if it differs. */}
      {text(s.summary) && text(s.summary) !== postContent.trim() && (
        <section className={c.docSection} aria-labelledby="thesis-core">
          <h2 id="thesis-core" className={c.docLabel}>The thesis</h2>
          <p className={c.prose} style={{ fontSize: 16 }}>{text(s.summary)}</p>
        </section>
      )}

      {(reasoning.length > 0 || scenarios.length > 0) && (
        <section className={c.docSection} aria-labelledby="thesis-reasoning">
          <h2 id="thesis-reasoning" className={c.docLabel}>Reasoning & evidence</h2>
          {reasoning.map((r) => (
            <div key={r.key}>
              <h3 className={c.docSub}>{r.label}</h3>
              <p className={c.prose}>{text(s[r.key])}</p>
            </div>
          ))}
          {scenarios.map((r) => (
            <div key={r.key}>
              <h3 className={c.docSub}>{r.label}</h3>
              <p className={c.prose}>{text(s[r.key])}</p>
            </div>
          ))}
        </section>
      )}

      {text(s.risk_register) && (
        <section className={c.docSection} aria-labelledby="thesis-risks">
          <h2 id="thesis-risks" className={c.docLabel}>Risks</h2>
          <p className={c.prose}>{text(s.risk_register)}</p>
        </section>
      )}

      <section className={c.docSection} aria-labelledby="thesis-wrong">
        <div className={c.challenge}>
          <h2 id="thesis-wrong" className={c.docLabel} style={{ color: "var(--brass-dark)" }}>Prove me wrong</h2>
          {text(s.invalidation_conditions) ? (
            <p className={c.prose}>{text(s.invalidation_conditions)}</p>
          ) : (
            <p className="qf-secondary">The author hasn&apos;t listed invalidation conditions.</p>
          )}
          <button type="button" className="qf-btn-primary mt-4" onClick={onChallenge}>
            Challenge this reasoning
          </button>
        </div>
      </section>

      <section className={c.docSection} aria-labelledby="thesis-sources">
        <h2 id="thesis-sources" className={c.docLabel}>Sources & disclosures</h2>
        {snap.sources.length > 0 ? (
          <ul className="text-sm space-y-1.5">
            {snap.sources.map((src, i) => (
              <li key={i} style={{ overflowWrap: "anywhere" }}>
                {src.label}{src.reference && <span className="qf-secondary"> — {src.reference}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="qf-secondary">No sources listed.</p>
        )}
        <dl className="mt-3 grid gap-1 text-sm" style={{ gridTemplateColumns: "auto 1fr", columnGap: 12 }}>
          <dt className="qf-secondary">Conflict of interest</dt>
          <dd>{disclosure(s.conflict_disclosed, s.conflict_detail, "Disclosed", "None declared")}</dd>
          <dt className="qf-secondary">Position</dt>
          <dd>{disclosure(s.position_disclosed, s.position_detail, "Holds a position", "No position declared")}</dd>
          {text(s.research_date) && (<><dt className="qf-secondary">Research date</dt><dd>{text(s.research_date)}</dd></>)}
        </dl>
        <p className={`${c.notice} mt-4`}>
          Published version {snap.version}. This is the author&apos;s reasoning shared for discussion — not a
          recommendation to buy or sell, and not personalised advice.
        </p>
      </section>
    </div>
  );
}

export default function PostDetailPage() {
  const { postId } = useParams<{ postId: string }>();
  const { session } = useSession();
  const canComment = session !== null;
  const [post, setPost] = useState<Post | null>(null);
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [thesis, setThesis] = useState<ThesisSnapshot | null | undefined>(undefined); // undefined = not loaded / n/a
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [newComment, setNewComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [liked, setLiked] = useState(false);
  const [bookmarked, setBookmarked] = useState(false);
  const [deleteCommentTarget, setDeleteCommentTarget] = useState<string | null>(null);
  const [confirmPostDelete, setConfirmPostDelete] = useState(false);
  const [postDeleted, setPostDeleted] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  const loadComments = useCallback(async () => {
    const data = await api.get<CommentListResponse>(`/community/posts/${postId}/comments?page_size=100`);
    setComments(data.items);
  }, [postId]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const postData = await api.get<Post>(`/community/posts/${postId}`);
      setPost(postData);
      setLiked(!!postData.viewer_reacted);
      setBookmarked(!!postData.viewer_bookmarked);
      await loadComments();
      if (postData.post_type === "thesis" && postData.research_id) {
        setThesis(await api.get<ThesisSnapshot>(`/community/posts/${postId}/thesis`).catch(() => null));
      }
    } catch (err) {
      setError(err instanceof ApiError && err.status === 404
        ? "This post isn't available. It may have been removed."
        : err instanceof ApiError && err.status === 403
          ? "Verify your email address to read Community posts."
          : "We couldn't load this post. Try again.");
    }
  }, [postId, loadComments]);

  useEffect(() => { load(); }, [load]);

  const tree = useMemo(() => (comments ? buildCommentTree(comments) : []), [comments]);

  function focusComposer() {
    composerRef.current?.focus();
    composerRef.current?.scrollIntoView({ block: "center" });
  }

  async function handleNewComment(e: React.FormEvent) {
    e.preventDefault();
    if (!newComment.trim() || !canComment) return;
    setSubmitting(true);
    setNotice(null);
    try {
      await api.post(`/community/posts/${postId}/comments`, { content: newComment });
      setNewComment("");
      await loadComments();
      setPost((p) => p ? { ...p, comment_count: p.comment_count + 1 } : p);
    } catch {
      setNotice("Couldn't post that. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReply(commentId: string, content: string) {
    await api.post(`/community/comments/${commentId}/replies`, { content });
    await loadComments();
    setPost((p) => p ? { ...p, comment_count: p.comment_count + 1 } : p);
  }

  async function handleCommentEdit(commentId: string, content: string) {
    await api.patch(`/community/comments/${commentId}`, { content });
    await loadComments();
  }

  async function confirmDeleteComment() {
    if (!deleteCommentTarget) return;
    const id = deleteCommentTarget;
    setDeleteCommentTarget(null);
    try {
      await api.delete(`/community/comments/${id}`);
      await loadComments();
    } catch {
      setNotice("Couldn't delete that reply. Try again.");
    }
  }

  async function handleLike() {
    const was = liked;
    setLiked(!was);
    setPost((p) => p ? { ...p, reaction_count: p.reaction_count + (was ? -1 : 1) } : p);
    try {
      if (was) await api.delete(`/community/post/${postId}/reactions`);
      else await api.post(`/community/post/${postId}/reactions`, { reaction_type: "like" });
    } catch {
      setLiked(was);
      setPost((p) => p ? { ...p, reaction_count: p.reaction_count + (was ? 1 : -1) } : p);
    }
  }

  async function handleBookmark() {
    const was = bookmarked;
    setBookmarked(!was);
    try {
      if (was) await api.delete(`/community/bookmarks/${postId}`);
      else await api.post(`/community/bookmarks`, { post_id: postId });
    } catch {
      setBookmarked(was);
      setNotice("Couldn't update Saved.");
    }
  }

  async function handlePostEdit(content: string) {
    await api.patch(`/community/posts/${postId}`, { content });
    setPost((p) => p ? { ...p, content, is_edited: true } : p);
  }

  async function handlePostDelete() {
    setConfirmPostDelete(false);
    try {
      await api.delete(`/community/posts/${postId}`);
      setPostDeleted(true);
    } catch {
      setNotice("Couldn't delete this post. Try again.");
    }
  }

  async function handleReport() {
    if (!post) return;
    try {
      await api.post("/moderation/reports", { target_type: "post", target_id: post.id, reason: "Reported from thread view" });
      setNotice("Thanks — the moderators will review this post.");
    } catch {
      setNotice("Couldn't submit your report. Try again.");
    }
  }

  if (postDeleted) {
    return (
      <div className={c.page}>
        <p className="text-sm" role="status">This post has been deleted.</p>
        <Link href="/community" className="qf-btn-ghost mt-3" style={{ textDecoration: "none" }}>← Back to Community</Link>
      </div>
    );
  }
  if (error) return <div className={c.page}><ErrorState message={error} onRetry={load} /></div>;
  if (comments === null || post === null) {
    return (
      <div className={c.page} aria-busy="true" aria-label="Loading post">
        <div className="qf-skeleton" style={{ height: 14, width: 160 }} />
        <div className="qf-skeleton mt-3" style={{ height: 28, width: "70%" }} />
        <div className="qf-skeleton mt-4" style={{ height: 120, width: "100%" }} />
      </div>
    );
  }

  const isOwn = session?.user_id === post.author.id;
  const isThesis = post.post_type === "thesis";
  const isQuestion = post.post_type === "question";
  const composerLabel = isThesis ? "Challenge or discuss this thesis" : isQuestion ? "Your answer" : "Add to the discussion";
  const composerPlaceholder = isThesis
    ? "Which assumption is weakest? What evidence would change the author's mind?"
    : isQuestion ? "Share a useful answer — explain your reasoning." : "Add your perspective…";
  const submitLabel = isThesis ? "Post Challenge" : isQuestion ? "Post Answer" : "Post Reply";
  const threadTitle = isThesis ? "Challenges & discussion" : isQuestion ? "Answers" : "Replies";

  return (
    <div className={`${c.page} ${c.touch}`}>
      {deleteCommentTarget && (
        <ConfirmDialog message="Delete this reply?" onCancel={() => setDeleteCommentTarget(null)} onConfirm={confirmDeleteComment} />
      )}
      {confirmPostDelete && (
        <ConfirmDialog message="Delete this post?" onCancel={() => setConfirmPostDelete(false)} onConfirm={handlePostDelete} />
      )}

      <Link href={isThesis ? "/community?pillar=thesis" : isQuestion ? "/community?pillar=question" : "/community"}
        className="qf-secondary inline-flex items-center" style={{ minHeight: 44 }}>
        ← {isThesis ? "Thesis" : isQuestion ? "Q&A" : "Community"}
      </Link>

      {isThesis && post.thesis && (
        <header className="mt-2">
          <p className={c.eyebrow}>
            Thesis · {[post.thesis.company.symbol, post.thesis.company.name].filter(Boolean).join(" · ")}
          </p>
          <h1 className={c.docTitle}>{post.thesis.research_title ?? "Investment thesis"}</h1>
        </header>
      )}
      {!isThesis && <h1 className={c.srOnly}>{isQuestion ? "Question" : "Discussion"}</h1>}

      <PostCard
        post={post}
        isOwn={isOwn}
        liked={liked}
        onToggleLike={handleLike}
        bookmarked={bookmarked}
        onToggleBookmark={handleBookmark}
        onEdit={handlePostEdit}
        onDelete={() => setConfirmPostDelete(true)}
        onReport={!isOwn ? handleReport : undefined}
        clamp={false}
      />

      {isThesis && isOwn && post.research_id && (
        <p className="text-sm mt-3">
          <Link href={`/research/${post.research_id}`} className="underline">Open your research in the Research Lab</Link>
        </p>
      )}

      {isThesis && thesis && <ThesisDocument snap={thesis} postContent={post.content} onChallenge={focusComposer} />}
      {isThesis && thesis === null && (
        <p className={`${c.notice} mt-4`}>The full published reasoning for this thesis is no longer available.</p>
      )}

      <section aria-labelledby="thread-title" className="mt-8">
        <h2 id="thread-title" className="qf-section-title">
          {threadTitle} <span className="qf-secondary" style={{ fontSize: 14 }}>({comments.length})</span>
        </h2>

        {canComment ? (
          <form onSubmit={handleNewComment} className="space-y-2 mt-3">
            <label htmlFor="thread-composer" className="qf-card-title block">{composerLabel}</label>
            <textarea
              id="thread-composer"
              ref={composerRef}
              className="qf-input min-h-[100px]"
              placeholder={composerPlaceholder}
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
            />
            <button type="submit" disabled={submitting || !newComment.trim()} className="qf-btn-primary">
              {submitting ? "Posting…" : submitLabel}
            </button>
          </form>
        ) : (
          <p className="text-sm text-ink-soft mt-3">Sign in to join the discussion.</p>
        )}
        {notice && <p className="text-sm mt-2" role="status" style={{ color: "var(--ink-soft)" }}>{notice}</p>}

        <div className={c.thread}>
          {tree.length === 0 && (
            <p className="qf-secondary mt-4">
              {isThesis ? "No challenges yet. Be the first to test this reasoning."
                : isQuestion ? "No answers yet." : "No replies yet."}
            </p>
          )}
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
        <span className={c.srOnly}>{comments.length} {replyNoun(post.post_type, comments.length)}</span>
      </section>
    </div>
  );
}
