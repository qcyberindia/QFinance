"use client";

/**
 * AI Provider connection settings — BYOK (bring your own key) only.
 *
 * Reuses the existing, already-wired backend contract exactly as-is:
 *   POST   /ai/connect   { provider, api_key } -> StatusResponse (no key echoed back)
 *   GET    /ai/status?provider=<provider>      -> StatusResponse
 *   DELETE /ai/connect?provider=<provider>     -> 204
 * (apps/api/app/modules/ai/router.py + schemas.py). No new storage, no new
 * endpoint, no provider list endpoint exists so PROVIDERS below is hardcoded
 * to mirror the backend's provider registry. The OpenAI-compatible provider
 * is displayed as "Ollama (OpenAI-Compatible)" and accepts an endpoint/model
 * while using the backend provider value `openai_compatible`.
 *
 * SECURITY, matching the task's explicit checklist:
 * - The typed key lives only in this component's local `apiKey` state
 *   during entry. It is cleared immediately after a successful submit
 *   (success or failure both clear the input — never left sitting in a
 *   field pointing at a request that already happened).
 * - Never written to localStorage/sessionStorage — plain useState only.
 * - Never console.logged.
 * - Never included in any error message shown to the user — `ApiError`
 *   messages come from the backend's own JSON error body, which
 *   (per ai/schemas.py) has no field capable of carrying the key back.
 * - The stored/connected state never displays the key itself, only
 *   provider name + connected_at, exactly what StatusResponse returns.
 */
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import { Card } from "@/components/states";
import { ConfirmDialog } from "@/components/confirm-dialog";

interface AiStatus {
  connected: boolean;
  provider: string | null;
  connected_at: string | null;
}

/** Mirrors app/modules/ai/models.py's VALID_PROVIDERS exactly (as of the
 * AI-provider-registry pass: widened from Anthropic-only to also include
 * OpenAI, since a real, already-written adapter for it existed in
 * `integrations/ai_providers/openai_provider.py` — previously orphaned,
 * now wired to this table's CHECK constraint via migration 0008). No other
 * provider is listed because no adapter code for one exists in the repo. */
const PROVIDERS = [
  { value: "anthropic", label: "Anthropic" },
  { value: "openai", label: "OpenAI" },
  { value: "openai_compatible", label: "Ollama (OpenAI-Compatible)" },
] as const;

type Phase = "loading" | "idle" | "submitting" | "disconnecting";

