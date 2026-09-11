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
