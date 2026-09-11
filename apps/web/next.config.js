/** @type {import('next').NextConfig} */
const NEXT_PUBLIC_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Proxies /api/v1/* to the FastAPI backend during `next dev`/`next start`
    // so the browser only ever talks to one origin — this is what lets the
    // backend's HttpOnly qf_session cookie work without CORS/SameSite
    // complications. In production this proxy is typically replaced by a
    // reverse proxy (nginx/Vercel rewrites) doing the same job.
    return [
      { source: "/api/v1/:path*", destination: `${NEXT_PUBLIC_API_BASE_URL}/api/v1/:path*` },
    ];
  },
};

module.exports = nextConfig;
