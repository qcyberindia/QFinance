"""
Top-level /api/v1 router aggregation (API-001).
`auth`, `companies`, `research`, `membership`, `billing`, `users` (acknowledgment
endpoints only), `community`, `moderation`, `journal`, `portfolio`, `ratings`
(V2 P0) are wired in this pass. `credits` (V2 P0/P1) has no module directory
yet — genuinely not started, confirmed by directory listing, not just this
comment (this file previously claimed `ratings` was also unimplemented; it
was actually fully built and just never wired — fixed this pass, and this
comment kept in sync with the fix rather than left stale again).
`watchlist`, `notifications`, `admin` (V1) remain unimplemented from before
this restructure. Do not infer module existence from this file alone; see
work_memory.md for the real status.
WRITTEN, NOT EXECUTED.
"""
from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.billing.router import router as billing_router
from app.modules.community.router import research_discussion_router
from app.modules.community.router import router as community_router
from app.modules.companies.router import router as companies_router
from app.modules.journal.router import router as journal_router
from app.modules.membership.router import router as membership_router
from app.modules.moderation.router import router as moderation_router
from app.modules.portfolio.router import router as portfolio_router
from app.modules.ratings.router import router as ratings_router
from app.modules.research.router import router as research_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(companies_router)
api_router.include_router(research_router)
api_router.include_router(research_discussion_router)  # /research/{id}/discussion — mounts alongside research_router
api_router.include_router(membership_router)
api_router.include_router(billing_router)
api_router.include_router(community_router)
api_router.include_router(ratings_router)  # shares the /community prefix — same technique as research_discussion_router
api_router.include_router(moderation_router)
api_router.include_router(journal_router)
api_router.include_router(portfolio_router)

# NOT YET WIRED (modules not yet implemented in code — confirmed absent, not
# just unwired, by directory listing under app/modules/):
# api_router.include_router(credits_router)
# api_router.include_router(watchlist_router)
# api_router.include_router(notifications_router)
# api_router.include_router(admin_router)
