"use client";

import { useEffect, useRef } from "react";
import { api, ApiError } from "@/lib/api-client";

/**
 * Zerodha (Kite Connect) redirect target — register
 * `<FRONTEND_BASE_URL>/portfolio/zerodha/callback` in the Kite developer
 * console. Kite returns `request_token`, `status` and our OAuth `state`
 * (sent via redirect_params). This page:
 *   1. removes them from the address bar and history immediately,
 *   2. POSTs them to the API in a JSON body (never a URL the API logs),
 *   3. lands on a clean /portfolio?zerodha=<outcome> — the token is never
 *      put in a URL, state or storage anywhere else.
 */
export default function ZerodhaCallbackPage() {
  const started = useRef(false); // effects run twice in dev; the state is single-use

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const params = new URLSearchParams(window.location.search);
    const requestToken = params.get("request_token") ?? "";
    const state = params.get("state") ?? "";
    const status = params.get("status");
    window.history.replaceState(null, "", "/portfolio/zerodha/callback");

    const finish = (outcome: string) => window.location.replace(`/portfolio?zerodha=${outcome}`);
    if (status !== "success" || !requestToken) {
      finish("cancelled");
      return;
    }
    api.post("/portfolio/zerodha/callback", { request_token: requestToken, state })
      .then(() => finish("connected"))
      .catch((err) => finish(err instanceof ApiError && err.code === "BROKER_STATE_INVALID" ? "expired" : "failed"));
  }, []);

  return <p className="qf-secondary py-8" role="status">Finishing your Zerodha connection…</p>;
}
