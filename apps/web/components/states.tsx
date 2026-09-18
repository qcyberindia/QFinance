import type { ReactNode } from "react";

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="qf-card p-8 text-center">
      <div className="font-display text-lg mb-2">{title}</div>
      <p className="text-sm text-ink-soft">{body}</p>
    </div>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return <div className="text-sm text-ink-soft py-8 text-center">{label}</div>;
}

export function FeedSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading feed" className="animate-pulse">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="py-4 border-b flex gap-3" style={{ borderColor: "var(--line)" }}>
          <div className="rounded-full bg-black/10" style={{ width: 36, height: 36, flexShrink: 0 }} />
          <div className="flex-1 space-y-2">
            <div className="h-3 w-1/3 rounded bg-black/10" />
            <div className="h-3 w-full rounded bg-black/10" />
            <div className="h-3 w-2/3 rounded bg-black/10" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="qf-card p-6 text-center" style={{ borderColor: "var(--down, #9C4B3F)" }}>
      <p className="text-sm mb-3" style={{ color: "#9C4B3F" }}>{message}</p>
      {onRetry && (
        <button className="qf-btn-ghost" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function NotAvailableYet({ feature }: { feature: string }) {
  return (
    <div className="qf-card p-6 text-center" style={{ background: "var(--cream-1)" }}>
      <p className="text-sm text-ink-soft">
        <strong>{feature}</strong> isn&apos;t available in this build yet. This screen is wired and ready — it
        will populate once the corresponding API is live.
      </p>
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`qf-card p-5 ${className}`}>{children}</div>;
}
