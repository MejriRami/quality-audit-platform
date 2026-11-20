import {
  Fragment,
  useMemo,
  useState,
  useCallback,
  useEffect,
  useRef,
} from "react";
import { useSelector } from "react-redux";
import axios from "axios";
import {
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  ChevronRightIcon,
  PaperClipIcon,
  CalendarDaysIcon,
  UserCircleIcon,
  IdentificationIcon,
  DocumentTextIcon,
  BuildingOffice2Icon,
  ArrowDownTrayIcon,
  PencilSquareIcon,
  PaperAirplaneIcon,
  EnvelopeIcon,
  ArrowsRightLeftIcon,
} from "@heroicons/react/24/outline";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "react-hot-toast";
import * as XLSX from "xlsx";
import {
  CorrectiveAction,
  CorrectiveActionActivityItem,
  CorrectiveActionDetail,
  CorrectiveActionReviewHistoryItem,
  CorrectiveActionStatus,
} from "../../../types";
import { fetchCorrectiveActionDetails } from "../../../services/correctiveActionsApi";
import { ReasonModal } from "../../modals/ReasonModal";
import { RootState } from "../../../redux/store";
import { Modal } from "../../ui/modal";
import { DatePickerOnly } from "../../calendar/DatePickerOnly";
import {
  MemberDirectoryPicker,
  PickedAuditee,
} from "../../common/MemberDirectoryPicker";
import { DirectoryEmailField } from "../../common/DirectoryEmailField";

interface TableCorrectiveActionsProps {
  correctiveActions: CorrectiveAction[];
  onAccept: (id: number) => Promise<void>;
  onReject: (id: number, reason: string) => Promise<void>;
  onExtendDueDate: (
    id: number,
    newDueDate: string,
    comment?: string,
  ) => Promise<void>;
  onEscalate: (id: number, emails: string[], comment?: string) => Promise<void>;
  onReassignAuditee: (
    id: number,
    newAuditeeEmail: string,
    reason?: string,
  ) => Promise<void>;
  targetCarId?: number | null;
  onTargetCarOpened?: (carId: number) => void;
  onRefresh?: () => void;
  /** Full filtered-but-unpaginated list to export from (so "Export" always
   *  covers every open NC for a plant, not just the current page). Falls
   *  back to `correctiveActions` if not provided. */
  exportSourceActions?: CorrectiveAction[];
}

type ActionDocument = CorrectiveAction["documents"][number];

function isPreviewableImage(filename: string) {
  return /\.(png|jpe?g|gif|webp|svg)$/i.test(filename);
}

function isPreviewablePdf(filename: string) {
  return /\.pdf$/i.test(filename);
}

function formatDocSize(size?: number) {
  const safeSize = Number(size || 0);
  if (safeSize < 1024) return `${safeSize} B`;
  if (safeSize < 1024 * 1024) return `${(safeSize / 1024).toFixed(1)} KB`;
  return `${(safeSize / (1024 * 1024)).toFixed(1)} MB`;
}

function formatUiDateTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function splitDocumentsByType(documents: ActionDocument[] = []) {
  const findingEvidence = documents.filter(
    (d) => d.document_type === "finding_evidence",
  );
  const carSolution = documents.filter(
    (d) => d.document_type !== "finding_evidence",
  );
  return { findingEvidence, carSolution };
}

function canManageCar(action: CorrectiveAction) {
  return !["Accepted", "Completed"].includes(String(action.status));
}

function dateToIsoDay(date: Date | null) {
  if (!date) return "";
  return date.toLocaleDateString("en-CA");
}

function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

const STATUS_META: Record<
  CorrectiveActionStatus,
  {
    bg: string;
    text: string;
    ring: string;
    dot: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  Pending: {
    bg: "bg-amber-50 dark:bg-amber-900/20",
    text: "text-amber-700 dark:text-amber-400",
    ring: "ring-amber-300 dark:ring-amber-700/50",
    dot: "bg-amber-400",
    icon: ClockIcon,
  },
  Submitted: {
    bg: "bg-indigo-50 dark:bg-indigo-900/30",
    text: "text-indigo-700 dark:text-indigo-300",
    ring: "ring-indigo-300 dark:ring-indigo-600/50",
    dot: "bg-indigo-500",
    icon: ExclamationTriangleIcon,
  },
  Accepted: {
    bg: "bg-emerald-50 dark:bg-emerald-900/20",
    text: "text-emerald-700 dark:text-emerald-400",
    ring: "ring-emerald-300 dark:ring-emerald-700/50",
    dot: "bg-emerald-500",
    icon: CheckCircleIcon,
  },
  Rejected: {
    bg: "bg-rose-50 dark:bg-rose-900/20",
    text: "text-rose-700 dark:text-rose-400",
    ring: "ring-rose-300 dark:ring-rose-700/50",
    dot: "bg-rose-500",
    icon: XCircleIcon,
  },
};

const FINDING_META: Record<
  string,
  { bg: string; text: string; border: string }
> = {
  FAIL: {
    bg: "bg-rose-50 dark:bg-rose-900/20",
    text: "text-rose-700 dark:text-rose-400",
    border: "border-rose-300 dark:border-rose-700/50",
  },
  IMPROVE: {
    bg: "bg-amber-50 dark:bg-amber-900/20",
    text: "text-amber-700 dark:text-amber-400",
    border: "border-amber-300 dark:border-amber-700/50",
  },
  PASS: {
    bg: "bg-emerald-50 dark:bg-emerald-900/20",
    text: "text-emerald-700 dark:text-emerald-400",
    border: "border-emerald-300 dark:border-emerald-700/50",
  },
};

const STATUS_ORDER: CorrectiveActionStatus[] = [
  "Pending",
  "Submitted",
  "Accepted",
  "Rejected",
];

const EMPTY_PLANT = "Unassigned plant";

function getPlantName(action: CorrectiveAction) {
  const raw = action.plant_name ?? action.plant;
  if (!raw) return EMPTY_PLANT;
  const trimmed = raw.trim();
  return trimmed.length ? trimmed : EMPTY_PLANT;
}

// Statuses considered "en cours" (still open, needing follow-up) for the
// per-plant export requested by auditors - explicitly Pending + Rejected,
// not Submitted (already with the auditor for review) or Accepted (closed).
const OPEN_NC_EXPORT_STATUSES: ReadonlySet<string> = new Set([
  "pending",
  "rejected",
]);

function isOpenNcStatus(action: CorrectiveAction) {
  return OPEN_NC_EXPORT_STATUSES.has(normalizeStatusForFilter(action.status));
}

function normalizeStatusForFilter(value: string) {
  return String(value ?? "").trim().toLowerCase();
}

// `corrective_action` ("Question") falls back to the underlying Question's
// description, or a legacy migrated-CAR field, when present - but freeform
// NC entries (IATF/ISO NC mode) have no linked Question, so this often ends
// up empty or coincidentally mirroring finding_text via other fallbacks.
// Only surface it when it actually adds information beyond the finding.
function distinctQuestionText(action: CorrectiveAction): string {
  const question = (action.corrective_action || "").trim();
  const finding = (action.finding_text || "").trim();
  if (!question || question === finding) return "";
  return question;
}

// Combines the CAR's primary auditee with any CC'd auditees into one
// comma-separated list, for audits/CARs with more than one person involved.
function combinedAuditeeList(action: CorrectiveAction): string {
  const emails = [action.auditee, ...(action.cc_emails || [])]
    .map((email) => (email || "").trim())
    .filter(Boolean);
  return [...new Set(emails)].join(", ");
}

