"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/session";

/**
 * `useSearchParams()` requires the component that calls it to be rendered
 * inside a <Suspense> boundary in the Next.js 14 App Router — Next needs to
 * bail out of static generation for exactly this subtree (the search params
 * aren't known at build time), and without the boundary the production
 * build fails with "useSearchParams() should be wrapped in a suspense
 * boundary". Splitting the actual form into its own component and wrapping
 * ONLY that component (see the default-exported `LoginPage` below) keeps
 * static optimization for the rest of the page/layout intact — no global
 * `dynamic = 'force-dynamic'`, no disabling of static optimization anywhere
 * else in the app. All client-side logic below is unchanged from before this
 * fix; only the component boundary/export shape changed.
 */
function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refresh } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.post("/auth/login", { email, password });
      await refresh();
      router.push(searchParams.get("next") || "/community");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="qf-card w-full max-w-sm p-8">
        <div className="font-display text-2xl mb-1">
          Q<em className="not-italic" style={{ color: "var(--brass)" }}>Finance</em>
        </div>
        <p className="text-sm text-ink-soft mb-6">Sign in to your workspace.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="qf-label" htmlFor="email">Email</label>
            <input
              id="email" type="email" required className="qf-input"
              value={email} onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="qf-label" htmlFor="password">Password</label>
            <input
              id="password" type="password" required className="qf-input"
              value={password} onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && <p className="text-sm" style={{ color: "#9C4B3F" }}>{error}</p>}
          <button type="submit" disabled={submitting} className="qf-btn-primary w-full">
            {submitting ? "Signing in…" : "Sign In"}
          </button>
        </form>

        <p className="text-sm text-ink-soft mt-6">
          New here?{" "}
          <Link href="/register" className="font-semibold" style={{ color: "var(--brass)" }}>
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
