import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register"];

/**
 * First-line-of-defense only: checks for the mere PRESENCE of the qf_session
 * cookie (it's HttpOnly, so this middleware cannot read or validate its
 * contents — only whether it exists at all). The authoritative check is the
 * client-side `useSession()` hook's call to GET /auth/session, which will
 * redirect to /login on a real 401 (e.g. an expired/invalidated session that
 * still has a stale cookie present). This middleware exists purely to avoid
 * flashing protected content for the common case of "no cookie at all."
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  const hasSessionCookie = request.cookies.has("qf_session");

  if (!isPublic && !hasSessionCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
