"use client";

import { useEffect, useState } from "react";
import { Avatar } from "@/components/avatar";
import type { Post } from "@/lib/types";
import c from "@/components/community/community.module.css";

/** Thesis posts are not composed here — they are published from Research
 * (POST /research/{id}/publish-to-community), which links the post to the
 * author's published, versioned reasoning. */
type ComposerType = "discussion" | "question";

const TYPE_OPTIONS: Record<ComposerType, { label: string; prompt: string; placeholder: string; submit: string }> = {
  discussion: {
    label: "Discussion",
    prompt: "Start a discussion — share an idea worth challenging…",
    placeholder: "What idea do you want to discuss? Lay out your reasoning so others can engage with it.",
    submit: "Post Discussion",
  },
  question: {
    label: "Question",
    prompt: "Ask the community a question…",
    placeholder: "What do you want to understand? Add context so people can give useful answers.",
    submit: "Ask Question",
  },
};

export function Composer({
  username,
  onSubmit,
  types = ["discussion", "question"],
}: {
  username: string | null;
  onSubmit: (content: string, postType: Post["post_type"]) => Promise<void>;
  types?: ComposerType[];
}) {
  const [expanded, setExpanded] = useState(false);
  const [content, setContent] = useState("");
  const [postType, setPostType] = useState<ComposerType>(types[0]);
  const [submitting, setSubmitting] = useState(false);
  const [failed, setFailed] = useState(false);

  // Follow the active pillar when the allowed types change.
  useEffect(() => { setPostType(types[0]); }, [types.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const active = TYPE_OPTIONS[postType];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    setSubmitting(true);
    setFailed(false);
    try {
      await onSubmit(content, postType);
      setContent("");
      setExpanded(false);
    } catch {
      setFailed(true);
    } finally {
      setSubmitting(false);
    }
  }

  if (!expanded) {
    return (
      <div className={c.composer}>
        <button type="button" onClick={() => setExpanded(true)} className={c.composerPrompt}>
          <Avatar username={username} size={28} />
          <span className="flex-1">{types.length === 1 ? active.prompt : "Start a discussion or ask a question…"}</span>
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className={`${c.composer} space-y-3 ${c.touch}`}>
      {types.length > 1 && (
        <div role="radiogroup" aria-label="Post type" className={c.typeSwitch}>
          {types.map((t) => (
            <button
              key={t}
              type="button"
              role="radio"
              aria-checked={postType === t}
              onClick={() => setPostType(t)}
              className={c.typeOption}
            >
              {TYPE_OPTIONS[t].label}
            </button>
          ))}
        </div>
      )}
      <label htmlFor="composer-text" className={c.srOnly}>{active.label}</label>
      <textarea
        id="composer-text"
        className="qf-input min-h-[120px]"
        placeholder={active.placeholder}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        autoFocus
      />
      <p className={c.notice}>
        Share reasoning, not trade calls — no buy/sell recommendations or target prices.
      </p>
      {failed && <p className="text-xs" style={{ color: "var(--down)" }} role="alert">Couldn&apos;t publish your post. Try again.</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={submitting || !content.trim()} className="qf-btn-primary">
          {submitting ? "Posting…" : active.submit}
        </button>
        <button type="button" className="qf-btn-ghost" onClick={() => { setExpanded(false); setContent(""); setFailed(false); }}>
          Cancel
        </button>
      </div>
    </form>
  );
}
