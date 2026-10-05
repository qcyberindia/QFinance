"use client";

/**
 * Research Assistant — the contextual AI column of the Research workspace.
 *
 * STAGE KEYS: `POST /research/{id}/ai/ask` returns `current_stage` as a clean
 * SECTION KEY (e.g. "business") via research/sections.py's
 * `current_stage_key()` — the same keys `ADD_TO_RESEARCH_STAGES` and this
 * file's `STAGE_QUESTIONS` use, so `answer.current_stage` is used directly.
 *
 * CONTEXT: the panel follows the document's active section
 * (`activeSectionKey`) for its header and suggested questions. Add to
 * Research still targets the stage the backend reported for the answer
 * (unchanged behavior) — and the button names that destination explicitly,
 * so the user knows where the text will land before clicking.
 *
 * AI answers are never saved automatically: only the explicit Add to
 * Research action persists one.
 *
 * CSRF/auth: unchanged — both calls go through the shared `api` client
 * (session cookie + X-CSRF-Token attached automatically).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import { SECTIONS, STAGE_PURPOSE } from "@/lib/research-progress";
import s from "@/components/research/research.module.css";

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
 * `answer.current_stage` and `ADD_TO_RESEARCH_STAGES` both use. This map's
 * key set IS the addable-stage set on the frontend side. */
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

const PROVIDER_LABEL: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  openai_compatible: "OpenAI-Compatible",
};

const labelOf = (key: string) => SECTIONS.find((x) => x.key === key)?.label ?? key;

