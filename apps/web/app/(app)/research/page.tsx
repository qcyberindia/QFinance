"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import type { Company, CompanyListResponse } from "@/lib/types";
import { Card, NotAvailableYet } from "@/components/states";

const RESEARCH_TYPES = ["deep_dive", "quick_take", "sector_note"];

export default function ResearchPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [researchType, setResearchType] = useState(RESEARCH_TYPES[0]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api
      .get<CompanyListResponse>("/companies?page_size=100")
      .then((data) => setCompanies(data.items))
      .catch(() => setCompanies([]));
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!companyId) {
      setError("Choose a company first.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const created = await api.post<{ id: string }>("/research", {
        company_id: companyId,
        research_type: researchType,
        title: title || undefined,
      });
      router.push(`/research/${created.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start this research item.");
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
          {error && <p className="text-sm" style={{ color: "#9C4B3F" }}>{error}</p>}
          <button type="submit" disabled={creating} className="qf-btn-primary">
            {creating ? "Creating…" : "Start Draft"}
          </button>
        </form>
      </Card>

      {/* GENUINE BACKEND GAP: there is no "list my own research (drafts +
          published)" JSON endpoint in the current backend — only the public
          /research/library (published-only, all authors) and
          /research/export.csv (CSV, not JSON) exist. This is documented in
          work_memory.md rather than faked with a wrong endpoint call. */}
      <NotAvailableYet feature="Your research list" />
    </div>
  );
}
