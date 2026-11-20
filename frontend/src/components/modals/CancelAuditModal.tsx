import React, { useMemo, useState } from "react";
import { Ban, TriangleAlert } from "lucide-react";
import { useDispatch, useSelector } from "react-redux";
import { Modal } from "../ui/modal";
import { AppDispatch, RootState } from "../../redux/store";
import { Audit, AuditCancelRequest } from "../../redux/audit/audit-types";
import { cancelAudit } from "../../redux/audit/audit-slice";
import toast from "react-hot-toast";

interface CancelAuditModalProps {
  audit: Audit;
  onClose: () => void;
  onSaved?: (audit: Audit) => void;
}

const REASON_OPTIONS = [
  { value: 1, label: "Auditee did not respond" },
  { value: 2, label: "Auditee is on holiday" },
  { value: 3, label: "Auditor is on leave" },
  { value: 4, label: "Auditee is not available" },
  { value: 99, label: "Other" },
];
const CancelAuditModal: React.FC<CancelAuditModalProps> = ({
  audit,
  onClose,
  onSaved,
}) => {
  const dispatch = useDispatch<AppDispatch>();
  const { user } = useSelector((state: RootState) => state.auth);
  const [reasonCode, setReasonCode] = useState<number>(1);
  const [reasonNote, setReasonNote] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const selectedLabel = useMemo(
    () => REASON_OPTIONS.find((r) => r.value === reasonCode)?.label ?? "Reason",
    [reasonCode],
  );

  const handleSubmit = async () => {
    setError("");
    if (!user?.email) {
      setError("User email is missing.");
      return;
    }

    if (reasonCode === 99 && !reasonNote.trim()) {
      setError("Please provide a note when selecting 'Autre'.");
      return;
    }

    try {
      setLoading(true);
      const payload: AuditCancelRequest = {
        reason_code: reasonCode,
        reason: reasonNote.trim() || undefined,
        email: user.email,
      };

      const updatedAudit = await dispatch(
        cancelAudit({ auditId: audit.id, data: payload }),
      ).unwrap();
      onSaved?.(updatedAudit);
      toast.success("Audit cancelled. You can reschedule later from the same table.");
      onClose();
    } catch (err: unknown) {
      const msg =
        (err as { detail?: string })?.detail ||
        (err as Error)?.message ||
        "Failed to cancel audit.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} className="max-w-[680px] p-0">
      <div className="rounded-3xl border border-[#064273]/15 bg-white dark:border-[#064273]/40 dark:bg-gray-900">
        <div className="rounded-t-3xl border-b border-[#064273]/15 bg-gradient-to-r from-[#064273] via-[#0a4f7f] to-[#0f628f] px-6 py-5 dark:border-[#064273]/40">
          <h2 className="text-xl font-semibold text-white">Cancel Audit</h2>
          <p className="mt-1 text-sm text-blue-100/90">
            Traceability is mandatory. Select a structured reason and optional note.
          </p>
        </div>

        <div className="space-y-5 px-6 py-5">
          <div className="rounded-xl border border-[#F68C1F]/25 bg-[#fff6ee] p-3 text-sm text-[#8a4e00] dark:border-[#F68C1F]/35 dark:bg-[#F68C1F]/10 dark:text-orange-200">
            <p>
              <strong>Audit:</strong> {audit.audit_number}
            </p>
            <p className="mt-1">
              This action will set status to <strong>cancelled</strong>, notify participants,
              and keep history for future analysis and rescheduling.
            </p>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Cancellation reason
            </label>
            <select
              value={reasonCode}
              onChange={(e) => setReasonCode(Number(e.target.value))}
              className="h-11 w-full rounded-lg border border-[#064273]/20 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-[#064273] focus:ring-2 focus:ring-[#064273]/20 dark:border-[#064273]/40 dark:bg-white/[0.04] dark:text-slate-200"
            >
              {REASON_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.value} - {option.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Selected: {selectedLabel}
            </p>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Note (optional)
            </label>
            <textarea
              rows={3}
              value={reasonNote}
              onChange={(e) => setReasonNote(e.target.value)}
              className="w-full rounded-lg border border-[#064273]/20 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition focus:border-[#F68C1F]/70 focus:ring-2 focus:ring-[#F68C1F]/20 dark:border-[#064273]/40 dark:bg-white/[0.04] dark:text-slate-200"
              placeholder="Add context that quality managers can analyze later..."
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800/40 dark:bg-red-900/20 dark:text-red-300">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              onClick={onClose}
              className="rounded-lg border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              Keep audit
            </button>

            <button
              onClick={handleSubmit}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Ban className="h-4 w-4" />
              {loading ? "Cancelling..." : "Cancel audit"}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
};

export default CancelAuditModal;