export function ResearchAssistantPanel({
  researchId,
  activeSectionKey,
  isDraft = true,
  onStageChange,
  onAdded,
}: {
  researchId: string;
  /** The document's active section — drives the header and suggestions. */
  activeSectionKey: string;
  /** Add to Research only writes to drafts (backend rule); published research
   * shows an explanation instead of a button that would fail. */
  isDraft?: boolean;
  /** Moves the document to the section Continue advanced to. */
  onStageChange?: (sectionKey: string) => void;
  /** Called after a successful add so the document can reload its content. */
  onAdded?: () => void;
}) {
  const [active, setActive] = useState<AiConnection | null | undefined>(undefined); // undefined = loading, null = none connected
  const [statusError, setStatusError] = useState(false);
  const [customQuestion, setCustomQuestion] = useState("");
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AiAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [askFailed, setAskFailed] = useState(false);

  const [addStatus, setAddStatus] = useState<"idle" | "adding" | "added" | "error">("idle");
  const [stagesComplete, setStagesComplete] = useState(false);

  useEffect(() => {
    api
      .get<AiConnection[]>("/ai/connections")
      .then((rows) => setActive(rows[0] ?? null))
      .catch(() => setStatusError(true));
  }, []);

  // A new section is a new context: clear the previous section's exchange.
  useEffect(() => {
    setAnswer(null);
    setAskFailed(false);
    setAddStatus("idle");
    setLastQuestion(null);
    setStagesComplete(false);
  }, [activeSectionKey]);

  const connected = !!active?.connected;
  const suggestedQuestions = STAGE_QUESTIONS[activeSectionKey] ?? DEFAULT_QUESTIONS;
  // Addable iff the AI's reported stage is one of the field-backed stages —
  // matches research/sections.py's ADD_TO_RESEARCH_STAGES on the backend.
  const addableSectionKey = answer && answer.current_stage in STAGE_QUESTIONS ? answer.current_stage : undefined;

  // Continue advances in SECTIONS order, preferring the stage the answer was
  // about, skipping stages with no single addable target (09 Bull/Base/Bear,
  // 11 Investment Thesis, 13 Review) — the documented Phase 4/5 scope limit.
  const fromKey = addableSectionKey ?? activeSectionKey;
  const fromIdx = SECTIONS.findIndex((x) => x.key === fromKey);
  const nextStage = SECTIONS.slice(fromIdx + 1).find((x) => x.key in STAGE_QUESTIONS) ?? null;

  async function ask(question: string) {
    const normalized = question.trim();
    if (!normalized || asking) return;
    setLastQuestion(normalized);
    setAskFailed(false);
    setAnswer(null);
    setAddStatus("idle");
    setAsking(true);
    try {
      const result = await api.post<AiAnswer>(`/research/${researchId}/ai/ask`, { question: normalized });
      setAnswer(result);
    } catch {
      setAskFailed(true);
    } finally {
      setAsking(false);
    }
  }

  async function handleAddToResearch() {
    if (!answer || !addableSectionKey || addStatus === "adding") return;
    setAddStatus("adding");
    try {
      await api.post<{ added: boolean; already_added: boolean }>(
        `/research/${researchId}/ai/add-to-research`,
        { stage: addableSectionKey, question: lastQuestion ?? customQuestion, answer: answer.answer },
      );
      setAddStatus("added"); // a fresh add and an already-present answer both read as added
      onAdded?.();
    } catch {
      setAddStatus("error");
    }
  }

  function handleContinueResearch() {
    // Never auto-saves the current answer — the user already chose to, or didn't.
    setAnswer(null);
    setAddStatus("idle");
    setAskFailed(false);
    setLastQuestion(null);
    if (!nextStage) {
      setStagesComplete(true);
      return;
    }
    onStageChange?.(nextStage.key);
  }

  const continueLabel = nextStage ? `Continue to ${nextStage.label} →` : "Finish research stages";

  return (
    <aside className={`${s.assistant} ${s.touch}`} aria-label="Research Assistant">
      <div className={s.assistantHead}>
        <p className="qf-caption">Research Assistant</p>
        <p className="qf-section-title mt-2">{labelOf(activeSectionKey)}</p>
        <p className="qf-secondary mt-1">{STAGE_PURPOSE[activeSectionKey]}</p>
      </div>

      <div className={s.assistantBody}>
        {active === null && !statusError && (
          <div>
            <p className="text-sm font-semibold">Connect your AI provider to continue.</p>
            <p className="qf-secondary mt-1">
              The assistant uses your own AI key. Nothing is added to your research automatically.
            </p>
            <a href="/profile" className="qf-btn-primary w-full mt-3" style={{ textDecoration: "none" }}>
              Connect AI
            </a>
          </div>
        )}

        <section aria-labelledby="ra-suggested">
          <p id="ra-suggested" className={s.blockLabel}>Suggested questions</p>
          <ul className="grid gap-2 mt-2">
            {suggestedQuestions.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  className={`${s.suggestion} ${lastQuestion === q && (asking || answer) ? s.suggestionActive : ""}`}
                  onClick={() => ask(q)}
                  disabled={!connected || asking}
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <label htmlFor="ra-custom" className={s.blockLabel}>Ask your own question</label>
          <textarea
            id="ra-custom"
            className="qf-input mt-2"
            style={{ minHeight: 84 }}
            placeholder={activeSectionKey in STAGE_QUESTIONS ? `Ask about ${labelOf(activeSectionKey).toLowerCase()}…` : "Ask something about this research…"}
            value={customQuestion}
            onChange={(e) => setCustomQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); ask(customQuestion); }
            }}
            disabled={!connected || asking}
          />
          <button
            type="button"
            className="qf-btn-primary w-full mt-2"
            onClick={() => ask(customQuestion)}
            disabled={!connected || asking || !customQuestion.trim()}
          >
            {asking ? "Thinking…" : "Ask Research Assistant"}
          </button>
        </section>

        <div aria-live="polite">
          {asking && (
            <div className={s.aiResponse} aria-busy="true">
              <span className={s.aiTag}>AI Response</span>
              <p className="qf-secondary mt-2">Thinking through your research…</p>
              <div className={`${s.thinking} mt-3`} aria-hidden>
                <div className={s.thinkingLine} style={{ width: "92%" }} />
                <div className={s.thinkingLine} style={{ width: "78%" }} />
                <div className={s.thinkingLine} style={{ width: "64%" }} />
              </div>
            </div>
          )}

          {askFailed && !asking && (
            <div className={s.aiResponse} role="alert" style={{ borderLeftColor: "var(--down)" }}>
              <p className="text-sm font-semibold">The research assistant could not respond.</p>
              <p className="qf-secondary mt-1">Check your AI connection, then try again.</p>
              <button type="button" className="qf-btn-ghost mt-3" onClick={() => lastQuestion && ask(lastQuestion)}>
                Try Again
              </button>
            </div>
          )}

          {answer && !asking && (
            <article className={s.aiResponse} aria-label="AI response">
              <span className={s.aiTag}>
                <span aria-hidden>◆</span> AI Response · not yet in your research
              </span>
              {lastQuestion && <p className={s.aiQuestion}>“{lastQuestion}”</p>}
              <div className={s.aiText}>{answer.answer}</div>
              <div className={s.aiDivider} />

              {addStatus === "added" ? (
                <p className={`${s.status} ${s.statusOk}`} role="status">
                  ✓ Added to {labelOf(addableSectionKey ?? "")} — now part of your research
                </p>
              ) : !isDraft ? (
                <p className="qf-secondary">
                  This research is published. Edit a section directly to include anything useful.
                </p>
              ) : addableSectionKey ? (
                <>
                  <button
                    type="button"
                    className="qf-btn-primary w-full"
                    onClick={handleAddToResearch}
                    disabled={addStatus === "adding"}
                  >
                    {addStatus === "adding" ? "Adding…" : `Add to ${labelOf(addableSectionKey)}`}
                  </button>
                  <p className="qf-secondary mt-1.5" style={{ fontSize: 12 }}>
                    Appends this answer to your {labelOf(addableSectionKey)} findings. You can edit it afterwards.
                  </p>
                </>
              ) : (
                <p className="qf-secondary">
                  This answer isn&apos;t tied to a single section — copy what&apos;s useful into a section yourself.
                </p>
              )}
              {addStatus === "error" && (
                <p className={`${s.status} ${s.statusErr} mt-2`} role="alert">
                  Couldn&apos;t add this to your research. Try again.
                </p>
              )}

              {!stagesComplete && (
                <button type="button" className="qf-btn-ghost w-full mt-3" onClick={handleContinueResearch}>
                  {continueLabel}
                </button>
              )}
            </article>
          )}

          {!answer && !asking && !askFailed && connected && (
            <p className="qf-secondary">
              Answers appear here, marked as AI. Nothing is saved until you choose Add to Research.
            </p>
          )}

          {stagesComplete && (
            <p className="qf-secondary mt-2" role="status">
              You&apos;ve reached the last assisted stage. Review your research when you&apos;re ready.
            </p>
          )}
        </div>

        {!answer && !asking && !stagesComplete && connected && nextStage && (
          <button type="button" className={s.linkBtn} style={{ justifySelf: "start" }} onClick={handleContinueResearch}>
            {continueLabel}
          </button>
        )}
      </div>

      <div className={s.assistantFoot}>
        {statusError ? (
          <><span className={`${s.connDot} ${s.connDotOff}`} aria-hidden /> Connection status unavailable</>
        ) : active === undefined ? (
          <><span className={`${s.connDot} ${s.connDotOff}`} aria-hidden /> Checking AI connection…</>
        ) : active ? (
          <>
            <span className={s.connDot} aria-hidden />
            <span>
              Connected · {PROVIDER_LABEL[active.provider ?? ""] ?? active.provider}
              {active.model && <span className="qf-metadata"> · {active.model}</span>}
            </span>
          </>
        ) : (
          <><span className={`${s.connDot} ${s.connDotOff}`} aria-hidden /> Not connected</>
        )}
      </div>
    </aside>
  );
}
