"use client";

import { Card, NotAvailableYet } from "@/components/states";

export default function CreditsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-2xl">Credits &amp; Premium</h1>
        <p className="text-sm text-ink-soft">
          Community contribution earns credits toward your next Premium period.
        </p>
      </div>

      <Card>
        <div className="text-xs text-ink-soft uppercase tracking-wide">Current balance</div>
        <div className="font-display text-3xl mt-1">₹0</div>
      </Card>

      {/* GENUINE BACKEND GAP: contributions/credit_ledger (Phase 5/P1) has not
          been built yet — see Architecture V2 §7 and work_memory.md. No
          billing changes are made from this screen regardless. */}
      <NotAvailableYet feature="Contribution history and credit ledger" />
    </div>
  );
}
