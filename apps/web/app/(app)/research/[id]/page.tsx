"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import type { ResearchFull } from "@/lib/types";
import { ErrorState } from "@/components/states";
import { ThesisCardFromResearch } from "@/components/ThesisCard";
import { ResearchAssistantPanel } from "@/components/research-assistant-panel";
import { useSession } from "@/lib/session";
import {
  SECTIONS, STAGE_GROUPS, STAGE_PURPOSE, computeProgress, deriveInvestmentThesis, deriveReviewSummary,
  isSectionFilled, type GuidedSection,
} from "@/lib/research-progress";
import s from "@/components/research/research.module.css";

/**
 * Research Workspace — three areas that read as one workspace:
 *   LEFT   progress rail (STAGE_GROUPS over lib/research-progress.ts SECTIONS)
 *   CENTER one research document for the active stage
 *   RIGHT  the contextual Research Assistant (follows the active stage)
 *
 * Section -> field mapping is unchanged (all real `ResearchFull` fields,
 * saved via the existing `PATCH /research/{id}`; see lib/research-progress.ts):
 *   01 question -> summary, 02 business -> business_model, 03 industry ->
 *   competitive_position, 04 financials -> financial_snapshot, 05 growth ->
 *   catalysts, 06 management -> management_notes, 07 forecast ->
 *   assumptions_outlook, 08 valuation -> valuation_range, 09 scenarios ->
 *   bull/base/bear_case, 10 risks -> risk_register, 11 thesis -> DERIVED,
 *   12 invalidation -> invalidation_conditions, 13 review -> DERIVED.
 *
 * Each field has ONE surface: saved content renders as document prose with
 * an Edit action; the editor only appears when writing or editing. Publishing
 * concepts live in 13 · Review only. No fake evidence, no scoring, no
 * buy/sell verdicts, and AI content is never saved without Add to Research.
 */

type SaveStatus = "idle" | "saving" | "saved" | "error";

