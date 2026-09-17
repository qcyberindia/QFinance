"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import type { Company, CompanyListResponse, MyResearchItem, MyResearchListResponse } from "@/lib/types";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/states";

const RESEARCH_TYPES = ["deep_dive", "quick_take", "sector_note"];

export default function ResearchPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [researchType, setResearchType] = useState(RESEARCH_TYPES[0]);
  const [title, setTitle] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [items, setItems] = useState<MyResearchItem[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<CompanyListResponse>("/companies?page_size=100")
      .then((data) => setCompanies(data.items))
      .catch(() => setCompanies([]));
  }, []);

  const loadMine = useCallback(async () => {
    setListError(null);
    try {
      // Real endpoint: GET /research/mine (API Spec V2 §2) — the member's own
      // drafts AND published items, distinct from the public /research/library.
      const data = await api.get<MyResearchListResponse>("/research/mine");
      setItems(data.items);
    } catch (err) {
      setListError(err instanceof ApiError ? err.message : "Could not load your research.");
    }
  }, []);

  useEffect(() => {
    loadMine();
  }, [loadMine]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!companyId) {
      setCreateError("Choose a company first.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const created = await api.post<{ id: string }>("/research", {
        company_id: companyId,
        research_type: researchType,
        title: title || undefined,
      });
      router.push(`/research/${created.id}`);
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "Could not start this research item.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-2xl">My Research</h1>
        <p className="text-sm text-ink-soft">
          Your private research workspace. Drafts stay private until you publish.
        </p>
      </div>

      <Card>
        <h2 className="font-display text-lg mb-3">Start new research</h2>
        <form onSubmit={handleCreate} className="space-y-3">
          <div>
            <label className="qf-label">Company</label>
            <select className="qf-input" value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
              <option value="">Select a company…</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>{c.name} ({c.exchange})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="qf-label">Research type</label>
            <select className="qf-input" value={researchType} onChange={(e) => setResearchType(e.target.value)}>
              {RESEARCH_TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
            </select>
          </div>
          <div>
            <label className="qf-label">Working title (optional)</label>
            <input className="qf-input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          {createError && <p className="text-sm" style={{ color: "#9C4B3F" }}>{createError}</p>}
          <button type="submit" disabled={creating} className="qf-btn-primary">
            {creating ? "Creating…" : "Start Draft"}
          </button>
        </form>
      </Card>

      <div>
        <h2 className="font-display text-lg mb-3">Your research</h2>
        {listError && <ErrorState message={listError} onRetry={loadMine} />}
        {!listError && items === null && <LoadingState label="Loading your research…" />}
        {!listError && items !== null && items.length === 0 && (
          <EmptyState title="No research yet" body="Start a draft above to begin building your first thesis." />
        )}
        {!listError && items !== null && items.length > 0 && (
          <div className="space-y-3">
            {items.map((item) => (
              <Link key={item.id} href={`/research/${item.id}`} className="block">
                <Card>
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className="text-xs font-semibold uppercase tracking-wide"
                      style={{ color: item.status === "published" ? "var(--brass)" : "var(--ink-soft)" }}
                    >
                      {item.status}
                    </span>
                    <span className="text-xs text-ink-soft">{item.company.name ?? "Unknown company"}</span>
                  </div>
                  <div className="font-display text-base">{item.title}</div>
                  <p className="text-sm text-ink-soft line-clamp-2">{item.summary}</p>
                  <p className="text-xs text-ink-soft mt-2">
                    Updated {new Date(item.updated_at).toLocaleDateString()}
                    {item.status === "published" ? ` · v${item.current_version}` : ""}
                  </p>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
