import React, { useState } from "react";
import { Users, TriangleAlert } from "lucide-react";
import { useSelector } from "react-redux";
import toast from "react-hot-toast";
import { Modal } from "../ui/modal";
import { RootState } from "../../redux/store";
import { Audit, AuditAuditeeUpdateRequest } from "../../redux/audit/audit-types";
import { apiUpdateAuditAuditees } from "../../redux/audit/audit";
import {
  MemberDirectoryPicker,
  PickedAuditee,
} from "../common/MemberDirectoryPicker";

interface ManageAuditeesModalProps {
  audit: Audit;
  onClose: () => void;
  onSaved: (audit: Audit) => void;
}

// Prefer `auditee_details` (carries people_id per auditee, added alongside
// the plain `auditees` list) so re-opening this modal shows existing
// directory-picked auditees correctly instead of as "manual". Falls back to
// plain `auditees` for any audit fetched before this field existed.
const toPickedAuditees = (audit: Audit): PickedAuditee[] => {
  if (audit.auditee_details && audit.auditee_details.length > 0) {
    const seen = new Set<string>();
    return audit.auditee_details
      .map((a) => ({ email: a.email.trim().toLowerCase(), people_id: a.people_id ?? null }))
      .filter((a) => {
        if (seen.has(a.email)) return false;
        seen.add(a.email);
        return true;
      });
  }
  return Array.from(
    new Set((audit.auditees ?? []).map((e) => e.trim().toLowerCase())),
  ).map((email) => ({ email, people_id: null }));
};

const isAuditeeUnavailableError = (msg: string) => {
  const lower = (msg || "").toLowerCase();
  return (
    (lower.includes("auditee") && lower.includes("not available")) ||
    (lower.includes("auditee") && lower.includes("approved leave")) ||
    (lower.includes("auditor") && lower.includes("conflicting audit"))
  );
};

const ManageAuditeesModal: React.FC<ManageAuditeesModalProps> = ({
  audit,
  onClose,
  onSaved,
}) => {
  const [auditees, setAuditees] = useState<PickedAuditee[]>(
    toPickedAuditees(audit),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showUnavailableConfirm, setShowUnavailableConfirm] = useState(false);
  const [confirmUnavailableMessage, setConfirmUnavailableMessage] = useState("");
  const { user } = useSelector((state: RootState) => state.auth);

  const submit = async (allowUnavailableAuditee: boolean) => {
    if (!user?.email) {
      setError("User not found.");
      return;
    }

    const payload: AuditAuditeeUpdateRequest = {
      auditee_emails: auditees.map((a) => a.email),
      auditees,
      email: user.email,
      allow_unavailable_auditee: allowUnavailableAuditee,
    };

    setLoading(true);
    try {
      const updatedAudit = await apiUpdateAuditAuditees(audit.id, payload);
      toast.success("Auditees updated successfully!");
      setShowUnavailableConfirm(false);
      onSaved(updatedAudit);
      onClose();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err as Error)?.message ||
        "Failed to update auditees.";

      if (!allowUnavailableAuditee && isAuditeeUnavailableError(msg)) {
        setConfirmUnavailableMessage(msg);
        setShowUnavailableConfirm(true);
      } else {
        setError(msg);
        setShowUnavailableConfirm(false);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    setError("");
    setShowUnavailableConfirm(false);

    if (!user?.email) {
      setError("User not found.");
      return;
    }

    if (auditees.length === 0) {
      setError("At least one auditee email is required.");
      return;
    }

    await submit(false);
  };

  const handleSaveAnyway = async () => {
    setError("");
    await submit(true);
  };

  return (
    <Modal isOpen={true} onClose={onClose} className="max-w-[700px] p-0">
      <div className="rounded-3xl border border-[#064273]/15 bg-white dark:border-[#064273]/40 dark:bg-gray-900">
        <div className="rounded-t-3xl border-b border-[#064273]/15 bg-gradient-to-r from-[#064273] via-[#0a4f7f] to-[#0f628f] px-6 py-5 dark:border-[#064273]/40">
          <div className="flex items-start justify-between gap-3 pr-12">
            <div>
              <h2 className="text-xl font-semibold text-white">Manage Auditees</h2>
              <p className="mt-1 text-sm text-blue-100/90">
                Add, remove, or replace auditees for planned and rescheduled audits.
              </p>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-white/15 px-2.5 py-1 text-xs font-medium text-blue-100">
              <Users className="h-3.5 w-3.5" />
              {audit?.audit_number || "Audit"}
            </span>
          </div>
        </div>

        <div className="space-y-5 px-6 py-5">
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800/40">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Schedule
            </p>
            <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
              {audit.planned_start_date || "—"} to {audit.planned_end_date || "—"}
            </p>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Auditees
            </label>
            <MemberDirectoryPicker value={auditees} onChange={setAuditees} />
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Existing auditees are prefilled. Save to replace the list with the auditees above.
            </p>
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
                  onClick={handleSaveAnyway}
                  disabled={loading}
                  className="rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Save Anyway
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
              className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-[#064273] to-[#0f628f] px-4 py-2 text-sm font-semibold text-white transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Users className="h-4 w-4" />
              {loading ? "Saving..." : "Save Auditees"}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
};

export default ManageAuditeesModal;
