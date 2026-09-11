/** Types mirror the ACTUAL backend Pydantic schemas read from the real
 * project this session — apps/api/app/modules/{auth,community,research,
 * journal,portfolio}/schemas.py. Kept in one file since the surface is still
 * small; split when it grows. */

export interface SessionResponse {
  user_id: string;
  email: string;
  roles: string[];
  effective_tier: "FREE" | "CORE";
}

export interface AuthorRef {
  id: string;
  name: string | null;
  username: string | null;
}

// ---- Community ----
export interface Post {
  id: string;
  channel: string | null;
  research_id: string | null;
  author: AuthorRef;
  content: string;
  created_at: string;
  updated_at: string;
  is_edited: boolean;
  status: string;
  reaction_count: number;
  comment_count: number;
}
export interface PostListResponse { items: Post[]; page: number; page_size: number; total: number }

export interface Comment {
  id: string;
  post_id: string;
  author: AuthorRef;
  content: string;
  created_at: string;
  is_edited: boolean;
  status: string;
}
export interface CommentListResponse { items: Comment[]; page: number; page_size: number; total: number }

export interface BookmarkItem { post_id: string; post_summary: string; bookmarked_at: string }
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
  research_type: string;
  industry: string | null;
  status: "draft" | "published";
  moderation_status: string;
  access_tier: string;
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

// ---- Portfolio ----
export interface Holding {
  trading_symbol: string;
  quantity: number;
  average_price: number;
  last_price: number | null;
  pnl: number | null;
  exchange: string | null;
}
export interface PortfolioResponse {
  holdings: Holding[];
  positions: Holding[];
  last_synced_at: string;
  read_only_notice: string;
}
export interface ConnectResponse { login_url: string }
export interface ConnectionStatusResponse {
  broker: string;
  status: "connected" | "disconnected" | "error";
  connected_at: string | null;
  last_synced_at: string | null;
}

// ---- Companies (for association pickers) ----
export interface Company { id: string; name: string; exchange: string }
export interface CompanyListResponse { items: Company[]; total: number; page: number; page_size: number }
