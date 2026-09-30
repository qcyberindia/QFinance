"use client";

/**
 * STAGE-KEY BUG FIXED this pass: this file previously carried a
 * `FIELD_TO_SECTION_KEY` translation, on the assumption that `POST
 * /research/{id}/ai/ask`'s `current_stage` was a raw DB column name (e.g.
 * "business_model"). That was true at the time it was written, but
 * research/ai_context.py was fixed in an earlier pass to return a clean
 * SECTION KEY (e.g. "business") via research/sections.py's
 * `current_stage_key()` — the same keys `ADD_TO_RESEARCH_STAGES` and this
 * file's own `STAGE_QUESTIONS` already use. The translation map was solving
 * a problem that no longer existed, and its lookup returned `undefined` for
 * every real value (`FIELD_TO_SECTION_KEY["business"]` is not one of its
 * keys), so "Add to Research" was unconditionally disabled for every
 * answer — confirmed by reading research/ai_context.py fresh, not assumed.
 * Removed: `answer.current_stage` is used directly as the section key now.
 *
 * CSRF/auth: unchanged — both calls go through the same shared `api` client
 * every other mutating request in this app already uses (session cookie +
 * X-CSRF-Token attached automatically).
 */
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import { Card } from "@/components/states";
import { SECTIONS } from "@/lib/research-progress";

interface AiConnection {
  connected: boolean;
  provider: string | null;
  connected_at: string | null;
  endpoint: string | null;
  model: string | null;
}

interface AiAnswer {
  answer: string;
  current_stage: string; // a SECTION KEY, e.g. "business" — matches lib/research-progress.ts's SECTIONS[].key
  provider: string;
  model: string | null;
}

/** Stage-specific suggested questions, keyed by the SAME section keys
 * `answer.current_stage` and `ADD_TO_RESEARCH_STAGES` both use (see module
 * docstring). This map's key set IS the addable-stage set on the frontend
 * side — there is no separate `ADD_TO_RESEARCH_STAGES` mirror needed here
 * beyond it, since checking `stage in STAGE_QUESTIONS` answers the same
 * question research/sections.py's dict answers server-side. */
const STAGE_QUESTIONS: Record<string, string[]> = {
  business: [
    "How does this company actually make money?",
    "What are its main business segments, and which is growing fastest?",
    "Who are its customers, and how concentrated is that base?",
  ],
  industry: [
    "Who are the company's main competitors?",
    "What gives this company a durable edge, if anything?",
    "What could weaken its competitive position?",
  ],
  financials: [
    "What do the last few years of revenue and margin trends show?",
    "How healthy is the balance sheet and cash flow?",
    "Where would I look to check these claims myself?",
  ],
  growth: [
    "What's actually driving growth here?",
    "How big is the realistic addressable opportunity?",
    "What could stall growth over the next few years?",
  ],
  management: [
    "What is known about leadership's track record?",
    "How has capital been allocated historically?",
    "Are there governance concerns worth flagging?",
  ],
  forecast: [
    "What are the key assumptions behind a reasonable outlook?",
    "Which of those assumptions is most fragile?",
    "What would have to be true for the outlook to disappoint?",
  ],
  valuation: [
    "What valuation approach fits this kind of business?",
    "What assumptions would meaningfully change the valuation?",
    "How does this compare to how similar businesses are typically valued?",
  ],
  risks: [
    "What are the two or three risks that matter most here?",
    "How would I know if one of those risks were materializing?",
    "What's the impact if the worst-case risk actually happens?",
  ],
  invalidation: [
    "What would prove this thesis wrong?",
    "What evidence, if it appeared, should make me reconsider?",
    "Is there a near-term signal worth watching for this?",
  ],
};

const DEFAULT_QUESTIONS = [
  "What are this company's biggest sources of revenue?",
  "What could go wrong with this thesis in the next 12 months?",
  "How does this company's margin trend compare to its own history?",
];

