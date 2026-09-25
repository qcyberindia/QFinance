"use client";

import { useEffect, useRef } from "react";

export function ConfirmDialog({
  message,
  onCancel,
  onConfirm,
  confirmLabel = "Delete",
}: {
  message: string;
  onCancel: () => void;
  onConfirm: () => void;
  /** Defaults to "Delete" to preserve every existing caller's behavior
   * exactly — pass an explicit label (e.g. "Disconnect") for actions that
   * aren't literally a delete. */
  confirmLabel?: string;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(43,38,33,.45)" }}
      role="alertdialog"
      aria-modal="true"
      aria-label={message}
      onClick={onCancel}
    >
      <div className="qf-card w-full max-w-sm p-5" onClick={(e) => e.stopPropagation()}>
        <p className="text-sm mb-4">{message}</p>
        <div className="flex gap-3 justify-end">
          <button ref={cancelRef} className="qf-btn-ghost text-sm" onClick={onCancel}>
            Cancel
          </button>
          <button className="qf-btn-primary text-sm" style={{ background: "#9C4B3F" }} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
