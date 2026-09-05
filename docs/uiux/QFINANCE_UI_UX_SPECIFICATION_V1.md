# QFinance — UI/UX Specification V1

**Status:** 🔵 DRAFT — created 2026-08-31 under founder-authorized autonomous execution (`work_memory.md` §28A/§30).
**Depends on:** `docs/PRD/QFINANCE_MVP_PRD_V1.md` (🔒 LOCKED), `docs/architecture/QFINANCE_ARCHITECTURE_V1.md` (🔒 APPROVED), `docs/database/QFINANCE_DATABASE_SCHEMA_V1.md` (🔒 APPROVED), `docs/api/QFINANCE_API_SPECIFICATION_V1.md` (🔒 LOCKED)
**Visual design source:** `qfinance-uiux-v1-final.html` (founder-supplied cream/brass mockup) — verified against the locked PRD before adoption: no live market/price data, ₹799 INR-only pricing, additive OD-05 RBAC, correct 9-section Q-RESEARCH editor, no avatar upload, no Phase 2/3 features. Adopted for visual tokens/component styling; this document supplies screen-by-screen API traceability, interaction states, IA, and compliance UX the mockup doesn't cover.
**Project root:** `/home/prd/Projects/QFinance`
**Introduces no new product/architecture/API scope.** Every screen below maps to an endpoint in the locked API Specification V1 and a requirement ID in the locked PRD.

---

## 1. Design System (from the mockup, referenced not redefined)

Cream/brass "ledger" theme. Fraunces (display), Inter (body), JetBrains Mono (data — counts, timestamps, codes; **never** live prices, per BOUND-001/NFR-005). Colour tokens, component gallery (buttons, badges, ledger rows), and the three-state access pattern (full colour = allowed, brass badge = gated, hatch-fill = denied) are defined in the mockup file and adopted as-is. No new tokens introduced here.

## 2. Information Architecture

```
Public (unauthenticated)
├── / (landing)
├── /pricing
├── /research/[slug]  (preview only)
└── /login, /register, /password-reset

Authenticated shell (sidebar nav)
├── /dashboard
├── /research            (library, browse/search)
├── /research/editor/[id] (Q-RESEARCH workspace)
├── /research/[slug]     (full reader, tier-gated)
├── /community/[channel]
├── /watchlist
├── /membership           (plan, invoices, cancel)
├── /profile
├── /notifications
└── Staff (role-gated)
    ├── /admin/moderation
    ├── /admin/research-review
    └── /admin/* (users, memberships, payments, companies, audit, metrics, settings)
```

Route guard: every authenticated route checks the session server-side (Next.js middleware) before render (Architecture §4.3); role-gated nav items are hidden client-side for UX only — the API (RBAC-001) is the actual enforcement boundary on every request, never the UI.

## 3. Screen Specifications

Each screen lists: Route · API calls · RBAC · States · Compliance notes.

### 3.1 Landing / Pricing (Public)
- Route `/`, `/pricing`. API: `GET /membership/plans`.
- States: static content + live plan pricing (so ₹799 is never hardcoded in frontend copy, per OD-22).
- No research previews with live data; no signal/tip-channel-style copy (positioning per PRD §1).

### 3.2 Registration / Login / Verification / Reset
- APIs: `1.1–1.6`.
- States: form validation (inline, password ≥12 chars per OD-03), loading, `EMAIL_ALREADY_REGISTERED`/`USERNAME_TAKEN`/`INVALID_CREDENTIALS`/`TOO_MANY_ATTEMPTS` error states, success/redirect.
- **CMPL-005 risk disclosure:** shown as a persistent, non-dismissible-on-first-view panel at the end of registration, before the account is usable. Calls `POST /users/me/acknowledge-risk-disclosure {context:"signup"}` (§4.5.2). Registration is not considered complete until this call succeeds.

### 3.3 Dashboard
- Route `/dashboard`. APIs: `GET /users/me`, `GET /watchlist` (top N), `GET /research/library` (recent/highlighted).
- Per mockup: research-activity + community-signal widgets only. **No market index/price widget — confirmed absent, per WL-002/NFR-005/BOUND-001.**
- FREE members see a locked "Core Research Highlights" panel (brass-badge gated state) driving `/pricing`.
- States: loading skeleton, empty (new member, no activity yet), populated.

