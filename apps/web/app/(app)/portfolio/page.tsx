"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { ConnectionStatusResponse, ConnectResponse, Holding, PortfolioResponse } from "@/lib/types";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { ErrorState } from "@/components/states";
import s from "@/components/portfolio/portfolio.module.css";

/**
 * Portfolio — a READ-ONLY view of the member's own Zerodha holdings.
 * Qfinera never places orders or changes the broker account; there are no
 * trading controls here by design. Every figure is the broker's own value
 * (or arithmetic on it, computed server-side in portfolio/service.py);
 * anything that can't be computed from the data shows "Not available".
 *
 * Zerodha OAuth return is handled by /portfolio/zerodha/callback, which
 * POSTs the one-time token + OAuth state and lands here with ?zerodha=<outcome>.
 */

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const qtyFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 4 });
const money = (v: number | null) => (v == null ? null : inr.format(v));
const pct = (v: number | null) => (v == null ? null : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
const signedMoney = (v: number | null) => (v == null ? null : `${v > 0 ? "+" : v < 0 ? "−" : ""}${inr.format(Math.abs(v))}`);
const tone = (v: number | null) => (v == null || v === 0 ? "" : v > 0 ? s.up : s.down);

function NA() {
  return <span className={s.na}>Not available</span>;
}

type SortKey = "current_value" | "pnl" | "pnl_percent" | "allocation_percent" | "trading_symbol";
const SORTS: { key: SortKey; label: string }[] = [
  { key: "current_value", label: "Value" },
  { key: "pnl", label: "P&L" },
  { key: "pnl_percent", label: "P&L %" },
  { key: "allocation_percent", label: "Allocation" },
  { key: "trading_symbol", label: "Symbol" },
];

function sortHoldings(rows: Holding[], key: SortKey, dir: 1 | -1): Holding[] {
  return [...rows].sort((a, b) => {
    if (key === "trading_symbol") return a.trading_symbol.localeCompare(b.trading_symbol) * dir;
    const av = a[key], bv = b[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1; // unavailable values always sink to the bottom
    if (bv == null) return -1;
    return (av - bv) * dir;
  });
}

const WIDGETS = [
  { id: "allocation", label: "Allocation" },
  { id: "concentration", label: "Concentration" },
  { id: "performance", label: "Performance" },
  { id: "sector", label: "Sector exposure" },
  { id: "positions", label: "Open positions" },
] as const;
type WidgetId = (typeof WIDGETS)[number]["id"];
const WIDGET_PREF_KEY = "qf.portfolio.dashboard.hidden";

export default function PortfolioPage() {
  const [connection, setConnection] = useState<ConnectionStatusResponse | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [loadingPortfolio, setLoadingPortfolio] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [tab, setTab] = useState<"holdings" | "dashboard">("holdings");
  const [sortKey, setSortKey] = useState<SortKey>("current_value");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [hidden, setHidden] = useState<Set<WidgetId>>(new Set());
  const handledOutcome = useRef(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(WIDGET_PREF_KEY);
      if (raw) setHidden(new Set(JSON.parse(raw) as WidgetId[]));
    } catch { /* per-device preference only; default = all widgets shown */ }
  }, []);

  function toggleWidget(id: WidgetId) {
    setHidden((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      try { localStorage.setItem(WIDGET_PREF_KEY, JSON.stringify([...next])); } catch { /* ignore */ }
      return next;
    });
  }

  const loadPortfolio = useCallback(async () => {
    setLoadingPortfolio(true);
    setFetchError(null);
    try {
      setPortfolio(await api.get<PortfolioResponse>("/portfolio"));
    } catch (err) {
      if (err instanceof ApiError && (err.code === "BROKER_SESSION_EXPIRED" || err.code === "BROKER_NOT_CONNECTED")) {
        setConnection(await api.get<ConnectionStatusResponse>("/portfolio/connection").catch(() => null));
        setPortfolio(null);
      } else {
        setFetchError("We couldn't reach Zerodha just now. Your last loaded data is shown below if available.");
      }
    } finally {
      setLoadingPortfolio(false);
    }
  }, []);

  const loadConnection = useCallback(async () => {
    setPageError(null);
    try {
      const info = await api.get<ConnectionStatusResponse>("/portfolio/connection");
      setConnection(info);
      if (info.status === "connected") await loadPortfolio();
    } catch (err) {
      setPageError(err instanceof ApiError && err.status === 403
        ? "Verify your email address to connect a portfolio."
        : "We couldn't load your portfolio connection. Try again.");
    }
  }, [loadPortfolio]);

  // Outcome of a Zerodha login, set by /portfolio/zerodha/callback (which
  // handles the token itself — no token ever reaches this page's URL).
  useEffect(() => {
    if (handledOutcome.current) return;
    handledOutcome.current = true;
    const outcome = new URLSearchParams(window.location.search).get("zerodha");
    if (outcome) {
      window.history.replaceState(null, "", "/portfolio");
      setNotice({
        connected: "Zerodha connected. Read-only access only — Qfinera cannot trade.",
        cancelled: "The Zerodha login was cancelled. Nothing was connected.",
        expired: "That Zerodha login link expired or wasn't started from this session. Please connect again.",
        failed: "We couldn't complete the Zerodha connection. Please try connecting again.",
      }[outcome] ?? null);
    }
    loadConnection();
  }, [loadConnection]);

  async function handleConnect() {
    setConnecting(true);
    setNotice(null);
    try {
      const { login_url } = await api.get<ConnectResponse>("/portfolio/zerodha/connect");
      window.location.href = login_url; // Kite's own hosted login — Qfinera never sees the Zerodha password
    } catch (err) {
      setNotice(err instanceof ApiError && err.code === "BROKER_NOT_CONFIGURED"
        ? "Zerodha connections aren't available right now."
        : "We couldn't start the Zerodha connection. Try again.");
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    setConfirmDisconnect(false);
    try {
      await api.delete("/portfolio/zerodha");
      setPortfolio(null);
      setNotice("Zerodha disconnected. Qfinera has deleted its stored access token. (Zerodha also ends API sessions automatically each day.)");
      await loadConnection();
    } catch {
      setNotice("We couldn't disconnect Zerodha. Try again.");
    }
  }

  const holdings = useMemo(
    () => (portfolio ? sortHoldings(portfolio.holdings, sortKey, sortDir) : []),
    [portfolio, sortKey, sortDir],
  );

  function sortBy(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortKey(key); setSortDir(key === "trading_symbol" ? 1 : -1); }
  }

  const status = connection?.status;
  const connected = status === "connected";
  const needsReconnect = status === "error";
  const lastSynced = portfolio?.last_synced_at ?? connection?.last_synced_at ?? null;

  return (
    <div className={`${s.page} ${s.touch}`}>
      {confirmDisconnect && (
        <ConfirmDialog
          message="Disconnect Zerodha? Qfinera deletes its stored access and stops reading your holdings. Nothing in your Zerodha account changes."
          onCancel={() => setConfirmDisconnect(false)}
          onConfirm={handleDisconnect}
        />
      )}

      <header>
        <h1 className="qf-page-title">Portfolio</h1>
        <p className="qf-secondary mt-1">What you currently own, and how your portfolio is positioned.</p>
        <p className={`${s.readOnly} mt-2`}><span className={s.readOnlyDot} aria-hidden /> Read-only — Qfinera cannot place trades or change your Zerodha account.</p>
      </header>

      <div aria-live="polite" className="mt-3">
        {notice && (
          <p className="text-sm" role="status">
            {notice}{" "}
            <button type="button" className="underline" onClick={() => setNotice(null)}>Dismiss</button>
          </p>
        )}
      </div>

      {pageError && <div className="mt-4"><ErrorState message={pageError} onRetry={loadConnection} /></div>}

      {!pageError && connection === null && (
        <div aria-busy="true" aria-label="Loading portfolio" className="mt-6 space-y-3">
          <div className="qf-skeleton" style={{ height: 18, width: 220 }} />
          <div className="qf-skeleton" style={{ height: 88, width: "100%" }} />
          <p className="qf-secondary">Loading your portfolio…</p>
        </div>
      )}

      {!pageError && connection && !connected && (
        <section className={s.onboard} aria-labelledby="connect-title">
          <h2 id="connect-title" className="qf-section-title">
            {needsReconnect ? "Reconnect Zerodha to refresh your portfolio" : "Connect Zerodha to view your portfolio"}
          </h2>
          <p className="qf-secondary mt-2">
            {needsReconnect
              ? "Your Zerodha session has expired (Zerodha sessions end daily). Log in again to see current holdings."
              : "Qfinera reads your holdings from Zerodha so you can see what you own in one place."}
          </p>
          <ul className={s.onboardList}>
            <li>Read-only access — Qfinera can&apos;t place orders, move money or change your account.</li>
            <li>You log in on Zerodha&apos;s own page; Qfinera never sees your Zerodha password.</li>
            <li>Your portfolio stays private — it is never shown in Community or on your profile.</li>
          </ul>
          <button type="button" className="qf-btn-primary mt-5" onClick={handleConnect} disabled={connecting}>
            {connecting ? "Opening Zerodha…" : needsReconnect ? "Reconnect Zerodha" : "Connect Zerodha"}
          </button>
        </section>
      )}

      {!pageError && connected && (
        <>
          <div className={`${s.connBar} mt-5`}>
            <span><strong>Zerodha</strong> · Connected</span>
            <span>
              {lastSynced ? <>Last updated <time dateTime={lastSynced}>{new Date(lastSynced).toLocaleString()}</time></> : "Not synced yet"}
            </span>
            <div className={s.connActions}>
              <button type="button" className="qf-btn-ghost" onClick={loadPortfolio} disabled={loadingPortfolio} aria-busy={loadingPortfolio}>
                {loadingPortfolio ? "Refreshing…" : "Refresh"}
              </button>
              <button type="button" className="qf-btn-ghost" onClick={() => setConfirmDisconnect(true)}>Disconnect</button>
            </div>
          </div>

          {fetchError && (
            <p className="text-sm mt-3" role="alert" style={{ color: "var(--down)" }}>
              {fetchError} <button type="button" className="underline" onClick={loadPortfolio}>Try again</button>
            </p>
          )}

          {!portfolio && loadingPortfolio && (
            <div aria-busy="true" aria-label="Loading holdings" className="mt-5 space-y-2">
              <div className="qf-skeleton" style={{ height: 88, width: "100%" }} />
              <div className="qf-skeleton" style={{ height: 200, width: "100%" }} />
            </div>
          )}

          {portfolio && (
            <>
              <Summary portfolio={portfolio} />

              <div role="tablist" aria-label="Portfolio views" className={s.tabs}>
                {(["holdings", "dashboard"] as const).map((t) => (
                  <button
                    key={t}
                    id={`pf-tab-${t}`}
                    role="tab"
                    aria-selected={tab === t}
                    aria-controls="pf-panel"
                    tabIndex={tab === t ? 0 : -1}
                    className={`${s.tab} ${tab === t ? s.tabActive : ""}`}
                    onClick={() => setTab(t)}
                    onKeyDown={(e) => {
                      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                        e.preventDefault();
                        const next = t === "holdings" ? "dashboard" : "holdings";
                        setTab(next);
                        document.getElementById(`pf-tab-${next}`)?.focus();
                      }
                    }}
                  >
                    {t === "holdings" ? `Holdings (${portfolio.holdings.length})` : "Dashboard"}
                  </button>
                ))}
              </div>

              <section id="pf-panel" role="tabpanel" aria-labelledby={`pf-tab-${tab}`}>
                {tab === "holdings" ? (
                  <HoldingsView holdings={holdings} sortKey={sortKey} sortDir={sortDir} onSort={sortBy}
                    onSelectSort={(k) => { setSortKey(k); setSortDir(k === "trading_symbol" ? 1 : -1); }} />
                ) : (
                  <Dashboard portfolio={portfolio} hidden={hidden} onToggle={toggleWidget} />
                )}
              </section>

              <p className={s.footnote}>
                Figures come directly from Zerodha at the time shown above and are not live-streamed. Holding
                quantity includes shares awaiting T+1 settlement. This is a view of your own account — not
                investment advice, and not a recommendation to buy, sell or hold anything.
              </p>
            </>
          )}
        </>
      )}
    </div>
  );
}

