"use client";

import { useState } from "react";
import { Avatar } from "@/components/avatar";
import type { Post } from "@/lib/types";

const TYPE_OPTIONS: { value: Post["post_type"]; label: string; placeholder: string }[] = [
  { value: "general", label: "Discussion", placeholder: "Share an idea, question, or thesis…" },
  { value: "question", label: "Question", placeholder: "What do you want to ask the community?" },
  { value: "thesis", label: "Thesis", placeholder: "Lay out your investment thesis…" },
];

export function Composer({
  username,
  onSubmit,
}: {
  username: string | null;
  onSubmit: (content: string, postType: Post["post_type"]) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [content, setContent] = useState("");
  const [postType, setPostType] = useState<Post["post_type"]>("general");
  const [submitting, setSubmitting] = useState(false);

  const active = TYPE_OPTIONS.find((t) => t.value === postType)!;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(content, postType);
      setContent("");
      setExpanded(false);
      setPostType("general");
    } finally {
      setSubmitting(false);
    }
  }

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="w-full flex items-center gap-3 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded"
        style={{ outlineColor: "var(--brass)" }}
      >
        <Avatar username={username} size={32} />
        <span className="text-sm text-ink-soft flex-1 border rounded-full px-4 py-2" style={{ borderColor: "var(--line)" }}>
          Share an idea, question, or thesis…
        </span>
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="py-3 space-y-3">
      <div className="flex gap-2" role="tablist" aria-label="Post type">
        {TYPE_OPTIONS.map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={postType === t.value}
            onClick={() => setPostType(t.value)}
            className="text-xs font-semibold px-3 py-1 rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            style={{
              border: "1px solid var(--line)",
              background: postType === t.value ? "var(--ink)" : "transparent",
              color: postType === t.value ? "var(--cream-0)" : "var(--ink-soft)",
              outlineColor: "var(--brass)",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <textarea
        className="qf-input min-h-[90px]"
        placeholder={active.placeholder}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        autoFocus
      />
      <div className="flex gap-2">
        <button type="submit" disabled={submitting || !content.trim()} className="qf-btn-primary">
          {submitting ? "Posting…" : active.value === "question" ? "Ask" : "Post"}
        </button>
        <button
          type="button"
          className="qf-btn-ghost"
          onClick={() => { setExpanded(false); setContent(""); setPostType("general"); }}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
