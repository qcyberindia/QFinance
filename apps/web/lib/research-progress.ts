/**
 * Research Workspace completeness + section metadata — extracted from
 * app/(app)/research/[id]/page.tsx so it can be tested independently of
 * React/JSX (see research-progress.test.mjs).
 *
 * "Completeness" is a count of sections with real, persisted, non-empty
 * content — explicitly NOT a score, ranking, or quality signal.
 *
 * REDESIGN NOTE (retail-friendly workflow pass): section LABELS and
 * SIMPLE-EXPLANATION copy were updated to match plain-language retail
 * framing (e.g. "Financial Health" instead of "Financials", each section
 * carries a `proTerm`/`simpleExplanation` pair for the small
 * "Professional concept → Simple explanation" helper text). NO backend
 * field mapping changed — every FUNCTIONAL section still binds to the exact
 * same real `research` table column it always did.
 *
 * Sections 11 (Investment Thesis) and 13 (Review) are now marked
 * `implemented: true` with `derived: true` — they are NOT new editable
 * fields and do NOT add persistence. Both are computed, read-only summaries
 * assembled entirely from fields the researcher already saved elsewhere
 * (business_model, competitive_position, risk_register, invalidation_
 * conditions, valuation_range, bull/base/bear_case). This directly matches
 * the instruction that Investment Thesis should "generate a structured
 * summary from the researcher's own work" and Review should "show a clean
 * summary... show research completeness only" — neither requires a new
 * database column, so none was added (Database Schema V1 §8 unchanged).
 * See `deriveInvestmentThesis`/`deriveReviewSummary` below.
 *
 * Sections 06 (Management) and 07 (Assumptions & Outlook) are
 * `implemented: true` — `management_notes`/`assumptions_outlook` were added
 * as real, additive-only columns via alembic/versions/0007_research_
 * management_and_assumptions.py, and are bound below exactly like every
 * other functional section (no fabrication; confirmed against the actual
 * migration and `research/schemas.py`'s `ResearchPatchRequest` before this
 * comment was corrected).
 */
import type { ResearchFull } from "@/lib/types";

export interface GuidedSection {
  n: string;
  key: string;
  label: string;
  field: keyof ResearchFull | null;
  implemented: boolean;
  /** True for a computed/derived section with no field of its own — never
   * independently editable or saveable; always assembled from other
   * sections' already-persisted data. */
  derived?: boolean;
  question?: string;
  guidance?: string[];
  contentLabel?: string;
  placeholder?: string;
  /** "Professional concept → Simple explanation" helper pair, shown as
   * small subtitle text under the section header where present. */
  proTerm?: string;
  simpleExplanation?: string;
}