### 3.4 Research Library / Search
- Route `/research`. APIs: `GET /research/library`, `GET /research/search`.
- Per-item card reads `access_tier` (API §7.4.1/7.4.2): `free_example` → full card for every caller; `core` → paywalled preview card for FREE callers (badge "Unlock Full Core Report"), full card for CORE/MEMBER.
- States: loading, empty (no results), paginated list, filter (company/industry) applied.

### 3.5 Research Reader (Paywall Preview)
- Route `/research/[slug]`. API: `GET /research/{id}` (§7.1.2).
- Exec summary always fully readable for FREE members before the gate (per mockup FIX 2/OD-22 pricing). `access_tier='free_example'` items render in full for FREE members — the gate component does not render at all for those items.
- CTA reads live `price_paise` from `GET /membership/plans`, never a hardcoded "₹799" string, so a future `PATCH /admin/settings/pricing` change (§10.8) is reflected without a frontend deploy.

### 3.6 Research Workspace / Q-RESEARCH Editor
- Route `/research/editor/[id]`. APIs: `POST /research` (create), `PATCH /research/{id}` (§7.1.3, per-section autosave, debounced), `POST /research/{id}/sources` / `DELETE .../sources/{id}`, `POST /research/{id}/publish` (§7.3.1), `PATCH /research/{id}` on published items (§7.1.4, same validation gate).
- Nine-section navigator (Q-R-E-S-E-A-R-C-H) with per-stage completion dot, matching the mockup exactly. `conflict_disclosed`/`position_disclosed` render as explicit selected chips (No is a first-class selected state, never a blank field — SRC-004).
- **Publish button behavior:** disabled-with-tooltip is *not* used (would hide the checklist); instead, clicking Publish with missing fields calls `§7.3.1`, receives `422 RESEARCH_PUBLISH_MISSING_FIELDS` with a `fields` map, and the UI renders every missing item as a checklist inline (not just the first) — API is designed to return the complete list in one round trip specifically for this UX.
- **Editing a published item:** requires a non-empty `change_note` field before the same Publish-equivalent action is enabled; on `422` the currently-published version is untouched (per AD-17) and the UI shows the same missing-fields checklist without discarding the author's in-progress edits.
- States: draft autosave ("saved 2s ago" indicator, per mockup), publish validation error (checklist), publish success, version history view (`GET /research/{id}/versions`), read-only historical version banner ("You are viewing version 3 of 5").

### 3.7 Company Pages / Watchlist
- Routes `/companies/[id]`, `/watchlist`. APIs: `GET /companies/{id}`, `POST/DELETE /companies` (create, MEMBER-gated with `POSSIBLE_DUPLICATE_COMPANY` confirm-dialog flow per §6.3), `GET/POST/DELETE /watchlist*`.
- **No price/ticker column anywhere — confirmed absent, matching mockup FIX 1 and WL-002 exactly.** Company name + research/discussion counts only.
- FREE members see `403`-equivalent "Core-only" state on `/watchlist` (WL-001) with upgrade CTA, not a broken page.

### 3.8 Community (Channels, Posts, Comments)
- Route `/community/[channel]`. APIs: `4.1–4.4`.
- 7 fixed channel tabs; Announcements is read-only-post for non-staff (post composer hidden for non-MODERATOR/ADMIN, enforced server-side regardless of UI state per §4.1.2).
- **First-post gate (CMPL-004):** first attempt to post/comment triggers a Member Charter acknowledgment modal (`POST /users/me/acknowledge-charter`, §4.5.1) if not already acknowledged; the compose action is retried automatically after acknowledgment succeeds, not silently dropped.
- Reporting: every post/comment has a "Report" action → `POST /moderation/reports` with a reason field.
- States: channel feed loading/empty/populated, `CHARTER_NOT_ACKNOWLEDGED` (403) → acknowledgment modal, own-content edit/delete affordances only, "edited" indicator, soft-removed content shows a neutral "This content was removed" placeholder to non-authors (never a blank gap that reads as a bug).

### 3.9 Membership / Billing
- Route `/membership`. APIs: `3.1.1–3.4.1`.
- Checkout button calls `POST /membership/checkout`; if `CORE_BILLING_ENABLED` is off (pre-OD-01, per §3.2.1), the UI shows a clear "Core billing isn't live yet" state instead of a broken/silent failure — this is the frontend's read of the `503 BILLING_NOT_YET_AVAILABLE` response, not a frontend-side flag duplicating the backend's.
- **CMPL-005 risk disclosure, second occasion:** shown again at checkout initiation (`context:"first_payment"`) before the Razorpay handoff, per PRD's "at signup and at first payment" requirement — this is a second, independent acknowledgment call, not a re-display of the signup one.
- Cancellation flow: confirmation dialog stating access continues until `current_period_end` (no partial refund, per OD-07 placeholder wording — UI copy flagged as legal-review-pending, matching PRD §12).
- Invoice list (`GET /membership/invoices`) — no PDF download in MVP (not in API spec); list view only.
- States: FREE view (upgrade CTA), CORE-active view, past_due/grace-period banner ("payment failed, retry by [date]"), canceled-but-still-active-until-period-end banner.

