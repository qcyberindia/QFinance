/** Types mirror the ACTUAL backend Pydantic schemas read from the real
 * project this session — apps/api/app/modules/{auth,community,research,
 * journal,portfolio}/schemas.py. Kept in one file since the surface is still
 * small; split when it grows. */

export interface SessionResponse {
  user_id: string;
  email: string;
  username: string;
  name: string;
  roles: string[];
  effective_tier: "FREE" | "CORE";
}

export interface AuthorRef {
  id: string;
  username: string | null;
}

export interface RatingSummary {
  average: number | null;
  count: number;
  my_rating: number | null;
}

// ---- Community ----
export interface Post {
  id: string;
  channel: string | null;
  research_id: string | null;
  post_type: "general" | "thesis" | "question" | "discussion";
  author: AuthorRef;
  content: string;
  created_at: string;
  updated_at: string;
  is_edited: boolean;
  status: string;
  reaction_count: number;
  comment_count: number;
  rating?: RatingSummary;
  /** Whether the signed-in viewer has liked / saved this post. */
  viewer_reacted?: boolean;
  viewer_bookmarked?: boolean;
  /** Present on thesis posts while the linked research is published. */
  thesis?: ThesisRef | null;
}
export interface ThesisCompanyRef { name: string | null; symbol: string | null; exchange: string | null }
export interface ThesisRef {
  research_title: string | null;
  version: number;
  published_at: string | null;
  company: ThesisCompanyRef;
}
/** GET /community/posts/{id}/thesis — the published, versioned reasoning. */
export interface ThesisSnapshot {
  post_id: string;
  company: ThesisCompanyRef;
  version: number;
  version_created_at: string;
  published_at: string | null;
  sections: Record<string, string | boolean | null>;
  sources: { label: string | null; reference: string | null; supports_claim: string | null }[];
}
export type CommunityPillar = "discussion" | "question" | "thesis";
export interface PostListResponse { items: Post[]; page: number; page_size: number; total: number }

export interface Comment {
  id: string;
  post_id: string;
  parent_comment_id: string | null;
  author: AuthorRef;
  content: string;
  created_at: string;
  is_edited: boolean;
  status: string;
  replies?: Comment[];
}
export interface CommentListResponse { items: Comment[]; page: number; page_size: number; total: number }

export interface BookmarkItem {
  post_id: string;
  post_summary: string;
  bookmarked_at: string;
  /** null when the post is no longer available (removed/restricted). */
  post_type: Post["post_type"] | null;
  available: boolean;
}
export interface BookmarkListResponse { items: BookmarkItem[]; page: number; page_size: number; total: number }

export const COMMUNITY_CHANNELS = [
  "announcements", "general_discussion", "research_discussion",
  "market_discussion", "learning", "help_questions", "off_topic",
] as const;
export type CommunityChannel = (typeof COMMUNITY_CHANNELS)[number];

// ---- Journal ----
export interface JournalEntry {
  id: string;
  user_id: string;
  company_id: string | null;
  entry_type: "decision" | "reasoning" | "observation" | "note";
  content: string;
  created_at: string;
  updated_at: string;
}
export interface JournalEntryListResponse { items: JournalEntry[]; page: number; page_size: number; total: number }

