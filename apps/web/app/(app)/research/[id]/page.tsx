"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import type { Company, CompanyListResponse, ResearchFull } from "@/lib/types";
import { Card, ErrorState, LoadingState } from "@/components/states";
import { ThesisCardFromResearch } from "@/components/ThesisCard";
import { ResearchAssistantPanel } from "@/components/research-assistant-panel";
import {
  SECTIONS, computeProgress, deriveInvestmentThesis, deriveReviewSummary, isSectionFilled, type GuidedSection,
} from "@/lib/research-progress";

/**
 * Research Workspace — Phase 2A: converts existing-but-previously-unwired
 * backend fields into real, editable, persisted sections.
 *
 * FIELD-MAPPING NOTE, updated in the Research-Section-completion pass: the
 * `research` table now also has `management_notes`/`assumptions_outlook`
 * (alembic/versions/0007_research_management_and_assumptions.py, additive-
 * only) so Sections 06/07 are real, persisted fields like every other
 * section below — not fabricated, not client-only. "Investment Thesis" (11)
 * and "Review" (13) remain DERIVED, read-only summaries assembled from
 * already-saved fields (see lib/research-progress.ts's
 * deriveInvestmentThesis/deriveReviewSummary) — correctly so, since neither
 * needs its own database column.
 *
 * VERIFIED before writing any frontend code (per this phase's own "inspect
 * the existing PATCH API before changing it" instruction): `research/
 * schemas.py`'s `ResearchPatchRequest` already accepts every field below as
 * an independently-optional partial-PATCH field, and `research/service.py`'s
 * `patch_draft`/`patch_published` already handle all of them generically via
 * `_PATCHABLE_CONTENT_FIELDS`. NO backend/API change was needed or made for
 * this phase — confirmed, not assumed.
 *
 * Phase 2A verification pass note: `SECTIONS`/`isSectionFilled`/
 * `computeProgress` were extracted to `lib/research-progress.ts` (zero
 * behavior change) so the completeness logic can be tested independently of
 * React — see that file and `lib/research-progress.test.mjs`.
 *
 * Section -> field mapping, all real fields, none invented (all 13 render):
 *   01 Research Focus          -> summary                              FUNCTIONAL
 *   02 Business                -> business_model                       FUNCTIONAL
 *   03 Industry & Competition  -> competitive_position                  FUNCTIONAL
 *   04 Financials              -> financial_snapshot                    FUNCTIONAL
 *   05 Growth Drivers          -> catalysts                             FUNCTIONAL
 *   06 Management              -> management_notes                      FUNCTIONAL (0007 migration)
 *   07 Assumptions & Outlook   -> assumptions_outlook                   FUNCTIONAL (0007 migration)
 *   08 Valuation                -> valuation_range                      FUNCTIONAL (notes/assumptions only — no DCF engine)
 *   09 Bull / Base / Bear       -> bull_case / base_case / bear_case    FUNCTIONAL
 *   10 Risks                    -> risk_register                       FUNCTIONAL
 *   11 Investment Thesis        -> DERIVED (see InvestmentThesisSection) — no field of its own, by design
 *   12 What Could Prove Me Wrong? -> invalidation_conditions            FUNCTIONAL
 *   13 Review                    -> DERIVED (see ReviewSection) — no field of its own, by design
 *
 * Every functional section below is a real textarea bound to a real
 * `ResearchFull` field, saved via the existing `PATCH /research/{id}`
 * endpoint, reloaded from the real backend response — never localStorage as
 * the source of truth. No fake evidence/source UI, no fake thesis field, no
 * probability/expected-return generation, no buy/sell/valuation verdict.
 */

interface GuidedSectionLocalAlias extends GuidedSection {}

type SaveStatus = "idle" | "saving" | "saved" | "error";

/** Generic editable-textarea section — used by every FUNCTIONAL section
 * except 01 (Research Focus, which has its own change-note/publish-aware
 * form) and 09 (Bull/Base/Bear, which needs three fields at once). Reused
 * rather than duplicated per the "no duplicate abstractions" instruction. */