### 3.10 Notifications
- Route `/notifications`. APIs: `9.1–9.3`. Standard list/unread-count/mark-read states.

### 3.11 Profile / Member Directory
- Routes `/profile`, `/directory` (Core-gated, §2.4). APIs: `2.1–2.4`.
- Profile fields are text-only (name, username, bio, experience level, interests) — **no avatar upload UI exists anywhere in this spec**, per OD-21/PROF-006.

### 3.12 Admin — Moderation Queue
- Route `/admin/moderation`. APIs: `5.1–5.6`.
- Matches mockup exactly: flagged-content evidence block, action buttons (Dismiss/Restrict/Remove/Ban), rule-note banner stating matches are signal-only (MOD-003/CMPL-003) — this banner text is fixed copy, not conditional, so it's always visible to reinforce the compliance boundary to every moderator on every view.
- MODERATOR sees `/admin/moderation` only; ADMIN/SUPER_ADMIN see it plus the rest of `/admin/*`.

### 3.13 Admin — Research Review Queue
- Route `/admin/research-review` (REVIEWER-gated, distinct from moderation per PRD §30 — REVIEWER cannot moderate, MODERATOR cannot review-approve research). No dedicated endpoint beyond `research`/`community` reads with elevated visibility (`?include_moderated=true`, API §10 closing note) — UI reuses the Research Library list component with REVIEWER-specific filters (drafts pending review).

### 3.14 Admin — Users / Memberships / Payments / Companies / Audit / Metrics / Settings
- Routes `/admin/users`, `/admin/memberships`, `/admin/payments`, `/admin/companies`, `/admin/audit-log`, `/admin/metrics`, `/admin/settings`. APIs: `10.1–10.9`.
- `10.3` role-grant editor: multi-select of the 6 additive roles (checkboxes, not radio buttons — reinforces OD-05 additivity in the UI itself, not just the backend). Escalating to/from ADMIN/SUPER_ADMIN requires the acting user to already be SUPER_ADMIN (§10.3) — the UI disables those specific checkboxes for an ADMIN-level actor rather than submitting and failing.
- `10.8`/`10.9` (pricing change, billing-flag toggle) require step-up re-authentication (SEC-007): a password-confirmation modal appears before submission, consistent across both.
- `admin/audit-log`: MODERATOR sees only own actions (server-enforced, §10.7) — UI does not attempt to show a "restricted view" notice beyond the naturally shorter result set, since the API doesn't distinguish 403-vs-filtered here.
- **No "Research Reviewed" metric tile anywhere on `/admin/metrics`** — confirmed absent, per OD-15/ADMIN-002.
- Metrics dashboard reads `10.1` directly; no client-side computation of MRR/churn/etc. — the API is authoritative for every number shown.

## 4. Cross-Cutting States (STATE-001–003)

- **Loading:** skeleton components matching each screen's layout, never a blank white flash.
- **Empty:** every list screen has a distinct empty-state illustration/copy (new member, no drafts yet; no watchlist items yet; no search results) — never a bare "No data."
- **Error:** every API error's `code` (§0.3) maps to a specific UI treatment where a named mapping exists above (e.g., `CHARTER_NOT_ACKNOWLEDGED`, `RESEARCH_PUBLISH_MISSING_FIELDS`, `BILLING_NOT_YET_AVAILABLE`, `POSSIBLE_DUPLICATE_COMPANY`); all other errors fall back to a generic toast showing `error.message` (never raw exception text, STATE-003).

## 5. Accessibility (A11Y-001–003)

Keyboard navigability for the Q-RESEARCH editor's step navigator and all modals (Charter/risk-disclosure/step-up-auth); colour is never the sole signal for gated/denied state (badge text + icon accompany the hatch-fill/brass patterns); form fields carry associated `<label>`s (mockup's `.field label` pattern) and error text is programmatically associated via `aria-describedby`. No further A11Y architecture exists at the Architecture-doc level (noted there as deferred to this spec) — this section is that deferral's resolution at a specification level; exact implementation (audit tooling, WCAG target level) is a frontend-build-phase detail, not re-specified further here.