export const SECTIONS: GuidedSection[] = [
  {
    n: "01", key: "question", label: "Research Question", field: "summary", implemented: true,
    simpleExplanation: "What am I trying to understand?",
  },
  {
    n: "02", key: "business", label: "Business", field: "business_model", implemented: true,
    question: "How does this company actually make money?",
    proTerm: "Qualitative Analysis", simpleExplanation: "What makes this business good or weak?",
    guidance: [
      "What does the company sell?",
      "Who are its customers?",
      "How does it make money?",
      "What are its major revenue segments?",
      "What are its key products or services?",
    ],
    contentLabel: "Researcher's analysis",
    placeholder: "Describe the business model in your own words…",
  },
  {
    n: "03", key: "industry", label: "Industry & Competition", field: "competitive_position", implemented: true,
    question: "How does this company compete?",
    simpleExplanation: "Understand the environment around the company.",
    guidance: [
      "What differentiates the company?",
      "Who are the major competitors?",
      "What could make customers leave?",
      "Does the company appear to have pricing power?",
      "What competitive advantages exist?",
    ],
    contentLabel: "Researcher's analysis",
    placeholder: "Document your read on the competitive landscape…",
  },
  {
    n: "04", key: "financials", label: "Financial Health", field: "financial_snapshot", implemented: true,
    question: "What are the numbers telling you?",
    proTerm: "Quantitative Analysis", simpleExplanation: "What do the numbers tell us?",
    guidance: [
      "Revenue growth and profit growth",
      "Margins",
      "Cash flow",
      "Debt",
      "ROE / ROCE, where relevant",
    ],
    contentLabel: "Researcher's financial observations",
    placeholder: "Record your financial observations — this is a free-text snapshot, not a normalized financial-data model…",
  },
  {
    n: "05", key: "growth", label: "Growth", field: "catalysts", implemented: true,
    question: "Why could this business grow?",
    guidance: [
      "Current growth drivers",
      "Future opportunities",
      "New products or markets",
      "Pricing or volume expansion",
      "What must go right?",
    ],
    contentLabel: "Researcher's notes",
    placeholder: "List and describe the growth drivers you've identified…",
  },
  {
    n: "06", key: "management", label: "Management", field: "management_notes", implemented: true,
    question: "Who is running this business, and do you trust them with your capital?",
    simpleExplanation: "Who is running the business?",
    guidance: [
      "Track record of the leadership team",
      "Insider ownership and recent buying/selling",
      "Capital allocation history",
      "Related-party transactions or governance concerns",
    ],
    contentLabel: "Researcher's notes",
    placeholder: "Document what you know about management and governance…",
  },
  {
    n: "07", key: "forecast", label: "Assumptions & Outlook", field: "assumptions_outlook", implemented: true,
    question: "What has to be true for your thesis to hold?",
    proTerm: "Forecast Model", simpleExplanation: "What needs to be true for my thinking to work?",
    guidance: [
      "This is a notes/assumptions editor, not a forecasting engine.",
      "Key assumptions behind your growth/margin expectations",
      "What would have to change for the outlook to break",
    ],
    contentLabel: "Researcher's assumptions",
    placeholder: "Record the assumptions behind your outlook — this does not model or forecast anything for you…",
  },
  {
    n: "08", key: "valuation", label: "Valuation", field: "valuation_range", implemented: true,
    question: "Does the current price make sense relative to the business?",
    proTerm: "Equity Valuation Methodology", simpleExplanation: "What am I paying compared with what the business may be worth?",
    guidance: [
      "This is a notes/assumptions editor, not a calculation engine.",
      "Potential future methods: P/E, P/B, EV/EBITDA, EV/Sales, DCF, DDM, SOTP — Coming next.",
      "This section never generates a BUY/SELL/HOLD recommendation.",
    ],
    contentLabel: "Researcher's valuation notes",
    placeholder: "Record your valuation range and the assumptions behind it — this does not calculate anything for you…",
  },
  {
    n: "09", key: "scenarios", label: "Bull / Base / Bear", field: "bull_case", implemented: true,
    proTerm: "Scenario Analysis", simpleExplanation: "What happens if things go better or worse?",
    contentLabel: "Researcher's scenarios",
  },
  {
    n: "10", key: "risks", label: "Risks", field: "risk_register", implemented: true,
    question: "What could break your thinking?",
    proTerm: "Risk Assessment Framework", simpleExplanation: "What could go wrong?",
    guidance: [
      "Business risk, Financial risk, Industry risk",
      "Management/Governance risk, Regulatory risk, Valuation risk",
      "For each: Risk → why it matters → what would indicate it's increasing",
    ],
    contentLabel: "Researcher's risk register",
    placeholder: "Document the risks you've identified…",
  },
  {
    n: "11", key: "thesis", label: "Investment Thesis", field: null, implemented: true, derived: true,
    simpleExplanation: "What do I currently believe, and why?",
  },
  {
    n: "12", key: "invalidation", label: "Prove Me Wrong", field: "invalidation_conditions", implemented: true,
    question: "Why could your thesis be wrong?",
    simpleExplanation: "What evidence would change my mind?",
    guidance: [
      "What evidence would change my mind?",
      "Which assumption is most fragile?",
      "What should I monitor?",
      "What would invalidate my thesis?",
    ],
    contentLabel: "Researcher's invalidation conditions",
    placeholder: "What would tell you that you're wrong?",
  },
  {
    n: "13", key: "review", label: "Review", field: null, implemented: true, derived: true,
    simpleExplanation: "Step back and review the whole research.",
  },
];

export function isSectionFilled(item: ResearchFull, s: GuidedSection): boolean {
  if (s.key === "scenarios") {
    return [item.bull_case, item.base_case, item.bear_case].every(
      (v) => typeof v === "string" && v.trim().length > 0
    );
  }
  if (s.derived || !s.field) return false; // derived sections never count toward completeness on their own
  const value = item[s.field];
  return typeof value === "string" && value.trim().length > 0;
}

export function computeProgress(item: ResearchFull): { done: number; total: number } {
  const done = SECTIONS.filter((s) => isSectionFilled(item, s)).length;
  return { done, total: SECTIONS.length };
}

export interface InvestmentThesis {
  /** "What I believe" */
  thesis: string;
  /** "Why I believe it" */
  keyReasons: string[];
  keyAssumptions: string[];
  /** "Biggest risks" */
  keyRisks: string[];
  /** "What would prove me wrong?" — mirrors Section 12's own field so the
   * culmination view shows it alongside the rest of the thesis, not just
   * buried in Section 12. */
  whatWouldProveWrong: string;
  isEmpty: boolean;
}

/** Section 11 — assembled ENTIRELY from already-persisted fields. Never
 * invents content: any part the researcher hasn't written yet is simply
 * omitted (shown as an honest "not yet written" note in the UI), never
 * filled with placeholder/fabricated text. No scoring, no recommendation. */
export function deriveInvestmentThesis(item: ResearchFull): InvestmentThesis {
  const thesis = item.summary?.trim() || "";
  const keyReasons = [item.business_model, item.competitive_position, item.catalysts]
    .filter((v): v is string => !!v && v.trim().length > 0);
  const keyAssumptions = [item.valuation_range, item.base_case]
    .filter((v): v is string => !!v && v.trim().length > 0);
  const keyRisks = [item.risk_register, item.bear_case]
    .filter((v): v is string => !!v && v.trim().length > 0);
  const whatWouldProveWrong = item.invalidation_conditions?.trim() || "";

  return {
    thesis, keyReasons, keyAssumptions, keyRisks, whatWouldProveWrong,
    isEmpty: !thesis && keyReasons.length === 0 && keyAssumptions.length === 0
      && keyRisks.length === 0 && !whatWouldProveWrong,
  };
}

/** Section 13 — a completeness-only overview, explicitly never a score or
 * recommendation, per instruction. */
export function deriveReviewSummary(item: ResearchFull) {
  return SECTIONS.filter((s) => !s.derived).map((s) => ({
    key: s.key, n: s.n, label: s.label, filled: isSectionFilled(item, s), implemented: s.implemented,
  }));
}
