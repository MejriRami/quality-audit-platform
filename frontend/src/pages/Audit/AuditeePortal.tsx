import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import axiosInstance from "../../services/axiosInstance";
import {
  fetchChatHistory,
  sendChatMessage,
  generateDraft,
  uploadChatDocument,
  fetchChatDocuments,
  CHATBOT_DOCUMENT_ACCEPT,
  CHATBOT_DOCUMENT_MAX_SIZE,
  type ChatbotMessage,
  type ChatbotDraft,
  type ChatbotDocument,
} from "../../services/auditeeChatbotApi";

const chatMarkdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="mb-2 last:mb-0">{children}</p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="mb-2 list-disc space-y-1 pl-4 last:mb-0">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="mb-2 list-decimal space-y-1 pl-4 last:mb-0">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="leading-snug">{children}</li>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  a: ({ children, href }: { children?: React.ReactNode; href?: string }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="underline underline-offset-2"
    >
      {children}
    </a>
  ),
  code: ({ children }: { children?: React.ReactNode }) => (
    <code className="rounded bg-black/10 px-1 py-0.5 text-xs">
      {children}
    </code>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="mb-2 overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full border-collapse text-left text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }: { children?: React.ReactNode }) => (
    <thead className="bg-slate-100">{children}</thead>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="border-b border-slate-200 px-3 py-2 font-semibold text-slate-700">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="border-b border-slate-100 px-3 py-2 align-top">
      {children}
    </td>
  ),
  tr: ({ children }: { children?: React.ReactNode }) => (
    <tr className="even:bg-slate-50">{children}</tr>
  ),
};

function DraftEntryView({
  entry,
  emptyLabel = "Not yet stated.",
}: {
  entry: { text: string; verdict: "ready" | "weak"; suggested_rewrite: string | null; note: string | null };
  emptyLabel?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-start gap-2">
        <span
          className={`mt-0.5 flex-shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
            entry.verdict === "ready"
              ? "bg-emerald-100 text-emerald-700"
              : "bg-amber-100 text-amber-700"
          }`}
        >
          {entry.verdict === "ready" ? "Ready" : "Needs work"}
        </span>
        <span className="flex-1">{entry.text || emptyLabel}</span>
      </div>
      {entry.suggested_rewrite && (
        <p className="rounded-lg bg-white/70 px-2.5 py-1.5 text-xs italic text-slate-600">
          Suggested wording (clarity only, same facts): "{entry.suggested_rewrite}"
        </p>
      )}
      {entry.note && (
        <p className="rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs text-amber-800">
          {entry.note}
        </p>
      )}
    </div>
  );
}

/**
 * AuditeePortal - A secure, responsive portal for managing corrective actions
 * Features: OTP verification, session persistence, status filtering, evidence management
 */

type AccessMode = "auditee" | "manager";

type PortalPlantResponse = {
  plants: string[];
};

type PortalRequestOtpResponse = {
  message: string;
  otp_sent?: boolean;
  already_verified?: boolean;
  plant?: string;
  email?: string;
  access_mode?: AccessMode;
  session_token?: string;
  session_expires_at?: string;
};

type PortalVerifyOtpResponse = {
  message: string;
  verified: boolean;
  session_token: string;
  session_expires_at: string;
  access_mode: AccessMode;
};

type PortalDocument = {
  id: number;
  filename: string;
  size: number;
  file_url: string;
  uploaded_at?: string | null;
  uploaded_by?: number | null;
};

type PortalReviewHistoryEntry = {
  decision: string;
  comment?: string | null;
  reviewed_at?: string | null;
  auditor_name?: string | null;
};

type PortalRequirementDetail = {
  requirement_code?: string | null;
  description?: string | null;
  fulfilled?: boolean | null;
  value?: number | null;
  finding_text?: string | null;
  is_car_requirement?: boolean;
};

type PortalRelatedRequirement = {
  standard_code?: string | null;
  standard_label?: string | null;
  questionnaire_name?: string | null;
  question_code?: string | null;
  question_description?: string | null;
  chapter?: string | null;
  subgroup?: string | null;
  element?: string | null;
  standard_paragraph?: string | null;
  process?: string | null;
  requirements: PortalRequirementDetail[];
};

type PortalLinkedAction = {
  car_id: number;
  action_type: string;
  status: string;
  submitted_at?: string | null;
  submission_due_at?: string | null;
  closure_due_at?: string | null;
  can_submit: boolean;
  submission_evidence: PortalDocument[];
  submission_evidence_count: number;
};

type PortalLinkedActionFormData = {
  car_id: number;
  action_type: string;
  implemented_solution: string;
  root_cause: string;
  is_submitted: boolean;
  status: string;
  submitted_at: string | null;
  submission_due_at: string | null;
  closure_due_at: string | null;
  documents: PortalDocument[];
};

type PortalCar = {
  car_id: number;
  identifier?: string | null;
  action_type?: string;
  linked_action?: PortalLinkedAction | null;
  question?: string | null;
  finding?: string | null;
  reason_why?: string | null;
  due_date?: string | null;
  status: string;
  submitted_at?: string | null;
  created_at?: string | null;
  can_submit: boolean;
  form_url: string;
  auditee_email?: string | null;
  finding_evidence: PortalDocument[];
  submission_evidence: PortalDocument[];
  finding_evidence_count: number;
  submission_evidence_count: number;
  // Any invited auditee on the audit can submit any of its CARs, so this can
  // differ from the CAR's current assignee — the only durable record of who
  // actually submitted and whether they used the portal or the emailed link.
  submitted_by_email?: string | null;
  submission_channel?: string | null;
  // Auditor may reject a submitted CAR — this is the latest rejection
  // comment (distinct from reason_why) plus the full decision history, so
  // the auditee can see why it was rejected and what to fix.
  rejection_reason?: string | null;
  review_history?: PortalReviewHistoryEntry[];
  related_requirement?: PortalRelatedRequirement | null;
  // Immediate-action CARs carry accelerated 24h-submit / 48h-close
  // deadlines instead of the regular due date.
  immediate_action_required?: boolean;
  submission_due_at?: string | null;
  closure_due_at?: string | null;
};

type PortalAudit = {
  audit_id: number;
  audit_number: string;
  plant: string;
  sector?: string | null;
  status: string;
  // Which checklist/standard this audit was run against (e.g. "IATF
  // Checklist", "VDA 6.3", "Plant Manager IATF Checklist").
  questionnaire_name?: string | null;
  planned_start_date?: string | null;
  planned_end_date?: string | null;
  auditee_count: number;
  // Any auditee invited to this audit can act on any of its CARs (not just
  // the one it happens to be assigned to) — the actual list, not just the
  // count, so an auditee can see who else shares that access.
  auditee_emails?: string[];
  leave_url?: string | null;
  cars: PortalCar[];
};

type PortalSummary = {
  total_audits: number;
  total_cars: number;
  total_auditees: number;
  status_counts: Record<string, number>;
};

type PortalAuditsResponse = {
  plant: string;
  email: string;
  access_mode: AccessMode;
  status_filter?: string | null;
  summary: PortalSummary;
  audits: PortalAudit[];
};

type StoredPortalSession = {
  token: string;
  expiresAt?: string | null;
};

type PortalCarFormData = {
  action_type?: string;
  linked_action?: PortalLinkedActionFormData | null;
  audit_number: string;
  auditee_name: string;
  audit_type: string;
  audit_plant: string;
  reason_why: string;
  due_date: string;
  finding: string;
  implemented_solution: string;
  root_cause: string;
  is_submitted: boolean;
  status: string;
  submitted_at: string | null;
  documents: PortalDocument[];
  finding_evidence: PortalDocument[];
  rejection_reason?: string | null;
  review_history?: PortalReviewHistoryEntry[];
  related_requirement?: PortalRelatedRequirement | null;
  can_reassign?: boolean;
  reassigned_at?: string | null;
  reassigned_from_email?: string | null;
  cc_emails?: string[];
  submitted_by_email?: string | null;
  submission_channel?: string | null;
  // Immediate-action CARs carry accelerated 24h-submit / 48h-close
  // deadlines instead of the regular due date.
  immediate_action_required?: boolean;
  submission_due_at?: string | null;
  closure_due_at?: string | null;
};

// Hyphenated names are valid (jordan.marin@example.com).
const emailPattern = /^[A-Za-z]+(?:-[A-Za-z]+)*\.[A-Za-z]+(?:-[A-Za-z]+)*@northwind\.com$/i;
const SUCCESS_PREFIX = "SUCCESS:";
const ERROR_PREFIX = "ERROR:";

// FastAPI's automatic request-validation errors (422) shape `detail` as an
// array of {msg, loc, ...} objects, not a string -- every call site here
// used to interpolate the raw error response body directly, assuming it's
// always a string, which crashes later .startsWith()/.includes() calls on
// the resulting message state when it isn't. Centralize the extraction so
// it's always a plain string.
function extractApiErrorDetail(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : String(item),
      )
      .join(" ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return "";
}
const STATUS_OPTIONS = [
  "pending",
  "rejected",
  "submitted",
  "accepted",
  "closed",
];

const accessCopy: Record<
  AccessMode,
  { title: string; subtitle: string; helper: string }
> = {
  auditee: {
    title: "Auditee CAR workspace",
    subtitle:
      "Review your related audits, supporting evidence, and corrective actions in one secure place.",
    helper:
      "Use your Northwind email to verify access and submit only your assigned corrective actions.",
  },
  manager: {
    title: "Manager oversight portal",
    subtitle:
      "Managers and directors of any department can review the full corrective action picture for their plant.",
    helper:
      "Select your plant and use your Northwind email to verify access and monitor audit corrective actions.",
  },
};

function formatDate(value?: string | null, includeTime = false) {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return includeTime
    ? parsed.toLocaleString()
    : parsed.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
}

function daysUntil(value?: string | null) {
  if (!value) return null;
  const due = new Date(value);
  if (Number.isNaN(due.getTime())) return null;
  const today = new Date();
  due.setHours(0, 0, 0, 0);
  today.setHours(0, 0, 0, 0);
  return Math.round((due.getTime() - today.getTime()) / 86_400_000);
}

function formatFileSize(bytes: number) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(size >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

function channelLabel(channel?: string | null) {
  if (channel === "portal") return "portal";
  if (channel === "form_link") return "standalone form";
  return null;
}

function statusLabel(value?: string | null) {
  const normalized = (value || "unknown").replace(/_/g, " ").trim();
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function statusPill(status: string) {
  switch (status.toLowerCase()) {
    case "pending":
      return "bg-amber-100 text-amber-900 border-amber-200";
    case "submitted":
      return "bg-sky-100 text-sky-900 border-sky-200";
    case "accepted":
      return "bg-emerald-100 text-emerald-900 border-emerald-200";
    case "closed":
      return "bg-slate-200 text-slate-900 border-slate-300";
    case "rejected":
      return "bg-rose-100 text-rose-900 border-rose-200";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
}

function messageTone(message: string) {
  if (message.startsWith(SUCCESS_PREFIX)) return "success" as const;
  if (message.startsWith(ERROR_PREFIX)) return "error" as const;
  return "info" as const;
}

function stripMessagePrefix(message: string) {
  return message.replace(SUCCESS_PREFIX, "").replace(ERROR_PREFIX, "").trim();
}

function sessionStorageKey(mode: AccessMode, plant: string, email: string) {
  return `portal-session:${mode}:${plant.trim().toLowerCase()}:${email
    .trim()
    .toLowerCase()}`;
}

function readStoredSession(
  mode: AccessMode,
  plant: string,
  email: string,
): StoredPortalSession | null {
  const raw = window.sessionStorage.getItem(
    sessionStorageKey(mode, plant, email),
  );
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredPortalSession;
  } catch {
    return null;
  }
}

function writeStoredSession(
  mode: AccessMode,
  plant: string,
  email: string,
  session: StoredPortalSession,
) {
  window.sessionStorage.setItem(
    sessionStorageKey(mode, plant, email),
    JSON.stringify(session),
  );
}

function clearStoredSession(mode: AccessMode, plant: string, email: string) {
  window.sessionStorage.removeItem(sessionStorageKey(mode, plant, email));
}

function extractTokenFromFormUrl(formUrl: string) {
  try {
    return new URL(formUrl).searchParams.get("token") || "";
  } catch {
    return "";
  }
}

function countWhyLines(rootCause: string) {
  const lines = rootCause
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  return lines.filter((line) => /^(why\s*\d+|why)\s*[:\-.)]?\s+.+$/i.test(line))
    .length;
}

function getRootCauseError(rootCause: string) {
  const whyCount = countWhyLines(rootCause);
  if (whyCount < 3) {
    return "Root cause must follow a 5 Whys structure with at least 3 Why statements.";
  }
  return "";
}

function splitWhys(rootCause: string) {
  const whyLines = (rootCause || "")
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*(why\s*\d*\s*[:\-.)]?\s*)/i, "").trim())
    .filter(Boolean)
    .slice(0, 5);

  return Array.from({ length: 5 }).map((_, index) => whyLines[index] || "");
}

function joinWhys(whys: string[]) {
  return whys
    .map((why) => why.trim())
    .filter(Boolean)
    .map((why, index) => `Why ${index + 1}: ${why}`)
    .join("\n");
}

function countFilledWhys(whys: string[]) {
  return whys.filter((why) => why.trim().length > 0).length;
}

const apiBaseUrl = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

// Shared "glass" panel treatment: soft shadow + translucent blurred fill
// instead of a hard border, used across the portal's cards for a consistent,
// less traditional-admin-template look than a flat white bordered box.
const GLASS_PANEL =
  "rounded-3xl border border-white/60 bg-white/70 shadow-[0_8px_30px_-4px_rgba(15,23,42,0.12)] backdrop-blur-xl";
const GLASS_PILL =
  "border border-white/60 bg-white/70 shadow-sm backdrop-blur-xl";

function buildApiUrl(path: string) {
  return `${apiBaseUrl}${path}`;
}

// Static PDF served straight off disk via the backend's /assets mount (see
// app/main.py and app/assets/guides/README.md) — no upload feature, no DB
// row; replacing the file at that path is enough to update the guide.
const CHATBOT_USER_GUIDE_URL = buildApiUrl(
  "/assets/guides/auditee-ai-assistant-user-guide.pdf",
);

interface MetricCardProps {
  label: string;
  value: string | number;
  tone: "blue" | "teal" | "amber" | "slate" | "rose" | "emerald";
  isLoading?: boolean;
  icon?: React.ReactNode;
}

