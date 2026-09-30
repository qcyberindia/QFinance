"use client";

/**
 * Company (Stock subject) picker for Research -> Start Research.
 *
 * Data comes ONLY from the existing backend `GET /companies?search=&page_size=`
 * (companies/router.py) — no company is hardcoded here. Search is server-side
 * (name OR symbol, per companies/service.py::list_companies), so it scales to a
 * full exchange master instead of only the first page of results.
 *
 * States (exact copy per the task): loading "Searching companies...", no match
 * "No companies found.", empty registry "No companies available yet.", error
 * "Unable to load companies. Please try again." (with Retry).
 *
 * Selecting a company hands the parent the real company object (its real `id`
 * is what Start Research sends to POST /research).
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api } from "@/lib/api-client";
import type { Company, CompanyListResponse } from "@/lib/types";

const PAGE_SIZE = 20;
const DEBOUNCE_MS = 300;

type Status = "idle" | "loading" | "error";

export function CompanyPicker({
  value,
  onChange,
  inputId,
}: {
  value: Company | null;
  onChange: (company: Company | null) => void;
  inputId?: string;
}) {
  const listId = useId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Company[] | null>(null);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<Status>("idle");
  const [activeIndex, setActiveIndex] = useState(-1);
  const seq = useRef(0); // ignore responses from superseded requests
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchCompanies = useCallback(async (q: string) => {
    const mine = ++seq.current;
    setStatus("loading");
    try {
      const qs = new URLSearchParams({ page_size: String(PAGE_SIZE) });
      if (q.trim()) qs.set("search", q.trim());
      const data = await api.get<CompanyListResponse>(`/companies?${qs.toString()}`);
      if (mine !== seq.current) return;
      setResults(data.items);
      setTotal(data.total);
      setActiveIndex(data.items.length > 0 ? 0 : -1);
      setStatus("idle");
    } catch {
      if (mine !== seq.current) return;
      setStatus("error"); // deliberately generic — never surface raw error text here
    }
  }, []);

  // Fetch when the list is open: immediately for an empty query (so companies
  // appear the moment the field is focused), debounced while typing.
  useEffect(() => {
    if (!open) return;
    if (!query.trim()) {
      fetchCompanies("");
      return;
    }
    const t = setTimeout(() => fetchCompanies(query), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [open, query, fetchCompanies]);

  function select(c: Company) {
    onChange(c);
    setOpen(false);
    setQuery("");
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      if (results && results.length > 0) setActiveIndex((i) => (i + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (results && results.length > 0) setActiveIndex((i) => (i <= 0 ? results.length - 1 : i - 1));
    } else if (e.key === "Enter") {
      if (open && results && activeIndex >= 0 && results[activeIndex]) {
        e.preventDefault(); // don't submit the surrounding form while choosing
        select(results[activeIndex]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  if (value) {
    return (
      <div
        className="flex items-center justify-between gap-3 px-3 py-2 rounded"
        style={{ border: "1px solid var(--brass)", background: "rgba(168,134,62,.08)" }}
      >
        <div className="min-w-0">
          <p className="text-sm font-semibold truncate">{value.name}</p>
          <p className="text-xs text-ink-soft">
            {value.symbol ?? "No symbol on file"} · {value.exchange}
          </p>
        </div>
        <button
          type="button"
          className="qf-btn-ghost text-xs shrink-0"
          style={{ padding: "4px 10px" }}
          onClick={() => {
            onChange(null);
            setTimeout(() => inputRef.current?.focus(), 0);
          }}
        >
          Change
        </button>
      </div>
    );
  }

  const showEmptyRegistry = status === "idle" && results !== null && results.length === 0 && !query.trim();
  const showNoMatch = status === "idle" && results !== null && results.length === 0 && !!query.trim();

  return (
    <div
      className="relative"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <input
        ref={inputRef}
        id={inputId}
        className="qf-input"
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && activeIndex >= 0 ? `${listId}-opt-${activeIndex}` : undefined}
        autoComplete="off"
        placeholder="Search company name or symbol…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && (
        <div
          className="absolute z-20 left-0 right-0 mt-1 rounded max-h-72 overflow-y-auto"
          style={{ border: "1px solid var(--line)", background: "var(--cream-0)", boxShadow: "0 8px 24px rgba(43,38,33,.12)" }}
          onMouseDown={(e) => e.preventDefault() /* keep input focus so blur doesn't close before click */}
        >
          <div aria-live="polite">
            {status === "loading" && (
              <p className="text-xs text-ink-soft px-3 py-2">Searching companies...</p>
            )}
            {status === "error" && (
              <div className="px-3 py-2">
                <p className="text-xs" style={{ color: "var(--down)" }}>
                  Unable to load companies. Please try again.
                </p>
                <button
                  type="button"
                  className="qf-btn-ghost text-xs mt-2"
                  style={{ padding: "3px 9px" }}
                  onClick={() => fetchCompanies(query)}
                >
                  Retry
                </button>
              </div>
            )}
            {showEmptyRegistry && <p className="text-xs text-ink-soft px-3 py-2">No companies available yet.</p>}
            {showNoMatch && <p className="text-xs text-ink-soft px-3 py-2">No companies found.</p>}
          </div>
          {status !== "error" && results && results.length > 0 && (
            <ul id={listId} role="listbox" aria-label="Companies">
              {results.map((c, i) => (
                <li
                  key={c.id}
                  id={`${listId}-opt-${i}`}
                  role="option"
                  aria-selected={i === activeIndex}
                  onMouseEnter={() => setActiveIndex(i)}
                  onClick={() => select(c)}
                  className="px-3 py-2 cursor-pointer"
                  style={{ background: i === activeIndex ? "var(--cream-1)" : "transparent" }}
                >
                  <p className="text-sm">{c.name}</p>
                  <p className="text-xs text-ink-soft">
                    {c.symbol ?? "No symbol on file"} · {c.exchange}
                  </p>
                </li>
              ))}
            </ul>
          )}
          {status !== "error" && results && total > results.length && (
            <p className="text-[11px] text-ink-soft px-3 py-2" style={{ borderTop: "1px dashed var(--line)" }}>
              Showing {results.length} of {total} — keep typing to narrow.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
