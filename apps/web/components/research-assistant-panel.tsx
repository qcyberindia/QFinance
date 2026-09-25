"use client";

/**
 * Research Assistant — right-pane UI architecture ONLY.
 *
 * Explicit scope boundary (per instruction): this component prepares the
 * UI shape for a future assistant (current question, suggested questions,
 * custom question, answer area, save-to-research, research context) but
 * does NOT call any AI provider and does NOT hit any AI "ask" endpoint —
 * no such endpoint exists in this API (confirmed: research/router.py has
 * no /ai/ask route). The only real network call this component makes is
 * GET /ai/status (already-existing, already-tested BYOK endpoint,
 * app/modules/ai/*) — purely to show the member their own honest
 * connection state, never to trigger a completion.
 *
 * "Save selected content" is deliberately NOT wired to any persistence
 * here: alembic/versions/0006_ai_research_assistant.py already defines a
 * `research_notes` table shaped for exactly this (question/answer/
 * is_selected/target_field), but no service.py/router.py exists for it yet,
 * and there is nothing genuine to save until a real answer can be
 * generated — building that CRUD now would just be scaffolding around a
 * feature that produces no real data yet. The button stays disabled with
 * an honest label instead of faking a save.
 *
 * DUPLICATE-MODULE NOTE (found, not fixed here — out of this pass's
 * scope): app/modules/research_ai/models.py defines a SECOND, different,
 * entirely unwired "ai_provider_keys"/"research_context_entries" design
 * that overlaps with the already-wired app/modules/ai/ (BYOK) system this
 * component actually calls. app/modules/ai_research/ is empty. Both are
 * dead code and should be removed by a human decision, not silently
 * merged or deleted here.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import { Card } from "@/components/states";

interface AiStatus {
  connected: boolean;
  provider: string | null;
  connected_at: string | null;
}

const SUGGESTED_QUESTIONS = [
  "What are this company's biggest sources of revenue?",
  "What could go wrong with this thesis in the next 12 months?",
  "How does this company's margin trend compare to its own history?",
];

export function ResearchAssistantPanel({ currentQuestion }: { currentQuestion: string }) {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [customQuestion, setCustomQuestion] = useState("");
  const [selectedQuestion, setSelectedQuestion] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<AiStatus>("/ai/status")
      .then(setStatus)
      .catch(() => setStatusError(true));
  }, []);

  return (
    <div className="qf-card p-4 space-y-4" style={{ width: 300, maxWidth: "100%", flexShrink: 0 }}>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">Research Assistant</p>
        <p className="text-[11px] text-ink-soft mt-1">
          Not available yet in this MVP. This panel shows what&apos;s coming — no question is sent anywhere.
        </p>
      </div>

      <div className="text-xs">
        {statusError && <span className="text-ink-soft">Connection status unavailable.</span>}
        {!statusError && status === null && <span className="text-ink-soft">Checking your AI connection…</span>}
        {!statusError && status && (
          <span style={{ color: status.connected ? "var(--brass)" : "var(--ink-soft)" }}>
            {status.connected
              ? `Your ${status.provider} key is connected — the assistant itself isn't live yet.`
              : "No AI provider connected."}
          </span>
        )}
      </div>

      <div>
        <p className="qf-label">Current research question</p>
        <p className="text-sm text-ink-soft italic">{currentQuestion || "Not set yet."}</p>
      </div>

      <div>
        <p className="qf-label">Suggested questions</p>
        <ul className="space-y-1.5">
          {SUGGESTED_QUESTIONS.map((q) => (
            <li key={q}>
              <button
                type="button"
                className="text-xs text-left w-full px-2 py-1.5 rounded"
                style={{
                  background: selectedQuestion === q ? "var(--cream-1)" : "transparent",
                  color: "var(--ink-soft)",
                }}
                onClick={() => setSelectedQuestion(q)}
                disabled
                title="Coming later — the assistant isn't live yet."
              >
                {q}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className="qf-label">Ask your own question</p>
        <textarea
          className="qf-input min-h-[70px] text-xs"
          placeholder="Coming later — nothing you type here is sent anywhere yet."
          value={customQuestion}
          onChange={(e) => setCustomQuestion(e.target.value)}
          disabled
        />
      </div>

      <Card>
        <p className="qf-label">Answer</p>
        <p className="text-xs text-ink-soft mt-1">
          The research assistant isn&apos;t connected yet. When it is, any answer shown here will be clearly
          labeled as system-generated context — never inserted into your research document automatically.
        </p>
      </Card>

      <div className="flex flex-col gap-2">
        <button type="button" className="qf-btn-ghost text-xs w-full" disabled title="Coming later.">
          Add to Research
        </button>
        <button type="button" className="qf-btn-ghost text-xs w-full" disabled title="Coming later — the assistant isn't live yet.">
          Continue Research →
        </button>
      </div>
    </div>
  );
}