function Summary({ portfolio }: { portfolio: PortfolioResponse }) {
  const sm = portfolio.summary;
  return (
    <section aria-label="Portfolio summary" className={s.tiles}>
      <div className={s.tile}>
        <div className={s.tileLabel}>Current value</div>
        <div className={s.tileValue}>{money(sm.current_value) ?? <NA />}</div>
        <div className={s.tileSub}>{sm.holdings_count} holding{sm.holdings_count === 1 ? "" : "s"}</div>
      </div>
      <div className={s.tile}>
        <div className={s.tileLabel}>Invested</div>
        <div className={s.tileValue}>{money(sm.invested_value) ?? <NA />}</div>
        <div className={s.tileSub}>At average buy price</div>
      </div>
      <div className={s.tile}>
        <div className={s.tileLabel}>Total P&amp;L</div>
        <div className={`${s.tileValue} ${tone(sm.pnl)}`}>{signedMoney(sm.pnl) ?? <NA />}</div>
        <div className={`${s.tileSub} ${tone(sm.pnl)}`}>{pct(sm.pnl_percent) ?? "—"}</div>
      </div>
      <div className={s.tile}>
        <div className={s.tileLabel}>Day change</div>
        <div className={`${s.tileValue} ${tone(sm.day_change_value)}`}>{signedMoney(sm.day_change_value) ?? <NA />}</div>
        <div className={`${s.tileSub} ${tone(sm.day_change_value)}`}>{pct(sm.day_change_percent) ?? "—"}</div>
      </div>
    </section>
  );
}

