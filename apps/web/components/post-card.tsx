"use client";

import Link from "next/link";
import { useState } from "react";
import { Avatar } from "@/components/avatar";
import { formatExactTime, formatRelativeTime } from "@/lib/time";
import type { Post } from "@/lib/types";

export function PostTypeBadge({ postType }: { postType: Post["post_type"] }) {
  if (postType === "question") {
    return (
      <span
        className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded"
        style={{ background: "var(--brass)", color: "var(--cream-0)" }}
      >
        Question
      </span>
    );
  }
  if (postType === "thesis") {
    return (
      <span
        className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded"
        style={{ background: "var(--ink)", color: "var(--cream-0)" }}
      >
        Thesis
      </span>
    );
  }
  return null;
}

export function Timestamp({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} title={formatExactTime(iso)} className="text-xs text-ink-soft">
      {formatRelativeTime(iso)}
    </time>
  );
}

function PostHeaderAndContent({ post }: { post: Post }) {
  return (
    <>
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-sm font-semibold" style={{ color: "var(--ink)" }}>
          {post.author.username ? `@${post.author.username}` : "Member"}
        </span>
        <span className="text-ink-soft text-xs">·</span>
        <Timestamp iso={post.created_at} />
        {post.is_edited && <span className="text-xs text-ink-soft">· edited</span>}
        <PostTypeBadge postType={post.post_type} />
      </div>
      <p className="text-sm mt-1 whitespace-pre-wrap leading-relaxed">{post.content}</p>
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
}

export function PostCard({
  post, href, isOwn, liked, onToggleLike, onToggleBookmark, bookmarked, onDelete, onEdit, onReport,
}: PostCardProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(post.content);
  const [saving, setSaving] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  async function submitEdit() {
    if (!onEdit || !draft.trim()) return;
    setSaving(true);
    try {
      await onEdit(draft);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="py-4 border-b transition-colors hover:bg-black/[0.015]" style={{ borderColor: "var(--line)" }}>
      <div className="flex gap-3">
        <Avatar username={post.author.username} />
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-sm font-semibold" style={{ color: "var(--ink)" }}>
                  {post.author.username ? `@${post.author.username}` : "Member"}
                </span>
                <PostTypeBadge postType={post.post_type} />
              </div>
              <textarea
                className="qf-input min-h-[70px] text-sm"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                autoFocus
              />
              <div className="flex gap-2">
                <button className="qf-btn-primary text-xs" disabled={saving || !draft.trim()} onClick={submitEdit}>
                  {saving ? "Saving…" : "Save"}
                </button>
                <button className="qf-btn-ghost text-xs" onClick={() => { setEditing(false); setDraft(post.content); }}>
                  Cancel
                </button>
              </div>
            </div>
          ) : href ? (
            <Link href={href} className="block focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded" style={{ outlineColor: "var(--brass)" }}>
              <PostHeaderAndContent post={post} />
            </Link>
          ) : (
            <PostHeaderAndContent post={post} />
          )}

          <div className="flex items-center gap-5 mt-2.5">
            <button
              type="button"
              onClick={onToggleLike}
              aria-pressed={liked}
              aria-label={liked ? "Unlike" : "Like"}
              className="flex items-center gap-1.5 text-xs text-ink-soft hover:text-[var(--brass-dark,var(--brass))] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded"
              style={{ outlineColor: "var(--brass)" }}
            >
              <span aria-hidden="true">{liked ? "♥" : "♡"}</span>
              <span>{post.reaction_count}</span>
            </button>

            <span className="flex items-center gap-1.5 text-xs text-ink-soft">
              <span aria-hidden="true">💬</span>
              <span>{post.comment_count}</span>
            </span>

            {onToggleBookmark && (
              <button
                type="button"
                onClick={onToggleBookmark}
                aria-pressed={!!bookmarked}
                aria-label={bookmarked ? "Remove from Saved" : "Save"}
                className="text-xs text-ink-soft hover:text-[var(--brass-dark,var(--brass))] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded"
                style={{ outlineColor: "var(--brass)" }}
              >
                <span aria-hidden="true">{bookmarked ? "🔖" : "🏷"}</span>
              </button>
            )}

            <div className="relative ml-auto">
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                aria-label="More actions"
                aria-expanded={menuOpen}
                className="text-xs text-ink-soft px-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded"
                style={{ outlineColor: "var(--brass)" }}
              >
                ⋯
              </button>
              {menuOpen && (
                <div role="menu" className="absolute right-0 top-6 z-10 qf-card py-1 min-w-[120px]">
                  {isOwn && onEdit && (
                    <button
                      role="menuitem"
                      className="block w-full text-left text-xs px-3 py-1.5 hover:bg-black/5"
                      onClick={() => { setEditing(true); setMenuOpen(false); }}
                    >
                      Edit
                    </button>
                  )}
                  {isOwn && onDelete && (
                    <button
                      role="menuitem"
                      className="block w-full text-left text-xs px-3 py-1.5 hover:bg-black/5"
                      style={{ color: "#9C4B3F" }}
                      onClick={() => { onDelete(); setMenuOpen(false); }}
                    >
                      Delete
                    </button>
                  )}
                  {!isOwn && onReport && (
                    <button
                      role="menuitem"
                      className="block w-full text-left text-xs px-3 py-1.5 hover:bg-black/5"
                      onClick={() => { onReport(); setMenuOpen(false); }}
                    >
                      Report
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
