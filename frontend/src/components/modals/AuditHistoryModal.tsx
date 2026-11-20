import { useEffect } from "react";
import { format } from "date-fns";
import { Clock3 } from "lucide-react";
import { Modal } from "../ui/modal";
import { useSelector } from "react-redux";
import { fetchAuditHistory } from "../../redux/audit/audit-slice";
import { useAppDispatch } from "../../redux/hooks";
import { RootState } from "../../redux/store";
import { Audit } from "../../redux/audit/audit-types";

interface AuditHistoryModalProps {
  audit: Audit;
  onClose: () => void;
}

const CANCEL_REASON_LABELS: Record<number, string> = {
  1: "Auditee did not respond",
  2: "Auditee on holiday",
  3: "Auditor on leave",
  4: "Auditee not available",
  99: "Other",
};

export default function AuditHistoryModal({
  audit,
  onClose,
}: AuditHistoryModalProps) {
  const dispatch = useAppDispatch();

  const { historyByAuditId, historyLoading } = useSelector(
    (state: RootState) => state.audit,
  );

  useEffect(() => {
    dispatch(fetchAuditHistory(audit.id));
  }, [dispatch, audit.id]);

  return (
    <Modal isOpen={true} onClose={onClose} className="max-w-[680px] p-0">
      <div className="rounded-3xl border border-[#064273]/15 bg-white dark:border-[#064273]/40 dark:bg-gray-900">
        <div className="rounded-t-3xl border-b border-[#064273]/15 bg-gradient-to-r from-[#064273] via-[#0a4f7f] to-[#0f628f] px-6 py-5 dark:border-[#064273]/40">
          <h2 className="text-xl font-semibold text-white">
            Audit Activity History
          </h2>
          <p className="mt-1 text-sm text-blue-100/90">
            Timeline of reschedules and cancellations for audit{" "}
            {audit.audit_number}.
          </p>
        </div>

        <div className="px-6 py-5">
          {historyLoading && (
            <p className="text-sm text-gray-500">Loading...</p>
          )}

          {!historyLoading && historyByAuditId?.length === 0 && (
            <p className="text-sm text-gray-500">
              No activity found for this audit.
            </p>
          )}

          {!historyLoading && (
            <div className="max-h-[60vh] overflow-y-auto pr-2">
              <div className="relative ml-4 mt-1 border-l border-[#064273]/20 dark:border-[#064273]/40">
                {historyByAuditId.map((h) => (
                  <div key={h.id} className="relative mb-6 ml-4">
                    <div className="absolute -left-5 top-1 h-3 w-3 rounded-full bg-[#F68C1F]" />

                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center gap-1 rounded-full border border-[#064273]/20 bg-[#064273]/10 px-2 py-0.5 text-[11px] font-semibold text-[#064273] dark:border-[#77b7de]/30 dark:bg-[#064273]/30 dark:text-blue-200">
                        <Clock3 className="h-3 w-3" />
                        {h.action_type.toUpperCase()}
                      </span>
                      <p className="text-xs text-gray-500">
                        {format(new Date(h.created_at), "PPpp")}
                      </p>
                    </div>

                    <div className="mt-2 rounded-lg border border-[#064273]/10 bg-[#f8fbfe] p-3 text-sm dark:border-[#064273]/35 dark:bg-[#064273]/15">
                      <p>
                        <strong>Old Date:</strong>{" "}
                        {h.old_date
                          ? format(new Date(h.old_date), "PPpp")
                          : "-"}
                      </p>
                      <p>
                        <strong>New Date:</strong>{" "}
                        {h.new_date
                          ? format(new Date(h.new_date), "PPpp")
                          : "-"}
                      </p>

                      {h.reason && (
                        <p className="mt-2 rounded-md border border-[#F68C1F]/20 bg-[#fff6ee] px-2 py-1.5 text-[#8a4e00] dark:border-[#F68C1F]/35 dark:bg-[#F68C1F]/12 dark:text-orange-200">
                          <strong>Reason:</strong> {h.reason}
                        </p>
                      )}
                      {typeof h.reason_code === "number" && (
                        <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">
                          Reason code: <strong>{h.reason_code}</strong> (
                          {CANCEL_REASON_LABELS[h.reason_code] ?? "N/A"})
                        </p>
                      )}

                      {h.changed_by && (
                        <p className="mt-2 text-xs text-gray-500">
                          Changed by: {h.changed_by}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
