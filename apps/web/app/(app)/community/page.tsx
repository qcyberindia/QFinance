"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/session";
import { COMMUNITY_CHANNELS, type Post, type PostListResponse } from "@/lib/types";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { MemberCharterModal } from "@/components/member-charter-modal";

export default function CommunityPage() {
  const { session } = useSession();
  // Basic/Pro product decision (backend: core/deps.py's require_verified_profile,
  // applied to POST /community/channels/{channel}/posts and every other
  // community-participation endpoint) — any Authenticated + Verified user may
  // post, not just Pro/Core members. The frontend can't see verification status
  // from `/auth/session` today (SessionResponse has no such field), so this
  // gate is simply "is there a session at all" — Basic includes everyone once
  // logged in. If a genuinely unverified user attempts to post, the backend's
  // real 403 ("Please verify your email address to continue.") surfaces
  // through the existing catch block below via ApiError.message, same as any
  // other API error — not pre-guessed or duplicated here.
  const canPost = session !== null;

  const [channel, setChannel] = useState<string>("general_discussion");
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [postType, setPostType] = useState<"general" | "question">("general");
  const [posting, setPosting] = useState(false);
  const [showCharterModal, setShowCharterModal] = useState(false);

  const load = useCallback(async (c: string) => {
    setError(null);
    setPosts(null);
    try {
      const data = await api.get<PostListResponse>(`/community/channels/${c}/posts`);
      setPosts(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the feed.");
    }
  }, []);

  useEffect(() => {
    load(channel);
  }, [channel, load]);

  async function submitPost() {
    setPosting(true);
    try {
      await api.post(`/community/channels/${channel}/posts`, { content, post_type: postType });
      setContent("");
      await load(channel);
    } catch (err) {
      if (err instanceof ApiError && err.code === "CHARTER_NOT_ACKNOWLEDGED") {
        // Legitimate backend gate (users/service.py's has_acknowledged_current_charter) —
        // not bypassed. Prompt the real acknowledgment flow instead of erroring out.
        setShowCharterModal(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not publish your post.");
      }
    } finally {
      setPosting(false);
    }
  }

  async function handlePost(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim() || !canPost) return;
    setError(null);
    await submitPost();
  }

  return (
    <div className="space-y-5">
      {showCharterModal && (
        <MemberCharterModal
          onCancel={() => setShowCharterModal(false)}
          onAcknowledged={async () => {
            setShowCharterModal(false);
            await submitPost(); // retry the original post now that the charter is acknowledged
          }}
        />
      )}
      <div>
        <h1 className="font-display text-2xl">Community</h1>
        <p className="text-sm text-ink-soft">Discuss ideas, share reasoning, learn from other members.</p>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {COMMUNITY_CHANNELS.map((c) => (
          <button
            key={c}
            onClick={() => setChannel(c)}
            className="text-xs font-semibold px-3 py-1.5 rounded-full whitespace-nowrap"
            style={{
              border: "1px solid var(--line)",
              background: channel === c ? "var(--brass)" : "transparent",
              color: channel === c ? "var(--cream-0)" : "var(--ink-soft)",
            }}
          >
            {c.replace("_", " ")}
          </button>
        ))}
      </div>

      <Card>
        {canPost ? (
          <form onSubmit={handlePost} className="space-y-3">
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setPostType("general")}
                className="text-xs font-semibold px-3 py-1 rounded-full"
                style={{
                  border: "1px solid var(--line)",
                  background: postType === "general" ? "var(--ink)" : "transparent",
                  color: postType === "general" ? "var(--cream-0)" : "var(--ink-soft)",
                }}
              >
                Discussion
              </button>
              <button
                type="button"
                onClick={() => setPostType("question")}
                className="text-xs font-semibold px-3 py-1 rounded-full"
                style={{
                  border: "1px solid var(--line)",
                  background: postType === "question" ? "var(--ink)" : "transparent",
                  color: postType === "question" ? "var(--cream-0)" : "var(--ink-soft)",
                }}
              >
                Question
              </button>
            </div>
            <textarea
              className="qf-input min-h-[80px]"
              placeholder={postType === "question" ? "What do you want to ask the community?" : "Share something with the community…"}
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
            <button type="submit" disabled={posting || !content.trim()} className="qf-btn-primary">
              {posting ? "Posting…" : postType === "question" ? "Ask" : "Post"}
            </button>
          </form>
        ) : (
          <div className="text-sm text-ink-soft">
            <p>Sign in to post, comment, and join the conversation.</p>
          </div>
        )}
      </Card>

      {error && <ErrorState message={error} onRetry={() => load(channel)} />}
      {!error && posts === null && <LoadingState label="Loading feed…" />}
      {!error && posts !== null && posts.length === 0 && (
        <EmptyState title="Nothing here yet" body="Be the first to post in this channel." />
      )}
      {!error && posts !== null && posts.length > 0 && (
        <div className="space-y-3">
          {posts.map((post) => (
            <Card key={post.id}>
              <Link href={`/community/${post.id}`} className="block">
                <div className="text-xs text-ink-soft mb-1 flex items-center gap-2">
                  {post.post_type === "question" && (
                    <span
                      className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded"
                      style={{ background: "var(--brass)", color: "var(--cream-0)" }}
                    >
                      Question
                    </span>
                  )}
                  {post.post_type === "thesis" && (
                    <span
                      className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded"
                      style={{ background: "var(--ink)", color: "var(--cream-0)" }}
                    >
                      Thesis
                    </span>
                  )}
                  <span className="font-semibold" style={{ color: "var(--ink)" }}>
                    {post.author.username ? `@${post.author.username}` : "Member"}
                  </span>
                  <span>· {new Date(post.created_at).toLocaleDateString()}</span>
                  {post.is_edited && <span>· edited</span>}
                </div>
                <p className="text-sm whitespace-pre-wrap">{post.content}</p>
                <div className="text-xs text-ink-soft mt-3 flex gap-4">
                  <span>{post.reaction_count} likes</span>
                  <span>{post.comment_count} comments</span>
                </div>
              </Link>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