## 6. Responsive Behavior

Sidebar collapses to a bottom/hamburger nav below the mockup's existing `900px` breakpoints (already defined in the mockup's own CSS `@media(max-width:900px)` rules for `app-shell`/`widget-grid`/`qres-editor`/`grid2`/`grid3`) — no new breakpoint scheme introduced; this spec adopts the mockup's existing responsive rules as authoritative.

## 7. RBAC UX Summary

Matches the mockup's additive RBAC table (§9 of the mockup) exactly — reproduced here only as a pointer, not restated, to avoid two documents drifting out of sync. Any future RBAC UI change must update both the mockup/component library and this document's §3.12–3.14 traceability together.

## 8. Explicitly Out of Scope (confirmed, not silently reintroduced)

Matches PRD §46–48 and the mockup's own §10 "Confirmed Out of MVP Scope" table: no Research Guilds UI, no live market/price UI anywhere, no member-facing AI UI, no Certification Track UI, no avatar upload UI, no "Research Reviewed" metric tile. Verified against this document's own §3 above — no screen listed reintroduces any of these.

## 9. Screen → API → PRD Traceability (summary)

| Screen | Primary API calls | PRD req IDs |
|---|---|---|
| Landing/Pricing | 3.1.1 | MEM-001/002, OD-22 |
| Auth (register/login/verify/reset) | 1.1–1.6 | AUTH-001–009 |
| Dashboard | 2.1, 8.1, 7.4.1 | WL-002, NFR-005 |
| Research Library/Search | 7.4.1, 7.4.2 | LIB-001–005, SEARCH-001–003 |
| Research Reader | 7.1.2 | LIB-003, MEM-004, CMPL-002 |
| Q-RESEARCH Editor | 7.1.1–7.1.4, 7.2.*, 7.3.* | RES-001–006, QRES-001–003, VER-001–004, SRC-001–004 |
| Company/Watchlist | 6.*, 8.* | CO-001–004, WL-001–003, OD-23 |
| Community | 4.1–4.5 | COMM-001–008, PCR-001–003, CMPL-004/005 |
| Membership/Billing | 3.1–3.4 | MEM-001–007, PAY-001–006, OD-06/07/10/16/22 |
| Notifications | 9.1–9.3 | NOTIF-001–003 |
| Profile/Directory | 2.1–2.4 | PROF-001–006, OD-21 |
| Admin — Moderation | 5.1–5.6 | MOD-001–005, CMPL-002/003 |
| Admin — Research Review | 7.4.1 (`?include_moderated`) | REVIEWER capability, PRD §30 |
| Admin — Users/Memberships/Payments/Companies/Audit/Metrics/Settings | 10.1–10.9 | ADMIN-001–007, OD-15/OD-19 |

## 10. Genuine Implementation Dependencies (flagged, not silently resolved)

1. **Newsletter signup** (mentioned as a FREE-tier feature in the PRD's tier table) has no corresponding API endpoint anywhere in API Specification V1. This spec does not design a UI for it. Needs either an endpoint added to a future API amendment, or an explicit founder decision that it's handled outside the product (e.g., a third-party embed) before frontend work reaches the landing page.
2. **Email-notification preference toggle:** NOTIF-003 (SHOULD-HAVE, email delivery) has no corresponding preference-management endpoint in the API spec (only in-app notification read/mark-read, §9). If a per-user opt-out UI is wanted, an endpoint must be added first.
3. **Research version-history read endpoint** (§7.3.2/7.3.3) is assumed sufficient for the "historical version" banner described in §3.6 above — this was re-confirmed present against the actual (now-locked) API Specification V1 content during this session, not assumed from a prior summary.

## 11. Verification Performed Before Finalizing This Document

Checked directly against the now-LOCKED API Specification V1 (not a summary): every screen above cites real, existing endpoints and real requirement IDs; no screen invents an endpoint. Checked against the mockup file directly: the four corrections it documents (no live market data, ₹799 INR-only, additive RBAC, 9-section editor) are consistent with this spec's own descriptions in §3.3/3.5/3.6/3.7/3.14. Checked against PRD §46–48 (§8 above). No Phase 2/3 feature UI is specified anywhere in this document.

---

*QFinance UI/UX Specification V1 — 🔵 DRAFT, created 2026-08-31. Not yet founder-reviewed (optional under the current execution authorization, but welcome). No frontend code exists yet — this is specification only.*