interface LoadingSkeletonProps {
  count?: number;
}

function LoadingSkeleton({ count = 1 }: LoadingSkeletonProps) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:p-6"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 space-y-3">
              <div className="h-6 w-40 animate-pulse rounded bg-slate-200" />
              <div className="h-4 w-full animate-pulse rounded bg-slate-200" />
              <div className="h-4 w-5/6 animate-pulse rounded bg-slate-200" />
            </div>
            <div className="h-12 w-24 animate-pulse rounded-lg bg-slate-200" />
          </div>
        </div>
      ))}
    </div>
  );
}

interface AlertProps {
  message: string;
  tone: "success" | "error" | "info";
  onClose?: () => void;
}

function Alert({ message, tone, onClose }: AlertProps) {
  const styleClasses = {
    success: "border-emerald-200 bg-emerald-50 text-emerald-900",
    error: "border-rose-200 bg-rose-50 text-rose-900",
    info: "border-amber-200 bg-amber-50 text-amber-900",
  };

  const iconClasses = {
    success: "text-emerald-600",
    error: "text-rose-600",
    info: "text-amber-600",
  };

  return (
    <div
      className={`rounded-2xl border p-5 shadow-sm flex items-start gap-4 ${styleClasses[tone]}`}
      role="alert"
    >
      <div className={`flex-shrink-0 mt-0.5 ${iconClasses[tone]}`}>
        {tone === "success" && (
          <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
        )}
        {tone === "error" && (
          <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clipRule="evenodd"
            />
          </svg>
        )}
        {tone === "info" && (
          <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clipRule="evenodd"
            />
          </svg>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold uppercase tracking-wider">
          {tone === "success"
            ? "Success"
            : tone === "error"
              ? "Attention"
              : "Info"}
        </p>
        <p className="mt-2 text-sm leading-relaxed">{message}</p>
      </div>
      {onClose && (
        <button
          onClick={onClose}
          className="flex-shrink-0 text-current opacity-50 hover:opacity-75 transition-opacity"
          aria-label="Close alert"
        >
          <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      )}
    </div>
  );
}

function MetricCard({
  label,
  value,
  tone,
  isLoading = false,
  icon,
}: MetricCardProps) {
  const toneClasses = {
    blue: "border-blue-200/50 bg-gradient-to-br from-blue-50/80 to-blue-100/50 text-blue-900",
    teal: "border-teal-200/50 bg-gradient-to-br from-teal-50/80 to-teal-100/50 text-teal-900",
    amber:
      "border-amber-200/50 bg-gradient-to-br from-amber-50/80 to-amber-100/50 text-amber-900",
    slate:
      "border-slate-200/50 bg-gradient-to-br from-slate-50/80 to-slate-100/50 text-slate-900",
    // Status-semantic tones (reserved meaning, not just another category color):
    // rose = needs attention now, emerald = all clear.
    rose: "border-rose-200/50 bg-gradient-to-br from-rose-50/80 to-rose-100/50 text-rose-900",
    emerald:
      "border-emerald-200/50 bg-gradient-to-br from-emerald-50/80 to-emerald-100/50 text-emerald-900",
  } satisfies Record<string, string>;
  const iconToneClasses = {
    blue: "bg-blue-600/10 text-blue-700",
    teal: "bg-teal-600/10 text-teal-700",
    amber: "bg-amber-600/10 text-amber-700",
    slate: "bg-slate-600/10 text-slate-700",
    rose: "bg-rose-600/10 text-rose-700",
    emerald: "bg-emerald-600/10 text-emerald-700",
  } satisfies Record<string, string>;

  return (
    <div
      className={`rounded-2xl border p-4 sm:p-5 shadow-sm backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${toneClasses[tone]}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider opacity-80">
          {label}
        </p>
        {icon && (
          <span
            className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${iconToneClasses[tone]}`}
          >
            {icon}
          </span>
        )}
      </div>
      {isLoading ? (
        <div className="mt-3 h-8 w-20 animate-pulse rounded bg-white/50" />
      ) : (
        <p className="mt-3 text-2xl sm:text-3xl font-bold leading-none">
          {value}
        </p>
      )}
    </div>
  );
}

interface EvidenceListProps {
  title: string;
  documents: PortalDocument[];
  isLoading?: boolean;
}

