// components/audit/DraftStatusBadge.tsx
// ─────────────────────────────────────────────────────────────────
//  Small, unobtrusive badge that shows draft save status.
//  Place it anywhere in the audit form header.
// ─────────────────────────────────────────────────────────────────

import { Cloud, CloudOff, Loader2, CheckCheck } from "lucide-react";

interface DraftStatusBadgeProps {
  saving: boolean;
  lastSavedAt: Date | null;
  /** Show a warning that fields have unsaved changes */
  isDirty?: boolean;
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function DraftStatusBadge({
  saving,
  lastSavedAt,
  isDirty = false,
}: DraftStatusBadgeProps) {
  if (saving) {
    return (
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-50 border border-blue-200 text-xs font-medium text-blue-700">
        <Loader2 size={12} className="animate-spin" />
        Saving draft…
      </div>
    );
  }

  if (isDirty && !lastSavedAt) {
    return (
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200 text-xs font-medium text-amber-700">
        <CloudOff size={12} />
        Unsaved
      </div>
    );
  }

  if (lastSavedAt) {
    return (
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-xs font-medium text-emerald-700">
        {isDirty ? (
          <>
            <Cloud size={12} />
            Draft (unsaved changes)
          </>
        ) : (
          <>
            <CheckCheck size={12} />
            Draft saved {formatTime(lastSavedAt)}
          </>
        )}
      </div>
    );
  }

  return null;
}
