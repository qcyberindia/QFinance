"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/session";
import { COMMUNITY_CHANNELS, type Post, type PostListResponse } from "@/lib/types";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/states";

export default function CommunityPage() {
  const { session } = useSession();
  // Mirrors the backend's actual gate on POST /community/channels/{channel}/posts
  // (require_role("MEMBER") — unchanged from V1, confirmed unchanged by API Spec
  // V2 §3: "All moderation/visibility/RBAC rules from V1 §4/§5 apply unchanged").
  // FREE_MEMBER genuinely cannot post per the locked spec — this is not a bug to
  // route around, it's a real entitlement the UI was simply failing to communicate.
  const canPost = session?.effective_tier === "CORE";

  const [channel, setChannel] = useState<string>("general_discussion");
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [posting, setPosting] = useState(false);

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

  async function handlePost(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim() || !canPost) return;
    setPosting(true);
    try {
      await api.post(`/community/channels/${channel}/posts`, { content });
      setContent("");
      await load(channel);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not publish your post.");
    } finally {
      setPosting(false);
    }
  }

  return (
    <div className="space-y-5">
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
            <textarea
              className="qf-input min-h-[80px]"
              placeholder="Share something with the community…"
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
            <button type="submit" disabled={posting || !content.trim()} className="qf-btn-primary">
              {posting ? "Posting…" : "Post"}
            </button>
          </form>
        ) : (
          <div className="text-sm text-ink-soft">
            <p>Posting is a Core membership benefit.</p>
            <p className="mt-1">
              You can still read the community feed on Free. Upgrading to Core — to post, comment, and join the
              conversation — isn&apos;t available in this app yet.
            </p>
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
                  <span className="font-semibold" style={{ color: "var(--ink)" }}>
                    {post.author.name || post.author.username || "Member"}
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