function EvidenceList({
  title,
  documents,
  isLoading = false,
}: EvidenceListProps) {
  return (
    <div
      className="rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:p-5 transition-all duration-200 hover:border-slate-300 hover:shadow-sm"
      role="region"
      aria-label={title}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-800">{title}</p>
        <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 shadow-sm border border-slate-100">
          {documents.length}
        </span>
      </div>
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="h-12 animate-pulse rounded-2xl bg-white/50"
            />
          ))}
        </div>
      ) : documents.length === 0 ? (
        <p className="text-sm text-slate-500">No documents available.</p>
      ) : (
        <div className="space-y-2">
          {documents.map((doc) => (
            <a
              key={doc.id}
              href={doc.file_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center justify-between gap-3 rounded-2xl border border-white bg-white px-3 py-3 text-sm shadow-sm transition-all duration-200 hover:border-blue-200 hover:bg-blue-50 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
              aria-label={`Download ${doc.filename}`}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-slate-900">
                  {doc.filename}
                </p>
                <p className="text-xs text-slate-500">
                  {formatFileSize(doc.size)} •{" "}
                  {formatDate(doc.uploaded_at, true)}
                </p>
              </div>
              <span className="whitespace-nowrap text-xs font-semibold uppercase tracking-wider text-blue-700 flex-shrink-0">
                Open
              </span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function ReviewHistoryList({ history }: { history: PortalReviewHistoryEntry[] }) {
  // Oldest first, matching how the backend already orders it — the auditee
  // should read this as a timeline of the back-and-forth, not just the
  // latest decision.
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
        Review history
      </p>
      <ol className="mt-3 space-y-3">
        {history.map((entry, index) => (
          <li
            key={index}
            className={`rounded-md border px-3 py-2 text-sm ${
              entry.decision === "rejected"
                ? "border-rose-200 bg-rose-50"
                : "border-emerald-200 bg-emerald-50"
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span
                className={`text-xs font-semibold uppercase tracking-wider ${
                  entry.decision === "rejected"
                    ? "text-rose-700"
                    : "text-emerald-700"
                }`}
              >
                {entry.decision === "rejected" ? "Rejected" : "Accepted"}
              </span>
              <span className="text-xs text-slate-500">
                {formatDate(entry.reviewed_at, true)}
                {entry.auditor_name ? ` · ${entry.auditor_name}` : ""}
              </span>
            </div>
            {entry.comment && (
              <p className="mt-1 text-slate-700">{entry.comment}</p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function RelatedRequirementCard({
  related,
}: {
  related: PortalRelatedRequirement;
}) {
  const hasClauseInfo =
    related.standard_label ||
    related.standard_code ||
    related.questionnaire_name ||
    related.question_code ||
    related.chapter ||
    related.subgroup ||
    related.element ||
    related.standard_paragraph ||
    related.process;
  if (!hasClauseInfo && related.requirements.length === 0) return null;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Related requirement
        </p>
        {/* Which standard/checklist this finding came from — VDA, IATF, and
            internal checklists structure a "question" differently (element
            vs. chapter vs. neither), so naming the source up front tells the
            auditee which structure the badges below belong to. */}
        {(related.standard_label || related.standard_code) && (
          <span className="text-xs font-semibold text-slate-700">
            {related.standard_label || related.standard_code}
            {related.questionnaire_name ? ` · ${related.questionnaire_name}` : ""}
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        {related.question_code && (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-700">
            {related.question_code}
          </span>
        )}
        {related.element && (
          <span className="rounded-full bg-blue-50 px-2.5 py-1 font-semibold text-blue-700">
            {related.element}
          </span>
        )}
        {related.chapter && (
          <span className="rounded-full bg-blue-50 px-2.5 py-1 font-semibold text-blue-700">
            Chapter {related.chapter}
          </span>
        )}
        {related.subgroup && (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-700">
            {related.subgroup}
          </span>
        )}
        {related.standard_paragraph && (
          <span className="rounded-full bg-indigo-50 px-2.5 py-1 font-semibold text-indigo-700">
            {related.standard_paragraph}
          </span>
        )}
        {related.process && (
          <span className="rounded-full bg-amber-50 px-2.5 py-1 font-semibold text-amber-800">
            Process: {related.process}
          </span>
        )}
      </div>
      {related.question_description && (
        <p className="mt-2 text-sm text-slate-700 leading-relaxed">
          {related.question_description}
        </p>
      )}
      {related.requirements.length > 0 && (
        <ul className="mt-3 space-y-2 text-sm">
          {related.requirements.map((req, index) => (
            <li
              key={index}
              className={`rounded-md border px-3 py-2 ${
                req.is_car_requirement
                  ? "border-rose-300 bg-rose-50"
                  : "border-slate-100 bg-slate-50"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-slate-700">
                  {req.is_car_requirement && (
                    <span className="mr-1 font-semibold text-rose-700">This CAR:</span>
                  )}
                  {req.requirement_code ? `[${req.requirement_code}] ` : ""}
                  {req.description}
                </span>
                {req.value !== null && req.value !== undefined && req.value >= 0 ? (
                  <span
                    className={`whitespace-nowrap text-xs font-semibold ${
                      req.value >= 10 ? "text-emerald-700" : "text-rose-700"
                    }`}
                  >
                    Score {req.value}
                  </span>
                ) : req.fulfilled !== null && req.fulfilled !== undefined && (
                  <span
                    className={`whitespace-nowrap text-xs font-semibold ${
                      req.fulfilled ? "text-emerald-700" : "text-rose-700"
                    }`}
                  >
                    {req.fulfilled ? "Fulfilled" : "Not fulfilled"}
                  </span>
                )}
              </div>
              {req.finding_text && (
                <p className="mt-1 text-xs text-slate-500">
                  Auditor note: {req.finding_text}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function AuditeePortal() {
  const [plants, setPlants] = useState<string[]>([]);
  const [selectedPlant, setSelectedPlant] = useState("");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [accessMode, setAccessMode] = useState<AccessMode>("auditee");
  const [step, setStep] = useState<"lookup" | "otp" | "audits">("lookup");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [auditsData, setAuditsData] = useState<PortalAuditsResponse | null>(
    null,
  );
  const [statusFilter, setStatusFilter] = useState("");
  const [auditSearch, setAuditSearch] = useState("");
  // Audits start collapsed — an empty set here means "nothing expanded yet",
  // so the CAR list only opens once you click an audit's header/chevron.
  const [expandedAuditIds, setExpandedAuditIds] = useState<Set<number>>(
    new Set(),
  );
  const [activeSession, setActiveSession] =
    useState<StoredPortalSession | null>(null);
  const [submissionCar, setSubmissionCar] = useState<PortalCar | null>(null);
  const [submissionToken, setSubmissionToken] = useState("");
  const [submissionForm, setSubmissionForm] =
    useState<PortalCarFormData | null>(null);
  const [submissionSolution, setSubmissionSolution] = useState("");
  const [submissionRootCause, setSubmissionRootCause] = useState("");
  const [submissionRootCauseWhys, setSubmissionRootCauseWhys] = useState<
    string[]
  >(Array.from({ length: 5 }, () => ""));
  const [submissionFiles, setSubmissionFiles] = useState<File[]>([]);
  const [submissionLoading, setSubmissionLoading] = useState(false);
  const [submissionMessage, setSubmissionMessage] = useState("");
  // Corrective section's own submitted state, since submissionForm.is_submitted
  // is a snapshot from the last fetch and doesn't update after a successful
  // submit within this session (see submitPortalCar's "both done" check).
  const [correctiveDone, setCorrectiveDone] = useState(false);
  /* ── linked immediate action (containment, no 5-Whys, 24h/48h) ─────────── */
  const [immSolution, setImmSolution] = useState("");
  const [immFiles, setImmFiles] = useState<File[]>([]);
  const [immLoading, setImmLoading] = useState(false);
  const [immMessage, setImmMessage] = useState("");
  const [immSubmitted, setImmSubmitted] = useState(false);
  const [immSubmittedDate, setImmSubmittedDate] = useState<string | null>(
    null,
  );
  const [reassignEmail, setReassignEmail] = useState("");
  const [reassignReason, setReassignReason] = useState("");
  const [reassignLoading, setReassignLoading] = useState(false);
  const [reassignMessage, setReassignMessage] = useState("");
  const [reassignedNow, setReassignedNow] = useState(false);
  const [ccEmailInput, setCcEmailInput] = useState("");
  const [ccLoading, setCcLoading] = useState(false);
  const [ccMessage, setCcMessage] = useState("");
  const [chatOpen, setChatOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatbotMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState("");
  const [chatWidth, setChatWidth] = useState(520);
  const [isResizingChat, setIsResizingChat] = useState(false);
  const [draftLoading, setDraftLoading] = useState(false);
  const [pendingDraft, setPendingDraft] = useState<ChatbotDraft | null>(null);
  const [draftError, setDraftError] = useState("");
  const [chatDocuments, setChatDocuments] = useState<ChatbotDocument[]>([]);
  const [chatUploading, setChatUploading] = useState(false);
  const [chatUploadError, setChatUploadError] = useState("");
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const chatFileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isResizingChat) return;

    const previousUserSelect = document.body.style.userSelect;
    const previousCursor = document.body.style.cursor;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";

    function handleMouseMove(e: MouseEvent) {
      const next = window.innerWidth - e.clientX;
      const min = 360;
      const max = Math.min(1000, window.innerWidth - 40);
      setChatWidth(Math.min(max, Math.max(min, next)));
    }
    function handleMouseUp() {
      setIsResizingChat(false);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      document.body.style.userSelect = previousUserSelect;
      document.body.style.cursor = previousCursor;
    };
  }, [isResizingChat]);

  const isEmailValid = useMemo(() => emailPattern.test(email.trim()), [email]);
  const canContinue = selectedPlant.trim().length > 0 && isEmailValid;

  useEffect(() => {
    let cancelled = false;

    async function loadPlants() {
      try {
        const res =
          await axiosInstance.get<PortalPlantResponse>("/car/portal/plants");
        if (cancelled) return;
        const nextPlants = res.data.plants ?? [];
        setPlants(nextPlants);
        setSelectedPlant((prev) => prev || nextPlants[0] || "");
      } catch (error: any) {
        if (cancelled) return;
        setMessage(
          `${ERROR_PREFIX} ${extractApiErrorDetail(error) || "Unable to load plants for the portal."}`,
        );
      }
    }

    loadPlants();
    return () => {
      cancelled = true;
    };
  }, []);

  async function fetchPortalAudits(sessionToken: string, nextStatus?: string) {
    const res = await axiosInstance.get<PortalAuditsResponse>(
      "/car/portal/audits",
      {
        params: {
          plant: selectedPlant,
          email: email.trim(),
          access_mode: accessMode,
          status: nextStatus || undefined,
        },
        headers: {
          "X-Portal-Session": sessionToken,
        },
      },
    );
    return res.data;
  }

  async function loadAuditsWithSession(
    session: StoredPortalSession,
    nextStatus = statusFilter,
  ) {
    const data = await fetchPortalAudits(session.token, nextStatus);
    setAuditsData(data);
    setActiveSession(session);
    setStep("audits");
    setMessage("");
  }

  async function requestOtp() {
    if (!canContinue || loading) return;
    try {
      setLoading(true);
      setMessage("");
      const res = await axiosInstance.post<PortalRequestOtpResponse>(
        "/car/portal/request-otp",
        {
          plant: selectedPlant,
          email: email.trim(),
          access_mode: accessMode,
        },
      );

      if (res.data.already_verified && res.data.session_token) {
        const session = {
          token: res.data.session_token,
          expiresAt: res.data.session_expires_at,
        };
        writeStoredSession(accessMode, selectedPlant, email, session);
        await loadAuditsWithSession(session);
        return;
      }

      if (res.data.otp_sent) {
        setStep("otp");
        setOtp("");
        setMessage(
          `${SUCCESS_PREFIX} A verification code has been sent to your email.`,
        );
        return;
      }

      setMessage(
        `${ERROR_PREFIX} ${res.data.message || "No corrective actions were found for this selection."}`,
      );
    } catch (error: any) {
      setMessage(
        `${ERROR_PREFIX} ${extractApiErrorDetail(error) || "Unable to request an OTP code right now."}`,
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleContinue() {
    if (!canContinue || loading) return;
    const stored = readStoredSession(accessMode, selectedPlant, email);

    if (stored?.token) {
      try {
        setLoading(true);
        await loadAuditsWithSession(stored);
        return;
      } catch (error: any) {
        clearStoredSession(accessMode, selectedPlant, email);
        setActiveSession(null);
        if (error?.response?.status !== 401) {
          setMessage(
            `${ERROR_PREFIX} ${extractApiErrorDetail(error) || "Unable to restore your portal session."}`,
          );
          setLoading(false);
          return;
        }
      } finally {
        setLoading(false);
      }
    }

    await requestOtp();
  }

  async function verifyOtp() {
    if (otp.trim().length !== 6 || loading) return;
    try {
      setLoading(true);
      setMessage("");
      const res = await axiosInstance.post<PortalVerifyOtpResponse>(
        "/car/portal/verify-otp",
        {
          plant: selectedPlant,
          email: email.trim(),
          access_mode: accessMode,
          code: otp.trim(),
        },
      );
      const session = {
        token: res.data.session_token,
        expiresAt: res.data.session_expires_at,
      };
      writeStoredSession(accessMode, selectedPlant, email, session);
      await loadAuditsWithSession(session);
    } catch (error: any) {
      setMessage(
        `${ERROR_PREFIX} ${extractApiErrorDetail(error) || "Invalid OTP code."}`,
      );
    } finally {
      setLoading(false);
    }
  }

  async function refreshAudits(nextStatus = statusFilter) {
    if (!activeSession) return;
    try {
      setLoading(true);
      await loadAuditsWithSession(activeSession, nextStatus);
    } catch (error: any) {
      clearStoredSession(accessMode, selectedPlant, email);
      setActiveSession(null);
      setAuditsData(null);
      setStep("lookup");
      setMessage(
        `${ERROR_PREFIX} ${extractApiErrorDetail(error) || "Your portal session expired. Please verify again."}`,
      );
    } finally {
      setLoading(false);
    }
  }

  function resetView() {
    setAuditsData(null);
    setOtp("");
    setStep("lookup");
    setMessage("");
    setStatusFilter("");
    setAuditSearch("");
    closeSubmissionPanel();
    setChatOpen(false);
    setChatMessages([]);
    setChatInput("");
    setChatSending(false);
    setChatError("");
  }

  function signOutSession() {
    clearStoredSession(accessMode, selectedPlant, email);
    setActiveSession(null);
    resetView();
  }

  function closeSubmissionPanel() {
    setSubmissionCar(null);
    setSubmissionToken("");
    setSubmissionForm(null);
    setSubmissionSolution("");
    setSubmissionRootCause("");
    setSubmissionRootCauseWhys(Array.from({ length: 5 }, () => ""));
    setSubmissionFiles([]);
    setSubmissionLoading(false);
    setSubmissionMessage("");
    setCorrectiveDone(false);
    setImmSolution("");
    setImmFiles([]);
    setImmLoading(false);
    setImmMessage("");
    setImmSubmitted(false);
    setImmSubmittedDate(null);
    setReassignEmail("");
    setReassignReason("");
    setReassignLoading(false);
    setReassignMessage("");
    setReassignedNow(false);
    setCcEmailInput("");
    setCcLoading(false);
    setCcMessage("");
    setPendingDraft(null);
    setDraftError("");
  }

  async function reassignPortalCar() {
    if (!submissionCar || !submissionToken || reassignLoading) return;
    if (!emailPattern.test(reassignEmail.trim())) {
      setReassignMessage(
        `${ERROR_PREFIX} Use an Northwind email format: first.last@example.com`,
      );
      return;
    }

    try {
      setReassignLoading(true);
      setReassignMessage("");
      await axiosInstance.post("/car/reassign", {
        token: submissionToken,
        email: email.trim(),
        new_email: reassignEmail.trim(),
        reason: reassignReason.trim() || undefined,
        portal_session_token: activeSession?.token,
        portal_plant: selectedPlant,
        portal_access_mode: accessMode,
      });
      setReassignedNow(true);
      setReassignMessage(
        `${SUCCESS_PREFIX} Reassigned to ${reassignEmail.trim()} — they've been notified.`,
      );
      await refreshAudits(statusFilter);
    } catch (error: any) {
      setReassignMessage(
        `${ERROR_PREFIX} ${extractApiErrorDetail(error) || "Unable to reassign this corrective action."}`,
      );
    } finally {
      setReassignLoading(false);
    }
  }

  async function addPortalCc() {
    if (!submissionCar || !submissionToken || ccLoading) return;
    if (!emailPattern.test(ccEmailInput.trim())) {
      setCcMessage(
        `${ERROR_PREFIX} Use an Northwind email format: first.last@example.com`,
      );
      return;
    }

    try {
      setCcLoading(true);
      setCcMessage("");
      const res = await axiosInstance.post("/car/add-cc", {
        token: submissionToken,
        email: email.trim(),
        cc_emails: [ccEmailInput.trim()],
        portal_session_token: activeSession?.token,
        portal_plant: selectedPlant,
        portal_access_mode: accessMode,
      });
      setSubmissionForm((prev) =>
        prev ? { ...prev, cc_emails: res.data.cc_emails } : prev,
      );
      setCcEmailInput("");
    } catch (error: any) {
      setCcMessage(
        `${ERROR_PREFIX} ${extractApiErrorDetail(error) || "Unable to add this address."}`,
      );
    } finally {
      setCcLoading(false);
    }
  }

  function chatIdentity() {
    if (!activeSession) return null;
    return {
      plant: selectedPlant,
      email: email.trim(),
      access_mode: accessMode,
      sessionToken: activeSession.token,
    };
  }

  async function loadChatHistory() {
    const identity = chatIdentity();
    if (!identity) return;
    try {
      const history = await fetchChatHistory(identity);
      setChatMessages(history);
    } catch (error: any) {
      setChatError(
        extractApiErrorDetail(error) || "Unable to load the AI assistant history.",
      );
    }
  }

  // The backend already tags every stored message with the car_id it belongs
  // to (or null for the general thread), so the whole history only needs to
  // be fetched once — each CAR's conversation is just that thread filtered
  // client-side, matching how the backend itself scopes chat context per CAR.
  const focusedCarId = submissionCar?.car_id ?? null;
  const visibleChatMessages = useMemo(
    () => chatMessages.filter((msg) => (msg.car_id ?? null) === focusedCarId),
    [chatMessages, focusedCarId],
  );

  async function sendChatbotMessage() {
    const text = chatInput.trim();
    const identity = chatIdentity();
    if (!text || chatSending || !identity) return;

    // Tag optimistic messages with the currently focused car_id so they land
    // in the right thread immediately (visibleChatMessages filters on this) —
    // without it they'd default to undefined and briefly render in the
    // general thread even while a specific CAR is focused.
    setChatMessages((prev) => [
      ...prev,
      { role: "user", content: text, car_id: focusedCarId },
    ]);
    setChatInput("");
    setChatSending(true);
    setChatError("");

    try {
      const { reply } = await sendChatMessage({
        ...identity,
        message: text,
        car_id: focusedCarId,
      });
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: reply, car_id: focusedCarId },
      ]);
    } catch (error: any) {
      setChatError(
        extractApiErrorDetail(error) || "The AI assistant is unavailable right now.",
      );
    } finally {
      setChatSending(false);
    }
  }

  async function loadChatDocuments(carId: number) {
    const identity = chatIdentity();
    if (!identity) return;
    try {
      const docs = await fetchChatDocuments({ ...identity, car_id: carId });
      setChatDocuments(docs);
    } catch {
      // Non-critical for the conversation itself — fail silently, the
      // attach button/history will simply appear empty on error.
    }
  }

  async function handleChatFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    const identity = chatIdentity();
    if (!identity || !submissionCar) {
      setChatUploadError(
        "Focus the chat on a specific CAR (using the dropdown above) before attaching a document.",
      );
      return;
    }
    if (file.size > CHATBOT_DOCUMENT_MAX_SIZE) {
      setChatUploadError(
        `File too large (max ${(CHATBOT_DOCUMENT_MAX_SIZE / 1_048_576).toFixed(0)} MB).`,
      );
      return;
    }

    setChatUploading(true);
    setChatUploadError("");
    try {
      const doc = await uploadChatDocument({
        ...identity,
        car_id: submissionCar.car_id,
        file,
      });
      setChatDocuments((prev) => [doc, ...prev]);
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `📎 Document attached: **${doc.filename}** (${formatFileSize(doc.size)}${
            doc.truncated ? ", truncated to the first portion" : ""
          }). I'll use it as reference for this corrective action.`,
          // Tag with the focused CAR's id, same as every other message here —
          // otherwise this defaults to undefined and visibleChatMessages
          // (which filters on car_id === focusedCarId) silently drops it from
          // the focused CAR's thread, only showing it in the general thread.
          car_id: focusedCarId,
        },
      ]);
    } catch (error: any) {
      setChatUploadError(
        extractApiErrorDetail(error) || "Could not attach this document.",
      );
    } finally {
      setChatUploading(false);
    }
  }

  async function handleGenerateDraft() {
    const identity = chatIdentity();
    if (!identity || !submissionCar || draftLoading) return;

    setDraftLoading(true);
    setDraftError("");
    setPendingDraft(null);

    try {
      const draft = await generateDraft({
        ...identity,
        car_id: submissionCar.car_id,
      });
      setPendingDraft(draft);
    } catch (error: any) {
      setDraftError(
        extractApiErrorDetail(error) || "Unable to generate a draft right now.",
      );
    } finally {
      setDraftLoading(false);
    }
  }

  function insertDraftIntoForm() {
    if (!pendingDraft) return;

    // Prefer the suggested (clarity-only) rewrite when offered; otherwise the
    // auditee's own words. Weak entries with no suggestion insert as-is —
    // the assistant never invents replacement content for those.
    const whys = Array.from({ length: 5 }, (_, i) => {
      const entry = pendingDraft.whys[i];
      return entry ? entry.suggested_rewrite || entry.text : "";
    });
    setSubmissionRootCauseWhys(whys);
    setSubmissionRootCause(joinWhys(whys));
    setSubmissionSolution(
      pendingDraft.implemented_solution.suggested_rewrite ||
        pendingDraft.implemented_solution.text ||
        "",
    );
    setPendingDraft(null);
    setSubmissionMessage(
      `${SUCCESS_PREFIX} Draft inserted from your conversation — review, edit, and attach evidence before submitting.`,
    );
  }

  function discardDraft() {
    setPendingDraft(null);
  }

  async function openSubmissionPanel(car: PortalCar) {
    // Opening the panel (to view/discuss/chat about a CAR) must stay possible
    // regardless of can_submit — that flag only gates whether THIS SESSION
    // can submit from here (false for every CAR in manager mode, and false
    // once a CAR leaves pending/rejected). Gating the open itself on it used
    // to silently no-op focusChatOnCar for managers and for non-editable
    // CARs, leaving the chat "stuck" on whatever was focused before.
    const token = extractTokenFromFormUrl(car.form_url);
    if (!token) {
      setMessage(
        `${ERROR_PREFIX} Unable to open the CAR form from this portal.`,
      );
      return;
    }

    try {
      setSubmissionLoading(true);
      setSubmissionMessage("");
      setSubmissionCar(car);
      setSubmissionToken(token);
      setSubmissionFiles([]);
      setCorrectiveDone(false);
      setImmSolution("");
      setImmFiles([]);
      setImmMessage("");
      setImmSubmitted(false);
      setImmSubmittedDate(null);
      // Switching the focused CAR switches the chat thread too — clear the
      // previous CAR's pending draft/upload error, plus any reassign/CC form
      // state, so none of it leaks into the newly-focused CAR (this path
      // doesn't go through closeSubmissionPanel — e.g. the chat's CAR
      // selector jumps straight from one CAR to another).
      setPendingDraft(null);
      setDraftError("");
      setChatUploadError("");
      setReassignEmail("");
      setReassignReason("");
      setReassignMessage("");
      setReassignedNow(false);
      setCcEmailInput("");
      setCcMessage("");

      const res = await axiosInstance.get<PortalCarFormData>("/car/form", {
        params: {
          token,
          email: email.trim(),
          portal_session_token: activeSession?.token,
          portal_plant: selectedPlant,
          portal_access_mode: accessMode,
          _t: Date.now(),
        },
        headers: {
          "Cache-Control": "no-cache, no-store",
          Pragma: "no-cache",
        },
      });

      setSubmissionForm(res.data);
      setSubmissionSolution(res.data.implemented_solution || "");
      setSubmissionRootCause(res.data.root_cause || "");
      setSubmissionRootCauseWhys(splitWhys(res.data.root_cause || ""));
      setCorrectiveDone(res.data.is_submitted);
      if (res.data.linked_action) {
        setImmSolution(res.data.linked_action.implemented_solution || "");
        setImmSubmitted(res.data.linked_action.is_submitted);
        setImmSubmittedDate(res.data.linked_action.submitted_at);
      }
    } catch (error: any) {
      setSubmissionCar(null);
      setSubmissionToken("");
      setSubmissionForm(null);
      setSubmissionMessage(
        extractApiErrorDetail(error) || "Unable to load the CAR form.",
      );
    } finally {
      setSubmissionLoading(false);
    }
  }

  function toggleAuditCollapse(auditId: number) {
    setExpandedAuditIds((prev) => {
      const next = new Set(prev);
      if (next.has(auditId)) {
        next.delete(auditId);
      } else {
        next.add(auditId);
      }
      return next;
    });
  }

  function focusChatOnCar(carId: string) {
    if (!carId) {
      closeSubmissionPanel();
      return;
    }
    const car = allPortalCars.find((c) => String(c.car_id) === carId);
    if (car) openSubmissionPanel(car);
  }

  useEffect(() => {
    if (chatOpen && activeSession && chatMessages.length === 0) {
      loadChatHistory();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatOpen, activeSession]);

  useEffect(() => {
    setChatUploadError("");
    if (chatOpen && activeSession && submissionCar) {
      loadChatDocuments(submissionCar.car_id);
    } else {
      setChatDocuments([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatOpen, activeSession, submissionCar?.car_id]);

  useEffect(() => {
    chatScrollRef.current?.scrollTo({
      top: chatScrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [visibleChatMessages]);

  function handleSubmissionFilesChange(event: ChangeEvent<HTMLInputElement>) {
    if (!event.target.files) return;
    const nextFiles = Array.from(event.target.files);
    setSubmissionFiles((prev) => [...prev, ...nextFiles]);
    event.target.value = "";
  }

  function removeSubmissionFile(index: number) {
    setSubmissionFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function submitPortalCar() {
    if (!submissionCar || !submissionToken || submissionLoading) return;

    const composedRootCause = joinWhys(submissionRootCauseWhys);
    const rootCauseError = getRootCauseError(composedRootCause);
    if (rootCauseError) {
      setSubmissionMessage(`${ERROR_PREFIX} ${rootCauseError}`);
      return;
    }

    const existingDocCount = submissionForm?.documents.length ?? 0;
    if (existingDocCount + submissionFiles.length < 1) {
      setSubmissionMessage(
        `${ERROR_PREFIX} At least one related document is required before submitting.`,
      );
      return;
    }

    try {
      setSubmissionLoading(true);
      setSubmissionMessage("");
      const formData = new FormData();
      formData.append("token", submissionToken);
      formData.append("email", email.trim());
      formData.append("implemented_solution", submissionSolution.trim());
      formData.append("root_cause", composedRootCause.trim());
      formData.append(
        "target_action_type",
        submissionForm?.action_type || "corrective",
      );
      if (activeSession?.token) {
        formData.append("portal_session_token", activeSession.token);
        formData.append("portal_plant", selectedPlant);
        formData.append("portal_access_mode", accessMode);
      }
      submissionFiles.forEach((file) => formData.append("files", file));

      await axiosInstance.post("/car/submit", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setCorrectiveDone(true);
      setMessage(
        `${SUCCESS_PREFIX} CAR ${submissionCar.identifier || submissionCar.car_id} submitted successfully.`,
      );
      // The linked immediate section (if any) may still be pending -- only
      // close the panel once nothing is left to do for this finding.
      if (!submissionCar.linked_action || immSubmitted) {
        closeSubmissionPanel();
      }
      await refreshAudits(statusFilter);
    } catch (error: any) {
      setSubmissionMessage(
        `${ERROR_PREFIX} ${extractApiErrorDetail(error) || "Unable to submit the CAR right now."}`,
      );
    } finally {
      setSubmissionLoading(false);
    }
  }

  function handleImmFilesChange(event: ChangeEvent<HTMLInputElement>) {
    if (!event.target.files) return;
    const nextFiles = Array.from(event.target.files);
    setImmFiles((prev) => [...prev, ...nextFiles]);
    event.target.value = "";
  }

  function removeImmFile(index: number) {
    setImmFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function submitImmediatePortalCar() {
    if (!submissionCar || !submissionToken || immLoading) return;
    if (!immSolution.trim()) {
      setImmMessage(
        `${ERROR_PREFIX} Please describe the immediate/containment action taken.`,
      );
      return;
    }
    const existingImmDocCount = submissionForm?.linked_action?.documents.length ?? 0;
    if (existingImmDocCount + immFiles.length < 1) {
      setImmMessage(
        `${ERROR_PREFIX} At least one related document is required before submitting.`,
      );
      return;
    }

    try {
      setImmLoading(true);
      setImmMessage("");
      const formData = new FormData();
      formData.append("token", submissionToken);
      formData.append("email", email.trim());
      formData.append("implemented_solution", immSolution.trim());
      // The immediate row has no root cause requirement, so root_cause is
      // omitted entirely -- an empty multipart field is indistinguishable
      // from a missing one to the backend's request parser, so sending ""
      // here would 422 before the request even reaches app code.
      formData.append("target_action_type", "immediate");
      if (activeSession?.token) {
        formData.append("portal_session_token", activeSession.token);
        formData.append("portal_plant", selectedPlant);
        formData.append("portal_access_mode", accessMode);
      }
      immFiles.forEach((file) => formData.append("files", file));

      const res = await axiosInstance.post("/car/submit", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setImmSubmitted(true);
      setImmSubmittedDate(res.data.submitted_at);
      setMessage(
        `${SUCCESS_PREFIX} Immediate action for CAR ${submissionCar.identifier || submissionCar.car_id} submitted successfully.`,
      );
      if (correctiveDone) {
        closeSubmissionPanel();
      }
      await refreshAudits(statusFilter);
    } catch (error: any) {
      setImmMessage(
        `${ERROR_PREFIX} ${extractApiErrorDetail(error) || "Unable to submit the immediate action right now."}`,
      );
    } finally {
      setImmLoading(false);
    }
  }

  useEffect(() => {
    if (step !== "audits" || !activeSession) return;
    const timeout = window.setTimeout(() => {
      refreshAudits(statusFilter);
    }, 150);
    return () => window.clearTimeout(timeout);
  }, [statusFilter]);

  useEffect(() => {
    resetView();
    setActiveSession(null);
  }, [accessMode]);

  const allPortalCars = useMemo(
    () =>
      (auditsData?.audits ?? []).flatMap((audit) =>
        audit.cars.map((car) => ({ ...car, audit_number: audit.audit_number })),
      ),
    [auditsData],
  );
  const openPortalCars = useMemo(
    () => allPortalCars.filter((car) => car.status === "pending" || car.status === "rejected"),
    [allPortalCars],
  );
  const overdueCarCount = useMemo(
    () => openPortalCars.filter((car) => (daysUntil(car.due_date) ?? 1) < 0).length,
    [openPortalCars],
  );
  // The single most time-critical CAR to act on next: earliest due date among
  // open (pending/rejected) CARs the auditee can actually act on right now.
  const mostUrgentCar = useMemo(() => {
    const actionable = openPortalCars.filter((car) => car.can_submit && car.due_date);
    if (actionable.length === 0) return null;
    return [...actionable].sort(
      (a, b) => new Date(a.due_date!).getTime() - new Date(b.due_date!).getTime(),
    )[0];
  }, [openPortalCars]);
  const currentCopy = accessCopy[accessMode];
  const submissionRootCauseError = getRootCauseError(
    joinWhys(submissionRootCauseWhys),
  );
  const submissionDocumentCount =
    (submissionForm?.documents.length || 0) + submissionFiles.length;
  const filteredAudits = useMemo(() => {
    if (!auditsData) return [];

    const query = auditSearch.trim().toLowerCase();
    if (!query) return auditsData.audits;

    return auditsData.audits.filter((audit) => {
      const auditNumber = (audit.audit_number || "").toLowerCase();
      const startIso = (audit.planned_start_date || "").toLowerCase();
      const endIso = (audit.planned_end_date || "").toLowerCase();
      const startLabel = formatDate(audit.planned_start_date).toLowerCase();
      const endLabel = formatDate(audit.planned_end_date).toLowerCase();
      const questionnaireName = (audit.questionnaire_name || "").toLowerCase();
      return [
        auditNumber,
        startIso,
        endIso,
        startLabel,
        endLabel,
        questionnaireName,
      ].some((value) => value.includes(query));
    });
  }, [auditsData, auditSearch]);

  return (
    <div
      className="relative min-h-screen overflow-hidden bg-slate-50 px-4 py-6 sm:px-6 lg:px-8 notranslate"
      translate="no"
    >
      {/* translate="no" / notranslate: Edge's/Chrome's built-in page
          translator rewrites text nodes directly in the DOM, which fights
          with React's reconciliation and can crash uploads mid-submit with
          "NotFoundError: Failed to execute 'removeChild' on 'Node'" — seen
          when a browser auto-translated this page (e.g. for a non-English
          locale user). Opting the whole portal out of translation avoids it. */}
      {/* Gradient mesh background: soft blurred color fields behind the glass
          panels, instead of a flat single-color page background. */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-blue-300/30 blur-3xl" />
        <div className="absolute -top-16 right-0 h-[28rem] w-[28rem] rounded-full bg-cyan-300/25 blur-3xl" />
        <div className="absolute bottom-0 left-1/3 h-96 w-96 rounded-full bg-indigo-200/20 blur-3xl" />
      </div>
      <div className="mx-auto max-w-7xl relative z-10">
        {/* Header Section */}
        <div className="mb-8 space-y-8 lg:mb-12">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            {/* Title & Description */}
            <div className="flex-1">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className={`inline-flex items-center gap-3 rounded-full px-3 py-1.5 sm:px-4 sm:py-2 ${GLASS_PILL}`}>
                  <span className="inline-flex h-8 w-8 sm:h-10 sm:w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-800 to-blue-950 text-white shadow-md flex-shrink-0">
                    <svg
                      className="h-4 w-4 sm:h-5 sm:w-5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 11c0 1.657-1.79 3-4 3s-4-1.343-4-3 1.79-3 4-3 4 1.343 4 3zm8 0c0 1.657-1.79 3-4 3-.728 0-1.41-.146-2-.4M12 11V7m0 4v4m0 0v2m0-2c.59.26 1.272.4 2 .4 2.21 0 4-1.343 4-3s-1.79-3-4-3c-.728 0-1.41.146-2 .4"
                      />
                    </svg>
                  </span>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-blue-800 hidden sm:block">
                      Northwind
                    </p>
                    <p className="text-xs sm:text-sm font-medium text-slate-600">
                      Corrective action portal
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setGuideOpen(true)}
                  title="Open the AI Assistant user guide"
                  className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-semibold text-blue-800 transition hover:bg-white/90 ${GLASS_PILL}`}
                >
                  <svg className="h-4 w-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"
                    />
                  </svg>
                  User Guide
                </button>
              </div>

              <h1 className="mt-4 text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-slate-950">
                {currentCopy.title}
              </h1>
              <p className="mt-4 max-w-2xl text-base text-slate-600 sm:text-lg leading-relaxed">
                {currentCopy.subtitle}
              </p>
            </div>

            {/* Trust Badge */}
            <div className="w-full max-w-sm rounded-3xl border border-emerald-200/50 bg-gradient-to-br from-emerald-50/80 to-emerald-100/40 p-4 sm:p-5 shadow-[0_8px_30px_-4px_rgba(16,185,129,0.15)] backdrop-blur-xl">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0">
                  <svg
                    className="h-6 w-6 text-emerald-600"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-emerald-900">
                    Secure Access
                  </p>
                  <p className="mt-1 text-sm text-emerald-800">
                    OTP verified • Session secure
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Main Content Grid */}
        <div className="grid gap-6 lg:gap-8 lg:grid-cols-[320px_1fr]">
          {/* Sidebar */}
          <aside className="space-y-5 lg:space-y-6">
            {/* Access Form */}
            <div className={`${GLASS_PANEL} p-5 sm:p-6`}>
              <h2 className="mb-4 text-lg sm:text-xl font-bold text-slate-950">
                Sign in to the portal
              </h2>

              {/* Access Mode Toggle */}
              <div className="mb-4 grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
                {(["auditee", "manager"] as AccessMode[]).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setAccessMode(mode)}
                    className={`rounded-lg px-3 py-2 text-xs sm:text-sm font-semibold transition-all duration-200 ${
                      accessMode === mode
                        ? "bg-white text-slate-950 shadow-sm"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                    }`}
                    aria-pressed={accessMode === mode}
                  >
                    {mode === "auditee" ? "Auditee" : "Manager"}
                  </button>
                ))}
              </div>
              <p className="mb-4 text-xs text-slate-500 leading-relaxed">
                {currentCopy.helper}
              </p>

              {/* Form Fields */}
              <div className="space-y-4">
                {/* Plant Select */}
                <div>
                  <label
                    htmlFor="plant-select"
                    className="mb-2 block text-sm font-semibold text-slate-700"
                  >
                    Plant <span className="text-rose-500">*</span>
                  </label>
                  <select
                    id="plant-select"
                    value={selectedPlant}
                    onChange={(e) => setSelectedPlant(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 bg-slate-100/70 px-3 py-3 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100 disabled:bg-slate-50 disabled:text-slate-500"
                    aria-label="Select plant location"
                  >
                    <option value="">Select a plant</option>
                    {plants.map((plant) => (
                      <option key={plant} value={plant}>
                        {plant}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Email Input */}
                <div>
                  <label
                    htmlFor="email-input"
                    className="mb-2 block text-sm font-semibold text-slate-700"
                  >
                    Northwind email <span className="text-rose-500">*</span>
                  </label>
                  <input
                    id="email-input"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={
                      accessMode === "auditee"
                        ? "first.last@example.com"
                        : "quinn.roux@example.com"
                    }
                    className="w-full rounded-xl border border-slate-200 bg-slate-100/70 px-3 py-3 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100 placeholder:text-slate-400"
                    aria-label="Your Northwind email address"
                  />
                  {email.length > 0 && !isEmailValid && (
                    <p className="mt-2 text-xs sm:text-sm text-rose-600 flex items-center gap-1">
                      <span className="font-semibold">✓</span> Use format:
                      first.last@example.com
                    </p>
                  )}
                </div>

                {/* OTP Input */}
                {step === "otp" && (
                  <div className="animate-in fade-in duration-300">
                    <label
                      htmlFor="otp-input"
                      className="mb-2 block text-sm font-semibold text-slate-700"
                    >
                      Verification code <span className="text-rose-500">*</span>
                    </label>
                    <input
                      id="otp-input"
                      type="text"
                      value={otp}
                      onChange={(e) =>
                        setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))
                      }
                      placeholder="000000"
                      maxLength={6}
                      inputMode="numeric"
                      className="w-full rounded-xl border border-slate-200 bg-slate-100/70 px-3 py-3 text-center text-2xl font-bold tracking-widest text-slate-900 outline-none transition-all duration-200 focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100 placeholder:text-slate-300"
                      aria-label="Enter 6-digit verification code"
                    />
                    <p className="mt-2 text-xs text-slate-500 text-center uppercase tracking-wider font-medium">
                      Check your email inbox
                    </p>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="space-y-3 pt-2">
                  {step !== "otp" ? (
                    <button
                      type="button"
                      onClick={handleContinue}
                      disabled={!canContinue || loading}
                      className="w-full rounded-lg px-4 py-3 text-sm font-semibold text-white transition-all duration-200 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 bg-gradient-to-r from-blue-900 via-blue-800 to-cyan-700 shadow-lg hover:shadow-xl hover:scale-105 active:scale-95 enabled:hover:translate-y-[-2px]"
                      aria-busy={loading}
                    >
                      {loading ? (
                        <span className="flex items-center justify-center gap-2">
                          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-r-transparent" />
                          Checking access...
                        </span>
                      ) : (
                        "Continue securely"
                      )}
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={verifyOtp}
                        disabled={otp.trim().length !== 6 || loading}
                        className="w-full rounded-lg px-4 py-3 text-sm font-semibold text-white transition-all duration-200 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 bg-gradient-to-r from-blue-900 via-blue-800 to-cyan-700 shadow-lg hover:shadow-xl hover:scale-105 active:scale-95 enabled:hover:translate-y-[-2px]"
                        aria-busy={loading}
                      >
                        {loading ? (
                          <span className="flex items-center justify-center gap-2">
                            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-r-transparent" />
                            Verifying...
                          </span>
                        ) : (
                          "Verify OTP"
                        )}
                      </button>
                      <div className="grid grid-cols-2 gap-3">
                        <button
                          type="button"
                          onClick={requestOtp}
                          disabled={loading}
                          className="rounded-full border border-slate-300 bg-white px-4 py-2.5 text-xs sm:text-sm font-semibold text-slate-700 transition-all duration-200 hover:border-blue-300 hover:bg-blue-50 disabled:opacity-50"
                        >
                          Resend code
                        </button>
                        <button
                          type="button"
                          onClick={resetView}
                          disabled={loading}
                          className="rounded-full border border-slate-300 bg-white px-4 py-2.5 text-xs sm:text-sm font-semibold text-slate-700 transition-all duration-200 hover:border-slate-400 hover:bg-slate-50 disabled:opacity-50"
                        >
                          Back
                        </button>
                      </div>
                    </>
                  )}

                  {step === "audits" && (
                    <div className="grid grid-cols-2 gap-3">
                      <button
                        type="button"
                        onClick={() => refreshAudits()}
                        disabled={loading}
                        className="rounded-full border border-slate-300 bg-white px-4 py-2.5 text-xs sm:text-sm font-semibold text-slate-700 transition-all duration-200 hover:border-blue-300 hover:bg-blue-50 disabled:opacity-50"
                        aria-busy={loading}
                      >
                        Refresh
                      </button>
                      <button
                        type="button"
                        onClick={signOutSession}
                        className="rounded-lg border-2 border-rose-200 bg-rose-50 px-4 py-2.5 text-xs sm:text-sm font-semibold text-rose-700 transition-all duration-200 hover:border-rose-300 hover:bg-rose-100"
                      >
                        Exit
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Alert Message */}
            {message && (
              <Alert
                message={stripMessagePrefix(message)}
                tone={messageTone(message)}
                onClose={() => setMessage("")}
              />
            )}

            {/* Session Info */}
            {step === "audits" && auditsData && (
              <div className={`${GLASS_PANEL} p-5 sm:p-6`}>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">
                  Current session
                </p>
                <dl className="space-y-3 text-sm">
                  <div>
                    <dt className="font-semibold text-slate-900">Role</dt>
                    <dd className="mt-1 text-slate-600 text-sm capitalize">
                      {statusLabel(auditsData.access_mode)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-slate-900">Plant</dt>
                    <dd className="mt-1 text-slate-600 text-sm">
                      {auditsData.plant}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-slate-900">Email</dt>
                    <dd className="mt-1 break-all text-slate-600 text-sm">
                      {auditsData.email}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-slate-900">Expiry</dt>
                    <dd className="mt-1 text-slate-600 text-sm">
                      {formatDate(activeSession?.expiresAt, true)}
                    </dd>
                  </div>
                </dl>
              </div>
            )}
          </aside>

          {/* Main Content */}
          <main className="space-y-6 lg:space-y-8">
            {step !== "audits" || !auditsData ? (
              // Initial Guide Section
              <div className={`${GLASS_PANEL} p-6 sm:p-8`}>
                <div className="max-w-4xl">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Getting started
                  </p>
                  <h2 className="mt-4 text-2xl sm:text-3xl font-bold text-slate-950">
                    Manage corrective actions securely
                  </h2>
                  <p className="mt-4 text-base text-slate-600 leading-relaxed">
                    This portal keeps your verified session active, so you can
                    work without interruption. Your session expires
                    automatically after a period of inactivity for security.
                  </p>
                  <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {[
                      {
                        num: "1",
                        title: "Select context",
                        desc: "Choose your role and plant location",
                        tint: "from-blue-50 to-blue-100/50 border-blue-100",
                        badge: "bg-blue-600 text-white",
                      },
                      {
                        num: "2",
                        title: "Verify once",
                        desc: "One-time code sent to your email",
                        tint: "from-cyan-50 to-cyan-100/50 border-cyan-100",
                        badge: "bg-cyan-600 text-white",
                      },
                      {
                        num: "3",
                        title: "Review & act",
                        desc: "Browse audits and manage CARs",
                        tint: "from-indigo-50 to-indigo-100/50 border-indigo-100",
                        badge: "bg-indigo-600 text-white",
                      },
                    ].map((step) => (
                      <div
                        key={step.num}
                        className={`rounded-2xl border bg-gradient-to-br p-4 sm:p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${step.tint}`}
                      >
                        <div
                          className={`inline-flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold mb-3 shadow-sm ${step.badge}`}
                        >
                          {step.num}
                        </div>
                        <p className="font-semibold text-slate-900">
                          {step.title}
                        </p>
                        <p className="mt-2 text-sm text-slate-600">
                          {step.desc}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              // Audits Section
              <>
                {/* Overview Section */}
                <section className={`${GLASS_PANEL} p-5 sm:p-6`}>
                  <div className="space-y-5">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <h2 className="text-xl sm:text-2xl font-bold text-slate-950">
                        Corrective action snapshot
                      </h2>
                      <p className="text-sm text-slate-500">
                        {auditsData.summary.total_cars} CAR
                        {auditsData.summary.total_cars === 1 ? "" : "s"} across{" "}
                        {auditsData.summary.total_audits} audit
                        {auditsData.summary.total_audits === 1 ? "" : "s"}
                      </p>
                    </div>

                    {/* Metrics — one flat row, equal weight, no gradient hero;
                        the number itself carries the emphasis. */}
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      <MetricCard
                        label="Corrective actions"
                        value={auditsData.summary.total_cars}
                        tone="teal"
                        isLoading={loading}
                      />
                      <MetricCard
                        label="Audits"
                        value={auditsData.summary.total_audits}
                        tone="blue"
                        isLoading={loading}
                      />
                      <MetricCard
                        label="Auditees"
                        value={auditsData.summary.total_auditees}
                        tone="amber"
                        isLoading={loading}
                      />
                      <MetricCard
                        label="Overdue"
                        value={overdueCarCount}
                        tone={overdueCarCount > 0 ? "rose" : "emerald"}
                        isLoading={loading}
                      />
                    </div>

                    {/* Most urgent CAR callout */}
                    {mostUrgentCar && (
                      <div
                        className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl border px-4 py-3 ${
                          (daysUntil(mostUrgentCar.due_date) ?? 0) < 0
                            ? "border-rose-200 bg-rose-50"
                            : "border-amber-200 bg-amber-50"
                        }`}
                      >
                        <p className="text-sm text-slate-800">
                          <span
                            className={`mr-2 font-semibold uppercase tracking-wider text-xs ${
                              (daysUntil(mostUrgentCar.due_date) ?? 0) < 0
                                ? "text-rose-700"
                                : "text-amber-700"
                            }`}
                          >
                            Most urgent
                          </span>
                          CAR {mostUrgentCar.identifier || mostUrgentCar.car_id} (audit{" "}
                          {mostUrgentCar.audit_number}) —{" "}
                          {(() => {
                            const days = daysUntil(mostUrgentCar.due_date);
                            if (days === null) return `due ${formatDate(mostUrgentCar.due_date)}`;
                            if (days < 0) return `overdue by ${Math.abs(days)} day${Math.abs(days) === 1 ? "" : "s"}`;
                            if (days === 0) return "due today";
                            return `due in ${days} day${days === 1 ? "" : "s"}`;
                          })()}
                        </p>
                        <button
                          type="button"
                          onClick={() => openSubmissionPanel(mostUrgentCar)}
                          className="rounded-full bg-slate-950 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 flex-shrink-0"
                        >
                          Open CAR
                        </button>
                      </div>
                    )}

                    {/* Filters — one row: status is a single set of clickable
                        chips (doubles as both the filter control and the
                        status legend), search sits alongside it. No separate
                        dropdown duplicating the same filter. */}
                    <div className="flex flex-col gap-3 border-t border-slate-200/60 pt-4 lg:flex-row lg:items-center lg:justify-between">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => setStatusFilter("")}
                          className={`rounded-full border px-3 py-1.5 text-xs sm:text-sm font-semibold transition-all duration-200 ${
                            statusFilter === ""
                              ? "border-slate-900 bg-slate-900 text-white"
                              : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                          }`}
                          aria-pressed={statusFilter === ""}
                        >
                          All ({auditsData.summary.total_cars})
                        </button>
                        {STATUS_OPTIONS.map((status) => (
                          <button
                            key={status}
                            type="button"
                            onClick={() => setStatusFilter(status)}
                            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs sm:text-sm font-semibold transition-all duration-200 ${statusPill(status)} ${statusFilter === status ? "ring-2 ring-offset-1 ring-slate-400" : "opacity-80 hover:opacity-100"}`}
                            aria-pressed={statusFilter === status}
                          >
                            {statusLabel(status)}
                            <span className="rounded-full bg-white/70 px-1.5 py-0.5 text-[11px] font-bold">
                              {auditsData.summary.status_counts[status] || 0}
                            </span>
                          </button>
                        ))}
                      </div>

                      <div className="relative w-full lg:w-72">
                        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M21 21l-4.35-4.35m1.85-5.15a7 7 0 11-14 0 7 7 0 0114 0z"
                            />
                          </svg>
                        </span>
                        <input
                          id="audit-search"
                          type="search"
                          value={auditSearch}
                          onChange={(e) => setAuditSearch(e.target.value)}
                          placeholder="Search audit number or date"
                          className="w-full rounded-full border border-slate-200 bg-slate-100/70 px-10 py-2 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
                          aria-label="Search audits by audit number or planned date"
                        />
                      </div>
                    </div>
                  </div>
                </section>

                {/* Audits List */}
                {loading ? (
                  <LoadingSkeleton count={2} />
                ) : filteredAudits.length === 0 ? (
                  <div className="rounded-2xl border-2 border-dashed border-slate-300 bg-white/80 p-8 sm:p-12 text-center shadow-sm">
                    <svg
                      className="h-12 w-12 text-slate-300 mx-auto mb-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
                      />
                    </svg>
                    <h3 className="text-lg sm:text-xl font-bold text-slate-900">
                      {auditSearch || statusFilter
                        ? "No audits match your search"
                        : "No CARs match this filter"}
                    </h3>
                    <p className="mt-2 text-sm text-slate-600">
                      {auditSearch || statusFilter
                        ? "Try a different audit number or planned date, or clear the filters."
                        : "Try another filter or refresh to load the latest data."}
                    </p>
                  </div>
                ) : (
                  <section className="space-y-6">
                    {filteredAudits.map((audit) => {
                      const isCollapsed = !expandedAuditIds.has(audit.audit_id);
                      return (
                      <article
                        key={audit.audit_id}
                        className={`overflow-hidden ${GLASS_PANEL} transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_16px_40px_-8px_rgba(15,23,42,0.18)]`}
                      >
                        {/* Audit Header — click anywhere on it (outside the
                            action links) to expand/collapse this audit's
                            CAR list; the chevron button is the keyboard-
                            accessible equivalent. */}
                        <div
                          onClick={() => toggleAuditCollapse(audit.audit_id)}
                          className="cursor-pointer border-b border-white/40 bg-gradient-to-r from-blue-50/60 to-cyan-50/40 px-5 sm:px-6 py-5 sm:py-6 transition-colors hover:from-blue-50/90 hover:to-cyan-50/70"
                        >
                          <div className="space-y-4">
                            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                              <span className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs sm:text-sm font-semibold uppercase tracking-wider text-slate-700">
                                Audit #{audit.audit_number}
                              </span>
                              <span
                                className={`rounded-full border px-3 py-1 text-xs sm:text-sm font-semibold uppercase tracking-wider ${statusPill(audit.status)}`}
                              >
                                {statusLabel(audit.status)}
                              </span>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleAuditCollapse(audit.audit_id);
                                }}
                                className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3 py-1 text-xs sm:text-sm font-semibold text-slate-700 transition hover:border-blue-300 hover:bg-blue-50"
                                aria-expanded={!isCollapsed}
                                aria-controls={`audit-cars-${audit.audit_id}`}
                              >
                                {isCollapsed ? "Show CARs" : "Hide CARs"}
                                <svg
                                  className={`h-3.5 w-3.5 transition-transform duration-200 ${isCollapsed ? "" : "rotate-180"}`}
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M19 9l-7 7-7-7"
                                  />
                                </svg>
                              </button>
                            </div>
                            <h3 className="text-xl sm:text-2xl font-bold text-slate-950">
                              {audit.plant}
                              {audit.sector && (
                                <span className="text-slate-600">
                                  {" "}
                                  • {audit.sector}
                                </span>
                              )}
                            </h3>
                            {audit.questionnaire_name && (
                              <span className="inline-flex w-fit items-center rounded-full border border-sky-200 bg-sky-50 px-2.5 py-0.5 text-xs font-semibold text-sky-800">
                                {audit.questionnaire_name}
                              </span>
                            )}
                            <div className="flex flex-wrap gap-4 sm:gap-6 text-xs sm:text-sm text-slate-600">
                              <span>
                                Start:{" "}
                                <strong className="text-slate-900">
                                  {formatDate(audit.planned_start_date)}
                                </strong>
                              </span>
                              <span>
                                End:{" "}
                                <strong className="text-slate-900">
                                  {formatDate(audit.planned_end_date)}
                                </strong>
                              </span>
                              <span>
                                Auditees:{" "}
                                <strong className="text-slate-900">
                                  {audit.auditee_count}
                                </strong>
                              </span>
                              <span>
                                CARs:{" "}
                                <strong className="text-slate-900">
                                  {audit.cars.length}
                                </strong>
                              </span>
                            </div>

                            {/* Any auditee invited to this audit can open/act
                                on any of its CARs, not just the one it's
                                assigned to — show who else shares that access. */}
                            {audit.auditee_emails && audit.auditee_emails.length > 0 && (
                              <div className="flex flex-wrap items-center gap-1.5">
                                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                  Auditees on this audit:
                                </span>
                                {audit.auditee_emails.map((auditeeEmail) => (
                                  <span
                                    key={auditeeEmail}
                                    className="rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-medium text-slate-700"
                                  >
                                    {auditeeEmail}
                                  </span>
                                ))}
                              </div>
                            )}

                            {/* Action Buttons */}
                            <div
                              onClick={(e) => e.stopPropagation()}
                              className="flex flex-wrap gap-2 pt-3"
                            >
                              <a
                                href={buildApiUrl(
                                  // Cache-bust so a regenerated report is never shown from a stale browser copy.
                                  `/reports/${audit.audit_id}/preview-pdf?v=${Date.now()}`,
                                )}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-2 rounded-lg border border-blue-300 bg-gradient-to-r from-blue-50 to-blue-100 px-4 py-2 text-xs sm:text-sm font-semibold text-blue-700 shadow-sm transition-all duration-200 hover:shadow-md hover:from-blue-100 hover:to-blue-200"
                              >
                                <svg
                                  className="h-4 w-4"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                                  />
                                </svg>
                                View Report
                              </a>
                              {accessMode === "auditee" && audit.leave_url && (
                                <a
                                  href={audit.leave_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-gradient-to-r from-amber-50 to-amber-100 px-4 py-2 text-xs sm:text-sm font-semibold text-amber-700 shadow-sm transition-all duration-200 hover:shadow-md hover:from-amber-100 hover:to-amber-200"
                                >
                                  <svg
                                    className="h-4 w-4"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      strokeWidth={2}
                                      d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"
                                    />
                                  </svg>
                                  Declare Leave
                                </a>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* CARs List */}
                        {!isCollapsed && (
                        <div
                          id={`audit-cars-${audit.audit_id}`}
                          className="space-y-4 px-5 sm:px-6 py-5 sm:py-6"
                        >
                          {audit.cars.map((car) => (
                            <section
                              key={car.car_id}
                              className="rounded-xl border border-slate-200 bg-slate-50 p-4 sm:p-5 transition-all duration-200 hover:border-slate-300 hover:shadow-md"
                            >
                              <div className="space-y-4">
                                {/* CAR Header */}
                                <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                                  <span className="rounded-full bg-slate-950 px-3 py-1 text-xs sm:text-sm font-semibold uppercase tracking-wider text-white">
                                    {car.identifier || `CAR ${car.car_id}`}
                                  </span>
                                  <span
                                    className={`rounded-full border px-3 py-1 text-xs sm:text-sm font-semibold uppercase tracking-wider ${statusPill(car.status)}`}
                                  >
                                    {statusLabel(car.status)}
                                  </span>
                                  {car.linked_action && (
                                    <span
                                      className={`rounded-full border px-3 py-1 text-xs sm:text-sm font-semibold uppercase tracking-wider ${car.linked_action.status === "submitted" || car.linked_action.status === "accepted" ? "border-emerald-300 bg-emerald-50 text-emerald-700" : "border-red-300 bg-red-50 text-red-700"}`}
                                    >
                                      + Immediate action:{" "}
                                      {statusLabel(car.linked_action.status)}
                                    </span>
                                  )}
                                  {car.auditee_email && (
                                    <span className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs sm:text-sm font-medium text-slate-600">
                                      {car.auditee_email}
                                    </span>
                                  )}
                                  {accessMode === "auditee" && (
                                    <div className="ml-auto flex flex-wrap items-center gap-3">
                                      {/* "Submit in portal" is the recommended
                                          path — solid, primary. "Open CAR form"
                                          (the standalone emailed link, same
                                          form on its own page) is a muted
                                          fallback for people who'd rather work
                                          from that link, not a second equal
                                          choice. */}
                                      {car.can_submit && (
                                        <button
                                          type="button"
                                          onClick={() =>
                                            openSubmissionPanel(car)
                                          }
                                          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-all duration-200 hover:bg-emerald-700 hover:shadow-md"
                                        >
                                          <svg
                                            className="h-3.5 w-3.5"
                                            fill="none"
                                            stroke="currentColor"
                                            viewBox="0 0 24 24"
                                          >
                                            <path
                                              strokeLinecap="round"
                                              strokeLinejoin="round"
                                              strokeWidth={2}
                                              d="M12 4v16m8-8H4"
                                            />
                                          </svg>
                                          Respond here (recommended)
                                        </button>
                                      )}
                                      {!["submitted", "accepted"].includes(
                                        (car.status || "").toLowerCase(),
                                      ) && (
                                        <a
                                          href={car.form_url}
                                          target="_blank"
                                          rel="noreferrer"
                                          title="Opens the same form as a standalone page, outside the portal"
                                          className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 underline decoration-slate-300 underline-offset-2 transition-colors hover:text-slate-700 hover:decoration-slate-500"
                                        >
                                          Open standalone form
                                          <svg
                                            className="h-3 w-3"
                                            fill="none"
                                            stroke="currentColor"
                                            viewBox="0 0 24 24"
                                          >
                                            <path
                                              strokeLinecap="round"
                                              strokeLinejoin="round"
                                              strokeWidth={2}
                                              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                                            />
                                          </svg>
                                        </a>
                                      )}
                                    </div>
                                  )}
                                </div>

                                {/* Meta strip — created / due / submitted /
                                    evidence counts as one compact row instead
                                    of a separate boxed "Timeline" panel. */}
                                <div className="flex flex-wrap gap-x-6 gap-y-1.5 rounded-lg bg-white px-4 py-3 text-xs sm:text-sm border border-slate-200">
                                  <span className="text-slate-600">
                                    Created{" "}
                                    <strong className="text-slate-900">
                                      {formatDate(car.created_at)}
                                    </strong>
                                  </span>
                                  <span className="text-slate-600">
                                    Due{" "}
                                    <strong className="text-slate-900">
                                      {formatDate(car.due_date)}
                                    </strong>
                                  </span>
                                  {car.immediate_action_required && (
                                    <span className="text-red-700">
                                      Submit by{" "}
                                      <strong>
                                        {formatDate(car.submission_due_at, true)}
                                      </strong>{" "}
                                      · Close by{" "}
                                      <strong>
                                        {formatDate(car.closure_due_at, true)}
                                      </strong>
                                    </span>
                                  )}
                                  <span className="text-slate-600">
                                    Submitted{" "}
                                    <strong className="text-slate-900">
                                      {car.submitted_at
                                        ? formatDate(car.submitted_at)
                                        : "Pending"}
                                    </strong>
                                  </span>
                                  {car.submitted_at && car.submitted_by_email && (
                                    <span className="text-slate-600">
                                      By{" "}
                                      <strong className="text-slate-900">
                                        {car.submitted_by_email}
                                        {channelLabel(car.submission_channel)
                                          ? ` (${channelLabel(car.submission_channel)})`
                                          : ""}
                                      </strong>
                                    </span>
                                  )}
                                  <span className="text-slate-600">
                                    Evidence{" "}
                                    <strong className="text-slate-900">
                                      {car.finding_evidence_count} finding ·{" "}
                                      {car.submission_evidence_count} submission
                                    </strong>
                                  </span>
                                </div>

                                {/* CAR details — one card, stacked rows instead
                                    of three separate boxes. */}
                                <div className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
                                  <div className="px-4 py-3">
                                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                      Related question
                                    </p>
                                    <p className="mt-1 text-sm sm:text-base font-semibold text-slate-900 leading-relaxed">
                                      {car.question || "Corrective action"}
                                    </p>
                                  </div>
                                  <div className="px-4 py-3">
                                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                      Finding
                                    </p>
                                    <p className="mt-1 text-sm text-slate-700 leading-relaxed">
                                      {car.finding || "N/A"}
                                    </p>
                                  </div>
                                  <div className="px-4 py-3">
                                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                      Reason why
                                    </p>
                                    <p className="mt-1 text-sm text-slate-700 leading-relaxed">
                                      {car.reason_why || "N/A"}
                                    </p>
                                  </div>
                                </div>

                                {accessMode === "auditee" && car.can_submit && (
                                  <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs sm:text-sm font-medium text-emerald-800">
                                    This CAR is pending and can be submitted
                                    from the portal.
                                  </p>
                                )}

                                {car.status === "rejected" && car.rejection_reason && (
                                  <div className="rounded-lg border border-rose-200 bg-rose-50 p-4">
                                    <p className="text-xs font-semibold uppercase tracking-wider text-rose-700">
                                      Latest rejection reason
                                    </p>
                                    <p className="mt-2 text-sm text-rose-900 leading-relaxed">
                                      {car.rejection_reason}
                                    </p>
                                  </div>
                                )}

                                {car.related_requirement && (
                                  <RelatedRequirementCard
                                    related={car.related_requirement}
                                  />
                                )}

                                {car.review_history && car.review_history.length > 0 && (
                                  <ReviewHistoryList history={car.review_history} />
                                )}

                                {/* Evidence — one row, two equal-weight lists. */}
                                <div className="grid gap-4 sm:grid-cols-2">
                                  <EvidenceList
                                    title="Finding evidence"
                                    documents={car.finding_evidence}
                                    isLoading={loading}
                                  />
                                  <EvidenceList
                                    title="Submission evidence"
                                    documents={car.submission_evidence}
                                    isLoading={loading}
                                  />
                                </div>
                              </div>
                            </section>
                          ))}
                        </div>
                        )}
                      </article>
                      );
                    })}
                  </section>
                )}
              </>
            )}
          </main>
        </div>

        {submissionCar && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4 py-6 backdrop-blur-sm">
            <div className="relative max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-3xl border border-white bg-white shadow-2xl">
              <div className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      {submissionCar.can_submit ? "Direct submission" : "Review & discuss"}
                    </p>
                    <h3 className="mt-1 text-xl font-bold text-slate-950">
                      {submissionForm?.audit_number ||
                        `CAR ${submissionCar.identifier || submissionCar.car_id}`}
                    </h3>
                    {(submissionForm?.immediate_action_required ??
                      submissionCar.immediate_action_required) && (
                      <span className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-red-300 bg-red-50 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-red-700">
                        Immediate action — 24h submit / 48h close
                      </span>
                    )}
                    <p className="mt-1 text-sm text-slate-600">
                      {submissionCar.can_submit
                        ? "Complete the response here and submit without leaving the portal."
                        : "This CAR can't be submitted from here right now — review its details or ask the AI Assistant about it below."}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={closeSubmissionPanel}
                    className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
                    aria-label="Close submission panel"
                  >
                    <svg
                      className="h-5 w-5"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>
                </div>
              </div>

              <div className="grid gap-6 px-5 py-5 lg:grid-cols-[1.25fr_0.85fr]">
                <div className="space-y-5">
                  {submissionMessage && (
                    <Alert
                      message={stripMessagePrefix(submissionMessage)}
                      tone={messageTone(submissionMessage)}
                      onClose={() => setSubmissionMessage("")}
                    />
                  )}

                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:p-5">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                          Plant
                        </p>
                        <p className="mt-1 font-semibold text-slate-900">
                          {submissionForm?.audit_plant || selectedPlant}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                          Due date
                        </p>
                        <p className="mt-1 font-semibold text-slate-900">
                          {submissionForm?.due_date ||
                            formatDate(submissionCar.due_date)}
                        </p>
                      </div>
                      {(submissionForm?.immediate_action_required ??
                        submissionCar.immediate_action_required) && (
                        <div className="sm:col-span-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
                          <p className="text-xs font-semibold uppercase tracking-wider text-red-700">
                            Immediate action deadlines
                          </p>
                          <p className="mt-1 text-sm font-medium text-red-800">
                            Submit by{" "}
                            {submissionForm?.submission_due_at ||
                              formatDate(submissionCar.submission_due_at, true)}{" "}
                            · Close by{" "}
                            {submissionForm?.closure_due_at ||
                              formatDate(submissionCar.closure_due_at, true)}
                          </p>
                        </div>
                      )}
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                          Finding
                        </p>
                        <p className="mt-1 text-sm text-slate-700 leading-relaxed">
                          {submissionForm?.finding ||
                            submissionCar.finding ||
                            "N/A"}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                          Reason why
                        </p>
                        <p className="mt-1 text-sm text-slate-700 leading-relaxed">
                          {submissionForm?.reason_why ||
                            submissionCar.reason_why ||
                            "N/A"}
                        </p>
                      </div>
                    </div>
                  </div>

                  {(submissionForm?.rejection_reason ||
                    submissionCar.rejection_reason) &&
                    submissionCar.status === "rejected" && (
                      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 sm:p-5">
                        <p className="text-xs font-semibold uppercase tracking-wider text-rose-700">
                          Latest rejection reason — address this before resubmitting
                        </p>
                        <p className="mt-2 text-sm text-rose-900 leading-relaxed">
                          {submissionForm?.rejection_reason ||
                            submissionCar.rejection_reason}
                        </p>
                      </div>
                    )}

                  {(submissionForm?.related_requirement ||
                    submissionCar.related_requirement) && (
                    <RelatedRequirementCard
                      related={
                        submissionForm?.related_requirement ||
                        (submissionCar.related_requirement as PortalRelatedRequirement)
                      }
                    />
                  )}

                  {((submissionForm?.review_history?.length ?? 0) > 0 ||
                    (submissionCar.review_history?.length ?? 0) > 0) && (
                    <ReviewHistoryList
                      history={
                        submissionForm?.review_history ||
                        submissionCar.review_history ||
                        []
                      }
                    />
                  )}

                  {/* Corrective Action header -- only shown alongside a
                      linked immediate section, so the two read as clearly
                      separate parts instead of one undifferentiated form. */}
                  {submissionForm?.linked_action && (
                    <div className="rounded-2xl border-2 border-blue-200 bg-blue-50/40 p-4 sm:p-5">
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="text-base font-bold text-blue-900">
                          Corrective Action — Root Cause Fix
                        </h3>
                        <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700 whitespace-nowrap">
                          Due{" "}
                          {submissionForm?.due_date ||
                            formatDate(submissionCar.due_date)}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-blue-800">
                        This is the permanent fix for the root cause of this
                        finding — separate from the Immediate / Containment
                        Action section further below.
                      </p>
                    </div>
                  )}

                  <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-sm">
                    <div>
                      <label
                        htmlFor="portal-solution"
                        className="mb-2 block text-sm font-semibold text-slate-800"
                      >
                        Implemented solution
                      </label>
                      <textarea
                        id="portal-solution"
                        value={submissionSolution}
                        onChange={(e) => setSubmissionSolution(e.target.value)}
                        rows={5}
                        className="w-full rounded-xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                        placeholder="Describe the corrective action taken..."
                      />
                    </div>

                    <div>
                      <div className="mb-2 flex items-center justify-between gap-3">
                        <label className="block text-sm font-semibold text-slate-800">
                          Root cause using 5 Whys
                        </label>
                        <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
                          {countFilledWhys(submissionRootCauseWhys)}/5 filled
                        </span>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {submissionRootCauseWhys.map((why, index) => (
                          <div
                            key={index}
                            className={index === 4 ? "sm:col-span-2" : ""}
                          >
                            <label
                              htmlFor={`portal-why-${index + 1}`}
                              className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500"
                            >
                              Why {index + 1}
                            </label>
                            <textarea
                              id={`portal-why-${index + 1}`}
                              rows={5}
                              value={why}
                              onChange={(event) => {
                                const next = [...submissionRootCauseWhys];
                                next[index] = event.target.value;
                                setSubmissionRootCauseWhys(next);
                                setSubmissionRootCause(joinWhys(next));
                              }}
                              placeholder={`Cause detail for Why ${index + 1}`}
                              className="w-full resize-y rounded-xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                            />
                          </div>
                        ))}
                      </div>
                      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                        <span>
                          {submissionRootCauseError ||
                            "Fill at least Why 1, Why 2, and Why 3."}
                        </span>
                        <span>
                          {countWhyLines(submissionRootCause)} Why lines
                        </span>
                      </div>
                    </div>

                    <div>
                      <label className="mb-2 block text-sm font-semibold text-slate-800">
                        Related documents
                      </label>
                      <label
                        className={`flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed px-4 py-6 text-center transition ${submissionLoading ? "cursor-not-allowed opacity-60" : "hover:border-blue-400 hover:bg-blue-50"} ${submissionDocumentCount > 0 ? "border-emerald-300 bg-emerald-50/50" : "border-amber-300 bg-amber-50/40"}`}
                      >
                        <svg
                          className={`h-10 w-10 ${submissionDocumentCount > 0 ? "text-emerald-500" : "text-amber-500"}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M12 12v9m4-4l-4 4-4-4"
                          />
                        </svg>
                        <p className="mt-2 text-sm font-semibold text-slate-700">
                          Upload supporting documents
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          PDF, images, Word or Excel files. At least one related
                          document is required.
                        </p>
                        <input
                          type="file"
                          multiple
                          accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx"
                          className="hidden"
                          onChange={handleSubmissionFilesChange}
                          disabled={submissionLoading}
                        />
                      </label>

                      {submissionFiles.length > 0 && (
                        <div className="mt-3 space-y-2">
                          {submissionFiles.map((file, index) => (
                            <div
                              key={`${file.name}-${index}`}
                              className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
                            >
                              <div className="min-w-0">
                                <p className="truncate font-medium text-slate-900">
                                  {file.name}
                                </p>
                                <p className="text-xs text-slate-500">
                                  {formatFileSize(file.size)}
                                </p>
                              </div>
                              <button
                                type="button"
                                onClick={() => removeSubmissionFile(index)}
                                className="rounded-lg px-2 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-50"
                              >
                                Remove
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {correctiveDone && (
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                        ✅ Corrective action submitted.
                      </div>
                    )}
                    <div className="flex flex-col gap-3 sm:flex-row">
                      <button
                        type="button"
                        onClick={submitPortalCar}
                        disabled={
                          submissionLoading ||
                          reassignedNow ||
                          correctiveDone ||
                          !submissionCar?.can_submit ||
                          Boolean(submissionRootCauseError) ||
                          !submissionSolution.trim() ||
                          submissionDocumentCount < 1
                        }
                        className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-900 via-blue-800 to-cyan-700 px-4 py-3 text-sm font-semibold text-white shadow-lg transition hover:shadow-xl disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
                      >
                        {submissionLoading ? (
                          <span className="flex items-center gap-2">
                            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-r-transparent" />
                            Submitting...
                          </span>
                        ) : correctiveDone ? (
                          "Submitted"
                        ) : (
                          "Submit CAR"
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={closeSubmissionPanel}
                        disabled={submissionLoading}
                        className="rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>

                  {/* Immediate / Containment Action — linked, separate deadline,
                      no 5-Whys required. Rendered only when this finding has
                      a linked immediate row. */}
                  {submissionForm?.linked_action && (
                    <div className="space-y-4 rounded-2xl border-2 border-red-200 bg-red-50/40 p-4 sm:p-5">
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="text-sm font-bold text-red-900">
                          Immediate / Containment Action — due within 48h
                        </h3>
                        {submissionForm.linked_action.closure_due_at && (
                          <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-700 whitespace-nowrap">
                            Close by {submissionForm.linked_action.closure_due_at}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-red-800">
                        Separate from the corrective action above: describe the
                        immediate containment action taken to control the issue
                        right away. No root-cause analysis is required here.
                      </p>

                      {immSubmitted ? (
                        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                          ✅ Immediate action submitted
                          {immSubmittedDate ? ` on ${immSubmittedDate}` : ""}.
                        </div>
                      ) : (
                        <>
                          {immMessage && (
                            <p
                              className={`text-xs font-medium ${immMessage.startsWith(ERROR_PREFIX) ? "text-rose-700" : "text-amber-700"}`}
                            >
                              {immMessage.replace(`${ERROR_PREFIX} `, "").replace(`${SUCCESS_PREFIX} `, "")}
                            </p>
                          )}
                          <div>
                            <label className="mb-2 block text-sm font-semibold text-slate-800">
                              Immediate action taken
                            </label>
                            <textarea
                              value={immSolution}
                              onChange={(e) => setImmSolution(e.target.value)}
                              rows={4}
                              className="w-full rounded-xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-red-500 focus:ring-4 focus:ring-red-100"
                              placeholder="Describe the immediate/containment action taken to control the issue..."
                              disabled={immLoading}
                            />
                          </div>

                          {((submissionForm.linked_action.documents?.length ?? 0) > 0 ||
                            immFiles.length > 0) && (
                            <div className="space-y-2">
                              {submissionForm.linked_action.documents.map((doc) => (
                                <div
                                  key={doc.id}
                                  className="flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-white px-4 py-3 text-sm"
                                >
                                  <div className="min-w-0">
                                    <p className="truncate font-medium text-slate-900">
                                      {doc.filename}
                                    </p>
                                    <p className="text-xs text-slate-500">
                                      {formatFileSize(doc.size)}
                                    </p>
                                  </div>
                                </div>
                              ))}
                              {immFiles.map((file, index) => (
                                <div
                                  key={`${file.name}-${index}`}
                                  className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
                                >
                                  <div className="min-w-0">
                                    <p className="truncate font-medium text-slate-900">
                                      {file.name}
                                    </p>
                                    <p className="text-xs text-slate-500">
                                      {formatFileSize(file.size)}
                                    </p>
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => removeImmFile(index)}
                                    className="rounded-lg px-2 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-50"
                                  >
                                    Remove
                                  </button>
                                </div>
                              ))}
                            </div>
                          )}

                          <label
                            className={`flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed px-4 py-5 text-center transition ${immLoading ? "cursor-not-allowed opacity-60" : "hover:border-red-400 hover:bg-red-50"} border-red-200 bg-white`}
                          >
                            <p className="text-sm font-semibold text-slate-700">
                              Upload supporting documents
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              PDF, images, Word or Excel files.
                            </p>
                            <input
                              type="file"
                              multiple
                              accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx"
                              className="hidden"
                              onChange={handleImmFilesChange}
                              disabled={immLoading}
                            />
                          </label>

                          <button
                            type="button"
                            onClick={submitImmediatePortalCar}
                            disabled={
                              immLoading ||
                              !immSolution.trim() ||
                              ((submissionForm.linked_action.documents?.length ?? 0) === 0 &&
                                immFiles.length === 0)
                            }
                            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-red-600 to-orange-600 px-4 py-3 text-sm font-semibold text-white shadow-lg transition hover:shadow-xl disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
                          >
                            {immLoading ? (
                              <span className="flex items-center gap-2">
                                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-r-transparent" />
                                Submitting...
                              </span>
                            ) : (
                              "Submit Immediate Action"
                            )}
                          </button>
                        </>
                      )}
                    </div>
                  )}

                  {/* Reassign — one-time handoff to someone else, same flow as
                      the standalone CAR form link (CarAccess.tsx). Hidden once
                      already used, locked, or already reassigned. */}
                  {(reassignedNow || submissionForm?.reassigned_at) ? (
                    <div className="rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
                      {reassignedNow
                        ? `Reassigned to ${reassignEmail.trim()} — no further action is needed from you.`
                        : `This CAR has been reassigned${submissionForm?.reassigned_from_email ? ` from ${submissionForm.reassigned_from_email}` : ""} and can no longer be reassigned again.`}
                    </div>
                  ) : (
                    submissionForm?.can_reassign && (
                      <div className="space-y-3 rounded-2xl border border-amber-200 bg-amber-50/60 p-4 sm:p-5">
                        <div>
                          <p className="text-sm font-semibold text-amber-900">
                            Not your responsibility?
                          </p>
                          <p className="mt-1 text-xs text-amber-800">
                            Hand this CAR off to the right person. This can only
                            be done once — they'll get the form link by email.
                          </p>
                        </div>
                        <input
                          type="email"
                          value={reassignEmail}
                          onChange={(e) => setReassignEmail(e.target.value)}
                          placeholder="first.last@example.com"
                          disabled={reassignLoading}
                          className="w-full rounded-lg border border-amber-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-100"
                        />
                        <textarea
                          value={reassignReason}
                          onChange={(e) => setReassignReason(e.target.value)}
                          placeholder="Reason (optional)"
                          rows={2}
                          disabled={reassignLoading}
                          className="w-full resize-none rounded-lg border border-amber-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-100"
                        />
                        {reassignMessage && (
                          <p
                            className={`text-xs ${messageTone(reassignMessage) === "error" ? "text-rose-700" : "text-amber-900"}`}
                          >
                            {stripMessagePrefix(reassignMessage)}
                          </p>
                        )}
                        <button
                          type="button"
                          onClick={reassignPortalCar}
                          disabled={reassignLoading || !reassignEmail.trim()}
                          className="w-full rounded-lg bg-amber-600 py-2.5 text-sm font-semibold text-white transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                        >
                          {reassignLoading ? "Reassigning..." : "Reassign"}
                        </button>
                      </div>
                    )
                  )}

                  {/* Add someone in copy — informational only, no action
                      expected from them; same flow as CarAccess.tsx. */}
                  <div className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:p-5">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">
                        Add someone in copy
                      </p>
                      <p className="mt-1 text-xs text-slate-600">
                        They'll be kept informed of updates on this corrective
                        action, without needing to take action.
                      </p>
                    </div>
                    {(submissionForm?.cc_emails?.length ?? 0) > 0 && (
                      <ul className="space-y-1 text-xs text-slate-700">
                        {submissionForm?.cc_emails?.map((cc) => (
                          <li key={cc} className="flex items-center gap-1.5">
                            <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                            {cc}
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="flex gap-2">
                      <input
                        type="email"
                        value={ccEmailInput}
                        onChange={(e) => setCcEmailInput(e.target.value)}
                        placeholder="first.last@example.com"
                        disabled={ccLoading}
                        className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                      />
                      <button
                        type="button"
                        onClick={addPortalCc}
                        disabled={ccLoading || !ccEmailInput.trim()}
                        className="rounded-lg bg-slate-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                      >
                        {ccLoading ? "Adding..." : "Add"}
                      </button>
                    </div>
                    {ccMessage && (
                      <p
                        className={`text-xs ${messageTone(ccMessage) === "error" ? "text-rose-700" : "text-slate-700"}`}
                      >
                        {stripMessagePrefix(ccMessage)}
                      </p>
                    )}
                  </div>
                </div>

                <aside className="space-y-4 self-start lg:sticky lg:top-[92px]">
                  <button
                    type="button"
                    onClick={() => setGuideOpen(true)}
                    className="flex w-full items-center justify-between gap-3 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-semibold text-blue-800 shadow-sm transition hover:border-blue-300 hover:bg-blue-100"
                  >
                    <span className="flex items-center gap-2">
                      <svg className="h-5 w-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"
                        />
                      </svg>
                      AI Assistant user guide
                    </span>
                    <span className="text-xs uppercase tracking-wider">Open</span>
                  </button>

                  <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 sm:p-5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-amber-700">
                      Auditor's evidence
                    </p>
                    <p className="mt-1 text-sm text-amber-800">
                      {(submissionForm?.finding_evidence || []).length} document
                      {(submissionForm?.finding_evidence || []).length === 1 ? "" : "s"} the
                      auditor attached to this finding.
                    </p>
                    <div className="mt-4 space-y-2">
                      {(submissionForm?.finding_evidence || []).length === 0 ? (
                        <p className="text-sm text-amber-700">
                          No evidence documents were attached by the auditor.
                        </p>
                      ) : (
                        submissionForm?.finding_evidence.map((doc) => (
                          <a
                            key={doc.id}
                            href={doc.file_url}
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center justify-between gap-3 rounded-xl border border-white bg-white px-3 py-3 text-sm shadow-sm transition hover:border-amber-300 hover:bg-amber-50"
                          >
                            <span className="min-w-0 flex-1 truncate font-medium text-slate-900">
                              {doc.filename}
                            </span>
                            <span className="text-xs font-semibold uppercase tracking-wider text-amber-700">
                              Open
                            </span>
                          </a>
                        ))
                      )}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:p-5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Existing documents
                    </p>
                    <p className="mt-1 text-sm text-slate-600">
                      {submissionDocumentCount} document
                      {submissionDocumentCount === 1 ? "" : "s"} available for
                      this CAR.
                    </p>
                    <div className="mt-4 space-y-2">
                      {(submissionForm?.documents || []).length === 0 ? (
                        <p className="text-sm text-slate-500">
                          No existing related documents loaded yet.
                        </p>
                      ) : (
                        submissionForm?.documents.map((doc) => (
                          <a
                            key={doc.id}
                            href={doc.file_url}
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center justify-between gap-3 rounded-xl border border-white bg-white px-3 py-3 text-sm shadow-sm transition hover:border-blue-200 hover:bg-blue-50"
                          >
                            <span className="min-w-0 flex-1 truncate font-medium text-slate-900">
                              {doc.filename}
                            </span>
                            <span className="text-xs font-semibold uppercase tracking-wider text-blue-700">
                              Open
                            </span>
                          </a>
                        ))
                      )}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 sm:p-5 text-sm text-blue-900">
                    <p className="font-semibold">Submission rules</p>
                    <ul className="mt-3 space-y-2 text-blue-800">
                      <li>At least 3 Why statements are required.</li>
                      <li>At least one related document is required.</li>
                      <li>Only pending or rejected CARs can be submitted.</li>
                    </ul>
                  </div>
                </aside>
              </div>
            </div>
          </div>
        )}
      </div>

      {guideOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/60 px-4 py-6 backdrop-blur-sm">
          <div className="flex h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border border-white bg-white shadow-2xl">
            <div className="flex flex-col gap-4 bg-gradient-to-r from-blue-900 via-blue-800 to-cyan-700 px-6 py-5 text-white sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-cyan-200">
                  Help &amp; Resources
                </p>
                <h3 className="mt-1 text-2xl font-bold">User Guide</h3>
                <p className="mt-1 max-w-xl text-sm text-blue-100">
                  Step-by-step guide to the AI Assistant. Read it here, open it in a new tab, or
                  download a copy.
                </p>
              </div>
              <div className="flex flex-shrink-0 items-center gap-2">
                <a
                  href={CHATBOT_USER_GUIDE_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-full border border-white/30 bg-white/10 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-white/20"
                >
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
                    />
                  </svg>
                  Open in new tab
                </a>
                <a
                  href={CHATBOT_USER_GUIDE_URL}
                  download
                  className="inline-flex items-center gap-1.5 rounded-full border border-white/30 bg-white/10 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-white/20"
                >
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 12m0 0l4.5-4.5M12 12V3"
                    />
                  </svg>
                  Download PDF
                </a>
                <button
                  type="button"
                  onClick={() => setGuideOpen(false)}
                  aria-label="Close"
                  className="rounded-full p-1.5 text-white/80 transition hover:bg-white/15 hover:text-white"
                >
                  <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                    <path
                      fillRule="evenodd"
                      d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              </div>
            </div>
            <iframe
              src={CHATBOT_USER_GUIDE_URL}
              title="AI Assistant User Guide"
              className="min-h-0 flex-1 bg-slate-100"
            />
          </div>
        </div>
      )}

      {step === "audits" && activeSession && (
        <>
          <button
            type="button"
            onClick={() => setChatOpen((prev) => !prev)}
            aria-label={chatOpen ? "Close AI assistant" : "Open AI assistant"}
            className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-blue-900 via-blue-800 to-cyan-700 text-white shadow-xl transition hover:scale-105 hover:shadow-2xl"
          >
            {chatOpen ? (
              <svg
                className="h-6 w-6"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                  clipRule="evenodd"
                />
              </svg>
            ) : (
              <svg
                className="h-6 w-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8-1.108 0-2.166-.180-3.146-.510L3 21l1.606-4.286C3.59 15.462 3 13.792 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                />
              </svg>
            )}
          </button>

          <div
            style={{ width: chatWidth, maxWidth: "100vw" }}
            className={`fixed inset-y-0 right-0 z-50 flex transform flex-col bg-white shadow-2xl ${
              isResizingChat ? "" : "transition-transform duration-300 ease-out"
            } ${chatOpen ? "translate-x-0" : "translate-x-full"}`}
          >
            <div
              onMouseDown={() => setIsResizingChat(true)}
              className="group absolute inset-y-0 left-0 z-10 w-1.5 cursor-col-resize touch-none select-none"
              aria-hidden="true"
            >
              <div
                className={`h-full w-full transition-colors ${
                  isResizingChat ? "bg-blue-500" : "bg-transparent group-hover:bg-blue-300"
                }`}
              />
            </div>
            <div className="flex items-center justify-between gap-3 bg-gradient-to-r from-blue-900 via-blue-800 to-cyan-700 px-5 py-4 text-white">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/15">
                  <svg
                    className="h-5 w-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8-1.108 0-2.166-.180-3.146-.510L3 21l1.606-4.286C3.59 15.462 3 13.792 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                    />
                  </svg>
                </span>
                <p className="text-sm font-bold leading-tight">AI Assistant</p>
              </div>
              <div className="flex items-center gap-1">
                {submissionCar && (
                  <button
                    type="button"
                    onClick={handleGenerateDraft}
                    disabled={draftLoading}
                    title="Generate an editable draft of the 5-Whys and Implemented Solution from this conversation"
                    className="rounded-full border border-white/30 bg-white/10 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {draftLoading ? "Generating..." : "Generate draft"}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setGuideOpen(true)}
                  title="Open the AI Assistant user guide"
                  className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border border-white/30 bg-white/10 text-white transition hover:bg-white/20"
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"
                    />
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={() => setChatOpen(false)}
                  aria-label="Close"
                  className="rounded-full p-1.5 text-white/80 transition hover:bg-white/15 hover:text-white"
                >
                  <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                    <path
                      fillRule="evenodd"
                      d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              </div>
            </div>

            <div
              className={`flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5 text-xs font-semibold ${
                submissionCar
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : "border-amber-200 bg-amber-50 text-amber-800"
              }`}
            >
              <span className="flex items-center gap-1.5">
                <span
                  className={`h-2 w-2 rounded-full ${submissionCar ? "bg-emerald-500" : "bg-amber-500"}`}
                />
                {submissionCar
                  ? `Focused on CAR ${submissionCar.identifier || submissionCar.car_id} — this conversation counts toward its draft`
                  : "General mode — not linked to a specific CAR. Messages here won't count toward any CAR's draft."}
              </span>
              <select
                value={submissionCar?.car_id ?? ""}
                onChange={(e) => focusChatOnCar(e.target.value)}
                className="rounded-md border border-current bg-white/70 px-2 py-1 text-xs font-semibold text-slate-800"
              >
                <option value="">General (no specific CAR)</option>
                {/* Every visible CAR is selectable here — focusing the chat on
                    one is a "discuss/view" action, not a "submit" action, so
                    it must not be limited to can_submit CARs (which is always
                    false in manager mode, and false once a CAR is no longer
                    pending/rejected). */}
                {allPortalCars.map((c) => (
                  <option key={c.car_id} value={c.car_id}>
                    {c.identifier || c.car_id} — {c.audit_number}
                  </option>
                ))}
              </select>
            </div>

            <div
              ref={chatScrollRef}
              className="flex-1 space-y-3 overflow-y-auto bg-slate-50 p-4"
            >
              {visibleChatMessages.length === 0 ? (
                <div className="space-y-3 rounded-2xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-700">
                  <p className="font-semibold text-slate-900">
                    👋 Hi, I'm your AI assistant for corrective actions.
                  </p>
                  <p>Here's how I can help:</p>
                  <ul className="list-disc space-y-1.5 pl-5 text-slate-600">
                    <li>
                      Explain what a finding actually means and which
                      requirement (standard or customer-specific) it relates
                      to.
                    </li>
                    <li>
                      Coach you step by step through a real investigation —
                      root cause, containment, corrective action — without
                      ever writing the answer for you.
                    </li>
                    <li>Answer questions about your CARs, e.g. "what's pending for me?".</li>
                  </ul>
                  <p className="rounded-xl bg-blue-50 px-3 py-2 text-blue-800">
                    <span className="font-semibold">To work on a specific CAR:</span>{" "}
                    pick it from the dropdown above (or click "Submit in
                    portal" on the CAR list), then chat here about that
                    finding. Once we've covered the investigation, click{" "}
                    <span className="font-semibold">"Generate draft"</span> at
                    the top to get an editable draft of your 5-Whys and
                    Implemented Solution — review and edit it before
                    submitting.
                  </p>
                </div>
              ) : (
                visibleChatMessages.map((msg, index) => (
                  <div
                    key={index}
                    className={`flex items-end gap-2 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
                  >
                    <span
                      className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                        msg.role === "user"
                          ? "bg-blue-800 text-white"
                          : "bg-cyan-100 text-cyan-800"
                      }`}
                    >
                      {msg.role === "user" ? "You" : "AI"}
                    </span>
                    <div
                      className={`rounded-2xl px-4 py-2.5 text-sm shadow-sm ${
                        msg.role === "user"
                          ? "max-w-[75%] whitespace-pre-wrap rounded-br-sm bg-blue-800 text-white"
                          : "max-w-[92%] rounded-bl-sm border border-slate-200 bg-white text-slate-800"
                      }`}
                    >
                      {msg.role === "assistant" ? (
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={chatMarkdownComponents}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      ) : (
                        msg.content
                      )}
                    </div>
                  </div>
                ))
              )}
              {chatSending && (
                <div className="flex items-end gap-2">
                  <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-cyan-100 text-xs font-semibold text-cyan-800">
                    AI
                  </span>
                  <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-white px-4 py-3 shadow-sm">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
                  </div>
                </div>
              )}

              {draftLoading && !chatSending && (
                <div className="rounded-2xl border border-dashed border-blue-300 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                  Generating a draft from this conversation...
                </div>
              )}

              {draftError && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-600">
                  {draftError}
                </div>
              )}

              {pendingDraft && (
                <div className="space-y-3 rounded-2xl border-2 border-dashed border-blue-300 bg-blue-50/60 p-4 text-sm text-slate-800 shadow-sm">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-bold uppercase tracking-wider text-blue-700">
                      Draft — review before inserting
                    </p>
                    <span
                      className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                        pendingDraft.overall_ready
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      {pendingDraft.overall_ready
                        ? "Looks audit-ready"
                        : "Needs more investigation"}
                    </span>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-slate-600">5 Whys</p>
                    {pendingDraft.whys.length === 0 ? (
                      <p className="mt-1 text-slate-500">No whys generated yet.</p>
                    ) : (
                      <ol className="mt-1 list-decimal space-y-2 pl-4">
                        {pendingDraft.whys.map((why, i) => (
                          <li key={i}>
                            <DraftEntryView entry={why} />
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-slate-600">
                      Implemented solution
                    </p>
                    <div className="mt-1">
                      <DraftEntryView
                        entry={pendingDraft.implemented_solution}
                        emptyLabel="Not discussed yet."
                      />
                    </div>
                  </div>

                  <p className="text-xs text-slate-500">
                    This is only a starting point synthesized from your own answers above — the assistant flags what still needs work but never invents facts on your behalf. Review and edit before submitting.
                  </p>

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={insertDraftIntoForm}
                      className="rounded-lg bg-blue-800 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-900"
                    >
                      Insert into form
                    </button>
                    <button
                      type="button"
                      onClick={discardDraft}
                      className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50"
                    >
                      Discard
                    </button>
                  </div>
                </div>
              )}
            </div>

            {chatError && (
              <p className="border-t border-rose-100 bg-rose-50 px-4 py-2 text-xs text-rose-600">
                {chatError}
              </p>
            )}

            {chatUploadError && (
              <p className="border-t border-rose-100 bg-rose-50 px-4 py-2 text-xs text-rose-600">
                {chatUploadError}
              </p>
            )}

            {submissionCar && chatDocuments.length > 0 && (
              <div className="flex flex-wrap gap-1.5 border-t border-slate-100 bg-slate-50 px-4 py-2">
                {chatDocuments.map((doc) => (
                  <span
                    key={doc.id}
                    title={`${formatFileSize(doc.size)}${doc.truncated ? " · truncated to first portion" : ""}`}
                    className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600"
                  >
                    📎 {doc.filename}
                  </span>
                ))}
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                sendChatbotMessage();
              }}
              className="flex items-center gap-2 border-t border-slate-200 bg-white p-3"
            >
              <input
                ref={chatFileInputRef}
                type="file"
                accept={CHATBOT_DOCUMENT_ACCEPT}
                onChange={handleChatFileSelected}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => chatFileInputRef.current?.click()}
                disabled={chatUploading || !submissionCar}
                title={
                  !submissionCar
                    ? "Focus the chat on a specific CAR to attach a document"
                    : "Attach a document (PDF, Word, or text) for this CAR — e.g. a customer requirement"
                }
                aria-label="Attach document"
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border border-slate-200 text-slate-500 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {chatUploading ? (
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                ) : (
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M21.44 11.05l-9.19 9.19a5 5 0 01-7.07-7.07l9.19-9.19a3.5 3.5 0 014.95 4.95l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"
                    />
                  </svg>
                )}
              </button>
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Type your message..."
                disabled={chatSending}
                className="flex-1 rounded-full border border-slate-200 px-4 py-2.5 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
              />
              <button
                type="submit"
                disabled={chatSending || !chatInput.trim()}
                aria-label="Send message"
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-900 to-cyan-700 text-white shadow-md transition hover:shadow-lg disabled:cursor-not-allowed disabled:from-slate-300 disabled:to-slate-300"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 19V5m0 0l-6 6m6-6l6 6"
                  />
                </svg>
              </button>
            </form>
          </div>
        </>
      )}
    </div>
  );
}