function TextFieldSection({
  meta, value, onSave, disabled,
}: {
  meta: GuidedSection;
  value: string;
  onSave: (newValue: string) => Promise<void>;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState(value);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { setDraft(value); setStatus("idle"); }, [value]);

  async function handleSave() {
    setStatus("saving");
    setErr(null);
    try {
      await onSave(draft);
      setStatus("saved");
    } catch (e) {
      setStatus("error");
      setErr(e instanceof ApiError ? e.message : "Could not save this section.");
    }
  }

  return (
    <Card>
      <label className="qf-label">{meta.n} · {meta.label}</label>
      {meta.question && <p className="text-sm font-medium mt-1">{meta.question}</p>}
      {meta.guidance && (
        <ul className="text-xs text-ink-soft mt-2 mb-3 list-disc pl-4 space-y-0.5">
          {meta.guidance.map((g, i) => <li key={i}>{g}</li>)}
        </ul>
      )}
      {meta.contentLabel && (
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft mt-3 mb-1">{meta.contentLabel}</p>
      )}
      <textarea
        className="qf-input min-h-[140px]"
        value={draft}
        placeholder={meta.placeholder}
        onChange={(e) => { setDraft(e.target.value); setStatus("idle"); }}
        disabled={disabled}
      />
      {err && <p className="text-sm mt-2" style={{ color: "#9C4B3F" }}>{err}</p>}
      <div className="flex items-center gap-3 mt-3">
        <button
          type="button"
          className="qf-btn-primary"
          onClick={handleSave}
          disabled={disabled || status === "saving" || draft === value}
        >
          {status === "saving" ? "Saving…" : "Save"}
        </button>
        {status === "saved" && <span className="text-xs" style={{ color: "var(--brass)" }}>✓ Saved just now</span>}
      </div>
      <p className="text-xs text-ink-soft mt-2">
        Evidence linking will be added in the Evidence phase.
      </p>
    </Card>
  );
}

/** Bull / Base / Bear — three fields, one section. Each saved independently
 * (matches the existing PATCH contract: partial, per-field). */
function ScenarioSection({
  item, onSave, disabled,
}: {
  item: ResearchFull;
  onSave: (field: "bull_case" | "base_case" | "bear_case", value: string) => Promise<void>;
  disabled?: boolean;
}) {
  const rows: { field: "bull_case" | "base_case" | "bear_case"; title: string; helper: string }[] = [
    { field: "bull_case", title: "Bull Case", helper: "Optimistic assumptions." },
    { field: "base_case", title: "Base Case", helper: "Central assumptions." },
    { field: "bear_case", title: "Bear Case", helper: "Downside assumptions." },
  ];
  return (
    <div className="space-y-4">
      {rows.map((row) => (
        <Card key={row.field}>
          <label className="qf-label">{row.title}</label>
          <p className="text-xs text-ink-soft mb-2">{row.helper}</p>
          <ScenarioField field={row.field} value={item[row.field] ?? ""} onSave={onSave} disabled={disabled} />
        </Card>
      ))}
      <p className="text-xs text-ink-soft">
        No probabilities or expected returns are assigned — each scenario is recorded as-is; none is marked correct.
      </p>
    </div>
  );
}

function ScenarioField({
  field, value, onSave, disabled,
}: {
  field: "bull_case" | "base_case" | "bear_case";
  value: string;
  onSave: (field: "bull_case" | "base_case" | "bear_case", value: string) => Promise<void>;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState(value);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { setDraft(value); setStatus("idle"); }, [value]);

  async function handleSave() {
    setStatus("saving");
    setErr(null);
    try {
      await onSave(field, draft);
      setStatus("saved");
    } catch (e) {
      setStatus("error");
      setErr(e instanceof ApiError ? e.message : "Could not save.");
    }
  }

  return (
    <>
      <textarea className="qf-input min-h-[90px]" value={draft} onChange={(e) => { setDraft(e.target.value); setStatus("idle"); }} disabled={disabled} />
      {err && <p className="text-sm mt-1" style={{ color: "#9C4B3F" }}>{err}</p>}
      <div className="flex items-center gap-3 mt-2">
        <button type="button" className="qf-btn-ghost text-xs" onClick={handleSave} disabled={disabled || status === "saving" || draft === value}>
          {status === "saving" ? "Saving…" : "Save"}
        </button>
        {status === "saved" && <span className="text-xs" style={{ color: "var(--brass)" }}>✓ Saved just now</span>}
      </div>
    </>
  );
}

/** Section 11 — Investment Thesis. Read-only, DERIVED entirely from fields
 * the researcher already saved elsewhere — clearly labeled as assembled,
 * not as new or system/AI-generated content (nothing here is AI-generated;
 * the assistant isn't live — see ResearchAssistantPanel). */
