"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import type { Company, CompanyListResponse, MyResearchItem, MyResearchListResponse } from "@/lib/types";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/states";

/** "Research format" — the EXISTING backend `research_type` field
 * (unchanged, same three values as before). Deliberately renamed in the UI
 * only (was "Research type") to avoid colliding with the NEW "Research
 * subject" concept below (Stock / Industry / Economy) — these are two
 * different dimensions and conflating their labels was the actual source
 * of confusion, not the underlying data. No schema/field change. */
const RESEARCH_FORMATS = ["deep_dive", "quick_take", "sector_note"] as const;

/** Research subject universe. Only STOCK can currently be persisted —
 * `research.company_id` is NOT NULL in the schema, so INDUSTRY/ECONOMY have
 * no company to attach to. This is a real, reported backend blocker (see
 * work_memory.md), not something this UI pass may silently work around.
 * Kept honest: both are visibly present (so the product's intent is clear)
 * and visibly disabled (so nobody believes they work). */
const SUBJECT_TYPES = [
  { key: "stock", label: "Stock", helper: "Research a specific listed company.", available: true },
  { key: "industry", label: "Industry", helper: "Coming soon — needs a backend change (no company to attach to yet).", available: false },
  { key: "economy", label: "Economy", helper: "Coming soon — needs a backend change (no company to attach to yet).", available: false },
] as const;

type SubjectKey = (typeof SUBJECT_TYPES)[number]["key"];

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full"
      style={{
        border: `1px solid ${status === "published" ? "var(--brass)" : "var(--line)"}`,
        color: status === "published" ? "var(--brass-dark)" : "var(--ink-soft)",
        background: status === "published" ? "rgba(168,134,62,.08)" : "transparent",
      }}
    >
      {status}
    </span>
  );
}

export default function ResearchPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [subject, setSubject] = useState<SubjectKey>("stock");
  const [researchFormat, setResearchFormat] = useState<(typeof RESEARCH_FORMATS)[number]>(RESEARCH_FORMATS[0]);
  const [question, setQuestion] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [startOpen, setStartOpen] = useState(false);

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
    if (subject !== "stock") {
      setCreateError("This research subject isn't available yet.");
      return;
    }
    if (!companyId) {
      setCreateError("Choose what you're researching first.");
      return;
    }
    if (!question.trim()) {
      setCreateError("Add the question you want this research to answer.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      // BUG FIX (previous pass): `summary` is now sent alongside `title` on
      // create — Section 01 ("Research Question") in the Workspace edits
      // `summary`, not `title`, so the question typed here must land in
      // both or it silently disappears once the workspace opens.
      const created = await api.post<{ id: string }>("/research", {
        company_id: companyId,
        research_type: researchFormat,
        title: question,
        summary: question,
      });
      router.push(`/research/${created.id}`);
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "Could not start this research item.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-8 max-w-3xl mx-auto">
      <div className="text-center py-8">
        <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--brass)" }}>
          Research Workspace
        </p>
        <h1 className="font-display text-3xl mt-2">Research, beyond the numbers.</h1>
        <p className="text-sm text-ink-soft mt-2 max-w-md mx-auto">
          Build an evidence-backed investment case using a structured, 13-section research process.
        </p>
        <button className="qf-btn-primary mt-5" onClick={() => setStartOpen(true)}>
          + Start Research
        </button>
        <div className="flex items-center justify-center gap-4 mt-3 text-xs">
          <a href="#my-research" className="text-ink-soft hover:underline">My Research</a>
          <Link href="/research/explore" className="text-ink-soft hover:underline">Explore Research</Link>
        </div>
      </div>

      {startOpen && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg">Start Research</h2>
            <button
              type="button"
              className="text-xs text-ink-soft qf-btn-ghost"
              style={{ padding: "4px 10px" }}
              onClick={() => setStartOpen(false)}
              aria-label="Close"
            >
              ✕ Close
            </button>
          </div>
          <form onSubmit={handleCreate} className="space-y-5">
            <div>
              <label className="qf-label">1. What are you researching?</label>
              <div className="grid grid-cols-3 gap-2">
                {SUBJECT_TYPES.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => t.available && setSubject(t.key)}
                    disabled={!t.available}
                    title={t.helper}
                    className="text-left px-3 py-2.5 rounded"
                    style={{
                      border: `1px solid ${subject === t.key ? "var(--brass)" : "var(--line)"}`,
                      background: subject === t.key ? "rgba(168,134,62,.08)" : "var(--cream-0)",
                      opacity: t.available ? 1 : 0.55,
                      cursor: t.available ? "pointer" : "not-allowed",
                    }}
                  >
                    <span className="text-sm font-semibold block">{t.label}</span>
                    {!t.available && <span className="text-[10px] text-ink-soft">Coming soon</span>}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-ink-soft mt-1.5">{SUBJECT_TYPES.find((t) => t.key === subject)?.helper}</p>
            </div>

            {subject === "stock" && (
              <div>
                <label className="qf-label" htmlFor="research-company">2. Company</label>
                <select id="research-company" className="qf-input" value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
                  <option value="">Search company…</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>{c.name} ({c.exchange})</option>
                  ))}
                </select>
              </div>
            )}

            <div>
              <label className="qf-label" htmlFor="research-question">3. What's the question you want to answer?</label>
              <textarea
                id="research-question"
                className="qf-input min-h-[80px]"
                placeholder="e.g. Is this business capable of sustaining growth without eroding margins?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <p className="text-[11px] text-ink-soft mt-1">This becomes your research's title and Section 01 focus.</p>
            </div>

            <div>
              <label className="qf-label" htmlFor="research-format">Research format</label>
              <select id="research-format" className="qf-input" value={researchFormat} onChange={(e) => setResearchFormat(e.target.value as (typeof RESEARCH_FORMATS)[number])}>
                {RESEARCH_FORMATS.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
              </select>
            </div>

            {createError && <p className="text-sm" style={{ color: "var(--down)" }}>{createError}</p>}
            <button
              type="submit"
              disabled={creating || subject !== "stock" || !companyId || !question.trim()}
              className="qf-btn-primary w-full"
              title={subject !== "stock" ? "This research subject isn't available yet." : undefined}
            >
              {creating ? "Starting…" : "Start Research →"}
            </button>
          </form>
        </Card>
      )}

      <div id="my-research">
        <h2 className="font-display text-lg mb-3">My Research</h2>
        {listError && <ErrorState message={listError} onRetry={loadMine} />}
        {!listError && items === null && <LoadingState label="Loading your research…" />}
        {!listError && items !== null && items.length === 0 && (
          <EmptyState title="No research yet" body="Start above to begin building your first thesis." />
        )}
        {!listError && items !== null && items.length > 0 && (
          <div className="space-y-3">
            {items.map((item) => (
              <Link key={item.id} href={`/research/${item.id}`} className="block">
                <Card className="qf-clickable">
                  <div className="flex items-center justify-between mb-1 gap-2">
                    <StatusPill status={item.status} />
                    <span className="text-xs text-ink-soft">{item.company.name ?? "Unknown company"}</span>
                  </div>
                  <div className="font-display text-base">{item.title}</div>
                  <p className="text-sm text-ink-soft line-clamp-2">{item.summary}</p>
                  <p className="text-xs text-ink-soft mt-2">
                    {item.research_type.replace("_", " ")} · Updated {new Date(item.updated_at).toLocaleDateString()}
                    {item.status === "published" ? ` · v${item.current_version}` : ""}
                  </p>
                  <p className="text-xs mt-2 font-semibold" style={{ color: "var(--brass-dark)" }}>Continue →</p>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