function Prose({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  return (
    <div className={s.prose}>
      {paragraphs.map((p, i) => <p key={i}>{p}</p>)}
    </div>
  );
}

/** One field, one surface: document view when saved, editor when writing. */
function ResearchField({
  id, ownerLabel, stageLabel, value, onSave, placeholder, emptyText, editorPrompt, published, changeNote, onChangeNote,
  readOnly = false,
}: {
  id: string;
  ownerLabel: string;
  stageLabel: string;
  value: string;
  onSave: (v: string) => Promise<void>;
  placeholder?: string;
  emptyText?: string;
  editorPrompt?: string;
  published: boolean;
  changeNote: string;
  onChangeNote: (v: string) => void;
  /** Another member viewing published research: document only, no editing. */
  readOnly?: boolean;
}) {
  const hasValue = value.trim().length > 0;
  if (readOnly) {
    return (
      <div>
        <div className={s.blockHead}>
          <span className={s.ownership}><span className={s.ownerDot} aria-hidden /> {ownerLabel.replace(/^Your /, "Author's ")}</span>
        </div>
        {hasValue ? <Prose text={value} /> : <p className="qf-secondary">The author didn&apos;t write this section.</p>}
      </div>
    );
  }
  return <EditableResearchField {...{ id, ownerLabel, stageLabel, value, onSave, placeholder, emptyText, editorPrompt, published, changeNote, onChangeNote }} />;
}

function EditableResearchField({
  id, ownerLabel, stageLabel, value, onSave, placeholder, emptyText, editorPrompt, published, changeNote, onChangeNote,
}: {
  id: string;
  ownerLabel: string;
  stageLabel: string;
  value: string;
  onSave: (v: string) => Promise<void>;
  placeholder?: string;
  emptyText?: string;
  editorPrompt?: string;
  published: boolean;
  changeNote: string;
  onChangeNote: (v: string) => void;
}) {
  const hasValue = value.trim().length > 0;
  const [editing, setEditing] = useState(!hasValue);
  const [draft, setDraft] = useState(value);
  const [status, setStatus] = useState<SaveStatus>("idle");

  // Keep in sync with the server (e.g. after an AI answer is added) unless
  // the user is mid-edit.
  useEffect(() => {
    if (!editing) setDraft(value);
    if (!value.trim()) setEditing(true);
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSave() {
    setStatus("saving");
    try {
      await onSave(draft);
      setStatus("saved");
      setEditing(!draft.trim());
    } catch {
      setStatus("error");
    }
  }

  const dirty = draft !== value;

  return (
    <div>
      <div className={s.blockHead}>
        <span className={s.ownership}><span className={s.ownerDot} aria-hidden /> {ownerLabel}</span>
        {!editing && (
          <button type="button" className={s.linkBtn} onClick={() => { setDraft(value); setEditing(true); setStatus("idle"); }}>
            Edit<span className={s.srOnly}> {stageLabel}</span>
          </button>
        )}
      </div>

      {!editing ? (
        <>
          <Prose text={value} />
          {status === "saved" && (
            <p className={`${s.status} ${s.statusOk} mt-3`} role="status">✓ Saved to {stageLabel}</p>
          )}
        </>
      ) : (
        <>
          {editorPrompt && <label htmlFor={id} className="qf-card-title block mb-2">{editorPrompt}</label>}
          {!editorPrompt && <label htmlFor={id} className={s.srOnly}>{ownerLabel} — {stageLabel}</label>}
          {!hasValue && emptyText && !draft && <p className="qf-secondary mb-2">{emptyText}</p>}
          <textarea
            id={id}
            className={`qf-input ${s.editor}`}
            value={draft}
            placeholder={placeholder}
            onChange={(e) => { setDraft(e.target.value); setStatus("idle"); }}
          />
          {published && (
            <div className="mt-3">
              <label className="qf-label" htmlFor={`${id}-note`}>Change note for this edit</label>
              <input id={`${id}-note`} className="qf-input" value={changeNote} onChange={(e) => onChangeNote(e.target.value)} />
            </div>
          )}
          <div className={s.actions}>
            <button
              type="button"
              className="qf-btn-primary"
              onClick={handleSave}
              disabled={status === "saving" || !dirty || !draft.trim()}
              aria-busy={status === "saving"}
            >
              {status === "saving" ? "Saving…" : "Save to Research"}
            </button>
            {hasValue && (
              <button type="button" className={s.linkBtn} onClick={() => { setDraft(value); setEditing(false); setStatus("idle"); }}>
                Cancel
              </button>
            )}
            {status === "error" && (
              <span className={`${s.status} ${s.statusErr}`} role="alert">Couldn&apos;t save. Please try again.</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function StageRail({ item, activeKey, onSelect }: { item: ResearchFull; activeKey: string; onSelect: (key: string) => void }) {
  return (
    <nav aria-label="Research progress">
      {STAGE_GROUPS.map((group) => (
        <div key={group.label} className={s.group}>
          <p className={s.groupLabel}>{group.label}</p>
          <ol className="grid gap-0.5">
            {group.keys.map((key) => {
              const meta = SECTIONS.find((x) => x.key === key);
              if (!meta) return null;
              const current = key === activeKey;
              const done = isSectionFilled(item, meta);
              const state = current ? (done ? "current, completed" : "current") : done ? "completed" : "upcoming";
              return (
                <li key={key}>
                  <button
                    type="button"
                    onClick={() => onSelect(key)}
                    aria-current={current ? "step" : undefined}
                    className={`${s.stage} ${current ? s.stageCurrent : ""} ${done && !current ? s.stageDone : ""}`}
                  >
                    <span
                      className={`${s.marker} ${done ? s.markerDone : ""} ${current && !done ? s.markerCurrent : ""}`}
                      aria-hidden
                    >
                      {done ? "✓" : ""}
                    </span>
                    <span className={s.stageNum}>{meta.n}</span>
                    <span className="flex-1 min-w-0">{meta.label}</span>
                    <span className={s.srOnly}>, {state}{meta.derived ? ", assembled from other sections" : ""}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
      ))}
    </nav>
  );
}

function InvestmentThesisBody({ item }: { item: ResearchFull }) {
  const t = deriveInvestmentThesis(item);
  if (t.isEmpty) {
    return <p className={s.emptyNote}>Fill in other sections to see your thesis take shape here.</p>;
  }
  const list = (title: string, rows: string[]) => rows.length > 0 && (
    <section className={s.block}>
      <p className={`${s.blockLabel} mb-2`}>{title}</p>
      {rows.map((r, i) => <div key={i} className={i ? "mt-3" : ""}><Prose text={r} /></div>)}
    </section>
  );
  return (
    <>
      {t.thesis && (
        <section className={s.block}>
          <p className={`${s.blockLabel} mb-2`}>What I believe</p>
          <Prose text={t.thesis} />
        </section>
      )}
      {list("Why I believe it", t.keyReasons)}
      {list("Key assumptions", t.keyAssumptions)}
      {list("Biggest risks", t.keyRisks)}
      {t.whatWouldProveWrong && (
        <section className={s.block}>
          <p className={`${s.blockLabel} mb-2`}>What would prove me wrong?</p>
          <Prose text={t.whatWouldProveWrong} />
        </section>
      )}
    </>
  );
}

/** Review → publish readiness. Mirrors the backend's publish gate
 * (research/validation.py validate_publish_readiness) so the author can
 * see and complete every requirement here — sources, disclosures and the
 * research date had no input anywhere in the workspace before. */
function PublishChecklist({
  item, onPatch, onReload, onSelect,
}: {
  item: ResearchFull;
  onPatch: (patch: Record<string, unknown>) => Promise<void>;
  onReload: () => Promise<void>;
  onSelect: (key: string) => void;
}) {
  const d = item.disclosure;
  const [label, setLabel] = useState("");
  const [reference, setReference] = useState("");
  const [addingSource, setAddingSource] = useState(false);
  const [conflict, setConflict] = useState<boolean | null>(d.conflict_disclosed);
  const [conflictDetail, setConflictDetail] = useState(d.conflict_detail ?? "");
  const [position, setPosition] = useState<boolean | null>(d.position_disclosed);
  const [positionDetail, setPositionDetail] = useState(d.position_detail ?? "");
  const [researchDate, setResearchDate] = useState(d.research_date ?? "");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [sourceError, setSourceError] = useState(false);

  const checks: { ok: boolean; label: string; go?: string }[] = [
    { ok: !!item.summary?.trim(), label: "Research question written", go: "question" },
    { ok: !!item.bear_case?.trim(), label: "Bear case written", go: "scenarios" },
    { ok: item.sources.length > 0, label: "At least one source" },
    { ok: d.conflict_disclosed !== null && d.position_disclosed !== null, label: "Conflict and position disclosures answered" },
    { ok: !!d.research_date, label: "Research date set" },
  ];

  async function addSource(e: React.FormEvent) {
    e.preventDefault();
    if (!label.trim() || !reference.trim()) return;
    setAddingSource(true);
    setSourceError(false);
    try {
      await api.post(`/research/${item.id}/sources`, { label: label.trim(), reference: reference.trim() });
      setLabel("");
      setReference("");
      await onReload();
    } catch {
      setSourceError(true);
    } finally {
      setAddingSource(false);
    }
  }

  async function saveDisclosures() {
    setStatus("saving");
    try {
      await onPatch({
        conflict_disclosed: conflict, conflict_detail: conflict ? conflictDetail : "",
        position_disclosed: position, position_detail: position ? positionDetail : "",
        research_date: researchDate || null,
      });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  const yesNo = (name: string, value: boolean | null, set: (v: boolean) => void) => (
    <div role="radiogroup" aria-label={name} className="flex gap-4 mt-1">
      {[true, false].map((v) => (
        <label key={String(v)} className="inline-flex items-center gap-2 text-sm" style={{ minHeight: 44 }}>
          <input type="radio" name={name} checked={value === v} onChange={() => set(v)} />
          {v ? "Yes" : "No"}
        </label>
      ))}
    </div>
  );

  return (
    <>
      <section className={s.block}>
        <p className={`${s.blockLabel} mb-2`}>Ready to publish?</p>
        <ul className="grid gap-1">
          {checks.map((ch) => (
            <li key={ch.label} className="flex items-center gap-3 text-sm" style={{ minHeight: 32 }}>
              <span className={`${s.marker} ${ch.ok ? s.markerDone : ""}`} aria-hidden>{ch.ok ? "✓" : ""}</span>
              <span className="flex-1">{ch.label}<span className={s.srOnly}>{ch.ok ? " — done" : " — missing"}</span></span>
              {!ch.ok && ch.go && (
                <button type="button" className={s.linkBtn} onClick={() => onSelect(ch.go!)}>Open</button>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className={s.block}>
        <p className={`${s.blockLabel} mb-2`}>Sources ({item.sources.length})</p>
        {item.sources.length > 0 && (
          <ul className="text-sm space-y-1.5 mb-3">
            {item.sources.map((src) => (
              <li key={src.id} style={{ overflowWrap: "anywhere" }}>{src.label} — <span className="qf-secondary">{src.reference}</span></li>
            ))}
          </ul>
        )}
        <form onSubmit={addSource} className="grid gap-2 sm:grid-cols-[1fr_1.4fr_auto] items-end">
          <div>
            <label className="qf-label" htmlFor="src-label">Source</label>
            <input id="src-label" className="qf-input" placeholder="e.g. Annual report FY26" value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          <div>
            <label className="qf-label" htmlFor="src-ref">Link or reference</label>
            <input id="src-ref" className="qf-input" placeholder="https://… or page reference" value={reference} onChange={(e) => setReference(e.target.value)} />
          </div>
          <button type="submit" className="qf-btn-ghost" disabled={addingSource || !label.trim() || !reference.trim()}>
            {addingSource ? "Adding…" : "Add source"}
          </button>
        </form>
        {sourceError && <p className={`${s.status} ${s.statusErr} mt-2`} role="alert">Couldn&apos;t add this source. Try again.</p>}
        <p className="qf-secondary mt-3" style={{ fontSize: 12 }}>
          Market data, recent developments and financial data are not connected — this research reflects only
          company information on file and what you&apos;ve written.
        </p>
      </section>

      <section className={s.block}>
        <p className={`${s.blockLabel} mb-2`}>Disclosures</p>
        <fieldset>
          <legend className="text-sm font-semibold">Do you have a conflict of interest with this company?</legend>
          {yesNo("Conflict of interest", conflict, setConflict)}
          {conflict && (
            <>
              <label className="qf-label mt-2" htmlFor="conflict-detail">Describe the conflict</label>
              <input id="conflict-detail" className="qf-input" value={conflictDetail} onChange={(e) => setConflictDetail(e.target.value)} />
            </>
          )}
        </fieldset>
        <fieldset className="mt-4">
          <legend className="text-sm font-semibold">Do you hold a position in this company?</legend>
          {yesNo("Position held", position, setPosition)}
          {position && (
            <>
              <label className="qf-label mt-2" htmlFor="position-detail">Describe the position (no amounts required)</label>
              <input id="position-detail" className="qf-input" value={positionDetail} onChange={(e) => setPositionDetail(e.target.value)} />
            </>
          )}
        </fieldset>
        <div className="mt-4" style={{ maxWidth: 240 }}>
          <label className="qf-label" htmlFor="research-date">Research date</label>
          <input id="research-date" type="date" className="qf-input" value={researchDate} onChange={(e) => setResearchDate(e.target.value)} />
        </div>
        <div className={s.actions}>
          <button
            type="button"
            className="qf-btn-primary"
            onClick={saveDisclosures}
            disabled={status === "saving" || conflict === null || position === null || !researchDate}
          >
            {status === "saving" ? "Saving…" : "Save disclosures"}
          </button>
          {status === "saved" && <span className={`${s.status} ${s.statusOk}`} role="status">✓ Disclosures saved</span>}
          {status === "error" && <span className={`${s.status} ${s.statusErr}`} role="alert">Couldn&apos;t save. Try again.</span>}
        </div>
      </section>
    </>
  );
}

export default function ResearchWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const { session } = useSession();
  const [item, setItem] = useState<ResearchFull | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [activeSection, setActiveSection] = useState<string>("question");
  const [railOpenMobile, setRailOpenMobile] = useState(false);

  const [changeNote, setChangeNote] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [postingToCommunity, setPostingToCommunity] = useState(false);
  const [communityPostId, setCommunityPostId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    setNotFound(false);
    try {
      setItem(await api.get<ResearchFull>(`/research/${id}`));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true);
      else setLoadError("We couldn't load this research right now.");
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  function selectSection(key: string) {
    setActiveSection(key);
    setRailOpenMobile(false);
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
      document.getElementById("research-document")?.scrollIntoView({ block: "start" });
    }
  }

  async function patchAndReload(patch: Record<string, unknown>) {
    if (!item) return;
    const body = { ...patch };
    if (item.status === "published" && !body.change_note) {
      body.change_note = changeNote || "Updated research section.";
    }
    await api.patch(`/research/${id}`, body);
    await load();
  }

  async function handlePublish() {
    setPublishing(true);
    setPublishError(null);
    try {
      await api.post(`/research/${id}/publish`, { change_note: changeNote || undefined });
      await load();
    } catch (err) {
      // Publish validation messages are user-facing guidance (e.g. a missing source).
      const missing = err instanceof ApiError && err.fields ? Object.keys(err.fields).map((f) => f.replace(/_/g, " ")).join(", ") : "";
      setPublishError(missing ? `Not ready to publish yet — still needed: ${missing}.` : "This research isn't ready to publish yet.");
    } finally {
      setPublishing(false);
    }
  }

  async function handlePublishToCommunity() {
    if (!item) return;
    setPostingToCommunity(true);
    setPublishError(null);
    try {
      const post = await api.post<{ id: string }>(`/research/${id}/publish-to-community`, { summary: item.summary });
      setCommunityPostId(post.id);
    } catch {
      setPublishError("Couldn't publish this thesis to Community. Try again.");
    } finally {
      setPostingToCommunity(false);
    }
  }

  if (notFound) {
    return <ErrorState message="This research doesn't exist, or you don't have access to it." onRetry={load} />;
  }
  if (loadError) return <ErrorState message={loadError} onRetry={load} />;
  if (!item) {
    return (
      <div aria-busy="true" aria-label="Loading your research workspace" className="space-y-4 py-2">
        <div className="qf-skeleton" style={{ height: 14, width: 120 }} />
        <div className="qf-skeleton" style={{ height: 30, width: "55%" }} />
        <div className="qf-skeleton" style={{ height: 3, width: "100%" }} />
        <div className="grid gap-3 pt-4">
          <div className="qf-skeleton" style={{ height: 18, width: "40%" }} />
          <div className="qf-skeleton" style={{ height: 120, width: "100%" }} />
        </div>
      </div>
    );
  }

  const progress = computeProgress(item);
  const activeIndex = SECTIONS.findIndex((x) => x.key === activeSection);
  const meta: GuidedSection = SECTIONS[activeIndex];
  const nextSection = activeIndex < SECTIONS.length - 1 ? SECTIONS[activeIndex + 1] : null;
  const published = item.status === "published";
  // Published research is open to every member (Qfinera is free); only the
  // author edits. Drafts never reach other members (the API returns 404).
  const readOnly = !!session && session.user_id !== item.author_id;
  const fieldProps = { published, changeNote, onChangeNote: setChangeNote, readOnly };

  return (
    <div className={`space-y-6 ${s.touch}`}>
      {/* ---- Header: what company, what research, how far along ---- */}
      <header className={s.header}>
        <p className="qf-metadata">
          {item.company.symbol && <span style={{ color: "var(--ink)", fontWeight: 600 }}>{item.company.symbol}</span>}
          {item.company.exchange && <> · {item.company.exchange}</>}
          {" · "}
          <span style={{ color: published ? "var(--up)" : "var(--brass-dark)" }}>
            {published ? `Published · v${item.current_version}` : "Draft"}
          </span>
          {readOnly && <> · Read-only</>}
        </p>
        <h1 className="qf-page-title mt-1.5">{item.company.name ?? item.title}</h1>
        <p className="qf-secondary mt-0.5">
          {item.title !== item.company.name && <>{item.title} · </>}
          {[item.company.sector, item.company.industry].filter(Boolean).join(" · ") || item.research_type.replace("_", " ")}
        </p>
        <div className="flex items-center gap-3 mt-4">
          <div
            className={`${s.progressTrack} flex-1`}
            role="progressbar"
            aria-label="Research progress"
            aria-valuemin={0}
            aria-valuemax={progress.total}
            aria-valuenow={progress.done}
            aria-valuetext={`${progress.done} of ${progress.total} sections completed`}
          >
            <div className={s.progressFill} style={{ width: `${(progress.done / progress.total) * 100}%` }} />
          </div>
          <span className="qf-metadata shrink-0">{progress.done}/{progress.total} sections</span>
        </div>
      </header>

      <div className={s.workspace}>
        {/* ---- LEFT: progress ---- */}
        <div className={s.railCol}>
          <div className="lg:hidden">
            <button
              type="button"
              className={s.railToggle}
              onClick={() => setRailOpenMobile((v) => !v)}
              aria-expanded={railOpenMobile}
              aria-controls="research-rail"
            >
              <span>
                <span className={s.stageNum}>{meta.n}</span>{" "}
                <span className="font-semibold">{meta.label}</span>
                <span className="qf-secondary"> · {progress.done}/{progress.total} done</span>
              </span>
              <span aria-hidden>{railOpenMobile ? "▲" : "▼"}</span>
            </button>
          </div>
          <div id="research-rail" className={`${railOpenMobile ? "block mt-3" : "hidden"} lg:block`}>
            <StageRail item={item} activeKey={activeSection} onSelect={selectSection} />
          </div>
        </div>

        {/* ---- CENTER: the research document ---- */}
        <article id="research-document" className={s.document} aria-labelledby="stage-title" style={{ scrollMarginTop: 16 }}>
          <p className={s.eyebrow}>{meta.n} · {meta.label}</p>
          <h2 id="stage-title" className={s.stageTitle}>
            {meta.key === "question" ? (readOnly ? "Research question" : "What are you trying to understand?") : meta.label}
          </h2>
          <p className={s.stagePurpose}>
            {readOnly && meta.key === "question" ? "The question that guides this research." : STAGE_PURPOSE[meta.key]}
          </p>
          {meta.derived && (
            <p className="mt-2"><span className="qf-derived-badge">Assembled from {readOnly ? "the author's" : "your"} sections · read-only</span></p>
          )}
          {readOnly ? (
            <p className="qf-secondary mt-2" style={{ fontSize: 13 }}>
              You&apos;re reading another member&apos;s published research. It documents their reasoning — not a
              recommendation to buy or sell.
            </p>
          ) : (
            <a href="#research-assistant" className={`${s.linkBtn} inline-flex items-center mt-2 xl:hidden`} style={{ paddingLeft: 0 }}>
              Ask the Research Assistant ↓
            </a>
          )}

          <div className="mt-6">
            {meta.key !== "question" && item.summary && (
              <section className={s.block}>
                <p className={`${s.blockLabel} mb-1.5`}>Guiding this research</p>
                <p className="qf-secondary" style={{ fontSize: 14 }}>{item.summary}</p>
              </section>
            )}

            {meta.key === "question" && (
              <section className={s.block}>
                <ResearchField
                  key="question"
                  id="field-question"
                  ownerLabel="Your research question"
                  stageLabel="Research Question"
                  value={item.summary ?? ""}
                  onSave={(v) => patchAndReload({ summary: v })}
                  placeholder="e.g. Can this business sustain growth without eroding margins?"
                  emptyText="Examples: What is driving this company's growth? Can it sustain its current margins? What are the biggest risks?"
                  {...fieldProps}
                />
              </section>
            )}

            {meta.field && meta.key !== "question" && meta.key !== "scenarios" && (
              <>
                {meta.question && (
                  <section className={s.block}>
                    <p className={`${s.blockLabel} mb-2`}>Research question</p>
                    <p className={s.guideQuestion}>{meta.question}</p>
                    {meta.guidance && (
                      <ul className={s.guidance} aria-label="What to investigate">
                        {meta.guidance.map((g) => <li key={g}>{g}</li>)}
                      </ul>
                    )}
                  </section>
                )}
                <section className={s.block}>
                  <ResearchField
                    key={meta.key}
                    id={`field-${meta.key}`}
                    ownerLabel="Your findings"
                    stageLabel={meta.label}
                    value={(item[meta.field] as string) ?? ""}
                    onSave={(v) => patchAndReload({ [meta.field as string]: v })}
                    placeholder={meta.placeholder}
                    emptyText="Nothing saved yet. Write your own findings, or ask the Research Assistant and add what's useful."
                    {...fieldProps}
                  />
                </section>
              </>
            )}

            {meta.key === "scenarios" && (
              <>
                {([
                  ["bull_case", "Bull case", "What happens if things go better than expected?"],
                  ["base_case", "Base case", "What happens under your central assumptions?"],
                  ["bear_case", "Bear case", "What happens if things go worse than expected?"],
                ] as const).map(([field, title, prompt]) => (
                  <section key={field} className={s.block}>
                    <p className="qf-section-title mb-1">{title}</p>
                    <p className="qf-secondary mb-3">{prompt}</p>
                    <ResearchField
                      id={`field-${field}`}
                      ownerLabel="Your scenario"
                      stageLabel={title}
                      value={item[field] ?? ""}
                      onSave={(v) => patchAndReload({ [field]: v })}
                      {...fieldProps}
                    />
                  </section>
                ))}
                <p className="qf-secondary">No probabilities or expected returns are assigned — none is marked correct.</p>
              </>
            )}

            {meta.key === "thesis" && <InvestmentThesisBody item={item} />}

            {meta.key === "review" && (
              <>
                <section className={s.block}>
                  <p className={`${s.blockLabel} mb-2`}>Completeness</p>
                  <p className="qf-secondary mb-2">A completeness check only — not a score, rating, or recommendation.</p>
                  <ul>
                    {deriveReviewSummary(item).map((r) => (
                      <li key={r.key} className="flex items-center gap-3 py-1.5" style={{ borderBottom: "1px solid var(--line)" }}>
                        <span className={`${s.marker} ${r.filled ? s.markerDone : ""}`} aria-hidden>{r.filled ? "✓" : ""}</span>
                        <span className={s.stageNum}>{r.n}</span>
                        <span className="flex-1 text-sm">{r.label}</span>
                        <span className="qf-secondary" style={{ fontSize: 12 }}>{r.filled ? "Complete" : "Not completed"}</span>
                        <button type="button" className={s.linkBtn} onClick={() => selectSection(r.key)}>
                          {readOnly ? "View" : r.filled ? "Edit" : "Open"}<span className={s.srOnly}> {r.label}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>

                {readOnly && item.sources.length > 0 && (
                  <section className={s.block}>
                    <p className={`${s.blockLabel} mb-2`}>Sources ({item.sources.length})</p>
                    <ul className="text-sm space-y-1.5">
                      {item.sources.map((src) => (
                        <li key={src.id} style={{ overflowWrap: "anywhere" }}>{src.label} — <span className="qf-secondary">{src.reference}</span></li>
                      ))}
                    </ul>
                  </section>
                )}

                {!readOnly && <PublishChecklist item={item} onPatch={patchAndReload} onReload={load} onSelect={selectSection} />}

                {!readOnly && <section className={s.block}>
                  <p className={`${s.blockLabel} mb-2`}>Publish</p>
                  <p className="qf-secondary mb-3">
                    Publishing locks in a versioned copy of your research. You can then publish it as a thesis to
                    Community, where your research question becomes the thesis summary and others can challenge
                    the reasoning.
                  </p>
                  {item.summary && (
                    <blockquote className="mb-4 pl-3" style={{ borderLeft: "2px solid var(--brass)" }}>
                      <p className={s.prose}>{item.summary}</p>
                    </blockquote>
                  )}
                  {published && <div className="mb-4"><ThesisCardFromResearch research={item} companyName={item.company.name ?? "This company"} /></div>}
                  {published && (
                    <div className="mb-3">
                      <label className="qf-label" htmlFor="change-note">Change note (required to re-publish edits)</label>
                      <input id="change-note" className="qf-input" value={changeNote} onChange={(e) => setChangeNote(e.target.value)} />
                    </div>
                  )}
                  {publishError && <p className={`${s.status} ${s.statusErr} mb-3`} role="alert">{publishError}</p>}
                  <div className={s.actions}>
                    <button className="qf-btn-gold" onClick={handlePublish} disabled={publishing}>
                      {publishing ? "Publishing…" : published ? "Re-publish" : "Publish Research"}
                    </button>
                    {published && !communityPostId && (
                      <button className="qf-btn-primary" onClick={handlePublishToCommunity} disabled={postingToCommunity}>
                        {postingToCommunity ? "Publishing thesis…" : "Publish Thesis to Community"}
                      </button>
                    )}
                    {communityPostId && (
                      <a href={`/community/${communityPostId}`} className="qf-btn-primary" style={{ textDecoration: "none" }}>
                        View Thesis in Community →
                      </a>
                    )}
                  </div>
                </section>}
              </>
            )}

            {nextSection && (
              <div className={s.nextStep}>
                <span className="qf-secondary self-center">
                  {isSectionFilled(item, meta) ? "This stage has content." : "Investigate next when you're ready."}
                </span>
                <button type="button" className={s.linkBtn} onClick={() => selectSection(nextSection.key)}>
                  Next: {nextSection.label} →
                </button>
              </div>
            )}
          </div>
        </article>

        {/* ---- RIGHT: contextual assistant ---- */}
        {!readOnly && (
          <div id="research-assistant" className={s.assistantCol} style={{ scrollMarginTop: 16 }}>
            <ResearchAssistantPanel
              researchId={item.id}
              activeSectionKey={activeSection}
              isDraft={!published}
              onStageChange={selectSection}
              onAdded={load}
            />
          </div>
        )}
      </div>
    </div>
  );
}
