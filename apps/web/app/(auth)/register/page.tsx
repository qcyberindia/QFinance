"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ name: "", username: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  function update(field: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [field]: e.target.value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setSubmitting(true);
    try {
      await api.post("/auth/register", form);
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        if (err.fields) setFieldErrors(err.fields);
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="qf-card w-full max-w-sm p-8 text-center">
          <div className="font-display text-xl mb-2">Check your email</div>
          <p className="text-sm text-ink-soft mb-6">
            We&apos;ve sent a verification link. Once verified, you can{" "}
            <Link href="/login" className="font-semibold" style={{ color: "var(--brass)" }}>sign in</Link>.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="qf-card w-full max-w-sm p-8">
        <div className="font-display text-2xl mb-1">
          Qfinera
        </div>
        <p className="text-sm text-ink-soft mb-6">Create your account.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="qf-label" htmlFor="name">Full name</label>
            <input id="name" required className="qf-input" value={form.name} onChange={update("name")} />
          </div>
          <div>
            <label className="qf-label" htmlFor="username">Username</label>
            <input id="username" required className="qf-input" value={form.username} onChange={update("username")} />
            {fieldErrors.username && <p className="text-xs mt-1" style={{ color: "#9C4B3F" }}>{fieldErrors.username}</p>}
          </div>
          <div>
            <label className="qf-label" htmlFor="email">Email</label>
            <input id="email" type="email" required className="qf-input" value={form.email} onChange={update("email")} />
            {fieldErrors.email && <p className="text-xs mt-1" style={{ color: "#9C4B3F" }}>{fieldErrors.email}</p>}
          </div>
          <div>
            <label className="qf-label" htmlFor="password">Password</label>
            <input id="password" type="password" required className="qf-input" value={form.password} onChange={update("password")} />
            {fieldErrors.password && <p className="text-xs mt-1" style={{ color: "#9C4B3F" }}>{fieldErrors.password}</p>}
          </div>
          {error && <p className="text-sm" style={{ color: "#9C4B3F" }}>{error}</p>}
          <button type="submit" disabled={submitting} className="qf-btn-primary w-full">
            {submitting ? "Creating account…" : "Create Account"}
          </button>
        </form>

        <p className="text-sm text-ink-soft mt-6">
          Already have an account?{" "}
          <Link href="/login" className="font-semibold" style={{ color: "var(--brass)" }}>Sign in</Link>
        </p>
      </div>
    </div>
  );
}