function exportOpenNonConformities(plant: string, actions: CorrectiveAction[]) {
  const openActions = actions.filter(isOpenNcStatus);

  if (!openActions.length) {
    toast.error(`No open non-conformities (Pending/Rejected) for ${plant}.`);
    return;
  }

  const rows = openActions.map((action) => ({
    "CAR ID": action.identifier || `#${action.id}`,
    "Audit Reference": action.audit_reference || "",
    Plant: plant,
    Process: action.process || "",
    "Standard Clause": action.standard_paragraph || "",
    Classification: action.classification || "",
    "Finding Type": action.finding_type || "",
    Question: distinctQuestionText(action),
    "Finding Text": action.finding_text || "",
    "Non-Conformity Observed": action.reason_why || "",
    "Root Cause (5 Whys)": action.root_cause || "",
    "Implemented Corrective Action": action.implemented_solution || "",
    Auditee: combinedAuditeeList(action),
    "Pilot / Auditor": action.pilotUser || "",
    "Due Date": action.due_date || "",
    Status: action.status || "",
    Escalated: action.escalated ? "Yes" : "No",
    "Submitted At": action.submitted_at || "",
    "Created At": action.created_at || "",
  }));

  const worksheet = XLSX.utils.json_to_sheet(rows);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, "Open NCs");

  const today = new Date().toISOString().slice(0, 10);
  const safePlant = plant.replace(/[^a-z0-9]+/gi, "_");
  XLSX.writeFile(workbook, `open_non_conformities_${safePlant}_${today}.xlsx`);

  toast.success(
    `${openActions.length} open non-conformit${openActions.length > 1 ? "ies" : "y"} exported for ${plant}.`,
  );
}

function statusCounts(items: CorrectiveAction[]) {
  return items.reduce<Record<CorrectiveActionStatus, number>>(
    (acc, item) => {
      if (STATUS_ORDER.includes(item.status as CorrectiveActionStatus)) {
        acc[item.status as CorrectiveActionStatus] += 1;
      }
      return acc;
    },
    { Pending: 0, Submitted: 0, Accepted: 0, Rejected: 0 },
  );
}

/* ─── Status Pill ─────────────────────────────────────────── */
function StatusPill({ status }: { status: CorrectiveActionStatus }) {
  const m = STATUS_META[status];
  if (!m) return <span className="text-xs text-gray-400">{status}</span>;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${m.bg} ${m.text} ${m.ring}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${m.dot}`} />
      {status}
    </span>
  );
}

/* ─── Finding Badge ───────────────────────────────────────── */
function FindingBadge({ type }: { type: string | null | undefined }) {
  if (!type)
    return <span className="text-xs text-gray-300 dark:text-gray-600">—</span>;
  const m = FINDING_META[type] ?? {
    bg: "bg-indigo-50 dark:bg-indigo-900/20",
    text: "text-indigo-700 dark:text-indigo-300",
    border: "border-indigo-300 dark:border-indigo-700/50",
  };
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[10.5px] font-bold tracking-wider ${m.bg} ${m.text} ${m.border}`}
    >
      {type}
    </span>
  );
}

/* ─── Truncated Cell ──────────────────────────────────────── */
function TruncatedCell({
  value,
  maxWidth = "max-w-[200px]",
}: {
  value: string | null | undefined;
  maxWidth?: string;
}) {
  if (!value)
    return <span className="text-xs text-gray-300 dark:text-gray-600">—</span>;
  return (
    <span
      className={`block ${maxWidth} truncate text-sm text-gray-700 dark:text-gray-300`}
      title={value}
    >
      {value}
    </span>
  );
}

/* ─── Info Field (detail panel) ───────────────────────────── */
function InfoField({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-bold uppercase tracking-widest text-indigo-400 dark:text-indigo-500">
        {label}
      </span>
      <span className="text-sm text-gray-700 dark:text-gray-300">
        {value || "—"}
      </span>
    </div>
  );
}

/* ─── Text Block (detail panel) ───────────────────────────── */
function TextBlock({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-indigo-400 dark:text-indigo-500">
        {label}
      </p>
      <p className="rounded-xl border border-indigo-200 bg-white px-4 py-3 text-sm leading-relaxed text-gray-700 shadow-sm dark:border-indigo-800/40 dark:bg-white/[0.04] dark:text-gray-300">
        {value}
      </p>
    </div>
  );
}