function InvestmentThesisSection({ item }: { item: ResearchFull }) {
  const t = deriveInvestmentThesis(item);
  return (
    <Card>
      <div className="flex items-center gap-2 mb-1">
        <label className="qf-label mb-0">11 · Investment Thesis</label>
        <span className="qf-derived-badge">Derived</span>
      </div>
      <p className="text-[11px] text-ink-soft mt-1 mb-3">
        Assembled automatically from what you&apos;ve written in other sections — not a new field, and not
        AI-generated. Edit the source section to change what appears here.
      </p>
      {t.isEmpty ? (
        <p className="text-sm text-ink-soft">Fill in other sections to see your thesis take shape here.</p>
      ) : (
        <div className="space-y-3">
          {t.thesis && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">What I believe</p>
              <p className="text-sm mt-0.5">{t.thesis}</p>
            </div>
          )}
          {t.keyReasons.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">Why I believe it</p>
              <ul className="text-sm mt-0.5 list-disc pl-4 space-y-1">
                {t.keyReasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}
          {t.keyAssumptions.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">Key assumptions</p>
              <ul className="text-sm mt-0.5 list-disc pl-4 space-y-1">
                {t.keyAssumptions.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}
          {t.keyRisks.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">Biggest risks</p>
              <ul className="text-sm mt-0.5 list-disc pl-4 space-y-1">
                {t.keyRisks.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}
          {t.whatWouldProveWrong && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">What would prove me wrong?</p>
              <p className="text-sm mt-0.5">{t.whatWouldProveWrong}</p>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

/** Section 13 — Review. Read-only completeness overview, DERIVED — never a
 * score or recommendation. Each row is a real jump-to-section control
 * ("Edit Section"), and unfilled functional sections say "Not completed"
 * in words, not just a hollow dot, per the no-color-only-meaning rule. */
function ReviewSection({ item, onEditSection }: { item: ResearchFull; onEditSection: (key: string) => void }) {
  const rows = deriveReviewSummary(item);
  return (
    <Card>
      <div className="flex items-center gap-2 mb-1">
        <label className="qf-label mb-0">13 · Review</label>
        <span className="qf-derived-badge">Derived</span>
      </div>
      <p className="text-[11px] text-ink-soft mt-1 mb-3">
        A completeness check only — not a score, rating, or recommendation of any kind.
      </p>
      <ul className="text-sm divide-y" style={{ borderColor: "var(--line)" }}>
        {rows.map((r) => (
          <li key={r.key} className="flex items-center gap-2 py-2">
            <span aria-hidden style={{ color: r.filled ? "var(--brass)" : "var(--line)" }}>
              {r.implemented ? (r.filled ? "●" : "○") : "–"}
            </span>
            <span className="font-mono text-xs text-ink-soft">{r.n}</span>
            <span className="flex-1">{r.label}</span>
            {!r.implemented && <span className="text-[10px] text-ink-soft">soon</span>}
            {r.implemented && !r.filled && <span className="text-[10px] text-ink-soft">Not completed</span>}
            {r.implemented && (
              <button
                type="button"
                className="qf-btn-ghost text-[11px]"
                style={{ padding: "3px 9px" }}
                onClick={() => onEditSection(r.key)}
              >
                Edit Section
              </button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function ResearchWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<ResearchFull | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [activeSection, setActiveSection] = useState<string>("question");
  const [navOpenMobile, setNavOpenMobile] = useState(false);

  const [questionDraft, setQuestionDraft] = useState("");
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);

  const [assistantOpenMobile, setAssistantOpenMobile] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [postingToCommunity, setPostingToCommunity] = useState(false);
  const [communityPostId, setCommunityPostId] = useState<string | null>(null);
  const [changeNote, setChangeNote] = useState("");

  const load = useCallback(async () => {
    setError(null);
    setNotFound(false);
    try {
      const data = await api.get<ResearchFull>(`/research/${id}`);
      setItem(data);
      setQuestionDraft(data.summary);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotFound(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not load this research item.");
      }
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

  async function patchAndReload(patch: Record<string, unknown>) {
    if (!item) return;
    const body = { ...patch };
    if (item.status === "published" && !body.change_note) {
      body.change_note = changeNote || "Updated research section.";
    }
    await api.patch(`/research/${id}`, body);
    await load();
  }

  async function handleSaveQuestion() {
    if (!item) return;
    setSaveStatus("saving");
    setSaveError(null);
    try {
      const patch: Record<string, unknown> = { summary: questionDraft };
      if (item.status === "published") patch.change_note = changeNote || "Updated research question.";
      const updated = await api.patch<{ summary: string }>(`/research/${id}`, patch);
      setItem((prev) => (prev ? { ...prev, summary: updated.summary ?? questionDraft } : prev));
      setSaveStatus("saved");
    } catch (err) {
      setSaveStatus("error");
      setSaveError(err instanceof ApiError ? err.message : "Could not save your research question.");
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
      const post = await api.post<{ id: string }>(`/research/${id}/publish-to-community`, { summary: item.summary });
      setCommunityPostId(post.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not publish this thesis to the community.");
    } finally {
      setPostingToCommunity(false);
    }
  }

  if (notFound) {
    return <ErrorState message="This research item doesn't exist, or you don't have access to it." onRetry={load} />;
  }
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!item) return <LoadingState label="Loading your research workspace…" />;

  const progress = computeProgress(item);
  const activeIndex = SECTIONS.findIndex((s) => s.key === activeSection);
  const activeMeta = SECTIONS[activeIndex];
  const prevSection = activeIndex > 0 ? SECTIONS[activeIndex - 1] : null;
  const nextSection = activeIndex < SECTIONS.length - 1 ? SECTIONS[activeIndex + 1] : null;

  const navList = (
    <nav aria-label="Research sections" className="space-y-0.5">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft mb-2 px-2">Research Workspace</p>
      {SECTIONS.map((s) => (
        <button
          key={s.key}
          type="button"
          onClick={() => { setActiveSection(s.key); setNavOpenMobile(false); }}
          aria-current={activeSection === s.key ? "true" : undefined}
          className="qf-nav-item w-full flex items-center gap-2 text-left text-sm px-2 py-1.5"
          style={{
            background: activeSection === s.key ? "rgba(168,134,62,.10)" : undefined,
            borderLeft: activeSection === s.key ? "2px solid var(--brass)" : "2px solid transparent",
            color: activeSection === s.key ? "var(--ink)" : "var(--ink-soft)",
            fontWeight: activeSection === s.key ? 600 : 400,
          }}
        >
          <span className="font-mono text-xs" style={{ color: "var(--ink-soft)" }}>{s.n}</span>
          <span className="flex-1">{s.label}</span>
          {s.implemented ? (
            isSectionFilled(item, s) ? (
              <span aria-label="Complete" style={{ color: "var(--brass)" }}>●</span>
            ) : (
              <span aria-label="Not started" style={{ color: "var(--line)" }}>○</span>
            )
          ) : (
            <span className="text-[10px] text-ink-soft">soon</span>
          )}
        </button>
      ))}
    </nav>
  );

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <span className="text-xs font-semibold uppercase" style={{ color: "var(--brass)" }}>
              {item.status}{item.status === "published" ? ` · v${item.current_version}` : ""}
            </span>
            <h1 className="font-display text-2xl truncate">{item.title}</h1>
            <p className="text-sm text-ink-soft">
              {companyName} · {item.research_type.replace("_", " ")}
            </p>
            <div className="mt-2 pt-2" style={{ borderTop: "1px dashed var(--line)" }}>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-soft">Research Question</p>
              <p className="text-sm mt-0.5">{item.summary || "— not yet written —"}</p>
            </div>
          </div>
          <div className="text-right text-xs text-ink-soft shrink-0">
            <div>
              Research Progress:{" "}
              <span className="font-semibold" style={{ color: "var(--ink)" }}>
                {progress.done} / {progress.total} sections completed
              </span>
            </div>
            <div className="mt-1">
              {saveStatus === "saving" && "Saving…"}
              {saveStatus === "saved" && "Saved just now"}
              {saveStatus === "error" && <span style={{ color: "#9C4B3F" }}>Not saved</span>}
              {saveStatus === "idle" && `Last updated ${new Date(item.updated_at).toLocaleString()}`}
            </div>
          </div>
        </div>
        <div className="mt-3 h-1.5 rounded-full overflow-hidden" style={{ background: "var(--cream-1)" }}>
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${(progress.done / progress.total) * 100}%`, background: "var(--brass)" }}
          />
        </div>
      </Card>

      {item.status === "published" && <ThesisCardFromResearch research={item} companyName={companyName} />}

      <div className="md:hidden">
        <button
          type="button"
          className="qf-btn-ghost w-full flex items-center justify-between text-sm"
          onClick={() => setNavOpenMobile((v) => !v)}
          aria-expanded={navOpenMobile}
        >
          <span>{activeMeta.n} · {activeMeta.label}</span>
          <span aria-hidden="true">{navOpenMobile ? "▲" : "▼"}</span>
        </button>
        {navOpenMobile && <div className="qf-card p-2 mt-1">{navList}</div>}
      </div>

      <div className="md:flex md:gap-5 md:items-start">
        <div className="hidden md:block qf-card p-3" style={{ width: 220, flexShrink: 0, position: "sticky", top: 16 }}>
          {navList}
        </div>

        <div className="flex-1 min-w-0 space-y-4">
          {activeSection === "question" && (
            <Card>
              <label className="qf-label" htmlFor="research-question">01 · Research Question</label>
              <p className="text-xs text-ink-soft mb-2">
                What are you trying to understand? This becomes your research&apos;s public summary once published.
              </p>
              <ul className="text-xs text-ink-soft mb-3 list-disc pl-4 space-y-0.5">
                <li>What is driving this company&apos;s growth?</li>
                <li>Can the business sustain its current margins?</li>
                <li>What are the biggest risks to the thesis?</li>
              </ul>
              <textarea
                id="research-question"
                className="qf-input min-h-[110px]"
                value={questionDraft}
                onChange={(e) => { setQuestionDraft(e.target.value); setSaveStatus("idle"); }}
                placeholder="e.g. Is this business capable of sustaining growth without eroding margins?"
              />
              {item.status === "published" && (
                <div className="mt-3">
                  <label className="qf-label" htmlFor="change-note">Change note (required to re-publish edits)</label>
                  <input id="change-note" className="qf-input" value={changeNote} onChange={(e) => setChangeNote(e.target.value)} />
                </div>
              )}
              {saveError && <p className="text-sm mt-2" style={{ color: "#9C4B3F" }}>{saveError}</p>}
              <div className="flex items-center gap-3 mt-3">
                <button
                  type="button"
                  className="qf-btn-primary"
                  onClick={handleSaveQuestion}
                  disabled={saveStatus === "saving" || !questionDraft.trim() || questionDraft === item.summary}
                >
                  {saveStatus === "saving" ? "Saving…" : "Save"}
                </button>
                {saveStatus === "saved" && <span className="text-xs" style={{ color: "var(--brass)" }}>✓ Saved just now</span>}
              </div>
            </Card>
          )}

          {activeMeta.implemented && activeMeta.field && activeMeta.key !== "scenarios" && (
            <TextFieldSection
              key={activeMeta.key}
              meta={activeMeta}
              value={(item[activeMeta.field] as string) ?? ""}
              onSave={(v) => patchAndReload({ [activeMeta.field as string]: v })}
            />
          )}

          {activeMeta.key === "scenarios" && (
            <ScenarioSection
              item={item}
              onSave={(field, value) => patchAndReload({ [field]: value })}
            />
          )}

          {activeMeta.key === "thesis" && <InvestmentThesisSection item={item} />}
          {activeMeta.key === "review" && <ReviewSection item={item} onEditSection={setActiveSection} />}

          {!activeMeta.implemented && (
            <Card>
              <label className="qf-label">{activeMeta.n} · {activeMeta.label}</label>
              <div className="mt-3 py-8 text-center">
                <p className="text-sm text-ink-soft">This section is not yet available.</p>
                <p className="text-xs text-ink-soft mt-1">
                  Coming later — this section needs a data-model decision before it can be built.
                </p>
              </div>
            </Card>
          )}

          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              className="qf-btn-ghost text-sm"
              disabled={!prevSection}
              onClick={() => prevSection && setActiveSection(prevSection.key)}
            >
              ← {prevSection ? prevSection.label : "Previous"}
            </button>
            <button
              type="button"
              className="qf-btn-ghost text-sm"
              disabled={!nextSection}
              onClick={() => nextSection && setActiveSection(nextSection.key)}
            >
              {nextSection ? nextSection.label : "Next"} →
            </button>
          </div>
        </div>

        <div className="hidden lg:block">
          <ResearchAssistantPanel currentQuestion={item.summary} />
        </div>
      </div>

      <div className="lg:hidden">
        <button
          type="button"
          className="qf-btn-ghost w-full text-sm"
          onClick={() => setAssistantOpenMobile((v) => !v)}
          aria-expanded={assistantOpenMobile}
        >
          Research Assistant {assistantOpenMobile ? "▲" : "▼"}
        </button>
        {assistantOpenMobile && (
          <div className="mt-2">
            <ResearchAssistantPanel currentQuestion={item.summary} />
          </div>
        )}
      </div>

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

      {error && <p className="text-sm" style={{ color: "#9C4B3F" }}>{error}</p>}

      <div className="flex gap-3 flex-wrap">
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