// ---- Research (My Research) ----
export interface ResearchFull {
  id: string;
  author_id: string;
  company_id: string;
  company: CompanyRef;
  research_type: string;
  industry: string | null;
  status: "draft" | "published";
  moderation_status: string;
  title: string;
  summary: string;
  current_version: number;
  business_quality: string | null;
  financial_snapshot: string | null;
  business_model: string | null;
  competitive_position: string | null;
  valuation_range: string | null;
  bull_case: string | null;
  base_case: string | null;
  bear_case: string | null;
  risk_register: string | null;
  catalysts: string | null;
  invalidation_conditions: string | null;
  management_notes: string | null;
  assumptions_outlook: string | null;
  disclosure: {
    conflict_disclosed: boolean | null;
    conflict_detail: string | null;
    position_disclosed: boolean | null;
    position_detail: string | null;
    research_date: string | null;
  };
  sources: { id: string; label: string; reference: string; supports_claim: string | null }[];
  tags: string[];
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

// ---- Portfolio (read-only, Zerodha) ----
// Mirrors portfolio/schemas.py. Every number is the broker's own value or
// arithmetic on it; `null` means "not available" — never an estimate.
export interface Holding {
  trading_symbol: string;
  exchange: string | null;
  isin: string | null;
  quantity: number;
  t1_quantity: number;
  average_price: number | null;
  last_price: number | null;
  close_price: number | null;
  invested_value: number | null;
  current_value: number | null;
  pnl: number | null;
  pnl_percent: number | null;
  day_change_value: number | null;
  day_change_percent: number | null;
  allocation_percent: number | null;
}
export interface Position {
  trading_symbol: string;
  exchange: string | null;
  product: string | null;
  quantity: number;
  average_price: number | null;
  last_price: number | null;
  pnl: number | null;
}
export interface PortfolioSummary {
  holdings_count: number;
  invested_value: number | null;
  current_value: number | null;
  pnl: number | null;
  pnl_percent: number | null;
  day_change_value: number | null;
  day_change_percent: number | null;
  top_holding_percent: number | null;
  top_five_percent: number | null;
}
export interface PortfolioResponse {
  holdings: Holding[];
  positions: Position[];
  summary: PortfolioSummary;
  last_synced_at: string;
  read_only_notice: string;
}
export interface ConnectResponse { login_url: string }
export interface ConnectionStatusResponse {
  broker: string;
  status: "connected" | "disconnected" | "error" | "not_connected";
  connected_at: string | null;
  last_synced_at: string | null;
}

// ---- Companies (for association pickers) ----
export interface Company { id: string; name: string; symbol: string | null; exchange: string }
export interface CompanyListResponse { items: Company[]; total: number; page: number; page_size: number }

// ---- Research Subject (Research Phase 3) ----
// Mirrors research/schemas.py's CompanyRef exactly — nested inside
// ResearchFull.company, replacing the earlier client-side "match company_id
// against a fetched company list" workaround.
export interface CompanyRef {
  id: string;
  name: string | null;
  symbol: string | null;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  description: string | null;
}

// ---- Research Library (API Spec §7.4.1/§7.4.2) ----
// Mirrors research/schemas.py's LibraryItem | ResearchPreviewResponse union
// exactly (see that file) — no fields invented here.
export interface LibraryItem {
  id: string;
  title: string;
  summary: string;
  author: AuthorRef;
  company: { id: string; name: string | null };
  industry: string | null;
  created_at: string;
  updated_at: string;
  status_label: string;
  moderation_status: string;
  tags: string[];
  source_count: number;
  current_version: number;
}
export interface LibraryListResponse {
  items: LibraryItem[];
  page: number;
  page_size: number;
  total: number;
}

// ---- My Research (API Spec V2 §2) ----
export interface MyResearchItem {
  id: string;
  title: string;
  summary: string;
  status: "draft" | "published";
  company: { id: string; name: string | null };
  research_type: string;
  current_version: number;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface MyResearchListResponse { items: MyResearchItem[]; page: number; page_size: number; total: number }

// ---- Profile (API Spec V2 §6, public, read-only) ----
export interface PublicPostSummary { id: string; post_type: string; content: string; created_at: string }
export interface PublicProfile {
  username: string;
  bio: string | null;
  joined_at: string | null;
  published_posts_count: number;
  published_theses_count: number;
  contribution_points: number;
  recent_posts: PublicPostSummary[];
}

/** GET/PATCH /users/me/profile — the member's own profile. `name` and
 * `email` are private account fields, never part of the public profile. */
export interface MyProfile {
  username: string;
  bio: string | null;
  experience_level: "beginner" | "intermediate" | "advanced" | null;
  name: string;
  email: string;
  email_verified: boolean;
  joined_at: string;
  published_posts_count: number;
  published_theses_count: number;
  contribution_points: number;
}

// ---- Q-Points (GET /credits/me) ----
// A reputation/contribution score only — never money: no currency, balance
// or paise fields exist on these types.
export interface QPointEntry { points: number; source_type: string; reason: string; created_at: string }
export interface QPointsSummary {
  points: number;
  entries: QPointEntry[];
  page: number;
  page_size: number;
  total: number;
}