/* ─── Detail Panel ────────────────────────────────────────── */
function DetailPanel({
  action,
  reviewHistory,
  activityTimeline,
  loadingDetails,
  onPreviewDocument,
  isAuditor,
}: {
  action: CorrectiveAction;
  reviewHistory?: CorrectiveActionReviewHistoryItem[];
  activityTimeline?: CorrectiveActionActivityItem[];
  loadingDetails?: boolean;
  onPreviewDocument: (doc: ActionDocument) => void;
  isAuditor: boolean;
}) {
  const { findingEvidence, carSolution } = splitDocumentsByType(
    action.documents ?? [],
  );

  return (
    <div className="border-t-2 border-indigo-200 bg-indigo-50/60 px-6 py-5 dark:border-indigo-800/60 dark:bg-indigo-950/30">
      {/* Meta grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-3 lg:grid-cols-4">
        {action.identifier && (
          <InfoField label="CAR ID" value={action.identifier} />
        )}
        {action.auditAnswerId && (
          <InfoField label="Answer ID" value={`#${action.auditAnswerId}`} />
        )}
        {action.process && <InfoField label="Process" value={action.process} />}
        {action.standard_paragraph && (
          <InfoField
            label="Standard Section"
            value={action.standard_paragraph}
          />
        )}
        {action.classification && (
          <InfoField label="Classification" value={action.classification} />
        )}
        {action.chapter && <InfoField label="Chapter" value={action.chapter} />}
        {action.submitted_at && (
          <InfoField label="Submitted" value={action.submitted_at} />
        )}
        {action.created_at && (
          <InfoField label="Created" value={action.created_at} />
        )}
      </div>

      {/* Text blocks */}
      {(action.finding_text ||
        action.corrective_action ||
        action.reason_why) && (
        <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {action.corrective_action && (
            <TextBlock label="Question" value={action.corrective_action} />
          )}
          {action.reason_why ? (
            <TextBlock label="Non-conformity" value={action.reason_why} />
          ) : (
            // Migrated (Monday.com) CARs never have reason_why - only
            // finding_text is available for them, so show it under the same
            // "Non-conformity" label rather than leaving the box empty.
            action.finding_text && (
              <TextBlock label="Non-conformity" value={action.finding_text} />
            )
          )}
          {isAuditor && action.finding_text && action.reason_why && (
            <TextBlock label="Finding text" value={action.finding_text} />
          )}
        </div>
      )}

      {(action.root_cause || action.implemented_solution) && (
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          {action.root_cause && (
            <TextBlock label="Root cause (5 Whys)" value={action.root_cause} />
          )}
          {action.implemented_solution && (
            <TextBlock
              label="Corrective action"
              value={action.implemented_solution}
            />
          )}
        </div>
      )}

      {/* Attachments */}
      {action.documents && action.documents.length > 0 && (
        <div className="mt-5">
          <p className="mb-2.5 text-[10px] font-bold uppercase tracking-widest text-indigo-400 dark:text-indigo-500">
            Attachments ({action.documents.length})
          </p>
          {isAuditor && findingEvidence.length > 0 && (
            <div className="mb-3">
              <p className="mb-2 text-xs font-semibold text-indigo-700 dark:text-indigo-300">
                Finding evidence ({findingEvidence.length})
              </p>
              <div className="flex flex-wrap gap-2">
                {findingEvidence.map((doc) => (
                  <button
                    key={`finding-${doc.id}`}
                    type="button"
                    onClick={() => onPreviewDocument(doc)}
                    className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs font-medium text-[#064273] shadow-sm transition hover:border-indigo-400 hover:shadow dark:border-indigo-800/40 dark:bg-white/5 dark:text-indigo-300 dark:hover:border-indigo-500"
                    title={`${doc.filename} - ${formatDocSize(doc.size)}`}
                  >
                    <DocumentTextIcon className="h-3.5 w-3.5 shrink-0" />
                    <span className="max-w-[160px] truncate">
                      {doc.filename}
                    </span>
                    <span className="text-gray-400 dark:text-gray-500">
                      {formatDocSize(doc.size)}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {carSolution.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold text-indigo-700 dark:text-indigo-300">
                CAR solution attachments ({carSolution.length})
              </p>
              <div className="flex flex-wrap gap-2">
                {carSolution.map((doc) => (
                  <button
                    key={`car-${doc.id}`}
                    type="button"
                    onClick={() => onPreviewDocument(doc)}
                    className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs font-medium text-[#064273] shadow-sm transition hover:border-indigo-400 hover:shadow dark:border-indigo-800/40 dark:bg-white/5 dark:text-indigo-300 dark:hover:border-indigo-500"
                    title={`${doc.filename} - ${formatDocSize(doc.size)}`}
                  >
                    <DocumentTextIcon className="h-3.5 w-3.5 shrink-0" />
                    <span className="max-w-[160px] truncate">
                      {doc.filename}
                    </span>
                    <span className="text-gray-400 dark:text-gray-500">
                      {formatDocSize(doc.size)}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Rejection reason */}
      {action.status === "Rejected" && action.review_comment && (
        <div className="mt-5 flex gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-800/40 dark:bg-rose-900/20">
          <XCircleIcon className="mt-0.5 h-4 w-4 shrink-0 text-rose-500 dark:text-rose-400" />
          <div>
            <p className="mb-1 text-xs font-bold text-rose-600 dark:text-rose-400">
              Rejection reason
            </p>
            <p className="text-sm leading-relaxed text-rose-700 dark:text-rose-300">
              {action.review_comment}
            </p>
          </div>
        </div>
      )}

      {loadingDetails && (
        <p className="mt-5 text-xs font-medium text-indigo-500 dark:text-indigo-400">
          Loading activity timeline...
        </p>
      )}

      {!loadingDetails && activityTimeline && activityTimeline.length > 0 && (
        <div className="mt-5">
          <p className="mb-2.5 text-[10px] font-bold uppercase tracking-widest text-indigo-400 dark:text-indigo-500">
            Activity timeline ({activityTimeline.length})
          </p>
          <div className="space-y-2">
            {activityTimeline.map((event) => (
              <div
                key={event.id}
                className="rounded-lg border border-indigo-200 bg-white px-3 py-2 dark:border-indigo-800/40 dark:bg-white/5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-indigo-700 dark:text-indigo-300">
                    {event.event_label}
                  </p>
                  <span className="text-[11px] text-gray-500 dark:text-gray-400">
                    {formatUiDateTime(event.at)}
                  </span>
                </div>
                {(event.actor || event.details) && (
                  <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                    {event.actor ? `By: ${event.actor}` : ""}
                    {event.actor && event.details ? " - " : ""}
                    {event.details || ""}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {!loadingDetails && reviewHistory && reviewHistory.length > 0 && (
        <div className="mt-5">
          <p className="mb-2.5 text-[10px] font-bold uppercase tracking-widest text-indigo-400 dark:text-indigo-500">
            Review history ({reviewHistory.length})
          </p>
          <div className="space-y-2">
            {reviewHistory.map((entry) => (
              <div
                key={entry.id}
                className="rounded-lg border border-indigo-200 bg-white px-3 py-2 dark:border-indigo-800/40 dark:bg-white/5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-indigo-700 dark:text-indigo-300">
                    Decision: {entry.decision}
                  </p>
                  <span className="text-[11px] text-gray-500 dark:text-gray-400">
                    {formatUiDateTime(entry.reviewed_at)}
                  </span>
                </div>
                {(entry.auditor || entry.comment) && (
                  <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                    {entry.auditor ? `By: ${entry.auditor}` : ""}
                    {entry.auditor && entry.comment ? " - " : ""}
                    {entry.comment || ""}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Spinner ─────────────────────────────────────────────── */

function DocumentPreviewModal({
  doc,
  onClose,
}: {
  doc: ActionDocument;
  onClose: () => void;
}) {
  const filename = doc.filename || `file-${doc.id}`;
  const canImage = isPreviewableImage(filename);
  const canPdf = isPreviewablePdf(filename);

  return (
    <div
      className="fixed inset-0 z-[100005] flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-5xl overflow-hidden rounded-xl bg-white shadow-2xl dark:bg-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
              {filename}
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {formatDocSize(doc.size)}
            </p>
          </div>
          <a
            href={doc.file_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:border-slate-600 dark:text-slate-200"
          >
            Open
          </a>
          <a
            href={doc.file_url}
            download={filename}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:border-slate-600 dark:text-slate-200"
          >
            <ArrowDownTrayIcon className="h-3.5 w-3.5" />
            Download
          </a>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white dark:bg-slate-700"
          >
            Close
          </button>
        </div>
        <div className="max-h-[75vh] overflow-auto bg-slate-100 p-4 dark:bg-slate-950">
          {canPdf ? (
            <iframe
              src={doc.file_url}
              title={filename}
              className="h-[70vh] w-full rounded-lg border border-slate-300 dark:border-slate-700"
            />
          ) : canImage ? (
            <img
              src={doc.file_url}
              alt={filename}
              className="mx-auto max-h-[70vh] max-w-full rounded-lg object-contain"
            />
          ) : (
            <div className="rounded-lg border border-slate-300 bg-white p-8 text-center text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
              Preview is not available for this file type.
              <div className="mt-3">
                <a
                  href={doc.file_url}
                  download={filename}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:border-slate-600 dark:text-slate-200"
                >
                  <ArrowDownTrayIcon className="h-3.5 w-3.5" />
                  Download file
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
function Spinner() {
  return (
    <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v8H4z"
      />
    </svg>
  );
}

/* ─── Action Buttons ──────────────────────────────────────── */
function ActionButtons({
  action,
  isSubmitting,
  submittingState,
  onAccept,
  onOpenReject,
  canReview,
  canManage,
  onOpenExtendDueDate,
  onOpenEscalate,
  onOpenReassign,
}: {
  action: CorrectiveAction;
  isSubmitting: boolean;
  submittingState: "accepting" | "rejecting" | null;
  onAccept: () => void;
  onOpenReject: () => void;
  canReview: boolean;
  canManage: boolean;
  onOpenExtendDueDate: () => void;
  onOpenEscalate: () => void;
  onOpenReassign: () => void;
}) {
  const showReview = canReview && action.status === "Submitted";
  const showManage = canManage && canManageCar(action);
  const showReassign = showManage && !action.reassigned_from_email;

  if (!showReview && !showManage) return null;

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {showManage && (
        <>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onOpenExtendDueDate();
            }}
            disabled={isSubmitting}
            className="inline-flex items-center gap-1.5 rounded-lg border border-sky-300 bg-white px-3 py-1.5 text-xs font-semibold text-sky-700 shadow-sm transition hover:bg-sky-50 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 dark:border-sky-700/50 dark:bg-transparent dark:text-sky-300 dark:hover:bg-sky-900/20"
          >
            <PencilSquareIcon className="h-3.5 w-3.5" /> Extend
          </button>

          <button
            onClick={(e) => {
              e.stopPropagation();
              onOpenEscalate();
            }}
            disabled={isSubmitting}
            className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-700 shadow-sm transition hover:bg-amber-50 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-700/50 dark:bg-transparent dark:text-amber-300 dark:hover:bg-amber-900/20"
          >
            <PaperAirplaneIcon className="h-3.5 w-3.5" /> Escalate
          </button>

          {showReassign && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onOpenReassign();
              }}
              disabled={isSubmitting}
              className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-300 bg-white px-3 py-1.5 text-xs font-semibold text-indigo-700 shadow-sm transition hover:bg-indigo-50 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 dark:border-indigo-700/50 dark:bg-transparent dark:text-indigo-300 dark:hover:bg-indigo-900/20"
            >
              <ArrowsRightLeftIcon className="h-3.5 w-3.5" /> Reassign
            </button>
          )}
        </>
      )}

      {showReview && (
        <>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onAccept();
            }}
            disabled={isSubmitting}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-700 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submittingState === "accepting" ? (
              <>
                <Spinner /> Saving…
              </>
            ) : (
              <>
                <CheckCircleIcon className="h-3.5 w-3.5" /> Accept
              </>
            )}
          </button>

          <button
            onClick={(e) => {
              e.stopPropagation();
              onOpenReject();
            }}
            disabled={isSubmitting}
            className="inline-flex items-center gap-1.5 rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-xs font-semibold text-rose-600 shadow-sm transition hover:bg-rose-50 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 dark:border-rose-700/50 dark:bg-transparent dark:text-rose-400 dark:hover:bg-rose-900/20"
          >
            {submittingState === "rejecting" ? (
              <>
                <Spinner /> Saving…
              </>
            ) : (
              <>
                <XCircleIcon className="h-3.5 w-3.5" /> Reject
              </>
            )}
          </button>
        </>
      )}
    </div>
  );
}

/* ─── Column definitions ──────────────────────────────────── */
const COLUMNS = [
  { key: "expand", label: "", width: 36 },
  { key: "idx", label: "#", width: 36 },
  { key: "identifier", label: "CAR ID", width: 120 },
  { key: "finding_type", label: "Finding", width: 86 },
  { key: "corrective_action", label: "Question / Action", width: 0 },
  { key: "auditee", label: "Auditee", width: 170 },
  { key: "pilot", label: "Pilot / Auditor", width: 160 },
  { key: "due_date", label: "Due Date", width: 104 },
  { key: "escalated", label: "Escalated", width: 88 },
  { key: "docs", label: "Docs", width: 52 },
  { key: "status", label: "Status", width: 118 },
  { key: "actions", label: "", width: 168 },
];

/* ══════════════════════════════════════════════════════════════
   Main component
══════════════════════════════════════════════════════════════ */
export default function TableCorrectiveActions({
  correctiveActions,
  onAccept,
  onReject,
  onExtendDueDate,
  onEscalate,
  onReassignAuditee,
  targetCarId,
  onTargetCarOpened,
  exportSourceActions,
}: TableCorrectiveActionsProps) {
  const [expandedPlants, setExpandedPlants] = useState<Record<string, boolean>>(
    {},
  );
  const [expandedAudits, setExpandedAudits] = useState<Record<number, boolean>>(
    {},
  );
  const [expandedRows, setExpandedRows] = useState<Record<number, boolean>>({});
  const [focusedCarId, setFocusedCarId] = useState<number | null>(null);
  const [submittingIds, setSubmittingIds] = useState<
    Record<number, "accepting" | "rejecting" | null>
  >({});
  const rowRefs = useRef<Record<number, HTMLTableRowElement | null>>({});
  const [rejectModal, setRejectModal] = useState<{
    open: boolean;
    actionId: number | null;
  }>({ open: false, actionId: null });
  const [extendModal, setExtendModal] = useState<{
    open: boolean;
    action: CorrectiveAction | null;
  }>({ open: false, action: null });
  const [escalateModal, setEscalateModal] = useState<{
    open: boolean;
    action: CorrectiveAction | null;
  }>({ open: false, action: null });
  const [reassignModal, setReassignModal] = useState<{
    open: boolean;
    action: CorrectiveAction | null;
  }>({ open: false, action: null });
  const [extendDueDateValue, setExtendDueDateValue] = useState<Date | null>(
    null,
  );
  const [extendComment, setExtendComment] = useState("");
  const [extendTouched, setExtendTouched] = useState(false);
  const [extendSubmitting, setExtendSubmitting] = useState(false);
  const [escalationRecipients, setEscalationRecipients] = useState<
    PickedAuditee[]
  >([]);
  const [escalationComment, setEscalationComment] = useState("");
  const [escalationTouched, setEscalationTouched] = useState(false);
  const [escalationSubmitting, setEscalationSubmitting] = useState(false);
  const [reassignEmail, setReassignEmail] = useState("");
  const [reassignReason, setReassignReason] = useState("");
  const [reassignTouched, setReassignTouched] = useState(false);
  const [reassignSubmitting, setReassignSubmitting] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<ActionDocument | null>(null);
  const [detailByCarId, setDetailByCarId] = useState<
    Record<number, CorrectiveActionDetail>
  >({});
  const [detailLoadingByCarId, setDetailLoadingByCarId] = useState<
    Record<number, boolean>
  >({});
  const roles = useSelector((state: RootState) => state.auth.role || []);
  const isAuditor = roles
    .map((role) => String(role).trim().toLowerCase())
    .includes("auditor");

  const togglePlant = (name: string) =>
    setExpandedPlants((prev) => ({ ...prev, [name]: !(prev[name] ?? true) }));

  const toggleAudit = (id: number) =>
    setExpandedAudits((prev) => ({ ...prev, [id]: !prev[id] }));

  const toggleRow = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedRows((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Mirrors of detailByCarId/detailLoadingByCarId kept in refs so that
  // ensureCarDetailsLoaded can have a stable identity ([] deps) instead of
  // changing every time any CAR's details load. A changing identity here
  // used to cascade into the auto-scroll effect below (which lists this
  // callback as a dependency) and re-trigger it for unrelated CARs.
  const detailByCarIdRef = useRef(detailByCarId);
  const detailLoadingByCarIdRef = useRef(detailLoadingByCarId);
  useEffect(() => {
    detailByCarIdRef.current = detailByCarId;
  }, [detailByCarId]);
  useEffect(() => {
    detailLoadingByCarIdRef.current = detailLoadingByCarId;
  }, [detailLoadingByCarId]);

  const ensureCarDetailsLoaded = useCallback(async (id: number) => {
    if (detailByCarIdRef.current[id]) return detailByCarIdRef.current[id];
    if (detailLoadingByCarIdRef.current[id]) return;
    detailLoadingByCarIdRef.current = {
      ...detailLoadingByCarIdRef.current,
      [id]: true,
    };
    setDetailLoadingByCarId((prev) => ({ ...prev, [id]: true }));
    try {
      const detail = await fetchCorrectiveActionDetails(id);
      detailByCarIdRef.current = { ...detailByCarIdRef.current, [id]: detail };
      setDetailByCarId((prev) => ({ ...prev, [id]: detail }));
      return detail;
    } catch {
      toast.error(`Failed to load details for CAR #${id}`);
    } finally {
      detailLoadingByCarIdRef.current = {
        ...detailLoadingByCarIdRef.current,
        [id]: false,
      };
      setDetailLoadingByCarId((prev) => ({ ...prev, [id]: false }));
    }
  }, []);

  const setSubmitting = (id: number, state: "accepting" | "rejecting" | null) =>
    setSubmittingIds((prev) => ({ ...prev, [id]: state }));

  const handlePreviewDocument = useCallback((doc: ActionDocument) => {
    if (!doc?.file_url) return;
    setPreviewDoc(doc);
  }, []);

  // Exports every open (Pending/Rejected) NC for one plant. Sourced from
  // exportSourceActions (the parent's full filtered-but-unpaginated list)
  // when provided, so the export always covers the whole plant regardless
  // of which page is currently displayed - falls back to the actions this
  // table was actually given otherwise.
  const handleExportPlant = useCallback(
    (plant: string) => {
      const source = exportSourceActions ?? correctiveActions;
      const plantActions = source.filter(
        (action) => getPlantName(action) === plant,
      );
      exportOpenNonConformities(plant, plantActions);
    },
    [exportSourceActions, correctiveActions],
  );

  /* ── Grouped data ── */
  const groupedByPlant = useMemo(() => {
    const plants = new Map<string, Map<number, CorrectiveAction[]>>();
    for (const action of correctiveActions) {
      const plant = getPlantName(action);
      if (!plants.has(plant)) plants.set(plant, new Map());
      const audits = plants.get(plant)!;
      if (!audits.has(action.auditId)) audits.set(action.auditId, []);
      audits.get(action.auditId)!.push(action);
    }
    return Array.from(plants.entries()).map(([plant, audits]) => ({
      plant,
      audits: Array.from(audits.entries()).map(([auditId, actions]) => ({
        auditId,
        actions,
      })),
    }));
  }, [correctiveActions]);

  /* ── Auto-scroll to target CAR ── */
  useEffect(() => {
    if (!targetCarId || !correctiveActions.length) return;
    const target = correctiveActions.find((a) => a.id === targetCarId);
    if (!target) return;
    const targetPlant = getPlantName(target);

    // Snapshot whether the plant/audit sections were already open *before*
    // this effect expands them. Read directly off current state (not as
    // effect deps — we only want this once when the target changes, not on
    // every unrelated expand/collapse elsewhere in the table).
    const wasPlantExpanded = expandedPlants[targetPlant] ?? true;
    const wasAuditExpanded = expandedAudits[target.auditId] ?? false;

    setExpandedPlants((prev) => ({ ...prev, [targetPlant]: true }));
    setExpandedAudits((prev) => ({ ...prev, [target.auditId]: true }));
    setExpandedRows((prev) => ({ ...prev, [targetCarId]: true }));
    void ensureCarDetailsLoaded(targetCarId);
    setFocusedCarId(targetCarId);
    onTargetCarOpened?.(targetCarId);

    // The plant/audit containers animate height 0 -> auto over 200ms
    // (framer-motion). If either was collapsed, scrolling on the next
    // animation frame lands against a layout that hasn't settled yet, so
    // wait out the expand transition (plus a small buffer) first.
    const needsAnimationDelay = !wasPlantExpanded || !wasAuditExpanded;
    const scrollDelay = needsAnimationDelay ? 320 : 0;
    const scrollTimeout = window.setTimeout(() => {
      rowRefs.current[targetCarId]?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, scrollDelay);
    const focusTimeout = window.setTimeout(
      () => setFocusedCarId(null),
      2500 + scrollDelay,
    );
    return () => {
      clearTimeout(scrollTimeout);
      clearTimeout(focusTimeout);
    };
    // expandedPlants/expandedAudits are read intentionally without being
    // deps: they're only used to snapshot pre-expansion state, not to react
    // to every unrelated toggle elsewhere in the table.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    targetCarId,
    correctiveActions,
    onTargetCarOpened,
    ensureCarDetailsLoaded,
  ]);

  /* ── Handlers ── */
  const handleAcceptClick = useCallback(
    async (id: number) => {
      try {
        setSubmitting(id, "accepting");
        await onAccept(id);
      } catch {
        toast.error("Failed to accept CAR. Please try again.");
      } finally {
        setSubmitting(id, null);
      }
    },
    [onAccept],
  );

  const handleRejectSubmit = useCallback(
    async (reason: string) => {
      if (!rejectModal.actionId) return;
      const id = rejectModal.actionId;
      try {
        setSubmitting(id, "rejecting");
        await onReject(id, reason);
        setRejectModal({ open: false, actionId: null });
      } catch {
        toast.error("Failed to reject CAR. Please try again.");
      } finally {
        setSubmitting(id, null);
      }
    },
    [onReject, rejectModal.actionId],
  );

  const closeExtendModal = useCallback(() => {
    setExtendModal({ open: false, action: null });
    setExtendDueDateValue(null);
    setExtendComment("");
    setExtendTouched(false);
  }, []);

  const closeEscalateModal = useCallback(() => {
    setEscalateModal({ open: false, action: null });
    setEscalationRecipients([]);
    setEscalationComment("");
    setEscalationTouched(false);
  }, []);

  const closeReassignModal = useCallback(() => {
    setReassignModal({ open: false, action: null });
    setReassignEmail("");
    setReassignReason("");
    setReassignTouched(false);
  }, []);

  const handleOpenExtendModal = useCallback((action: CorrectiveAction) => {
    setExtendModal({ open: true, action });
    setExtendDueDateValue(
      action.due_date ? new Date(`${action.due_date}T12:00:00`) : null,
    );
    setExtendComment("");
    setExtendTouched(false);
  }, []);

  const handleOpenEscalateModal = useCallback((action: CorrectiveAction) => {
    setEscalateModal({ open: true, action });
    setEscalationRecipients([]);
    setEscalationComment("");
    setEscalationTouched(false);
  }, []);

  const handleOpenReassignModal = useCallback((action: CorrectiveAction) => {
    setReassignModal({ open: true, action });
    setReassignEmail("");
    setReassignReason("");
    setReassignTouched(false);
  }, []);

  const parsedEscalationEmails = useMemo(
    () => escalationRecipients.map((r) => r.email),
    [escalationRecipients],
  );

  const extendDateIsInvalid =
    extendTouched &&
    (!extendDueDateValue ||
      !!(
        extendModal.action?.due_date &&
        dateToIsoDay(extendDueDateValue) <= extendModal.action.due_date
      ));

  const escalationEmailsInvalid =
    escalationTouched || escalationSubmitting
      ? parsedEscalationEmails.length === 0
      : false;

  const alreadyReassigned = !!reassignModal.action?.reassigned_from_email;

  const reassignEmailError = useMemo(() => {
    const trimmed = reassignEmail.trim().toLowerCase();
    const currentAuditee = (reassignModal.action?.auditee || "")
      .trim()
      .toLowerCase();
    if (!trimmed) return "Enter the new auditee's email.";
    if (!isValidEmail(trimmed)) return "Enter a valid email address.";
    if (trimmed === currentAuditee)
      return "This CAR is already assigned to that email.";
    return null;
  }, [reassignEmail, reassignModal.action]);

  const handleExtendSubmit = useCallback(async () => {
    if (!extendModal.action) return;
    setExtendTouched(true);
    if (
      !extendDueDateValue ||
      (extendModal.action.due_date &&
        dateToIsoDay(extendDueDateValue) <= extendModal.action.due_date)
    ) {
      return;
    }

    try {
      setExtendSubmitting(true);
      await onExtendDueDate(
        extendModal.action.id,
        dateToIsoDay(extendDueDateValue),
        extendComment.trim() || undefined,
      );
      closeExtendModal();
    } catch {
      toast.error("Failed to extend CAR due date. Please try again.");
    } finally {
      setExtendSubmitting(false);
    }
  }, [
    closeExtendModal,
    extendComment,
    extendDueDateValue,
    extendModal.action,
    onExtendDueDate,
  ]);

  const handleEscalateSubmit = useCallback(async () => {
    if (!escalateModal.action) return;
    setEscalationTouched(true);
    if (parsedEscalationEmails.length === 0) return;

    try {
      setEscalationSubmitting(true);
      await onEscalate(
        escalateModal.action.id,
        parsedEscalationEmails,
        escalationComment.trim() || undefined,
      );
      closeEscalateModal();
    } catch {
      toast.error("Failed to escalate CAR. Please try again.");
    } finally {
      setEscalationSubmitting(false);
    }
  }, [
    closeEscalateModal,
    escalateModal.action,
    escalationComment,
    onEscalate,
    parsedEscalationEmails,
  ]);

  const handleReassignSubmit = useCallback(async () => {
    if (!reassignModal.action) return;
    setReassignTouched(true);
    if (reassignEmailError) return;

    try {
      setReassignSubmitting(true);
      await onReassignAuditee(
        reassignModal.action.id,
        reassignEmail.trim(),
        reassignReason.trim() || undefined,
      );
      closeReassignModal();
    } catch (error) {
      const message = axios.isAxiosError(error)
        ? error.response?.data?.detail
        : undefined;
      toast.error(
        typeof message === "string"
          ? message
          : "Failed to reassign CAR. Please try again.",
      );
    } finally {
      setReassignSubmitting(false);
    }
  }, [
    closeReassignModal,
    onReassignAuditee,
    reassignEmail,
    reassignEmailError,
    reassignModal.action,
    reassignReason,
  ]);

  if (!correctiveActions?.length) return null;

  /* ══════════════════════════════════════════════════════════
     Render
  ══════════════════════════════════════════════════════════ */
  return (
    <div className="space-y-4">
      {groupedByPlant.map(({ plant, audits }) => {
        const isPlantExpanded = expandedPlants[plant] ?? true;
        const plantActions = audits.flatMap((a) => a.actions);
        const plantCounts = statusCounts(plantActions);

        return (
          <div
            key={plant}
            className="overflow-hidden rounded-2xl border border-indigo-200 shadow-sm dark:border-indigo-800/50"
          >
            {/* ── Plant header ─────────────────────────────── */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => togglePlant(plant)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  togglePlant(plant);
                }
              }}
              className="flex w-full cursor-pointer items-center gap-3 bg-gradient-to-r from-[#064273] via-[#0A4A78] to-[#0E5B93] px-5 py-4 text-left transition hover:from-[#05375f] hover:via-[#074066] hover:to-[#0A4A78]"
            >
              <motion.span
                animate={{ rotate: isPlantExpanded ? 90 : 0 }}
                transition={{ duration: 0.18, ease: "easeInOut" }}
                className="shrink-0 text-indigo-200"
              >
                <ChevronRightIcon className="h-4 w-4" />
              </motion.span>

              {/* Plant icon + name */}
              <span className="flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/15">
                  <BuildingOffice2Icon className="h-4 w-4 text-indigo-100" />
                </span>
                <span className="text-sm font-semibold tracking-tight text-white">
                  {plant}
                </span>
              </span>

              {/* Meta counts */}
              <span className="ml-3 text-xs font-medium text-indigo-200">
                {audits.length} audit{audits.length !== 1 ? "s" : ""} &middot;{" "}
                {plantActions.length} CAR{plantActions.length !== 1 ? "s" : ""}
              </span>

              {/* Status pills */}
              <div className="ml-auto flex shrink-0 flex-wrap items-center gap-1.5">
                {STATUS_ORDER.map((status) => {
                  const count = plantCounts[status];
                  if (!count) return null;
                  const meta = STATUS_META[status];
                  return (
                    <span
                      key={status}
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ${meta.bg} ${meta.text} ${meta.ring}`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${meta.dot}`}
                      />
                      {count} {status}
                    </span>
                  );
                })}
              </div>

              {/* Export open (Pending/Rejected) NCs for this plant */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleExportPlant(plant);
                }}
                title={`Export open non-conformities for ${plant}`}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/30 bg-white/10 px-2.5 py-1.5 text-[11px] font-semibold text-white transition hover:bg-white/20"
              >
                <ArrowDownTrayIcon className="h-3.5 w-3.5" />
                Export
              </button>
            </div>

            {/* ── Plant body ───────────────────────────────── */}
            <AnimatePresence initial={false}>
              {isPlantExpanded && (
                <motion.div
                  key={`plant-${plant}`}
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2, ease: "easeInOut" }}
                  className="overflow-hidden bg-indigo-50/40 dark:bg-indigo-950/20"
                >
                  <div className="space-y-3 p-3">
                    {audits.map(({ auditId, actions: auditActions }) => {
                      const isExpanded = expandedAudits[auditId] ?? false;
                      const dueDate = auditActions[0]?.due_date;
                      const ref = auditActions[0]?.audit_reference;
                      const auditCounts = statusCounts(auditActions);

                      return (
                        <div
                          key={`${plant}-${auditId}`}
                          className="overflow-hidden rounded-xl border border-indigo-200 bg-white shadow-sm dark:border-indigo-800/50 dark:bg-slate-900"
                        >
                          {/* ── Audit sub-header ──────────── */}
                          <button
                            type="button"
                            onClick={() => toggleAudit(auditId)}
                            className={[
                              "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors",
                              isExpanded
                                ? "border-b-2 border-indigo-200 bg-indigo-100/80 dark:border-indigo-700/60 dark:bg-indigo-900/40"
                                : "bg-indigo-50/70 hover:bg-indigo-100/60 dark:bg-indigo-900/20 dark:hover:bg-indigo-900/40",
                            ].join(" ")}
                          >
                            <motion.span
                              animate={{ rotate: isExpanded ? 90 : 0 }}
                              transition={{ duration: 0.18, ease: "easeInOut" }}
                              className="shrink-0 text-indigo-400"
                            >
                              <ChevronRightIcon className="h-3.5 w-3.5" />
                            </motion.span>

                            <span className="text-sm font-bold tracking-tight text-indigo-800 dark:text-indigo-200">
                              {ref || `Audit #${auditId}`}
                            </span>

                            {dueDate && (
                              <span className="inline-flex items-center gap-1.5 rounded-full border border-[#064273]/25 bg-[#064273]/10 px-2.5 py-1 text-xs font-semibold text-[#064273] dark:border-[#064273]/50 dark:bg-[#064273]/30 dark:text-blue-200">
                                <CalendarDaysIcon className="h-3.5 w-3.5" />
                                Due {dueDate}
                              </span>
                            )}

                            <span className="text-xs font-medium text-indigo-400 dark:text-indigo-500">
                              {auditActions.length} CAR
                              {auditActions.length !== 1 ? "s" : ""}
                            </span>

                            <div className="ml-auto flex shrink-0 flex-wrap items-center gap-1.5">
                              {STATUS_ORDER.map((status) => {
                                const count = auditCounts[status];
                                if (!count) return null;
                                const m = STATUS_META[status];
                                return (
                                  <span
                                    key={status}
                                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ${m.bg} ${m.text} ${m.ring}`}
                                  >
                                    <span
                                      className={`h-1.5 w-1.5 rounded-full ${m.dot}`}
                                    />
                                    {count} {status}
                                  </span>
                                );
                              })}
                            </div>
                          </button>

                          {/* ── Table ─────────────────────── */}
                          <AnimatePresence initial={false}>
                            {isExpanded && (
                              <motion.div
                                key={`table-${auditId}`}
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                transition={{
                                  duration: 0.2,
                                  ease: "easeInOut",
                                }}
                                className="overflow-hidden"
                              >
                                <div className="overflow-x-auto">
                                  <table
                                    className="w-full border-collapse text-sm"
                                    style={{
                                      tableLayout: "fixed",
                                      minWidth: 1082,
                                    }}
                                  >
                                    <colgroup>
                                      {COLUMNS.map((col) => (
                                        <col
                                          key={col.key}
                                          style={
                                            col.width
                                              ? { width: col.width }
                                              : undefined
                                          }
                                        />
                                      ))}
                                    </colgroup>

                                    {/* ── thead ── */}
                                    <thead>
                                      <tr className="border-b-2 border-indigo-200 bg-indigo-100 dark:border-indigo-700/60 dark:bg-indigo-900/50">
                                        {COLUMNS.map((col) => (
                                          <th
                                            key={col.key}
                                            className="px-3.5 py-2.5 text-left text-[10px] font-bold uppercase tracking-widest text-indigo-500 dark:text-indigo-400"
                                          >
                                            {col.label}
                                          </th>
                                        ))}
                                      </tr>
                                    </thead>

                                    {/* ── tbody ── */}
                                    <tbody className="divide-y divide-indigo-100 dark:divide-indigo-900/50">
                                      {auditActions.map((c, idx) => {
                                        const detail = detailByCarId[c.id];
                                        const mergedDocuments =
                                          detail?.documents ??
                                          c.documents ??
                                          [];
                                        const docsCount =
                                          c.documents_count ??
                                          mergedDocuments.length;
                                        const submittingState =
                                          submittingIds[c.id] ?? null;
                                        const isSubmitting = !!submittingState;
                                        const rowExpanded =
                                          expandedRows[c.id] ?? false;

                                        const hasDetail =
                                          c.root_cause ||
                                          c.implemented_solution ||
                                          (isAuditor && c.finding_text) ||
                                          c.process ||
                                          c.standard_paragraph ||
                                          c.classification ||
                                          c.reason_why ||
                                          docsCount > 0 ||
                                          (c.status === "Rejected" &&
                                            c.review_comment);

                                        return (
                                          <Fragment key={c.id}>
                                            {/* ── Data row ── */}
                                            <tr
                                              ref={(el) => {
                                                rowRefs.current[c.id] = el;
                                              }}
                                              className={[
                                                "transition-colors",
                                                focusedCarId === c.id
                                                  ? "bg-indigo-200/70 dark:bg-indigo-700/30 ring-2 ring-inset ring-indigo-400/40"
                                                  : rowExpanded
                                                    ? "bg-indigo-50/80 dark:bg-indigo-900/30"
                                                    : "bg-white hover:bg-indigo-50/60 dark:bg-slate-900 dark:hover:bg-indigo-900/20",
                                                isSubmitting
                                                  ? "opacity-60"
                                                  : "",
                                              ].join(" ")}
                                            >
                                              {/* Expand toggle */}
                                              <td className="px-3.5 py-3">
                                                {hasDetail && (
                                                  <button
                                                    onClick={(e) => {
                                                      const willExpand = !(
                                                        expandedRows[c.id] ??
                                                        false
                                                      );
                                                      toggleRow(c.id, e);
                                                      if (willExpand) {
                                                        void ensureCarDetailsLoaded(
                                                          c.id,
                                                        );
                                                      }
                                                    }}
                                                    className="flex h-6 w-6 items-center justify-center rounded-md text-indigo-400 transition hover:bg-indigo-100 hover:text-[#064273] dark:hover:bg-indigo-900/40 dark:hover:text-indigo-300"
                                                  >
                                                    <motion.span
                                                      animate={{
                                                        rotate: rowExpanded
                                                          ? 90
                                                          : 0,
                                                      }}
                                                      transition={{
                                                        duration: 0.15,
                                                      }}
                                                      className="block"
                                                    >
                                                      <ChevronRightIcon className="h-3.5 w-3.5" />
                                                    </motion.span>
                                                  </button>
                                                )}
                                              </td>

                                              {/* # */}
                                              <td className="px-3.5 py-3 text-xs font-semibold text-indigo-400 dark:text-indigo-500">
                                                {idx + 1}
                                              </td>

                                              {/* CAR ID */}
                                              <td className="px-3.5 py-3">
                                                {c.identifier ? (
                                                  <span className="inline-flex items-center gap-1.5 font-mono text-xs font-semibold text-[#064273] dark:text-indigo-300">
                                                    <IdentificationIcon className="h-3 w-3 shrink-0 text-indigo-400" />
                                                    <span className="truncate">
                                                      {c.identifier}
                                                    </span>
                                                  </span>
                                                ) : (
                                                  <span className="font-mono text-xs text-indigo-400 dark:text-indigo-500">
                                                    #{c.id}
                                                  </span>
                                                )}
                                                {c.action_type === "immediate" && (
                                                  <div className="mt-1">
                                                    <span className="inline-block rounded-full border border-red-300 bg-red-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-red-700 dark:border-red-700 dark:bg-red-950 dark:text-red-300">
                                                      Immediate action
                                                    </span>
                                                  </div>
                                                )}
                                                {c.action_type === "corrective" &&
                                                  c.linked_action_id && (
                                                    <div className="mt-1">
                                                      <span className="inline-block rounded-full border border-blue-300 bg-blue-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-700 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-300">
                                                        Corrective action
                                                      </span>
                                                    </div>
                                                  )}
                                              </td>

                                              {/* Finding */}
                                              <td className="px-3.5 py-3">
                                                <FindingBadge
                                                  type={c.finding_type}
                                                />
                                              </td>

                                              {/* Question / Action */}
                                              <td className="px-3.5 py-3">
                                                <TruncatedCell
                                                  value={c.corrective_action}
                                                  maxWidth="max-w-full"
                                                />
                                              </td>

                                              {/* Auditee */}
                                              <td className="px-3.5 py-3">
                                                <span className="flex min-w-0 items-center gap-1.5">
                                                  <UserCircleIcon className="h-3.5 w-3.5 shrink-0 text-indigo-400" />
                                                  <TruncatedCell
                                                    value={c.auditee}
                                                    maxWidth="max-w-full"
                                                  />
                                                  {!!c.cc_emails?.length && (
                                                    <span
                                                      className="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                                                      title={`In copy: ${c.cc_emails.join(", ")}`}
                                                    >
                                                      cc {c.cc_emails.length}
                                                    </span>
                                                  )}
                                                </span>
                                                {c.reassigned_from_email && (
                                                  <p
                                                    className="mt-0.5 truncate text-[10px] text-amber-600 dark:text-amber-400"
                                                    title={`Reassigned from ${c.reassigned_from_email}`}
                                                  >
                                                    ↩ from {c.reassigned_from_email}
                                                  </p>
                                                )}
                                              </td>

                                              {/* Pilot: lead auditor, then the second auditor (if any) on its own line */}
                                              <td className="px-3.5 py-3">
                                                {(c.pilotUser || "")
                                                  .split(" & ")
                                                  .map((email) => (
                                                    <TruncatedCell
                                                      key={email}
                                                      value={email}
                                                      maxWidth="max-w-full"
                                                    />
                                                  ))}
                                              </td>

                                              {/* Due date */}
                                              <td className="px-3.5 py-3">
                                                {c.due_date ? (
                                                  <span className="inline-flex items-center gap-1.5 rounded-full border border-[#064273]/20 bg-[#064273]/8 px-2.5 py-1 text-xs font-semibold text-[#064273] dark:border-[#064273]/45 dark:bg-[#064273]/25 dark:text-blue-200">
                                                    <CalendarDaysIcon className="h-3.5 w-3.5 shrink-0 text-[#064273] dark:text-blue-200" />
                                                    {c.due_date}
                                                  </span>
                                                ) : (
                                                  <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-400 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-500">
                                                    -
                                                  </span>
                                                )}
                                              </td>

                                              {/* Escalated */}
                                              <td className="px-3.5 py-3">
                                                {c.escalated ? (
                                                  <span className="inline-flex items-center gap-1 rounded-full border border-rose-300 bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-600 dark:border-rose-800/40 dark:bg-rose-900/20 dark:text-rose-400">
                                                    <ExclamationTriangleIcon className="h-3 w-3" />
                                                    Yes
                                                  </span>
                                                ) : (
                                                  <span className="text-xs text-gray-400 dark:text-gray-500">
                                                    No
                                                  </span>
                                                )}
                                              </td>

                                              {/* Docs */}
                                              <td className="px-3.5 py-3 text-center">
                                                {docsCount > 0 ? (
                                                  <button
                                                    type="button"
                                                    onClick={() => {
                                                      const firstDoc =
                                                        mergedDocuments[0];
                                                      if (firstDoc) {
                                                        handlePreviewDocument(
                                                          firstDoc,
                                                        );
                                                        return;
                                                      }
                                                      void ensureCarDetailsLoaded(
                                                        c.id,
                                                      ).then((detail) => {
                                                        const loadedFirst =
                                                          detail
                                                            ?.documents?.[0];
                                                        if (loadedFirst) {
                                                          handlePreviewDocument(
                                                            loadedFirst,
                                                          );
                                                        }
                                                      });
                                                    }}
                                                    className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-500 underline-offset-2 hover:underline dark:text-indigo-400"
                                                    title="Preview first attachment"
                                                  >
                                                    <PaperClipIcon className="h-3.5 w-3.5" />
                                                    {docsCount}
                                                  </button>
                                                ) : (
                                                  <span className="text-xs text-gray-300 dark:text-gray-600">
                                                    —
                                                  </span>
                                                )}
                                              </td>

                                              {/* Status */}
                                              <td className="px-3.5 py-3">
                                                <StatusPill
                                                  status={
                                                    c.status as CorrectiveActionStatus
                                                  }
                                                />
                                              </td>

                                              {/* Actions */}
                                              <td className="px-3.5 py-3">
                                                <ActionButtons
                                                  action={c}
                                                  isSubmitting={isSubmitting}
                                                  submittingState={
                                                    submittingState
                                                  }
                                                  canReview={isAuditor}
                                                  canManage={isAuditor}
                                                  onAccept={() =>
                                                    handleAcceptClick(c.id)
                                                  }
                                                  onOpenReject={() =>
                                                    setRejectModal({
                                                      open: true,
                                                      actionId: c.id,
                                                    })
                                                  }
                                                  onOpenExtendDueDate={() =>
                                                    handleOpenExtendModal(c)
                                                  }
                                                  onOpenEscalate={() =>
                                                    handleOpenEscalateModal(c)
                                                  }
                                                  onOpenReassign={() =>
                                                    handleOpenReassignModal(c)
                                                  }
                                                />
                                              </td>
                                            </tr>

                                            {/* ── Detail row ── */}
                                            <AnimatePresence initial={false}>
                                              {rowExpanded && (
                                                <motion.tr
                                                  key={`${c.id}-detail`}
                                                  initial={{ opacity: 0 }}
                                                  animate={{ opacity: 1 }}
                                                  exit={{ opacity: 0 }}
                                                  transition={{
                                                    duration: 0.15,
                                                  }}
                                                >
                                                  <td
                                                    colSpan={COLUMNS.length}
                                                    className="p-0"
                                                  >
                                                    <DetailPanel
                                                      action={{
                                                        ...c,
                                                        documents:
                                                          mergedDocuments,
                                                      }}
                                                      reviewHistory={
                                                        detail?.review_history
                                                      }
                                                      activityTimeline={
                                                        detail?.activity_timeline
                                                      }
                                                      loadingDetails={
                                                        !!detailLoadingByCarId[
                                                          c.id
                                                        ]
                                                      }
                                                      onPreviewDocument={
                                                        handlePreviewDocument
                                                      }
                                                      isAuditor={isAuditor}
                                                    />
                                                  </td>
                                                </motion.tr>
                                              )}
                                            </AnimatePresence>
                                          </Fragment>
                                        );
                                      })}
                                    </tbody>
                                  </table>
                                </div>
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}

      <AnimatePresence>
        {previewDoc && (
          <DocumentPreviewModal
            doc={previewDoc}
            onClose={() => setPreviewDoc(null)}
          />
        )}
      </AnimatePresence>

      <ReasonModal
        open={rejectModal.open}
        onClose={() => setRejectModal({ open: false, actionId: null })}
        onSubmit={handleRejectSubmit}
      />

      <Modal
        isOpen={extendModal.open}
        onClose={closeExtendModal}
        className="max-w-[620px] m-4 p-0"
      >
        <div className="border-b border-slate-200 px-6 py-5 dark:border-white/10">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
            Extend CAR Due Date
          </h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Update the due date manually and keep a traceability entry on the
            CAR timeline.
          </p>
        </div>
        <div className="space-y-5 px-6 py-5">
          <div className="rounded-xl border border-sky-100 bg-sky-50/70 px-4 py-3 text-sm text-sky-900 dark:border-sky-900/40 dark:bg-sky-950/30 dark:text-sky-100">
            <p className="font-semibold">
              {extendModal.action?.identifier ||
                `CAR #${extendModal.action?.id ?? ""}`}
            </p>
            <p className="mt-1 text-xs">
              Current due date: {extendModal.action?.due_date || "Not set"}
            </p>
          </div>
          <div>
            <DatePickerOnly
              id="extend-car-due-date"
              label="New due date"
              value={extendDueDateValue}
              onChange={(date) => {
                setExtendDueDateValue(date);
                setExtendTouched(true);
              }}
            />
            {extendDateIsInvalid && (
              <p className="mt-1.5 text-xs text-rose-500">
                Choose a date later than the current due date.
              </p>
            )}
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
              Comment
            </label>
            <textarea
              rows={4}
              value={extendComment}
              onChange={(e) => setExtendComment(e.target.value)}
              placeholder="Why is the due date being extended?"
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-sky-500 dark:border-white/10 dark:bg-white/5 dark:text-white"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-slate-200 px-6 py-4 dark:border-white/10">
          <button
            type="button"
            onClick={closeExtendModal}
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleExtendSubmit}
            disabled={extendSubmitting}
            className="inline-flex items-center gap-2 rounded-xl bg-sky-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {extendSubmitting ? (
              <Spinner />
            ) : (
              <PencilSquareIcon className="h-4 w-4" />
            )}
            Save due date
          </button>
        </div>
        <div id="datepicker-portal"></div>
      </Modal>

      <Modal
        isOpen={escalateModal.open}
        onClose={closeEscalateModal}
        className="max-w-[680px] m-4 p-0"
      >
        <div className="border-b border-slate-200 px-6 py-5 dark:border-white/10">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
            Escalate CAR
          </h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Enter the people who should receive the escalation email from the
            auditor.
          </p>
        </div>
        <div className="space-y-5 px-6 py-5">
          <div className="rounded-xl border border-amber-100 bg-amber-50/70 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100">
            <p className="font-semibold">
              {escalateModal.action?.identifier ||
                `CAR #${escalateModal.action?.id ?? ""}`}
            </p>
            <p className="mt-1 text-xs">
              Auditee: {escalateModal.action?.auditee || "N/A"} · Due date:{" "}
              {escalateModal.action?.due_date || "N/A"}
            </p>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
              Escalation emails
            </label>
            <MemberDirectoryPicker
              value={escalationRecipients}
              onChange={(next) => {
                setEscalationRecipients(next);
                setEscalationTouched(true);
              }}
              placeholder="Search the Northwind directory, or type an email and press Enter"
            />
            <div className="mt-1.5 flex items-center justify-between">
              {escalationEmailsInvalid ? (
                <p className="text-xs text-rose-500">
                  Add at least one recipient email.
                </p>
              ) : (
                <p className="text-xs text-slate-400">
                  Add every recipient who should receive the escalation.
                </p>
              )}
              <p className="text-xs text-slate-400">
                {parsedEscalationEmails.length} recipient
                {parsedEscalationEmails.length === 1 ? "" : "s"}
              </p>
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
              Comment
            </label>
            <textarea
              rows={4}
              value={escalationComment}
              onChange={(e) => setEscalationComment(e.target.value)}
              placeholder="Why are you escalating this CAR?"
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-amber-500 dark:border-white/10 dark:bg-white/5 dark:text-white"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-slate-200 px-6 py-4 dark:border-white/10">
          <button
            type="button"
            onClick={closeEscalateModal}
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleEscalateSubmit}
            disabled={escalationSubmitting}
            className="inline-flex items-center gap-2 rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {escalationSubmitting ? (
              <Spinner />
            ) : (
              <EnvelopeIcon className="h-4 w-4" />
            )}
            Send escalation
          </button>
        </div>
      </Modal>

      <Modal
        isOpen={reassignModal.open}
        onClose={closeReassignModal}
        className="max-w-[680px] m-4 p-0"
      >
        <div className="border-b border-slate-200 px-6 py-5 dark:border-white/10">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
            Reassign auditee
          </h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Hand this CAR off to a different auditee. This can only be done
            once per CAR.
          </p>
        </div>
        <div className="space-y-5 px-6 py-5">
          <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 px-4 py-3 text-sm text-indigo-900 dark:border-indigo-900/40 dark:bg-indigo-950/30 dark:text-indigo-100">
            <p className="font-semibold">
              {reassignModal.action?.identifier ||
                `CAR #${reassignModal.action?.id ?? ""}`}
            </p>
            <p className="mt-1 text-xs">
              Current auditee: {reassignModal.action?.auditee || "N/A"}
            </p>
          </div>
          {alreadyReassigned && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/70 px-4 py-3 text-xs text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100">
              This CAR was already reassigned once and can't be reassigned
              again.
            </div>
          )}
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
              New auditee email
            </label>
            <DirectoryEmailField
              value={reassignEmail}
              onChange={(email) => {
                setReassignEmail(email);
                setReassignTouched(true);
              }}
              placeholder="Search the Northwind directory, or type an email"
              disabled={alreadyReassigned}
              className={`h-11 w-full rounded-xl border pl-9 pr-3.5 py-2.5 text-sm outline-none transition placeholder:text-slate-400 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white/5 dark:text-white ${
                reassignTouched && reassignEmailError
                  ? "border-rose-300 focus:border-rose-400 dark:border-rose-700"
                  : "border-slate-300 focus:border-indigo-500 dark:border-white/10"
              }`}
            />
            {reassignTouched && reassignEmailError && (
              <p className="mt-1.5 text-xs text-rose-500">
                {reassignEmailError}
              </p>
            )}
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
              Reason (optional)
            </label>
            <textarea
              rows={3}
              value={reassignReason}
              onChange={(e) => setReassignReason(e.target.value)}
              placeholder="Why is this CAR being reassigned?"
              disabled={alreadyReassigned}
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/10 dark:bg-white/5 dark:text-white"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-slate-200 px-6 py-4 dark:border-white/10">
          <button
            type="button"
            onClick={closeReassignModal}
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleReassignSubmit}
            disabled={reassignSubmitting || alreadyReassigned}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {reassignSubmitting ? (
              <Spinner />
            ) : (
              <ArrowsRightLeftIcon className="h-4 w-4" />
            )}
            Reassign
          </button>
        </div>
      </Modal>
    </div>
  );
}
