"""Regression test: MVP is 100% free — no MVP participation endpoint may
require the `MEMBER` role_grant (that dependency is reserved for ADMIN/
SUPER_ADMIN/MODERATOR staff gates only, per the explicit product rule this
test enforces).

FIX (this revision): the first version of this test inspected
`app.main.app.routes` directly, filtering with `hasattr(r, "path")`. On this
project's actual installed FastAPI/Starlette version, routes registered via
`include_router()` are NOT eagerly flattened into plain objects with a
`.path` attribute in `app.routes` — they remain wrapped (e.g. as an internal
`_IncludedRouter`), so that filter silently skipped every route under
`/api/v1/*`, and the test failed with "route not found" for a route that
in fact exists and works correctly (confirmed by the real pytest run: this
was the ONLY failure out of 90 tests, and the actual export.csv fix itself
was never in question). This is a bug in the test's own route-discovery
method, not in the fix it was meant to verify.

CORRECTED APPROACH: import each module's `router` object directly (the same
`APIRouter` instances `api/v1/router.py` includes) and search each router's
OWN `.routes` list using the router's un-prefixed relative path — this
sidesteps the top-level app's route-flattening behavior entirely, since each
module router's `.routes` are always plain `APIRoute` objects with real
`.dependant` graphs, never wrapped.

No database or Redis connection is required — this only imports routers and
inspects their static dependency graphs.
"""
from app.modules.community.router import router as community_router
from app.modules.research.router import router as research_router

# (router object, relative path AS REGISTERED ON THAT ROUTER, method) — the
# relative path is what each module's own router.py actually uses in its
# @router.get/@router.post decorators, not the full /api/v1/... path.
MVP_PARTICIPATION_ROUTES = [
    (research_router, "/research/mine", "GET"),
    (community_router, "/community/channels/{channel}/posts", "POST"),
    (community_router, "/community/posts/{post_id}/comments", "POST"),
    (community_router, "/community/comments/{comment_id}/replies", "POST"),
    (community_router, "/community/bookmarks", "POST"),
    (community_router, "/community/{target_type}/{target_id}/reactions", "POST"),
]


def _find_route(router, path: str, method: str):
    for route in router.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route
    return None


def _route_depends_on_member_role(route) -> bool:
    """Inspects a route's resolved dependants for any dependency whose
    closure references the string "MEMBER" as a role check. `require_role`
    is a factory (`require_role("MEMBER")` returns a closure), so we inspect
    each dependency callable's closure cells for the literal role tuple."""
    for dependant in route.dependant.dependencies:
        call = dependant.call
        closure = getattr(call, "__closure__", None)
        if not closure:
            continue
        for cell in closure:
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if isinstance(value, tuple) and "MEMBER" in value:
                return True
    return False


def test_no_mvp_participation_route_requires_member_role():
    checked = 0
    for router, path, method in MVP_PARTICIPATION_ROUTES:
        route = _find_route(router, path, method)
        assert route is not None, (
            f"Route {method} {path} not found on router {router!r} — route table changed? "
            "(this checks the router's own relative path, not the full /api/v1/... path)"
        )
        assert not _route_depends_on_member_role(route), (
            f"{method} {path} still requires the MEMBER role — MVP must be 100% free, "
            "no Pro/Premium gate is allowed on this participation route."
        )
        checked += 1

    assert checked == len(MVP_PARTICIPATION_ROUTES)
