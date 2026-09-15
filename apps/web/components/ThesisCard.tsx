"use client";

/**
 * Qfinera's signature MVP social object. Built entirely from fields already
 * returned by the real backend (ResearchFull for the full/editor view, or a
 * Post whose post_type === "thesis" for the community-feed view) — no
 * fabricated fields. Deliberately contains no BUY/SELL/STRONG BUY/TARGET
 * PRICE/trading-signal language anywhere; the card frames a user's own
 * reasoning, not a recommendation.
 */
import type { RatingSummary, ResearchFull } from "@/lib/types";

type ThesisCardProps = {
  companyName: string;
  title: string;
  bullCase: string | null;
  baseCase: string | null;
  bearCase: string | null;
  keyAssumptions: string | null; // mapped from business_quality/competitive_position, whichever the caller has
  risks: string | null; // risk_register
  invalidation: string | null; // invalidation_conditions — "what would prove me wrong"
  sourceCount: number;
  rating?: RatingSummary;
  discussionCount?: number;
  onProveMeWrong?: () => void;
  onDiscuss?: () => void;
};

function Stars({ value }: { value: number | null }) {
  const rounded = value != null ? Math.round(value) : 0;
  return (
    <span aria-hidden className="tracking-wide" style={{ color: "var(--brass)" }}>
      {"★".repeat(rounded)}
      <span style={{ color: "var(--line)" }}>{"★".repeat(5 - rounded)}</span>
    </span>
  );
}

export function ThesisCard({
  companyName, title, bullCase, baseCase, bearCase, keyAssumptions, risks, invalidation,
  sourceCount, rating, discussionCount, onProveMeWrong, onDiscuss,
}: ThesisCardProps) {
  return (
    <div className="qf-card p-6 space-y-4" style={{ borderColor: "var(--brass)" }}>
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--brass)" }}>
          Why I Own This
        </div>
        <h2 className="font-display text-2xl mt-1">{companyName}</h2>
        {title && <p className="text-sm text-ink-soft mt-0.5">{title}</p>}
      </div>

      {(bullCase || baseCase || bearCase) && (
        <div>
          <div className="qf-label">Thesis</div>
          <div className="space-y-2 mt-1">
            {bullCase && <p className="text-sm"><span className="font-semibold">Bull case — </span>{bullCase}</p>}
            {baseCase && <p className="text-sm"><span className="font-semibold">Base case — </span>{baseCase}</p>}
            {bearCase && <p className="text-sm"><span className="font-semibold">Bear case — </span>{bearCase}</p>}
          </div>
        </div>
      )}

      {keyAssumptions && (
        <div>
          <div className="qf-label">Key Assumptions</div>
          <p className="text-sm mt-1">{keyAssumptions}</p>
        </div>
      )}

      {risks && (
        <div>
          <div className="qf-label">Biggest Risks</div>
          <p className="text-sm mt-1">{risks}</p>
        </div>
      )}

      {invalidation && (
        <div className="qf-card p-3" style={{ background: "var(--cream-1)" }}>
          <div className="qf-label">What Would Prove Me Wrong?</div>
          <p className="text-sm mt-1">{invalidation}</p>
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-ink-soft pt-2 border-t" style={{ borderColor: "var(--line)" }}>
        <span>{sourceCount} source{sourceCount === 1 ? "" : "s"}</span>
        {rating && (
          <span className="flex items-center gap-1.5">
            <Stars value={rating.average} />
            {rating.average != null ? rating.average.toFixed(1) : "No ratings yet"}
            {rating.count > 0 && ` (${rating.count})`}
          </span>
        )}
        {discussionCount != null && <span>{discussionCount} investors discussing</span>}
      </div>

      {(onProveMeWrong || onDiscuss) && (
        <div className="flex gap-3 pt-1">
          {onProveMeWrong && (
            <button className="qf-btn-gold" onClick={onProveMeWrong}>
              Prove Me Wrong
            </button>
          )}
          {onDiscuss && (
            <button className="qf-btn-ghost" onClick={onDiscuss}>
              Discuss
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** Convenience wrapper for the full research-editor view (ResearchFull),
 * mapping its field names onto ThesisCard's generic props. */
export function ThesisCardFromResearch({
  research, companyName, rating, discussionCount, onProveMeWrong, onDiscuss,
}: {
  research: ResearchFull;
  companyName: string;
  rating?: RatingSummary;
  discussionCount?: number;
  onProveMeWrong?: () => void;
  onDiscuss?: () => void;
}) {
  const assumptions = [research.business_quality, research.competitive_position].filter(Boolean).join(" ") || null;
  return (
    <ThesisCard
      companyName={companyName}
      title={research.title}
      bullCase={research.bull_case}
      baseCase={research.base_case}
      bearCase={research.bear_case}
      keyAssumptions={assumptions}
      risks={research.risk_register}
      invalidation={research.invalidation_conditions}
      sourceCount={research.sources.length}
      rating={rating}
      discussionCount={discussionCount}
      onProveMeWrong={onProveMeWrong}
      onDiscuss={onDiscuss}
    />
  );
}
