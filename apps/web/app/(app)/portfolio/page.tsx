"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { ConnectResponse, PortfolioResponse } from "@/lib/types";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/states";

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notConnected, setNotConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setNotConnected(false);
    try {
      const data = await api.get<PortfolioResponse>("/portfolio");
      setPortfolio(data);
    } catch (err) {
      if (err instanceof ApiError && (err.code === "BROKER_NOT_CONNECTED" || err.status === 404)) {
        setNotConnected(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not load your portfolio.");
      }
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const { login_url } = await api.get<ConnectResponse>("/portfolio/zerodha/connect");
      window.location.href = login_url; // Kite Connect's own hosted login — never a QFinance-rendered form
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the Zerodha connection.");
      setConnecting(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-2xl">Portfolio</h1>
        <p className="text-sm text-ink-soft">
          Read-only view of your Zerodha holdings. Qfinera cannot place trades or modify your account.
        </p>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}

      {!error && notConnected && (
        <Card className="text-center">
          <p className="text-sm text-ink-soft mb-4">Connect your Zerodha account to see your holdings here.</p>
          <button className="qf-btn-gold" onClick={handleConnect} disabled={connecting}>
            {connecting ? "Redirecting to Zerodha…" : "Connect Zerodha"}
          </button>
        </Card>
      )}

      {!error && !notConnected && portfolio === null && <LoadingState label="Loading portfolio…" />}

      {!error && portfolio && (
        <div className="space-y-4">
          <div className="text-xs text-ink-soft italic">{portfolio.read_only_notice}</div>

          <div>
            <h2 className="font-display text-lg mb-2">Holdings</h2>
            {portfolio.holdings.length === 0 ? (
              <EmptyState title="No holdings" body="Nothing to show yet from your Zerodha account." />
            ) : (
              <Card className="!p-0 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-ink-soft border-b" style={{ borderColor: "var(--line)" }}>
                      <th className="px-4 py-2">Symbol</th>
                      <th className="px-4 py-2">Qty</th>
                      <th className="px-4 py-2">Avg Price</th>
                      <th className="px-4 py-2">Last Price</th>
                      <th className="px-4 py-2">P&amp;L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.holdings.map((h) => (
                      <tr key={h.trading_symbol} className="border-b font-mono" style={{ borderColor: "var(--line)" }}>
                        <td className="px-4 py-2">{h.trading_symbol}</td>
                        <td className="px-4 py-2">{h.quantity}</td>
                        <td className="px-4 py-2">{h.average_price}</td>
                        <td className="px-4 py-2">{h.last_price ?? "—"}</td>
                        <td className="px-4 py-2">{h.pnl ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </div>

          {portfolio.positions.length > 0 && (
            <div>
              <h2 className="font-display text-lg mb-2">Positions</h2>
              <Card className="!p-0 overflow-hidden">
                <table className="w-full text-sm">
                  <tbody>
                    {portfolio.positions.map((p) => (
                      <tr key={p.trading_symbol} className="border-b font-mono" style={{ borderColor: "var(--line)" }}>
                        <td className="px-4 py-2">{p.trading_symbol}</td>
                        <td className="px-4 py-2">{p.quantity}</td>
                        <td className="px-4 py-2">{p.pnl ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </div>
          )}

          <p className="text-xs text-ink-soft">
            Last synced {new Date(portfolio.last_synced_at).toLocaleString()}
          </p>
        </div>
      )}
    </div>
  );
}
