"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import type { Company, CompanyListResponse, ResearchFull } from "@/lib/types";
import { Card, ErrorState, LoadingState } from "@/components/states";
import { ThesisCardFromResearch } from "@/components/ThesisCard";

const SECTION_FIELDS: { key: keyof ResearchFull; label: string }[] = [
  { key: "business_quality", label: "Q — Quality" },
  { key: "financial_snapshot", label: "R — Reality" },
  { key: "business_model", label: "E — Economics" },
  { key: "competitive_position", label: "S — Strength" },
  { key: "valuation_range", label: "E — Estimate" },
  { key: "bull_case", label: "A — Bull Case" },
  { key: "base_case", label: "A — Base Case" },
  { key: "bear_case", label: "A — Bear Case (required to publish)" },
  { key: "risk_register", label: "R — Risk" },
  { key: "catalysts", label: "C — Catalyst" },
  { key: "invalidation_conditions", label: "H — Hypothesis" },
];

export default function ResearchEditorPage() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<ResearchFull | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [postingToCommunity, setPostingToCommunity] = useState(false);
  const [communityPostId, setCommunityPostId] = useState<string | null>(null);
  const [changeNote, setChangeNote] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await api.get<ResearchFull>(`/research/${id}`);
      setItem(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this research item.");
    }
  }, [id]);

  useEffect(() => {
    load();
    api
      .get<CompanyListResponse>("/companies?page_size=100")
      .then((d) => setCompanies(d.items))
      .catch(() => setCompanies([]));
  }, [load]);

  const companyName = companies.find((c) => c.id === item?.company_id)?.name ?? "This company";

  function updateField(key: keyof ResearchFull, value: string) {
    setItem((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  async function handleSave() {
    if (!item) return;
    setSaving(true);
    setError(null);
    try {
      const patch: Record<string, unknown> = {
        title: item.title,
        summary: item.summary,
        ...Object.fromEntries(SECTION_FIELDS.map((f) => [f.key, item[f.key]])),
      };
      if (item.status === "published") patch.change_note = changeNote;
      await api.patch(`/research/${id}`, patch);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your changes.");
    } finally {
      setSaving(false);
    }
  }

  async function handlePublish() {
    setPublishing(true);
    setError(null);
    try {
      await api.post(`/research/${id}/publish`, { change_note: changeNote || undefined });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "This item isn't ready to publish yet.");
    } finally {
      setPublishing(false);
    }
  }

  async function handlePublishToCommunity() {
    if (!item) return;
    setPostingToCommunity(true);
    setError(null);
    try {
      const post = await api.post<{ id: string }>(`/research/${id}/publish-to-community`, {
        summary: item.summary,
      });
      setCommunityPostId(post.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not publish this thesis to the community.");
    } finally {
      setPostingToCommunity(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!item) return <LoadingState label="Loading research…" />;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-xs font-semibold uppercase" style={{ color: "var(--brass)" }}>{item.status}</span>
          <h1 className="font-display text-2xl">{item.title}</h1>
        </div>
        {item.status === "published" ? (
          <span className="text-xs text-ink-soft">v{item.current_version}</span>
        ) : null}
      </div>

      {item.status === "published" && (
        <ThesisCardFromResearch research={item} companyName={companyName} />
      )}

      <Card>
        <label className="qf-label">Title</label>
        <input className="qf-input mb-3" value={item.title} onChange={(e) => updateField("title", e.target.value)} />
        <label className="qf-label">Summary</label>
        <textarea className="qf-input min-h-[70px]" value={item.summary} onChange={(e) => updateField("summary", e.target.value)} />
      </Card>

      {SECTION_FIELDS.map((f) => (
        <Card key={f.key}>
          <label className="qf-label">{f.label}</label>
          <textarea
            className="qf-input min-h-[70px]"
            value={(item[f.key] as string) || ""}
            onChange={(e) => updateField(f.key, e.target.value)}
          />
        </Card>
      ))}

      <Card>
        <label className="qf-label">Sources ({item.sources.length})</label>
        {item.sources.length === 0 ? (
          <p className="text-sm text-ink-soft">At least one source is required to publish.</p>
        ) : (
          <ul className="text-sm space-y-1">
            {item.sources.map((s) => <li key={s.id}>{s.label} — {s.reference}</li>)}
          </ul>
        )}
      </Card>

      {item.status === "published" && (
        <Card>
          <label className="qf-label">Change note (required to re-publish edits)</label>
          <input className="qf-input" value={changeNote} onChange={(e) => setChangeNote(e.target.value)} />
        </Card>
      )}

      {error && <p className="text-sm" style={{ color: "#9C4B3F" }}>{error}</p>}

      <div className="flex gap-3 flex-wrap">
        <button className="qf-btn-ghost" onClick={handleSave} disabled={saving}>
          {saving ? "Saving…" : "Save Draft"}
        </button>
        <button className="qf-btn-gold" onClick={handlePublish} disabled={publishing}>
          {publishing ? "Publishing…" : item.status === "published" ? "Re-publish" : "Publish"}
        </button>
        {item.status === "published" && !communityPostId && (
          <button className="qf-btn-primary" onClick={handlePublishToCommunity} disabled={postingToCommunity}>
            {postingToCommunity ? "Sharing…" : "Share to Community"}
          </button>
        )}
        {communityPostId && (
          <a href={`/community/${communityPostId}`} className="qf-btn-primary">
            View in Community →
          </a>
        )}
      </div>
    </div>
  );
}