export function ResearchAssistantPanel({
  researchId,
  currentQuestion,
  onStageChange,
}: {
  researchId: string;
  currentQuestion: string;
  /** Optional: lets the panel move the document to the section it just
   * continued to, so the two stay in sync. The panel works fine without it
   * (Continue Research still updates its own suggested questions either
   * way) — kept optional so this isn't a required prop change everywhere
   * else the panel might be used. */
  onStageChange?: (sectionKey: string) => void;
}) {
  const [active, setActive] = useState<AiConnection | null | undefined>(undefined); // undefined = loading, null = none connected
  const [statusError, setStatusError] = useState(false);
  const [customQuestion, setCustomQuestion] = useState("");
  const [selectedQuestion, setSelectedQuestion] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AiAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [addStatus, setAddStatus] = useState<"idle" | "adding" | "added" | "error">("idle");
  const [addError, setAddError] = useState<string | null>(null);

  // Which stage's suggested-question list is currently shown. Starts on
  // Section 02 (Business) — Section 01 (the question itself) isn't an AI
  // target (see STAGE_QUESTIONS' key set).
  const [stageKey, setStageKey] = useState<string>("business");
  const [stagesComplete, setStagesComplete] = useState(false);

  useEffect(() => {
    api
      .get<AiConnection[]>("/ai/connections")
      .then((rows) => setActive(rows[0] ?? null))
      .catch(() => setStatusError(true));
  }, []);

  const connected = !!active?.connected;
  const stageMeta = SECTIONS.find((s) => s.key === stageKey);
  const suggestedQuestions = STAGE_QUESTIONS[stageKey] ?? DEFAULT_QUESTIONS;
  // Addable iff the AI's reported stage is one of this file's known,
  // field-backed stages (STAGE_QUESTIONS' key set) — "review" and any other
  // non-addable key (Section 01/09/11/13 equivalents) fall through to
  // undefined here, matching research/sections.py's ADD_TO_RESEARCH_STAGES
  // on the backend, which will also reject them with a clear 400 if this
  // check were ever bypassed.
  const addableSectionKey = answer && answer.current_stage in STAGE_QUESTIONS ? answer.current_stage : undefined;

  async function ask(question: string) {
    const normalized = question.trim();
    if (!normalized || asking) return;

    setError(null);
    setAnswer(null);
    setAddStatus("idle");
    setAddError(null);
    setAsking(true);

    try {
      const result = await api.post<AiAnswer>(
        `/research/${researchId}/ai/ask`,
        { question: normalized },
      );
      setAnswer(result);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "The Research Assistant could not answer right now.",
      );
    } finally {
      setAsking(false);
    }
  }

  function handleCustomAsk() {
    ask(customQuestion);
  }

  async function handleAddToResearch() {
    if (!answer || !addableSectionKey || addStatus === "adding") return;
    setAddStatus("adding");
    setAddError(null);
    try {
      const result = await api.post<{ added: boolean; already_added: boolean }>(
        `/research/${researchId}/ai/add-to-research`,
        { stage: addableSectionKey, question: selectedQuestion ?? customQuestion, answer: answer.answer },
      );
      setAddStatus("added"); // both a fresh add and an already-added answer read as "✓ Added to Research"
      void result;
    } catch (err) {
      setAddStatus("error");
      setAddError(err instanceof ApiError ? err.message : "Could not add this to your research.");
    }
  }

  function handleContinueResearch() {
    // Move to the next section in the SAME canonical order the document
    // itself uses (lib/research-progress.ts's SECTIONS) — reusing it rather
    // than a second stage list. Prefers the stage the just-answered question
    // was actually about; falls back to the panel's own current stage if the
    // AI's last stage had no addable section (e.g. Bull/Base/Bear,
    // Investment Thesis).
    //
    // Sections 09 (Bull/Base/Bear) and 11 (Investment Thesis) are
    // deliberately skipped when advancing: they have no single addable
    // target (09 maps to three separate scenario fields with no safe way to
    // infer which one an AI answer belongs to; 11 is a derived, read-only
    // summary with no field of its own — see research/sections.py's
    // docstring). This is the documented, intentional scope limit from
    // Phase 4/5, not an oversight.
    const fromKey = addableSectionKey ?? stageKey;
    const idx = SECTIONS.findIndex((s) => s.key === fromKey);
    const next = SECTIONS.slice(idx + 1).find((s) => s.key in STAGE_QUESTIONS);
    setAnswer(null); // Continue Research never auto-saves the current answer — the user already chose to, or didn't
    setAddStatus("idle");
    setError(null);
    setSelectedQuestion(null);
    if (!next) {
      setStagesComplete(true);
      return;
    }
    setStagesComplete(false);
    setStageKey(next.key);
    onStageChange?.(next.key);
  }

  return (
    <div
      className="qf-card p-4 space-y-4"
      style={{ width: 300, maxWidth: "100%", flexShrink: 0 }}
    >
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
          Research Assistant
        </p>
        <p className="text-[11px] text-ink-soft mt-1">
          Ask questions about your current research. Answers are generated by
          your connected AI provider and are not added to your research automatically.
        </p>
      </div>

      <div className="text-xs">
        {statusError && <span className="text-ink-soft">Connection status unavailable.</span>}
        {!statusError && active === undefined && <span className="text-ink-soft">Checking your AI connection…</span>}
        {!statusError && active === null && (
          <div className="space-y-1.5">
            <span className="text-ink-soft">No AI provider connected.</span>
            <a href="/profile" className="qf-btn-ghost text-xs block text-center" style={{ textDecoration: "none" }}>
              Connect AI Provider
            </a>
          </div>
        )}
        {!statusError && active && (
          <div>
            <span style={{ color: "var(--brass)" }}>
              Connected — {{ anthropic: "Anthropic", openai: "OpenAI", openai_compatible: "OpenAI-Compatible" }[active.provider ?? ""] ?? active.provider}
            </span>
            {active.model && <p className="text-ink-soft mt-0.5">Model — {active.model}</p>}
          </div>
        )}
      </div>

      <div>
        <p className="qf-label">Current research question</p>
        <p className="text-sm text-ink-soft italic">{currentQuestion || "Not set yet."}</p>
      </div>

      <div>
        <div className="flex items-center justify-between">
          <p className="qf-label mb-0">
            Suggested questions{stageMeta ? ` — ${stageMeta.n} · ${stageMeta.label}` : ""}
          </p>
        </div>
        <div className="space-y-1.5 mt-1.5">
          {suggestedQuestions.map((question) => (
            <button
              key={question}
              type="button"
              className="text-xs text-left w-full px-2 py-1.5 rounded"
              style={{
                background: selectedQuestion === question ? "var(--cream-1)" : "transparent",
                color: "var(--ink-soft)",
                border: "1px solid var(--cream-2)",
              }}
              onClick={() => { setSelectedQuestion(question); ask(question); }}
              disabled={!connected || asking}
            >
              {question}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="qf-label">Ask your own question</p>
        <textarea
          className="qf-input min-h-[90px] text-xs"
          placeholder="Ask something about this research…"
          value={customQuestion}
          onChange={(e) => setCustomQuestion(e.target.value)}
          disabled={!connected || asking}
        />
        <button
          type="button"
          className="qf-btn-primary text-xs w-full mt-2"
          onClick={handleCustomAsk}
          disabled={!connected || asking || !customQuestion.trim()}
        >
          {asking ? "Researching…" : "Ask Research Assistant"}
        </button>
      </div>

      {error && <p className="text-xs" style={{ color: "#9C4B3F" }} role="alert">{error}</p>}

      <Card>
        <p className="qf-label">Answer</p>
        {!answer && !asking && <p className="text-xs text-ink-soft mt-1">Ask a question to start researching.</p>}
        {asking && <p className="text-xs text-ink-soft mt-1">Your AI provider is researching this question…</p>}
        {answer && (
          <div className="mt-2 space-y-2">
            <p className="text-sm whitespace-pre-wrap leading-relaxed">{answer.answer}</p>
            <p className="text-[10px] text-ink-soft">
              Stage: {answer.current_stage}
              {answer.model ? ` · Model: ${answer.model}` : ""}
            </p>
          </div>
        )}
      </Card>

      {addError && <p className="text-xs" style={{ color: "#9C4B3F" }} role="alert">{addError}</p>}

      <div className="flex flex-col gap-2">
        {addStatus === "added" ? (
          <p className="text-xs text-center" style={{ color: "var(--brass)" }}>✓ Added to Research</p>
        ) : (
          <button
            type="button"
            className="qf-btn-ghost text-xs w-full"
            onClick={handleAddToResearch}
            disabled={!answer || !addableSectionKey || addStatus === "adding"}
            title={
              !answer ? "Ask a question first."
              : !addableSectionKey ? "This kind of answer isn't tied to a single section yet — copy what's useful into a section yourself."
              : undefined
            }
          >
            {addStatus === "adding" ? "Adding…" : "Add to Research"}
          </button>
        )}

        {stagesComplete ? (
          <p className="text-xs text-center text-ink-soft py-1.5">Research stages complete</p>
        ) : (
          <button
            type="button"
            className="qf-btn-ghost text-xs w-full"
            onClick={handleContinueResearch}
            disabled={!connected}
          >
            Continue Research →
          </button>
        )}
      </div>
    </div>
  );
}
