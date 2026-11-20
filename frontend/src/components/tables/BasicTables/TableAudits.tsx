import { useEffect, useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "../../ui/table";
import AuditHistoryModal from "../../modals/AuditHistoryModal";
import RescheduleAuditModal from "../../modals/RescheduleModal";
import ManageAuditeesModal from "../../modals/ManageAuditeesModal";
import CancelAuditModal from "../../modals/CancelAuditModal";
import AuditPlanningModal from "../../modals/AuditPlanningModal";
import { Modal } from "../../ui/modal";
import {
  ChevronDownIcon,
  ClipboardDocumentListIcon,
  DocumentTextIcon,
} from "@heroicons/react/24/solid";
import { motion, AnimatePresence } from "framer-motion";
import { useSelector } from "react-redux";
import type { AxiosError } from "axios";
import Pagination from "../../ui/pagination/pagination";
import { toast } from "react-hot-toast";
import { useAppDispatch } from "../../../redux/hooks";
import CompactReportActions from "../../report/CompactReportActions";
import PDFPreviewModal, {
  type ReportVariant,
} from "../../report/PDFPreviewModal";
import SendReportEmailModal from "../../report/SendReportEmailModal";
import {
  AlertCircle,
  Ban,
  Calendar,
  CheckCircle,
  Clock,
  FileQuestion,
  LucideIcon,
  RefreshCw,
  User,
  Users,
  XCircle,
} from "lucide-react";
import { Audit } from "../../../redux/audit/audit-types";
import { RootState } from "../../../redux/store";
import axiosInstance from "../../../services/axiosInstance";
import { apiSendAuditPlanningCalendar } from "../../../redux/audit/audit";
import AuditCARsModal from "../../audit/AuditCarsModal";
import AuditAnswersModal from "../../audit/AuditAnswersModal";
import { deleteAudit } from "../../../redux/audit/audit-slice";

interface TableAuditsProps {
  audits: Audit[];
  statusFilter?: string;
}

interface GeneratingStatus {
  [auditId: number]: boolean;
}

const TOAST_STYLE_BASE = { borderRadius: "12px", padding: "14px" };
const TOAST_DARK = {
  ...TOAST_STYLE_BASE,
  background: "#0b2c44",
  color: "#fff",
};
const TOAST_SUCCESS = {
  ...TOAST_STYLE_BASE,
  background: "#059669",
  color: "#fff",
};
const TOAST_ERROR = {
  ...TOAST_STYLE_BASE,
  background: "#dc2626",
  color: "#fff",
};
const TOAST_INFO = {
  ...TOAST_STYLE_BASE,
  background: "#064273",
  color: "#fff",
};

const getApiErrorMessage = (error: unknown, fallback: string) => {
  const axiosErr = error as AxiosError<{ detail?: string }>;
  return (
    axiosErr?.response?.data?.detail ||
    (error instanceof Error ? error.message : fallback)
  );
};

export default function TableAudits({
  audits = [],
  statusFilter = "",
}: TableAuditsProps) {
  const dispatch = useAppDispatch();
  const [planningAudit, setPlanningAudit] = useState<Audit | null>(null);
  const [rescheduleAudit, setRescheduleAudit] = useState<Audit | null>(null);
  const [manageAuditeesAudit, setManageAuditeesAudit] = useState<Audit | null>(
    null,
  );
  const [cancelAuditTarget, setCancelAuditTarget] = useState<Audit | null>(
    null,
  );
  const [deleteAuditTarget, setDeleteAuditTarget] = useState<Audit | null>(null);
  const [historyAudit, setHistoryAudit] = useState<Audit | null>(null);
  const [showPlanned, setShowPlanned] = useState(true);
  const [showCompleted, setShowCompleted] = useState(false);
  const [showOngoing, setShowOngoing] = useState(true);
  const [showCancelled, setShowCancelled] = useState(false);
  const [carsModalAudit, setCarsModalAudit] = useState<Audit | null>(null);
  const [answersModalAudit, setAnswersModalAudit] = useState<Audit | null>(
    null,
  );
  const [deletingAudit, setDeletingAudit] = useState(false);

  const [generatingReports, setGeneratingReports] = useState<GeneratingStatus>(
    {},
  );
  const [localReportStatus, setLocalReportStatus] = useState<{
    [auditId: number]: { report_exists: boolean };
  }>({});

  // PDF preview
  const [pdfPreviewOpen, setPdfPreviewOpen] = useState(false);
  const [previewPdfUrl, setPreviewPdfUrl] = useState("");
  const [currentPreviewAudit, setCurrentPreviewAudit] = useState<Audit | null>(
    null,
  );
  const [previewVariant, setPreviewVariant] =
    useState<ReportVariant>("standard");

  // Email
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [currentEmailAudit, setCurrentEmailAudit] = useState<Audit | null>(
    null,
  );
  const [sendingEmails, setSendingEmails] = useState<{
    [auditId: number]: boolean;
  }>({});
  const [emailsSent, setEmailsSent] = useState<{ [auditId: number]: boolean }>(
    {},
  );
  const [auditOverrides, setAuditOverrides] = useState<Record<number, Audit>>(
    {},
  );
  const [syncingCalendar, setSyncingCalendar] = useState<{
    [auditId: number]: boolean;
  }>({});

  const user = useSelector((state: RootState) => state.auth.user);
  const authRoles = useSelector((state: RootState) => state.auth.role || []);
  const normalizedRoles = authRoles.map((role: string) =>
    String(role).trim().toLowerCase(),
  );
  const isAuditor = normalizedRoles.includes("auditor");
  const visibleAudits = audits.map(
    (audit) => auditOverrides[audit.id] ?? audit,
  );

  useEffect(() => {
    const normalized = String(statusFilter || "")
      .trim()
      .toLowerCase();
    if (!normalized) {
      setShowPlanned(true);
      setShowOngoing(true);
      setShowCompleted(false);
      setShowCancelled(false);
      return;
    }

    setShowPlanned(
      normalized === "planned_or_rescheduled" ||
        normalized === "planned" ||
        normalized === "rescheduled",
    );
    setShowOngoing(normalized === "waiting_for_corrective_actions");
    setShowCompleted(normalized === "completed");
    setShowCancelled(normalized === "cancelled");
  }, [statusFilter]);

  // ── Helpers ────────────────────────────────────────────────────────────────

  const normalizedStatus = (s?: string) => (s ?? "").toLowerCase();
  const displayStatus = (s?: string) =>
    (s ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  type AuditStatus =
    | "planned"
    | "completed"
    | "rescheduled"
    | "waiting_for_corrective_actions"
    | "cancelled";

  interface StatusConfig {
    icon: LucideIcon;
    classes: string;
    dot: string;
  }

  const STATUS_CONFIGS: Record<AuditStatus, StatusConfig> = {
    planned: {
      icon: Calendar,
      classes:
        "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800/60 dark:text-slate-200 dark:border-slate-700",
      dot: "bg-slate-500",
    },
    completed: {
      icon: CheckCircle,
      classes:
        "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-800/60",
      dot: "bg-emerald-500",
    },
    rescheduled: {
      icon: Clock,
      classes:
        "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800",
      dot: "bg-amber-500",
    },
    waiting_for_corrective_actions: {
      icon: AlertCircle,
      classes:
        "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:border-orange-800/50",
      dot: "bg-red-500 animate-pulse",
    },
    cancelled: {
      icon: XCircle,
      classes:
        "bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-900/30 dark:text-gray-400 dark:border-gray-700",
      dot: "bg-gray-400",
    },
  };

  const getStatusConfig = (status?: string): StatusConfig =>
    STATUS_CONFIGS[normalizedStatus(status) as AuditStatus] ?? {
      icon: FileQuestion,
      classes:
        "bg-gray-50 text-gray-500 border-gray-200 dark:bg-gray-900/20 dark:text-gray-400 dark:border-gray-700",
      dot: "bg-gray-400",
    };

  const canHaveReport = (audit: Audit) => {
    const s = normalizedStatus(audit.status);
    return s !== "planned" && s !== "rescheduled" && s !== "cancelled";
  };

  const getEffectiveReportExists = (audit: Audit) =>
    localReportStatus[audit.id]?.report_exists ?? audit.report_exists ?? false;

  const handleDeleteAudit = async () => {
    if (!deleteAuditTarget) return;
    try {
      setDeletingAudit(true);
      await dispatch(deleteAudit(deleteAuditTarget.id)).unwrap();
      toast.success("Audit deleted successfully.");
      setDeleteAuditTarget(null);
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, "Failed to delete audit."));
    } finally {
      setDeletingAudit(false);
    }
  };

  // ── Splits ─────────────────────────────────────────────────────────────────

  const plannedAudits = visibleAudits.filter(
    (a) =>
      normalizedStatus(a.status) === "planned" ||
      normalizedStatus(a.status) === "rescheduled",
  );
  const ongoingAudits = visibleAudits.filter(
    (a) => normalizedStatus(a.status) === "waiting_for_corrective_actions",
  );
  const completedAudits = visibleAudits.filter(
    (a) => normalizedStatus(a.status) === "completed",
  );
  const cancelledAudits = visibleAudits.filter(
    (a) => normalizedStatus(a.status) === "cancelled",
  );
  const waitingActionsCount = visibleAudits.filter(
    (a) => normalizedStatus(a.status) === "waiting_for_corrective_actions",
  ).length;

  // ── Pagination ─────────────────────────────────────────────────────────────

  const [plannedPage, setPlannedPage] = useState(1);
  const [plannedPageSize, setPlannedPageSize] = useState(5);
  const [ongoingPage, setOngoingPage] = useState(1);
  const [ongoingPageSize, setOngoingPageSize] = useState(5);
  const [completedPage, setCompletedPage] = useState(1);
  const [completedPageSize, setCompletedPageSize] = useState(5);
  const [cancelledPage, setCancelledPage] = useState(1);
  const [cancelledPageSize, setCancelledPageSize] = useState(5);

  const totalPagesPlanned = Math.ceil(plannedAudits.length / plannedPageSize);
  const paginatedPlanned = plannedAudits.slice(
    (plannedPage - 1) * plannedPageSize,
    plannedPage * plannedPageSize,
  );
  const totalPagesOngoing = Math.ceil(ongoingAudits.length / ongoingPageSize);
  const paginatedOngoing = ongoingAudits.slice(
    (ongoingPage - 1) * ongoingPageSize,
    ongoingPage * ongoingPageSize,
  );
  const totalPagesCompleted = Math.ceil(
    completedAudits.length / completedPageSize,
  );
  const paginatedCompleted = completedAudits.slice(
    (completedPage - 1) * completedPageSize,
    completedPage * completedPageSize,
  );
  const totalPagesCancelled = Math.ceil(
    cancelledAudits.length / cancelledPageSize,
  );
  const paginatedCancelled = cancelledAudits.slice(
    (cancelledPage - 1) * cancelledPageSize,
    cancelledPage * cancelledPageSize,
  );

  // ── Report actions ─────────────────────────────────────────────────────────

  const handlePreviewPDF = async (
    audit: Audit,
    variant: ReportVariant = "standard",
  ) => {
    if (!canHaveReport(audit)) {
      toast.error("No report available until the audit is executed.", {
        style: TOAST_ERROR,
      });
      return;
    }
    const loadingToast = toast.loading(
      variant === "complete"
        ? `Building complete report for ${audit.audit_number}…`
        : `Loading preview for ${audit.audit_number}…`,
      { style: TOAST_DARK },
    );
    try {
      // Unique query string: a report regenerated at the same URL must never
      // be served from a browser-cached copy of the previous PDF. The
      // complete report (with Silent Box CARs) is built on demand, never
      // stored.
      const response = await axiosInstance.get(
        variant === "complete"
          ? `/reports/${audit.id}/complete-report-pdf`
          : `/reports/${audit.id}/preview-pdf`,
        { responseType: "blob", params: { v: Date.now() } },
      );
      setPreviewVariant(variant);
      const nextUrl = URL.createObjectURL(response.data);
      setPreviewPdfUrl((currentUrl) => {
        if (currentUrl) {
          URL.revokeObjectURL(currentUrl);
        }
        return nextUrl;
      });
      setCurrentPreviewAudit(audit);
      setPdfPreviewOpen(true);
      toast.success("Preview ready.", {
        id: loadingToast,
        style: TOAST_SUCCESS,
      });
    } catch (error: unknown) {
      const msg =
        (error as AxiosError)?.response?.status === 404
          ? "Report not found. Generate it first."
          : "Failed to load preview. Please try again.";
      toast.error(msg, { id: loadingToast, style: TOAST_ERROR });
    }
  };

  const downloadReport = async (auditId: number, auditNumber: string) => {
    const loadingToast = toast.loading("Downloading report…", {
      style: TOAST_DARK,
    });
    try {
      const response = await axiosInstance.get(
        `/reports/${auditId}/download-report`,
        { responseType: "blob", params: { v: Date.now() } },
      );
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `audit_report_${auditNumber}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Report downloaded.", {
        id: loadingToast,
        style: TOAST_INFO,
      });
    } catch {
      toast.error("Failed to download report.", {
        id: loadingToast,
        style: TOAST_ERROR,
      });
    }
  };

  const sendEmailAutomatically = async (audit: Audit) => {
    const recipients = audit.auditees ?? [];
    if (!recipients.length) {
      toast.error("No recipients found for this audit.", {
        style: TOAST_ERROR,
      });
      return;
    }
    const auditId = audit.id;
    setSendingEmails((p) => ({ ...p, [auditId]: true }));
    const emailToast = toast.loading(
      `Sending report to ${recipients.length + 1} recipient(s)…`,
      { style: TOAST_DARK },
    );
    try {
      const response = await axiosInstance.post(
        `/reports/${auditId}/send-email`,
        {
          recipients,
          include_auditor: true,
        },
      );
      if (response.data.success) {
        setEmailsSent((p) => ({ ...p, [auditId]: true }));
        toast.success(
          `Report sent to ${response.data.sent_to?.length ?? 0} recipient(s).`,
          { id: emailToast, style: TOAST_SUCCESS },
        );
      } else throw new Error();
    } catch (error: unknown) {
      toast.error(
        getApiErrorMessage(error, "Failed to send report via email."),
        {
          id: emailToast,
          style: TOAST_ERROR,
        },
      );
    } finally {
      setSendingEmails((p) => ({ ...p, [auditId]: false }));
    }
  };

  const generateReport = async (audit: Audit) => {
    if (!canHaveReport(audit)) {
      toast.error("Report can only be generated after audit execution.", {
        style: TOAST_ERROR,
      });
      return;
    }
    const auditId = audit.id;
    setGeneratingReports((p) => ({ ...p, [auditId]: true }));
    const loadingToast = toast.loading(
      `Generating report for ${audit.audit_number}…`,
      { style: TOAST_DARK },
    );
    try {
      const response = await axiosInstance.post(
        `/reports/${auditId}/generate-report`,
      );
      if (response.data.success && response.data.report_ready) {
        setLocalReportStatus((p) => ({
          ...p,
          [auditId]: { report_exists: true },
        }));
        toast.success(
          response.data.is_regeneration
            ? "Report regenerated successfully."
            : "Report generated successfully.",
          { id: loadingToast, style: TOAST_SUCCESS },
        );
        // Only auto-send on first generation. Regenerating an existing
        // report (e.g. after a content fix) must not silently re-email
        // auditees - use the Email button if a resend is actually wanted.
        if (!response.data.is_regeneration) {
          sendEmailAutomatically(audit);
        }
      } else throw new Error();
    } catch (error: unknown) {
      toast.error(getApiErrorMessage(error, "Failed to generate report."), {
        id: loadingToast,
        style: TOAST_ERROR,
      });
    } finally {
      setGeneratingReports((p) => ({ ...p, [auditId]: false }));
    }
  };

  const handleOpenEmailModal = (audit: Audit) => {
    const reportExists = getEffectiveReportExists(audit);
    if (!canHaveReport(audit)) {
      toast.error("Email can only be sent after a report exists.", {
        style: TOAST_ERROR,
      });
      return;
    }
    if (!reportExists) {
      toast.error("Generate the report first before sending.", {
        style: TOAST_ERROR,
      });
      return;
    }
    setCurrentEmailAudit(audit);
    setEmailModalOpen(true);
  };

  const handleSendEmail = async (
    recipients: string[],
    includeAuditor: boolean,
  ) => {
    if (!currentEmailAudit) return;
    const auditId = currentEmailAudit.id;
    setSendingEmails((p) => ({ ...p, [auditId]: true }));
    const loadingToast = toast.loading(
      `Sending report to ${recipients.length + (includeAuditor ? 1 : 0)} recipient(s)…`,
      { style: TOAST_DARK },
    );
    try {
      const response = await axiosInstance.post(
        `/reports/${auditId}/send-email`,
        {
          recipients,
          include_auditor: includeAuditor,
        },
      );
      if (response.data.success) {
        toast.success(
          `Report sent to ${response.data.sent_to?.length ?? 0} recipient(s).`,
          { id: loadingToast, style: TOAST_SUCCESS },
        );
        setEmailModalOpen(false);
        setCurrentEmailAudit(null);
      } else throw new Error();
    } catch (error: unknown) {
      toast.error(
        getApiErrorMessage(error, "Failed to send report via email."),
        {
          id: loadingToast,
          style: TOAST_ERROR,
        },
      );
    } finally {
      setSendingEmails((p) => ({ ...p, [auditId]: false }));
    }
  };

  // ── Shared sub-components ──────────────────────────────────────────────────

  const UserChip = ({
    email,
    variant = "blue",
  }: {
    email: string;
    variant?: "blue" | "indigo";
  }) => {
    const colorMap = {
      blue: "bg-slate-100 border-slate-200 text-slate-700 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200",
      indigo:
        "bg-blue-50 border-blue-200 text-blue-700 dark:bg-blue-900/30 dark:border-blue-800 dark:text-blue-200",
    };
    return (
      <div className="group relative inline-flex">
        <div
          className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold cursor-default shadow-sm ${colorMap[variant]}`}
        >
          {variant === "blue" ? (
            <User className="h-3 w-3" />
          ) : (
            <Users className="h-3 w-3" />
          )}
          {email.split("@")[0]}
        </div>
        <div className="invisible group-hover:visible absolute left-0 top-full mt-1.5 z-10 rounded-lg bg-gray-900 px-2.5 py-1.5 text-xs text-white shadow-lg whitespace-nowrap dark:bg-gray-700">
          {email}
          <div className="absolute -top-1 left-4 h-2 w-2 rotate-45 bg-gray-900 dark:bg-gray-700" />
        </div>
      </div>
    );
  };

  const AuditeeChips = ({ emails }: { emails?: string[] }) => {
    if (!emails?.length)
      return <span className="text-gray-400 text-xs">—</span>;
    return (
      <div className="flex flex-wrap gap-1">
        {emails.slice(0, 2).map((email, i) => (
          <UserChip key={i} email={email} variant="indigo" />
        ))}
        {emails.length > 2 && (
          <div className="group relative inline-flex">
            <div className="rounded-full border border-gray-200 bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600 cursor-default dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
              +{emails.length - 2}
            </div>
            <div className="invisible group-hover:visible absolute left-0 top-full mt-1.5 z-10 rounded-lg bg-gray-900 px-2.5 py-2 text-xs text-white shadow-lg dark:bg-gray-700">
              {emails.slice(2).map((e, i) => (
                <div key={i} className="py-0.5">
                  {e}
                </div>
              ))}
              <div className="absolute -top-1 left-4 h-2 w-2 rotate-45 bg-gray-900 dark:bg-gray-700" />
            </div>
          </div>
        )}
      </div>
    );
  };

  const StatusBadge = ({ status }: { status?: string }) => {
    const config = getStatusConfig(status);
    const Icon = config.icon;
    return (
      <span
        className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium ${config.classes}`}
      >
        <Icon className="h-3 w-3" />
        {displayStatus(status)}
      </span>
    );
  };

  // ── Column headers ─────────────────────────────────────────────────────────

  const ONGOING_HEADERS = [
    "Audit ID",
    "Type",
    "Questionnaire",
    "Auditor",
    "Auditee",
    "Plant",
    "Sector",
    "Start",
    "End",
    "Status",
    "Actions",
  ];
  const COMPLETED_HEADERS = [
    "Audit ID",
    "Type",
    "Questionnaire",
    "Auditor",
    "Auditee",
    "Plant",
    "Sector",
    "Dates",
    "Score",
    "Report",
  ];

  // ── Rows ───────────────────────────────────────────────────────────────────

  const handleRetryCalendarSync = async (audit: Audit) => {
    setSyncingCalendar((prev) => ({ ...prev, [audit.id]: true }));
    try {
      const result = await apiSendAuditPlanningCalendar(audit.id);
      setAuditOverrides((prev) => ({
        ...prev,
        [audit.id]: {
          ...(prev[audit.id] ?? audit),
          event_created: result.event_created,
          event_id: result.event_id,
        },
      }));
      toast.success(
        result.event_action === "recreated"
          ? "Outlook event was missing and has been recreated."
          : result.event_action === "updated"
            ? "Outlook event synced."
            : "Outlook event created.",
        { style: TOAST_SUCCESS },
      );
    } catch (error: unknown) {
      toast.error(
        getApiErrorMessage(error, "Failed to sync Outlook event."),
        { style: TOAST_ERROR },
      );
    } finally {
      setSyncingCalendar((prev) => ({ ...prev, [audit.id]: false }));
    }
  };

  const renderOngoingRow = (audit: Audit) => {
    const auditId = audit.id;
    const isGenerating = generatingReports[auditId] ?? false;
    const reportExists = getEffectiveReportExists(audit);
    const isSendingEmail = sendingEmails[auditId] ?? false;
    const emailSent = emailsSent[auditId] ?? false;
    const reportAllowed = canHaveReport(audit);
    const isOwner = user?.email === audit?.auditor?.email;
    const canManageAudit = isAuditor && isOwner;
    const auditorRestrictionMessage = !isAuditor
      ? "You are not auditor"
      : "Only the assigned auditor can manage this audit";

    return (
      <TableRow
        key={audit.id}
        className="transition-all hover:bg-slate-50 dark:hover:bg-slate-800/40"
      >
        <TableCell className="px-4 py-3 text-sm font-semibold text-gray-800 dark:text-gray-200 border-r border-gray-100 dark:border-white/5">
          {audit.audit_number}
        </TableCell>
        <TableCell className="px-4 py-3 border-r border-gray-100 dark:border-white/5">
          {audit.questionnaire?.type ? (
            <span className="inline-flex items-center rounded-full border border-[#064273]/20 bg-[#064273]/10 px-2.5 py-0.5 text-xs font-medium text-[#064273] dark:border-[#77b7de]/30 dark:bg-[#064273]/30 dark:text-blue-200">
              {audit.questionnaire.type}
            </span>
          ) : (
            <span className="text-gray-400 text-xs">—</span>
          )}
        </TableCell>
        <TableCell className="px-4 py-3 text-xs text-gray-700 dark:text-gray-300 border-r border-gray-100 dark:border-white/5">
          {audit.questionnaire?.name || "—"}
        </TableCell>
        <TableCell className="px-4 py-3 border-r border-gray-100 dark:border-white/5">
          {audit.auditor?.email ? (
            <div className="flex flex-col gap-1">
              <UserChip email={audit.auditor.email} variant="blue" />
              {audit.second_auditor?.email && (
                <UserChip email={audit.second_auditor.email} variant="blue" />
              )}
            </div>
          ) : (
            "—"
          )}
        </TableCell>
        <TableCell className="px-4 py-3 border-r border-gray-100 dark:border-white/5">
          <AuditeeChips emails={audit.auditees} />
        </TableCell>
        <TableCell className="px-4 py-3 text-xs text-gray-600 dark:text-gray-400 border-r border-gray-100 dark:border-white/5 capitalize">
          {audit.plant || "—"}
        </TableCell>
        <TableCell className="px-4 py-3 text-xs text-gray-600 dark:text-gray-400 border-r border-gray-100 dark:border-white/5">
          {audit.sector || "—"}
        </TableCell>
        <TableCell className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 border-r border-gray-100 dark:border-white/5">
          {audit.planned_start_date || "—"}
        </TableCell>
        <TableCell className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 border-r border-gray-100 dark:border-white/5">
          {audit.planned_end_date || "—"}
        </TableCell>
        <TableCell className="px-4 py-3 border-r border-gray-100 dark:border-white/5">
          <div className="space-y-1">
            <StatusBadge status={audit.status} />
            {normalizedStatus(audit.status) ===
              "waiting_for_corrective_actions" &&
              (audit.finalScore ?? audit.total_score) != null && (
                <span className="inline-flex items-center justify-center rounded-lg border border-[#0f628f]/20 bg-[#0f628f]/10 px-2.5 py-0.5 text-xs font-semibold text-[#0f628f] dark:border-[#85c7ea]/30 dark:bg-[#0f628f]/30 dark:text-sky-200">
                  Score: {audit.finalScore ?? audit.total_score}
                </span>
              )}
            {normalizedStatus(audit.status) === "cancelled" &&
              audit.cancel_reason && (
                <p className="max-w-[220px] text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
                  {audit.cancel_reason}
                </p>
              )}
          </div>
        </TableCell>
        <TableCell className="px-4 py-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {(normalizedStatus(audit.status) === "planned" ||
              normalizedStatus(audit.status) === "rescheduled") && (
              <>
                <button
                  onClick={() => setManageAuditeesAudit(audit)}
                  disabled={!canManageAudit}
                  title={
                    !canManageAudit ? auditorRestrictionMessage : undefined
                  }
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-sky-300 bg-gradient-to-r from-sky-500 to-cyan-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm transition hover:from-sky-600 hover:to-cyan-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Users className="h-3.5 w-3.5" />
                  Auditees
                </button>
                <button
                  onClick={() => setRescheduleAudit(audit)}
                  disabled={!canManageAudit}
                  title={
                    !canManageAudit ? auditorRestrictionMessage : undefined
                  }
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-[#0ABAB5]/40 bg-gradient-to-r from-violet-500 to-purple-600 px-2.5 py-1 text-xs font-semibold text-[#FAF9EE] shadow-sm transition hover:from-violet-600 disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#2bb673]/50 dark:from-violet dark:to-violet/70 dark:text-[#a7f3d0]"
                >
                  <Calendar className="h-3.5 w-3.5" />
                  Reschedule
                </button>
                <button
                  onClick={() => setPlanningAudit(audit)}
                  disabled={!canManageAudit}
                  title={
                    !canManageAudit ? auditorRestrictionMessage : undefined
                  }
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-[#064273]/30 bg-gradient-to-r from-[#064273] to-[#0f628f] px-2.5 py-1 text-xs font-semibold text-white shadow-sm transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Clock className="h-3.5 w-3.5" />
                  Edit
                </button>
                <button
                  onClick={() => setDeleteAuditTarget(audit)}
                  disabled={!canManageAudit}
                  title={
                    !canManageAudit ? auditorRestrictionMessage : undefined
                  }
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-red-300 bg-gradient-to-r from-red-500 to-rose-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm transition hover:from-red-600 hover:to-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  Delete
                </button>
                <button
                  onClick={() => void handleRetryCalendarSync(audit)}
                  disabled={!canManageAudit || syncingCalendar[audit.id]}
                  title={
                    !canManageAudit
                      ? auditorRestrictionMessage
                      : "Recreate/resync the Outlook calendar event for this audit"
                  }
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-amber-300 bg-gradient-to-r from-amber-500 to-orange-500 px-2.5 py-1 text-xs font-semibold text-white shadow-sm transition hover:from-amber-600 hover:to-orange-600 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <RefreshCw
                    className={`h-3.5 w-3.5 ${syncingCalendar[audit.id] ? "animate-spin" : ""}`}
                  />
                  {syncingCalendar[audit.id] ? "Syncing..." : "Retry Sync"}
                </button>
              </>
            )}
            {(normalizedStatus(audit.status) === "planned" ||
              normalizedStatus(audit.status) === "rescheduled") && (
              <button
                onClick={() => setCancelAuditTarget(audit)}
                disabled={!canManageAudit}
                title={!canManageAudit ? auditorRestrictionMessage : undefined}
                className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-red-300 bg-gradient-to-r from-orange-500 to-red-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm transition hover:from-orange-600 hover:to-red-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-800/50 dark:bg-red-900/25 dark:text-red-300 dark:hover:bg-red-900/35"
              >
                <Ban className="h-3.5 w-3.5" />
                Cancel
              </button>
            )}
            <button
              onClick={() => setHistoryAudit(audit)}
              className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-[#FF6363]/40 bg-gradient-to-r  px-2.5 py-1 text-xs font-semibold from-emerald-500 to-green-600 hover:from-emerald-600 hover:to-green-700 text-white shadow-sm transition hover:from-[#6ee7b7]/55 hover:to-[#34d399]/45 dark:border-[#2bb673]/50 dark:from-[#064e3b] dark:to-[#065f46] dark:text-[#a7f3d0]"
            >
              <Clock className="h-3.5 w-3.5" />
              History
            </button>
            {normalizedStatus(audit.status) ===
              "waiting_for_corrective_actions" && (
              <>
                <button
                  onClick={() => setCarsModalAudit(audit)}
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-[#064273]/20 bg-[#064273]/10 px-2.5 py-1 text-xs font-semibold text-[#064273] transition hover:bg-[#064273]/15 dark:border-[#77b7de]/30 dark:bg-[#064273]/30 dark:text-blue-200 dark:hover:bg-[#064273]/40"
                >
                  <DocumentTextIcon className="h-3.5 w-3.5" />
                  View CARs
                </button>
                <button
                  onClick={() => setAnswersModalAudit(audit)}
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-[#064273]/20 bg-[#064273]/10 px-2.5 py-1 text-xs font-semibold text-[#064273] transition hover:bg-[#064273]/15 dark:border-[#77b7de]/30 dark:bg-[#064273]/30 dark:text-blue-200 dark:hover:bg-[#064273]/40"
                >
                  <ClipboardDocumentListIcon className="h-3.5 w-3.5" />
                  View Responses
                </button>
              </>
            )}
            {reportAllowed ? (
              <CompactReportActions
                onGenerate={() => generateReport(audit)}
                onDownload={() => downloadReport(auditId, audit.audit_number)}
                onPreview={() => handlePreviewPDF(audit)}
                onSendEmail={() => handleOpenEmailModal(audit)}
                isGenerating={isGenerating}
                reportExists={reportExists}
                emailSent={emailSent}
                isSendingEmail={isSendingEmail}
                showGenerateActions={isAuditor}
                showEmailAction={isAuditor}
              />
            ) : (
              <span className="text-xs text-gray-400 dark:text-gray-600">
                No report yet
              </span>
            )}
          </div>
        </TableCell>
      </TableRow>
    );
  };

  const renderCompletedRow = (audit: Audit) => {
    const auditId = audit.id;
    const isGenerating = generatingReports[auditId] ?? false;
    const reportExists = getEffectiveReportExists(audit);
    const isSendingEmail = sendingEmails[auditId] ?? false;
    const emailSent = emailsSent[auditId] ?? false;
    const canUseCompletedAuditActions = isAuditor;

    return (
      <TableRow
        key={audit.id}
        className="transition-all hover:bg-slate-50 dark:hover:bg-slate-800/40"
      >
        <TableCell className="px-4 py-3 text-sm font-semibold text-gray-800 dark:text-gray-200 border-r border-gray-100 dark:border-white/5">
          {audit.audit_number}
        </TableCell>
        <TableCell className="px-4 py-3 border-r border-gray-100 dark:border-white/5">
          {audit.questionnaire?.type ? (
            <span className="inline-flex items-center rounded-full border border-[#0f628f]/20 bg-[#0f628f]/10 px-2.5 py-0.5 text-xs font-medium text-[#0f628f] dark:border-[#85c7ea]/30 dark:bg-[#0f628f]/30 dark:text-sky-200">
              {audit.questionnaire.type}
            </span>
          ) : (
            <span className="text-gray-400 text-xs">—</span>
          )}
        </TableCell>
        <TableCell className="px-4 py-3 text-xs text-gray-700 dark:text-gray-300 border-r border-gray-100 dark:border-white/5">
          {audit.questionnaire?.name || "—"}
        </TableCell>
        <TableCell className="px-4 py-3 border-r border-gray-100 dark:border-white/5">
          {audit.auditor?.email ? (
            <div className="flex flex-col gap-1">
              <UserChip email={audit.auditor.email} variant="blue" />
              {audit.second_auditor?.email && (
                <UserChip email={audit.second_auditor.email} variant="blue" />
              )}
            </div>
          ) : (
            "—"
          )}
        </TableCell>
        <TableCell className="px-4 py-3 border-r border-gray-100 dark:border-white/5">
          <AuditeeChips emails={audit.auditees} />
        </TableCell>
        <TableCell className="px-4 py-3 text-xs text-gray-600 dark:text-gray-400 border-r border-gray-100 dark:border-white/5 capitalize">
          {audit.plant || "—"}
        </TableCell>
        <TableCell className="px-4 py-3 text-xs text-gray-600 dark:text-gray-400 border-r border-gray-100 dark:border-white/5">
          {audit.sector || "—"}
        </TableCell>
        <TableCell className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 border-r border-gray-100 dark:border-white/5">
          <div>{audit.planned_start_date || "—"}</div>
          <div className="mt-0.5 text-gray-400 dark:text-gray-600">
            {audit.planned_end_date || "—"}
          </div>
        </TableCell>
        <TableCell className="px-4 py-3 border-r border-gray-100 dark:border-white/5">
          <span className="inline-flex items-center justify-center rounded-lg border border-[#0f628f]/20 bg-[#0f628f]/10 px-3 py-1 text-sm font-semibold text-[#0f628f] dark:border-[#85c7ea]/30 dark:bg-[#0f628f]/30 dark:text-sky-200">
            {audit.finalScore ?? audit.total_score ?? "—"}
          </span>
        </TableCell>
        <TableCell className="px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            {canUseCompletedAuditActions && (
              <button
                onClick={() => setCarsModalAudit(audit)}
                className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-[#064273]/20 bg-[#064273]/10 px-2.5 py-1 text-xs font-semibold text-[#064273] transition hover:bg-[#064273]/15 dark:border-[#77b7de]/30 dark:bg-[#064273]/30 dark:text-blue-200 dark:hover:bg-[#064273]/40"
              >
                <DocumentTextIcon className="h-3.5 w-3.5" />
                View CARs
              </button>
            )}
            <button
              onClick={() => setAnswersModalAudit(audit)}
              className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-[#064273]/20 bg-[#064273]/10 px-2.5 py-1 text-xs font-semibold text-[#064273] transition hover:bg-[#064273]/15 dark:border-[#77b7de]/30 dark:bg-[#064273]/30 dark:text-blue-200 dark:hover:bg-[#064273]/40"
            >
              <ClipboardDocumentListIcon className="h-3.5 w-3.5" />
              View Responses
            </button>
            <CompactReportActions
              onGenerate={() => generateReport(audit)}
              onDownload={() => downloadReport(auditId, audit.audit_number)}
              onPreview={() => handlePreviewPDF(audit)}
              onSendEmail={() => handleOpenEmailModal(audit)}
              isGenerating={isGenerating}
              reportExists={reportExists}
              emailSent={emailSent}
              isSendingEmail={isSendingEmail}
              showGenerateActions={isAuditor}
              showEmailAction={isAuditor}
            />
          </div>
        </TableCell>
      </TableRow>
    );
  };

  // ── Section wrapper ────────────────────────────────────────────────────────

  const SectionHeader = ({
    label,
    count,
    open,
    onToggle,
    variant,
  }: {
    label: string;
    count: number;
    open: boolean;
    onToggle: () => void;
    variant: "indigo" | "emerald";
  }) => {
    const sectionIcon =
      variant === "indigo" ? (
        <Calendar className="h-4 w-4" />
      ) : (
        <CheckCircle className="h-4 w-4" />
      );

    const pillColors = {
      indigo: "bg-white/15 text-[#d6e4ef] dark:bg-white/15 dark:text-[#d6e4ef]",
      emerald:
        "bg-white/15 text-[#d6e4ef] dark:bg-white/15 dark:text-[#d6e4ef]",
    };
    return (
      <button
        onClick={onToggle}
        className={`flex w-full items-center justify-between bg-gradient-to-r px-5 py-4 font-semibold text-[#eef5fb] transition hover:brightness-[1.05] bg-[#184e77] `}
      >
        <span className="flex items-center gap-2.5 text-sm">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-white/15 text-[#d6e4ef] shadow-sm">
            {sectionIcon}
          </span>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${pillColors[variant]}`}
          >
            {count}
          </span>
          {label}
        </span>
        <motion.div
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="rounded-md bg-white/15 p-1"
        >
          <ChevronDownIcon className="h-4 w-4 text-[#d6e4ef]" />
        </motion.div>
      </button>
    );
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5 [font-family:'Manrope',sans-serif]">
      {/* Overview strip */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-2xl border border-[#12293b] bg-gradient-to-br from-[#184e77] to-[#1e6091] px-4 py-3 text-white shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-200/85">
            Total Audits
          </p>
          <p className="mt-1 text-[28px] font-extrabold leading-none tracking-tight">
            {audits.length}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-900 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            Planned / Rescheduled
          </p>
          <p className="mt-1 text-[28px] font-extrabold leading-none tracking-tight">
            {plannedAudits.length}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-900 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            Completed
          </p>
          <p className="mt-1 text-[28px] font-extrabold leading-none tracking-tight">
            {completedAudits.length}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-900 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            Cancelled
          </p>
          <p className="mt-1 text-[28px] font-extrabold leading-none tracking-tight">
            {cancelledAudits.length}
          </p>
        </div>
        <div className="rounded-2xl border border-orange-300/70 bg-gradient-to-br from-orange-700 to-orange-700 px-4 py-3 text-white shadow-sm dark:border-orange-800/60 dark:from-orange-600 dark:to-orange-800">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-white-80/80 dark:text-orange-200/80">
            Need Action
          </p>
          <p className="mt-1 text-[28px] font-extrabold leading-none tracking-tight">
            {waitingActionsCount}
          </p>
        </div>
      </div>

      {/* Planned / rescheduled audits */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ring-1 ring-slate-900/5 dark:border-slate-700 dark:bg-[#0f1722] dark:ring-white/5">
        <SectionHeader
          label="Planned & rescheduled audits"
          count={plannedAudits.length}
          open={showPlanned}
          onToggle={() => setShowPlanned((v) => !v)}
          variant="indigo"
        />

        <AnimatePresence>
          {showPlanned && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: "easeInOut" }}
              className="overflow-hidden border-t border-[#1f4a69]/30 dark:border-[#1f4a69]"
            >
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-[#184e77] dark:bg-[#0f2333]">
                      {ONGOING_HEADERS.map((h, idx) => (
                        <TableCell
                          key={`ongoing-header-${h || "empty"}-${idx}`}
                          isHeader
                          className={`px-4 py-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#d7e5f1] dark:text-[#d7e5f1] ${idx < ONGOING_HEADERS.length - 1 ? "border-r border-[#1f3f58]" : ""}`}
                        >
                          {h}
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody className="divide-y divide-slate-200 dark:divide-slate-700/70">
                    {paginatedPlanned.length > 0 ? (
                      paginatedPlanned.map(renderOngoingRow)
                    ) : (
                      <TableRow>
                        <TableCell
                          colSpan={ONGOING_HEADERS.length}
                          className="py-10 text-center text-sm text-gray-400"
                        >
                          No planned or rescheduled audits
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
              {totalPagesPlanned > 0 && (
                <div className="border-t border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50">
                  <Pagination
                    currentPage={plannedPage}
                    totalPages={totalPagesPlanned}
                    pageSize={plannedPageSize}
                    onPageChange={setPlannedPage}
                    onPageSizeChange={(size) => {
                      setPlannedPageSize(size);
                      setPlannedPage(1);
                    }}
                  />
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Completed audits */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ring-1 ring-slate-900/5 dark:border-slate-700 dark:bg-[#0f1722] dark:ring-white/5">
        <SectionHeader
          label="Completed audits"
          count={completedAudits.length}
          open={showCompleted}
          onToggle={() => setShowCompleted((v) => !v)}
          variant="emerald"
        />

        <AnimatePresence>
          {showCompleted && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: "easeInOut" }}
              className="overflow-hidden border-t border-[#1f4a69]/30 dark:border-[#1f4a69]"
            >
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-[#184e77] dark:bg-[#0f2333]">
                      {COMPLETED_HEADERS.map((h, idx) => (
                        <TableCell
                          key={`completed-header-${h || "empty"}-${idx}`}
                          isHeader
                          className={`px-4 py-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#d7e5f1] dark:text-[#d7e5f1] ${idx < COMPLETED_HEADERS.length - 1 ? "border-r border-[#1f3f58]" : ""}`}
                        >
                          {h}
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody className="divide-y divide-slate-200 dark:divide-slate-700/70">
                    {paginatedCompleted.length > 0 ? (
                      paginatedCompleted.map(renderCompletedRow)
                    ) : (
                      <TableRow>
                        <TableCell
                          colSpan={COMPLETED_HEADERS.length}
                          className="py-10 text-center text-sm text-gray-400"
                        >
                          No completed audits
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
              {totalPagesCompleted > 0 && (
                <div className="border-t border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50">
                  <Pagination
                    currentPage={completedPage}
                    totalPages={totalPagesCompleted}
                    pageSize={completedPageSize}
                    onPageChange={setCompletedPage}
                    onPageSizeChange={(size) => {
                      setCompletedPageSize(size);
                      setCompletedPage(1);
                    }}
                  />
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Cancelled audits */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ring-1 ring-slate-900/5 dark:border-slate-700 dark:bg-[#0f1722] dark:ring-white/5">
        <SectionHeader
          label="Cancelled audits"
          count={cancelledAudits.length}
          open={showCancelled}
          onToggle={() => setShowCancelled((v) => !v)}
          variant="emerald"
        />

        <AnimatePresence>
          {showCancelled && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: "easeInOut" }}
              className="overflow-hidden border-t border-[#1f4a69]/30 dark:border-[#1f4a69]"
            >
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-[#184e77] dark:bg-[#0f2333]">
                      {ONGOING_HEADERS.map((h, idx) => (
                        <TableCell
                          key={`cancelled-header-${h || "empty"}-${idx}`}
                          isHeader
                          className={`px-4 py-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#d7e5f1] dark:text-[#d7e5f1] ${idx < ONGOING_HEADERS.length - 1 ? "border-r border-[#1f3f58]" : ""}`}
                        >
                          {h}
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody className="divide-y divide-slate-200 dark:divide-slate-700/70">
                    {paginatedCancelled.length > 0 ? (
                      paginatedCancelled.map(renderOngoingRow)
                    ) : (
                      <TableRow>
                        <TableCell
                          colSpan={ONGOING_HEADERS.length}
                          className="py-10 text-center text-sm text-gray-400"
                        >
                          No cancelled audits
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
              {totalPagesCancelled > 0 && (
                <div className="border-t border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50">
                  <Pagination
                    currentPage={cancelledPage}
                    totalPages={totalPagesCancelled}
                    pageSize={cancelledPageSize}
                    onPageChange={setCancelledPage}
                    onPageSizeChange={(size) => {
                      setCancelledPageSize(size);
                      setCancelledPage(1);
                    }}
                  />
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Ongoing audits */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ring-1 ring-slate-900/5 dark:border-slate-700 dark:bg-[#0f1722] dark:ring-white/5">
        <SectionHeader
          label="Ongoing audits"
          count={ongoingAudits.length}
          open={showOngoing}
          onToggle={() => setShowOngoing((v) => !v)}
          variant="indigo"
        />

        <AnimatePresence>
          {showOngoing && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: "easeInOut" }}
              className="overflow-hidden border-t border-[#1f4a69]/30 dark:border-[#1f4a69]"
            >
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-[#184e77] dark:bg-[#0f2333]">
                      {ONGOING_HEADERS.map((h, idx) => (
                        <TableCell
                          key={`ongoing-header-${h || "empty"}-${idx}`}
                          isHeader
                          className={`px-4 py-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#d7e5f1] dark:text-[#d7e5f1] ${idx < ONGOING_HEADERS.length - 1 ? "border-r border-[#1f3f58]" : ""}`}
                        >
                          {h}
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody className="divide-y divide-slate-200 dark:divide-slate-700/70">
                    {paginatedOngoing.length > 0 ? (
                      paginatedOngoing.map(renderOngoingRow)
                    ) : (
                      <TableRow>
                        <TableCell
                          colSpan={ONGOING_HEADERS.length}
                          className="py-10 text-center text-sm text-gray-400"
                        >
                          No ongoing audits
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
              {totalPagesOngoing > 0 && (
                <div className="border-t border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50">
                  <Pagination
                    currentPage={ongoingPage}
                    totalPages={totalPagesOngoing}
                    pageSize={ongoingPageSize}
                    onPageChange={setOngoingPage}
                    onPageSizeChange={(size) => {
                      setOngoingPageSize(size);
                      setOngoingPage(1);
                    }}
                  />
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Modals */}
      {planningAudit && (
        <AuditPlanningModal
          audit={planningAudit}
          onClose={() => setPlanningAudit(null)}
          onSaved={(updatedAudit) => {
            setAuditOverrides((prev) => ({
              ...prev,
              [updatedAudit.id]: updatedAudit,
            }));
          }}
        />
      )}
      {rescheduleAudit && (
        <RescheduleAuditModal
          audit={rescheduleAudit}
          onClose={() => setRescheduleAudit(null)}
          onSaved={(updatedAudit) => {
            setAuditOverrides((prev) => ({
              ...prev,
              [updatedAudit.id]: updatedAudit,
            }));
          }}
        />
      )}
      {manageAuditeesAudit && (
        <ManageAuditeesModal
          audit={manageAuditeesAudit}
          onClose={() => setManageAuditeesAudit(null)}
          onSaved={(updatedAudit) => {
            setAuditOverrides((prev) => ({
              ...prev,
              [updatedAudit.id]: updatedAudit,
            }));
          }}
        />
      )}
      {cancelAuditTarget && (
        <CancelAuditModal
          audit={cancelAuditTarget}
          onClose={() => setCancelAuditTarget(null)}
          onSaved={(updatedAudit) => {
            setAuditOverrides((prev) => ({
              ...prev,
              [updatedAudit.id]: updatedAudit,
            }));
          }}
        />
      )}
      {deleteAuditTarget && (
        <Modal isOpen={true} onClose={() => setDeleteAuditTarget(null)} className="max-w-[520px]">
          <div className="rounded-3xl border border-red-200 bg-white p-6 shadow-xl dark:border-red-900/40 dark:bg-gray-900">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Delete audit</h2>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              This will permanently delete audit <strong>{deleteAuditTarget.audit_number}</strong>.
              Use this only for typos or mistaken creation. Completed audits cannot be deleted.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setDeleteAuditTarget(null)}
                className="rounded-lg border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
              >
                Keep audit
              </button>
              <button
                onClick={handleDeleteAudit}
                disabled={deletingAudit}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
              >
                {deletingAudit ? "Deleting..." : "Delete audit"}
              </button>
            </div>
          </div>
        </Modal>
      )}
      {historyAudit && (
        <AuditHistoryModal
          audit={historyAudit}
          onClose={() => setHistoryAudit(null)}
        />
      )}
      {pdfPreviewOpen && currentPreviewAudit && (
        <PDFPreviewModal
          isOpen={pdfPreviewOpen}
          onClose={() => {
            setPdfPreviewOpen(false);
            if (previewPdfUrl) {
              URL.revokeObjectURL(previewPdfUrl);
            }
            setPreviewPdfUrl("");
            setCurrentPreviewAudit(null);
            setPreviewVariant("standard");
          }}
          pdfUrl={previewPdfUrl}
          auditNumber={currentPreviewAudit.audit_number}
          reportVariant={previewVariant}
          onReportVariantChange={
            isAuditor
              ? (variant) => handlePreviewPDF(currentPreviewAudit, variant)
              : undefined
          }
          onDownload={() => {
            if (previewVariant === "complete") {
              // The complete report is never stored -- save the copy
              // already loaded in the preview.
              const link = document.createElement("a");
              link.href = previewPdfUrl;
              link.setAttribute(
                "download",
                `complete_audit_report_${currentPreviewAudit.audit_number}.pdf`,
              );
              document.body.appendChild(link);
              link.click();
              link.remove();
              return;
            }
            downloadReport(
              currentPreviewAudit.id,
              currentPreviewAudit.audit_number,
            );
          }}
        />
      )}
      {emailModalOpen && currentEmailAudit && (
        <SendReportEmailModal
          isOpen={emailModalOpen}
          onClose={() => {
            setEmailModalOpen(false);
            setCurrentEmailAudit(null);
          }}
          audit={currentEmailAudit}
          onSend={handleSendEmail}
          isSending={sendingEmails[currentEmailAudit.id] ?? false}
        />
      )}

      {carsModalAudit && (
        <AuditCARsModal
          auditId={carsModalAudit.id}
          auditNumber={carsModalAudit.audit_number}
          onClose={() => setCarsModalAudit(null)}
        />
      )}
      {answersModalAudit && (
        <AuditAnswersModal
          auditId={answersModalAudit.id}
          auditNumber={answersModalAudit.audit_number}
          onClose={() => setAnswersModalAudit(null)}
        />
      )}
    </div>
  );
}