export function AiConnectionSettings() {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successNote, setSuccessNote] = useState<string | null>(null);

  const [provider, setProvider] = useState<string>(PROVIDERS[0].value);
  const [apiKey, setApiKey] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [model, setModel] = useState("");
  const [showReplace, setShowReplace] = useState(false);
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false);

  const loadStatus = useCallback(async () => {
    setLoadError(null);
    try {
      const data = await api.get<AiStatus>(`/ai/status?provider=${provider}`);
      setStatus(data);
      setPhase("idle");
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Could not check your AI connection.");
      setPhase("idle");
    }
  }, [provider]);

  // Reflect connection state after page reload (fresh mount always re-checks).
  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    if (!apiKey.trim()) {
      setActionError("Enter your API key first.");
      return;
    }
    setPhase("submitting");
    setActionError(null);
    setSuccessNote(null);
    try {
      const data = await api.post<AiStatus>("/ai/connect", {
        provider,
        api_key: apiKey,
        ...(provider === "openai_compatible"
          ? { endpoint: endpoint.trim(), model: model.trim() }
          : {}),
      });
      setStatus(data);
      setSuccessNote(showReplace ? "Your key was replaced." : "Connected.");
      setShowReplace(false);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not connect — check your key and try again.");
    } finally {
      // Cleared unconditionally: on success there's nothing left to submit;
      // on failure the person should re-type it deliberately, not have a
      // stale key sitting in the field pointing at a request that already
      // happened.
      setApiKey("");
      setPhase("idle");
    }
  }

  async function handleDisconnect() {
    setConfirmingDisconnect(false);
    setPhase("disconnecting");
    setActionError(null);
    setSuccessNote(null);
    try {
      await api.delete(`/ai/connect?provider=${provider}`);
      setStatus({ connected: false, provider: null, connected_at: null });
      setSuccessNote("Disconnected.");
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not disconnect — try again.");
    } finally {
      setPhase("idle");
    }
  }

  const busy = phase === "submitting" || phase === "disconnecting";

  return (
    <Card>
      <div className="flex items-center justify-between mb-1">
        <label className="qf-label mb-0">AI Provider</label>
        <span className="text-[10px] text-ink-soft">Only visible to you</span>
      </div>
      <p className="text-xs text-ink-soft mb-3">
        Connect your own AI provider API key to use with the Research Assistant. Qfinera does not supply AI
        access itself — your key is encrypted at rest and is never shown again after you enter it, including
        to Qfinera staff.
      </p>

      {phase === "loading" && <p className="text-xs text-ink-soft">Checking your connection…</p>}

      {loadError && (
        <div className="mb-3">
          <p className="text-sm" style={{ color: "var(--down)" }}>{loadError}</p>
          <button type="button" className="qf-btn-ghost text-xs mt-2" onClick={loadStatus}>Retry</button>
        </div>
      )}

      {!loadError && phase !== "loading" && status && (
        <>
          {status.connected && !showReplace ? (
            <div>
              <p className="text-sm">
                <span style={{ color: "var(--brass)" }}>●</span> Connected —{" "}
                <span className="font-semibold">{PROVIDERS.find((p) => p.value === status.provider)?.label ?? status.provider}</span>
              </p>
              {status.connected_at && (
                <p className="text-xs text-ink-soft mt-0.5">
                  Since {new Date(status.connected_at).toLocaleString()}
                </p>
              )}
              <div className="flex gap-3 mt-3">
                <button type="button" className="qf-btn-ghost text-xs" onClick={() => { setShowReplace(true); setActionError(null); setSuccessNote(null); }} disabled={busy}>
                  Replace API Key
                </button>
                <button
                  type="button"
                  className="qf-btn-ghost text-xs"
                  style={{ color: "var(--down)", borderColor: "var(--down)" }}
                  onClick={() => setConfirmingDisconnect(true)}
                  disabled={busy}
                >
                  {phase === "disconnecting" ? "Disconnecting…" : "Disconnect"}
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleConnect} className="space-y-3">
              {status.connected && showReplace && (
                <p className="text-xs text-ink-soft">
                  Replacing your key for <span className="font-semibold">{status.provider}</span>. Your old key
                  will stop working as soon as this succeeds.
                </p>
              )}
              <div>
                <label className="qf-label" htmlFor="ai-provider">Provider</label>
                <select
                  id="ai-provider"
                  className="qf-input"
                  value={provider}
                  onChange={(e) => {
                    setProvider(e.target.value);
                    setActionError(null);
                    setSuccessNote(null);
                  }}
                  disabled={busy || PROVIDERS.length < 2}
                >
                  {PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              {provider === "openai_compatible" && (
                <>
                  <div>
                    <label className="qf-label" htmlFor="ai-endpoint">Endpoint</label>
                    <input
                      id="ai-endpoint"
                      type="url"
                      autoComplete="off"
                      className="qf-input"
                      placeholder="http://127.0.0.1:11434/v1"
                      value={endpoint}
                      onChange={(e) => setEndpoint(e.target.value)}
                      disabled={busy}
                    />
                    <p className="text-[11px] text-ink-soft mt-1">
                      OpenAI-compatible base URL. Do not include /chat/completions.
                    </p>
                  </div>

                  <div>
                    <label className="qf-label" htmlFor="ai-model">Model</label>
                    <input
                      id="ai-model"
                      type="text"
                      autoComplete="off"
                      className="qf-input"
                      placeholder="qwen3-8b"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      disabled={busy}
                    />
                  </div>
                </>
              )}

              <div>
                <label className="qf-label" htmlFor="ai-api-key">API key</label>
                <input
                  id="ai-api-key"
                  type="password"
                  autoComplete="off"
                  className="qf-input"
                  placeholder={provider === "openai_compatible" ? "API key (if required)" : "sk-ant-…"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  disabled={busy}
                />
                <p className="text-[11px] text-ink-soft mt-1">
                  This is your own key from your provider account — Qfinera stores it encrypted and uses it only
                  to call the provider on your behalf when you ask the Research Assistant a question.
                </p>
              </div>
              {actionError && <p className="text-sm" style={{ color: "var(--down)" }}>{actionError}</p>}
              <div className="flex gap-3">
                <button type="submit" className="qf-btn-primary" disabled={busy}>
                  {phase === "submitting" ? "Connecting…" : showReplace ? "Save New Key" : "Connect"}
                </button>
                {showReplace && (
                  <button type="button" className="qf-btn-ghost text-sm" onClick={() => { setShowReplace(false); setApiKey(""); setActionError(null); }} disabled={busy}>
                    Cancel
                  </button>
                )}
              </div>
            </form>
          )}
          {successNote && !actionError && <p className="text-xs mt-2" style={{ color: "var(--brass)" }}>✓ {successNote}</p>}
        </>
      )}

      {confirmingDisconnect && (
        <ConfirmDialog
          message={`Disconnect your ${PROVIDERS.find((p) => p.value === provider)?.label ?? provider} key? The Research Assistant won't be usable until you reconnect.`}
          confirmLabel="Disconnect"
          onCancel={() => setConfirmingDisconnect(false)}
          onConfirm={handleDisconnect}
        />
      )}
    </Card>
  );
}