function HoldingsView({
  holdings, sortKey, sortDir, onSort, onSelectSort,
}: {
  holdings: Holding[];
  sortKey: SortKey;
  sortDir: 1 | -1;
  onSort: (k: SortKey) => void;
  onSelectSort: (k: SortKey) => void;
}) {
  if (holdings.length === 0) {
    return (
      <div className="py-10 text-center">
        <p className="qf-section-title">No holdings in this Zerodha account</p>
        <p className="qf-secondary mt-1">Once you hold shares, they&apos;ll appear here after a refresh.</p>
      </div>
    );
  }
  const header = (key: SortKey, label: string) => (
    <th scope="col" aria-sort={sortKey === key ? (sortDir === 1 ? "ascending" : "descending") : "none"}>
      <button type="button" className={s.sortBtn} onClick={() => onSort(key)}>
        {label}{sortKey === key && <span aria-hidden>{sortDir === 1 ? "↑" : "↓"}</span>}
      </button>
    </th>
  );
  return (
    <>
      <div className={`${s.tableWrap} ${s.desktopOnly}`}>
        <table className={s.table}>
          <caption className={s.srOnly}>Holdings, sorted by {SORTS.find((x) => x.key === sortKey)?.label}</caption>
          <thead>
            <tr>
              {header("trading_symbol", "Symbol")}
              <th scope="col">Qty</th>
              <th scope="col">Avg price</th>
              <th scope="col">Current price</th>
              {header("current_value", "Value")}
              {header("pnl", "P&L")}
              {header("pnl_percent", "P&L %")}
              {header("allocation_percent", "Allocation")}
            </tr>
          </thead>
          <tbody>
            {holdings.map((h) => (
              <tr key={`${h.exchange}:${h.trading_symbol}`}>
                <td>
                  <div className={s.symbol}>{h.trading_symbol}</div>
                  <div className={s.subtle}>{h.exchange ?? ""}{h.t1_quantity ? ` · ${qtyFmt.format(h.t1_quantity)} awaiting settlement` : ""}</div>
                </td>
                <td>{qtyFmt.format(h.quantity)}</td>
                <td>{money(h.average_price) ?? "—"}</td>
                <td>{money(h.last_price) ?? "—"}</td>
                <td>{money(h.current_value) ?? "—"}</td>
                <td className={tone(h.pnl)}>{signedMoney(h.pnl) ?? "—"}</td>
                <td className={tone(h.pnl_percent)}>{pct(h.pnl_percent) ?? "—"}</td>
                <td>{h.allocation_percent != null ? `${h.allocation_percent.toFixed(1)}%` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={s.mobileOnly}>
        <div className={s.sortSelect}>
          <label htmlFor="pf-sort">Sort by</label>
          <select id="pf-sort" className="qf-input" style={{ width: "auto" }} value={sortKey}
            onChange={(e) => onSelectSort(e.target.value as SortKey)}>
            {SORTS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
        </div>
        <ul className={s.cards} aria-label="Holdings">
          {holdings.map((h) => (
            <li key={`${h.exchange}:${h.trading_symbol}`} className={s.card}>
              <div className={s.cardTop}>
                <span className={s.symbol}>{h.trading_symbol} <span className={s.subtle}>{h.exchange}</span></span>
                <span>{money(h.current_value) ?? "Value n/a"}</span>
              </div>
              <dl className={s.cardGrid}>
                <div><dt>Quantity</dt><dd>{qtyFmt.format(h.quantity)}</dd></div>
                <div><dt>P&amp;L</dt><dd className={tone(h.pnl)}>{signedMoney(h.pnl) ?? "—"} {pct(h.pnl_percent) ? `(${pct(h.pnl_percent)})` : ""}</dd></div>
                <div><dt>Avg / current price</dt><dd>{money(h.average_price) ?? "—"} / {money(h.last_price) ?? "—"}</dd></div>
                <div><dt>Allocation</dt><dd>{h.allocation_percent != null ? `${h.allocation_percent.toFixed(1)}%` : "—"}</dd></div>
              </dl>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

function Dashboard({
  portfolio, hidden, onToggle,
}: {
  portfolio: PortfolioResponse;
  hidden: Set<WidgetId>;
  onToggle: (id: WidgetId) => void;
}) {
  const sm = portfolio.summary;
  const byAllocation = sortHoldings(portfolio.holdings, "allocation_percent", -1);
  const top = byAllocation.slice(0, 8);
  const otherShare = byAllocation.slice(8).reduce((sum, h) => sum + (h.allocation_percent ?? 0), 0);
  const allocationKnown = sm.current_value != null && portfolio.holdings.length > 0;
  const gainers = portfolio.holdings.filter((h) => (h.pnl ?? 0) > 0).length;
  const losers = portfolio.holdings.filter((h) => (h.pnl ?? 0) < 0).length;
  const show = (id: WidgetId) => !hidden.has(id);

  return (
    <>
      <fieldset className={s.customize}>
        <legend className="qf-caption">Customize dashboard</legend>
        {WIDGETS.map((w) => (
          <label key={w.id}>
            <input type="checkbox" checked={show(w.id)} onChange={() => onToggle(w.id)} /> {w.label}
          </label>
        ))}
      </fieldset>

      <div className={s.dash}>
        {show("allocation") && (
          <section className={`${s.widget} ${s.wide}`} aria-labelledby="w-alloc">
            <div className={s.widgetHead}>
              <h2 id="w-alloc" className={s.widgetTitle}>Allocation by holding</h2>
              <span className={s.widgetNote}>Share of current value</span>
            </div>
            {allocationKnown ? (
              <div className={s.bars} role="list">
                {top.map((h) => (
                  <div key={h.trading_symbol} className={s.barRow} role="listitem"
                    title={`${h.trading_symbol}: ${h.allocation_percent?.toFixed(2)}% · ${money(h.current_value)}`}>
                    <span className={s.barLabel}>{h.trading_symbol}</span>
                    <span className={s.barTrack} aria-hidden>
                      <span className={s.barFill} style={{ display: "block", width: `${h.allocation_percent ?? 0}%` }} />
                    </span>
                    <span className={s.barValue}>{h.allocation_percent?.toFixed(1)}%</span>
                  </div>
                ))}
                {otherShare > 0 && (
                  <div className={s.barRow} role="listitem" title={`${byAllocation.length - 8} other holdings: ${otherShare.toFixed(2)}%`}>
                    <span className={s.barLabel}>Other ({byAllocation.length - 8})</span>
                    <span className={s.barTrack} aria-hidden>
                      <span className={s.barFill} style={{ display: "block", width: `${otherShare}%`, opacity: 0.55 }} />
                    </span>
                    <span className={s.barValue}>{otherShare.toFixed(1)}%</span>
                  </div>
                )}
              </div>
            ) : (
              <p className={s.widgetNote}>Not available — allocation needs a current price for every holding.</p>
            )}
          </section>
        )}

        {show("concentration") && (
          <section className={s.widget} aria-labelledby="w-conc">
            <div className={s.widgetHead}><h2 id="w-conc" className={s.widgetTitle}>Concentration</h2></div>
            <div className={s.metricList}>
              <div className={s.metric}><span>Holdings</span><span>{sm.holdings_count}</span></div>
              <div className={s.metric}><span>Largest holding</span><span>{sm.top_holding_percent != null ? `${sm.top_holding_percent.toFixed(1)}%` : "Not available"}</span></div>
              <div className={s.metric}><span>Top 5 holdings</span><span>{sm.top_five_percent != null ? `${sm.top_five_percent.toFixed(1)}%` : "Not available"}</span></div>
            </div>
            <p className={`${s.widgetNote} mt-3`}>How much of your current value sits in your biggest positions.</p>
          </section>
        )}

        {show("performance") && (
          <section className={s.widget} aria-labelledby="w-perf">
            <div className={s.widgetHead}><h2 id="w-perf" className={s.widgetTitle}>Performance</h2></div>
            <div className={s.metricList}>
              <div className={s.metric}><span>Total P&amp;L</span><span className={tone(sm.pnl)}>{signedMoney(sm.pnl) ?? "Not available"} {pct(sm.pnl_percent) ? `(${pct(sm.pnl_percent)})` : ""}</span></div>
              <div className={s.metric}><span>Day change</span><span className={tone(sm.day_change_value)}>{signedMoney(sm.day_change_value) ?? "Not available"} {pct(sm.day_change_percent) ? `(${pct(sm.day_change_percent)})` : ""}</span></div>
              <div className={s.metric}><span>Holdings in profit / loss</span><span>{gainers} / {losers}</span></div>
            </div>
            <p className={`${s.widgetNote} mt-3`}>
              Unrealised P&amp;L against your average buy price. Time-weighted returns aren&apos;t shown — Zerodha&apos;s
              holdings data doesn&apos;t include the history needed to calculate them reliably.
            </p>
          </section>
        )}

        {show("sector") && (
          <section className={s.widget} aria-labelledby="w-sector">
            <div className={s.widgetHead}><h2 id="w-sector" className={s.widgetTitle}>Sector exposure</h2></div>
            <p className={s.widgetNote}>
              Not available yet. Zerodha doesn&apos;t provide sector data, and Qfinera&apos;s company records don&apos;t
              have reliable sector classifications, so we don&apos;t estimate one.
            </p>
          </section>
        )}

        {show("positions") && (
          <section className={s.widget} aria-labelledby="w-pos">
            <div className={s.widgetHead}>
              <h2 id="w-pos" className={s.widgetTitle}>Open positions</h2>
              <span className={s.widgetNote}>F&amp;O / intraday, net</span>
            </div>
            {portfolio.positions.length === 0 ? (
              <p className={s.widgetNote}>No open positions.</p>
            ) : (
              <table className={s.table}>
                <caption className={s.srOnly}>Open positions</caption>
                <thead><tr><th scope="col">Symbol</th><th scope="col">Qty</th><th scope="col">P&amp;L</th></tr></thead>
                <tbody>
                  {portfolio.positions.map((p) => (
                    <tr key={`${p.exchange}:${p.trading_symbol}:${p.product}`}>
                      <td><span className={s.symbol}>{p.trading_symbol}</span> <span className={s.subtle}>{p.product}</span></td>
                      <td>{qtyFmt.format(p.quantity)}</td>
                      <td className={tone(p.pnl)}>{signedMoney(p.pnl) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}
      </div>
    </>
  );
}
