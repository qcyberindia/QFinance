/**
 * Centralized API client for the QFinance backend.
 *
 * SECURITY: the session token lives only in the backend's HttpOnly `qf_session`
 * cookie — this file never reads, stores, or forwards it manually. The browser
 * attaches it automatically via `credentials: "include"`. The CSRF token,
 * by contrast, is intentionally NOT HttpOnly (per the backend's own design —
 * see core/deps.py's `require_csrf`), so it's readable here to attach as the
 * `X-CSRF-Token` header on every mutating request, matching the backend's
 * double-submit-cookie CSRF check exactly.
 */

const API_BASE = "/api/v1"; // same-origin — see next.config.js's rewrite to the real backend

export class ApiError extends Error {
  code: string;
  status: number;
  fields?: Record<string, string>;

  constructor(status: number, code: string, message: string, fields?: Record<string, string>) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

const MUTATING_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers);

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (MUTATING_METHODS.has(method)) {
    const csrf = readCsrfCookie();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, method, headers, credentials: "include" });
  } catch (networkErr) {
    throw new ApiError(0, "NETWORK_ERROR", "Could not reach the Qfinera server. Check your connection.");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await response.json().catch(() => null) : null;

  if (!response.ok) {
    const errorBody = body?.error;
    throw new ApiError(
      response.status,
      errorBody?.code || "UNKNOWN_ERROR",
      errorBody?.message || `Request failed with status ${response.status}.`,
      errorBody?.fields,
    );
  }

  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
