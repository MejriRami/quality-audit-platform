import React, { useState } from "react";
import { format } from "date-fns";
import { useDispatch, useSelector } from "react-redux";
import { CalendarClock, Clock3, TriangleAlert } from "lucide-react";
import { rescheduleAudit } from "../../redux/audit/audit-slice";
import { AppDispatch, RootState } from "../../redux/store";
import { Audit, AuditRescheduleRequest } from "../../redux/audit/audit-types";
import { Modal } from "../ui/modal";
import { DatePickerOnly } from "../calendar/DatePickerOnly";
import toast from "react-hot-toast";

interface RescheduleAuditModalProps {
  audit: Audit;
  onClose: () => void;
  onSaved?: (audit: Audit) => void;
}

const formatSafeDate = (value?: string | null) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return format(date, "PPpp");
};

const toInputDate = (value?: string | null) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return format(date, "yyyy-MM-dd");
};

const toPickerDate = (value?: string | null) => {
  const iso = toInputDate(value);
  return iso ? new Date(`${iso}T12:00:00`) : null;
};

const toInputTime = (value?: string | null) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return format(date, "HH:mm");
};

const RescheduleAuditModal: React.FC<RescheduleAuditModalProps> = ({
  audit,
  onClose,
  onSaved,
}) => {
  const [newDate, setNewDate] = useState<Date | null>(
    toPickerDate(audit.planned_start_date),
  );
  const [newStartTime, setNewStartTime] = useState(
    toInputTime(audit.planned_start_date),
  );
  const [newEndTime, setNewEndTime] = useState(
    toInputTime(audit.planned_end_date),
  );
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showUnavailableConfirm, setShowUnavailableConfirm] = useState(false);
  const [confirmUnavailableMessage, setConfirmUnavailableMessage] = useState("");
  const [pendingPayload, setPendingPayload] = useState<AuditRescheduleRequest | null>(null);

  const dispatch = useDispatch<AppDispatch>();
  const { user } = useSelector((state: RootState) => state.auth);

  const isAuditeeUnavailableError = (msg: string) => {
    const lower = (msg || "").toLowerCase();
    return (
      (lower.includes("auditee") && lower.includes("not available")) ||
      (lower.includes("auditee") && lower.includes("approved leave")) ||
      (lower.includes("auditor") && lower.includes("conflicting audit"))
    );
  };

  const handleSubmit = async () => {
    setError("");

    const selectedDate = newDate ? format(newDate, "yyyy-MM-dd") : "";

    if (!selectedDate || !newStartTime || !newEndTime) {
      setError("Date, start time, and end time are required.");
      return;
    }

    const newStart = `${selectedDate}T${newStartTime}`;
    const newEnd = `${selectedDate}T${newEndTime}`;

    if (new Date(newStart) >= new Date(newEnd)) {
      setError("Start time must be before end time.");
      return;
    }

    if (!reason.trim()) {
      setError("Reason is required.");
      return;
    }

    try {
      if (!user?.email) {
        throw new Error("User not found");
      }

      setLoading(true);

      const payload: AuditRescheduleRequest = {
        new_start_date: newStart,
        new_end_date: newEnd,
        reason: reason.trim(),
        email: user.email,
        allow_unavailable_auditee: false,
      };

      let updatedAudit: Audit;
      try {
        updatedAudit = await dispatch(
          rescheduleAudit({
            auditId: audit.id,
            data: payload,
          }),
        ).unwrap();
      } catch (firstErr: unknown) {
        const firstMsg =
          (firstErr as { response?: { data?: { detail?: string } } })?.response
            ?.data?.detail ||
          (firstErr as { detail?: string })?.detail ||
          (firstErr as Error)?.message ||
          (typeof firstErr === "string"
            ? firstErr
            : "Failed to reschedule audit.");

        if (!isAuditeeUnavailableError(firstMsg)) {
          throw firstErr;
        }

        setPendingPayload(payload);
        setConfirmUnavailableMessage(firstMsg);
        setShowUnavailableConfirm(true);
        setLoading(false);
        return;
      }

      onSaved?.(updatedAudit);
      toast.success("Audit rescheduled successfully!");
      onClose();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ||
        (err as { detail?: string })?.detail ||
        (err as Error)?.message ||
        (typeof err === "string" ? err : "Failed to reschedule audit.");

      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmRescheduleAnyway = async () => {
    if (!pendingPayload) return;
    try {
      setLoading(true);
      const updatedAudit = await dispatch(
        rescheduleAudit({
          auditId: audit.id,
          data: {
            ...pendingPayload,
            allow_unavailable_auditee: true,
          },
        }),
      ).unwrap();
      onSaved?.(updatedAudit);
      toast.success("Audit rescheduled successfully!");
      setShowUnavailableConfirm(false);
      setPendingPayload(null);
      onClose();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ||
        (err as { detail?: string })?.detail ||
        (err as Error)?.message ||
        (typeof err === "string" ? err : "Failed to reschedule audit.");
      setError(msg);
      setShowUnavailableConfirm(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
    <Modal isOpen={true} onClose={onClose} className="max-w-[700px] p-0">
      <div className="rounded-3xl border border-[#064273]/15 bg-white dark:border-[#064273]/40 dark:bg-gray-900">
        <div className="rounded-t-3xl border-b border-[#064273]/15 bg-gradient-to-r from-[#064273] via-[#0a4f7f] to-[#0f628f] px-6 py-5 dark:border-[#064273]/40">
          <div className="flex items-start justify-between gap-3 pr-12">
            <div>
              <h2 className="text-xl font-semibold text-white">
                Reschedule Audit
              </h2>
              <p className="mt-1 text-sm text-blue-100/90">
                Update the schedule and provide a clear reason for traceability.
              </p>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-white/15 px-2.5 py-1 text-xs font-medium text-blue-100">
              <CalendarClock className="h-3.5 w-3.5" />
              {audit?.audit_number || "Audit"}
            </span>
          </div>
        </div>

        <div className="space-y-5 px-6 py-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-[#064273]/10 bg-[#f3f9ff] p-3 dark:border-[#064273]/35 dark:bg-[#064273]/20">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-[#355f7f] dark:text-blue-200/90">
                Current Start
              </p>
              <p className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                {formatSafeDate(audit?.planned_start_date)}
              </p>
            </div>
            <div className="rounded-xl border border-[#F68C1F]/20 bg-[#fff6ee] p-3 dark:border-[#F68C1F]/35 dark:bg-[#F68C1F]/12">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-[#9a5300] dark:text-orange-200">
                Current End
              </p>
              <p className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                {formatSafeDate(audit?.planned_end_date)}
              </p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <DatePickerOnly
                id="reschedule-audit-date"
                label="New Date"
                value={newDate}
                onChange={setNewDate}
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
                Start Time
              </label>
              <input
                type="time"
                value={newStartTime}
                onChange={(e) => setNewStartTime(e.target.value)}
                className="h-11 w-full rounded-lg border border-[#064273]/20 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-[#064273] focus:ring-2 focus:ring-[#064273]/20 dark:border-[#064273]/40 dark:bg-white/[0.04] dark:text-slate-200"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
                End Time
              </label>
              <input
                type="time"
                value={newEndTime}
                onChange={(e) => setNewEndTime(e.target.value)}
                className="h-11 w-full rounded-lg border border-[#064273]/20 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-[#064273] focus:ring-2 focus:ring-[#064273]/20 dark:border-[#064273]/40 dark:bg-white/[0.04] dark:text-slate-200"
              />
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800/40">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Auditees
            </p>
            <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
              {(audit.auditees ?? []).join(", ") || "No auditees assigned"}
            </p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Auditee management is separate from rescheduling. This dialog only
              updates the audit date and time.
            </p>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Reason
            </label>
            <textarea
              rows={4}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full rounded-lg border border-[#064273]/20 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition focus:border-[#F68C1F]/70 focus:ring-2 focus:ring-[#F68C1F]/20 dark:border-[#064273]/40 dark:bg-white/[0.04] dark:text-slate-200"
              placeholder="Explain why the audit is being rescheduled..."
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800/40 dark:bg-red-900/20 dark:text-red-300">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {showUnavailableConfirm && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-700 dark:bg-amber-950/20 dark:text-amber-200">
              <p className="text-sm font-semibold">Auditee availability conflict</p>
              <p className="mt-1 text-sm">{confirmUnavailableMessage}</p>
              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowUnavailableConfirm(false)}
                  className="rounded-lg border border-amber-400 px-3 py-1.5 text-sm font-medium"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleConfirmRescheduleAnyway}
                  className="rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white"
                >
                  Reschedule Anyway
                </button>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              onClick={onClose}
              className="rounded-lg border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              Cancel
            </button>

            <button
              onClick={handleSubmit}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-[#F68C1F] to-[#EF7807] px-4 py-2 text-sm font-semibold text-white transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60 dark:from-[#B55A00] dark:to-[#8A4600]"
            >
              <Clock3 className="h-4 w-4" />
              {loading ? "Saving..." : "Reschedule"}
            </button>
          </div>
        </div>
      </div>
      <div id="datepicker-portal"></div>
    </Modal>
    </>
  );
};

export default RescheduleAuditModal;
