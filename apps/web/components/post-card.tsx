"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Avatar } from "@/components/avatar";
import { formatExactTime, formatRelativeTime } from "@/lib/time";
import type { Post } from "@/lib/types";
import c from "@/components/community/community.module.css";

const TYPE_META: Record<Post["post_type"], { label: string; className: string; replies: [string, string] }> = {
  general: { label: "Discussion", className: c.typeDiscussion, replies: ["reply", "replies"] },
  discussion: { label: "Discussion", className: c.typeDiscussion, replies: ["reply", "replies"] },
  question: { label: "Question", className: c.typeQuestion, replies: ["answer", "answers"] },
  thesis: { label: "Thesis", className: c.typeThesis, replies: ["reply", "replies"] },
};

export function PostTypeBadge({ postType }: { postType: Post["post_type"] }) {
  const meta = TYPE_META[postType] ?? TYPE_META.general;
  return <span className={`${c.typeLabel} ${meta.className}`}>{meta.label}</span>;
}

export function replyNoun(postType: Post["post_type"], n: number): string {
  const [one, many] = (TYPE_META[postType] ?? TYPE_META.general).replies;
  return n === 1 ? one : many;
}

export function Timestamp({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} title={formatExactTime(iso)} className="text-xs text-ink-soft">
      {formatRelativeTime(iso)}
    </time>
  );
}

function PostBody({ post, clamp }: { post: Post; clamp: boolean }) {
  // On the detail page the thesis header already shows the subject and title.
  const thesis = post.post_type === "thesis" && clamp ? post.thesis : null;
  return (
    <>
      {thesis && (
        <>
          <p className={c.subject}>
            {[thesis.company.symbol, thesis.company.name].filter(Boolean).join(" · ") || "Published research"}
          </p>
          {thesis.research_title && <p className={c.postTitle}>{thesis.research_title}</p>}
        </>
      )}
      <p className={`${c.postBody} ${clamp ? c.clamp : ""}`}>{post.content}</p>
    </>
  );
}

interface PostCardProps {
  post: Post;
  href?: string;
  isOwn: boolean;
  liked: boolean;
  onToggleLike: () => void;
  onToggleBookmark?: () => void;
  bookmarked?: boolean;
  onDelete?: () => void;
  onEdit?: (newContent: string) => Promise<void>;
  onReport?: () => void;
  /** Feed rows clamp long text; the detail page shows it in full. */
  clamp?: boolean;
}

export function PostCard({
  post, href, isOwn, liked, onToggleLike, onToggleBookmark, bookmarked, onDelete, onEdit, onReport, clamp = !!href,
}: PostCardProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(post.content);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const isThesis = post.post_type === "thesis";
  const authorName = post.author.username ? `@${post.author.username}` : "Member";

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [menuOpen]);

  async function submitEdit() {
    if (!onEdit || !draft.trim()) return;
    setSaving(true);
    setEditError(false);
    try {
      await onEdit(draft);
      setEditing(false);
    } catch {
      setEditError(true);
    } finally {
      setSaving(false);
    }
  }

  const hasMenu = (isOwn && (onEdit || onDelete)) || (!isOwn && onReport);

  return (
    <article className={`${c.post} ${isThesis ? c.postThesis : ""}`} aria-label={`${TYPE_META[post.post_type]?.label ?? "Post"} by ${authorName}`}>
      <div className="flex gap-3">
        <Avatar username={post.author.username} size={32} />
        <div className="min-w-0 flex-1">
          <div className={c.meta}>
            <PostTypeBadge postType={post.post_type} />
            <span aria-hidden>·</span>
            <span className={c.author}>{authorName}</span>
            <span aria-hidden>·</span>
            <Timestamp iso={post.created_at} />
            {post.is_edited && <span>· edited</span>}
          </div>

          {editing ? (
            <div className="space-y-2 mt-2">
              <label htmlFor={`edit-${post.id}`} className={c.srOnly}>Edit post</label>
              <textarea
                id={`edit-${post.id}`}
                className="qf-input min-h-[100px]"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                autoFocus
              />
              {editError && <p className="text-xs" style={{ color: "var(--down)" }} role="alert">Couldn&apos;t save your edit. Try again.</p>}
              <div className="flex gap-2">
                <button className="qf-btn-primary" disabled={saving || !draft.trim() || draft === post.content} onClick={submitEdit}>
                  {saving ? "Saving…" : "Save"}
                </button>
                <button className="qf-btn-ghost" onClick={() => { setEditing(false); setDraft(post.content); setEditError(false); }}>
                  Cancel
                </button>
              </div>
            </div>
          ) : href ? (
            <Link href={href} className={c.postLink}>
              <PostBody post={post} clamp={clamp} />
            </Link>
          ) : (
            <PostBody post={post} clamp={clamp} />
          )}

          <div className={c.actions}>
            <button
              type="button"
              onClick={onToggleLike}
              aria-pressed={liked}
              aria-label={`${liked ? "Unlike" : "Like"} · ${post.reaction_count} ${post.reaction_count === 1 ? "like" : "likes"}`}
              className={`${c.action} ${liked ? c.actionOn : ""}`}
            >
              <span aria-hidden>{liked ? "♥" : "♡"}</span>
              <span aria-hidden>{post.reaction_count}</span>
            </button>

            {href ? (
              <Link href={href} className={c.action} aria-label={`${post.comment_count} ${replyNoun(post.post_type, post.comment_count)}`}>
                <span aria-hidden>↳</span>
                <span aria-hidden>{post.comment_count} {replyNoun(post.post_type, post.comment_count)}</span>
              </Link>
            ) : (
              <span className={c.action}>{post.comment_count} {replyNoun(post.post_type, post.comment_count)}</span>
            )}

            {onToggleBookmark && (
              <button
                type="button"
                onClick={onToggleBookmark}
                aria-pressed={!!bookmarked}
                className={`${c.action} ${bookmarked ? c.actionOn : ""}`}
              >
                {bookmarked ? "Saved" : "Save"}
              </button>
            )}

            {hasMenu && (
              <div className="relative ml-auto" ref={menuRef}>
                <button
                  type="button"
                  onClick={() => setMenuOpen((v) => !v)}
                  aria-label="More actions"
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  className={c.action}
                >
                  ⋯
                </button>
                {menuOpen && (
                  <div role="menu" className={c.menu}>
                    {isOwn && onEdit && (
                      <button role="menuitem" className={c.menuItem} onClick={() => { setEditing(true); setMenuOpen(false); }}>
                        Edit
                      </button>
                    )}
                    {isOwn && onDelete && (
                      <button role="menuitem" className={`${c.menuItem} ${c.menuDanger}`} onClick={() => { onDelete(); setMenuOpen(false); }}>
                        Delete
                      </button>
                    )}
                    {!isOwn && onReport && (
                      <button role="menuitem" className={c.menuItem} onClick={() => { onReport(); setMenuOpen(false); }}>
                        Report
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
