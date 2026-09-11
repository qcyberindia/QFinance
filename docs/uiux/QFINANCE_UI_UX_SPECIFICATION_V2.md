# QFinance UI/UX Specification V2

**Status:** 🟢 ACTIVE — new navigation/screen set for the V2 product. Reuses the existing cream/brass "ledger" design system (tokens, type scale, component patterns) documented in V1's `qfinance-uiux-v1-final.html` — this document specifies WHAT screens/navigation exist, not new visual tokens.

## 1. Primary Navigation (replaces V1's app-shell nav)
```
Community (home/default)
Portfolio
Journal
My Research
Saved
Profile
Credits / Premium
```
Staff-only items (Moderation, Review Queue) remain in a "Staff" nav group exactly as V1 designed.

## 2. Screens (P0, build these; everything else is P1/P2 per the delivery priority)

1. **Community / Home** — feed of posts across types, `post_type` shown as a small badge (Thesis/Question/Discussion/General); thesis posts additionally show average rating + count inline.
2. **Portfolio** — connect-Zerodha CTA if not connected; holdings table (name, qty, avg price, current value/P&L as returned by Kite) if connected. No editing, no order placement — explicitly read-only, and the screen should visually communicate that (no buy/sell buttons anywhere).
3. **Journal** — private list + entry editor (type selector, optional company tag, free text). No "share" affordance anywhere on this screen — it must not be one click away from Community.
4. **My Research** — replaces V1's public-library screen; this is now a private workspace list (draft/published theses the member owns) with a clear "Publish to Community" action on published items.
5. **Research Editor** — reuse V1's nine-section Q-RESEARCH editor as-is (it already works and isn't part of what changed).
6. **Community Post/Thread** — post detail with nested comment threading (indent-per-depth, matching the "Reddit-like" reference point), rating widget shown only when `post_type='thesis'`.
7. **Saved** — reuse V1's ledger-row list pattern for saved posts.
8. **Profile** — public view: identity block, published posts/theses list, contribution summary card (shows 0s pre-Phase-5, not hidden — so the mechanic is visible/anticipated even before credits exist).
9. **Credits/Premium** (P1) — ledger table (reason, amount, date) + current Premium price vs. credit-adjusted effective price.
10. **Auth** — unchanged from the existing minimal scaffold.

## 3. Explicit Non-Goals for V2 UI
- No redesign of the visual system itself (tokens/type/color stay as V1 defined them).
- No dashboard/analytics screen beyond what's listed above.
- No mobile-specific layout work called out separately (responsive behavior follows the same rules V1's screens already used).
