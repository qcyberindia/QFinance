"""
Top-level /api/v1 router aggregation (API-001).
`auth`, `companies`, `research`, `membership`, `billing`, `users` (acknowledgment
endpoints only), `community` are wired in this pass — `moderation`, `watchlist`,
`notifications`, `admin` are specified in API Specification V1 but NOT YET
IMPLEMENTED as code. Do not infer their existence from this file; see
work_memory.md for the real status.
WRITTEN, NOT EXECUTED.
"""
from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.billing.router import router as billing_router
from app.modules.community.router import research_discussion_router
from app.modules.community.router import router as community_router
from app.modules.companies.router import router as companies_router
from app.modules.membership.router import router as membership_router
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

# NOT YET WIRED (modules not yet implemented in code):
# api_router.include_router(moderation_router)
# api_router.include_router(watchlist_router)
# api_router.include_router(notifications_router)
# api_router.include_router(admin_router)
