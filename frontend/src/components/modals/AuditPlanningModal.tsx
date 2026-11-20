import React, { useEffect, useState } from "react";
import { format } from "date-fns";
import { CalendarDays, MailCheck, Save, TriangleAlert } from "lucide-react";
import { useSelector } from "react-redux";
import toast from "react-hot-toast";
import { Modal } from "../ui/modal";
import { RootState } from "../../redux/store";
import {
  Audit,
  AuditPlanningDetails,
  AuditPlanningDetailsUpdate,
} from "../../redux/audit/audit-types";
import {
  apiGetAuditPlanningDetails,
  apiSendAuditPlanningCalendar,
  apiUpdateAuditPlanningDetails,
} from "../../redux/audit/audit";
import { DirectoryEmailField } from "../common/DirectoryEmailField";

interface AuditPlanningModalProps {
  audit: Audit;
  onClose: () => void;
  onSaved: (audit: Audit) => void;
}

interface PlanningFormState {
  plant: string;
  sector: string;
  supervisorEmail: string;
  hardwareEmail: string;
}

const plantOptions = [
  { value: "anhui", label: "Anhui" },
  { value: "chennai", label: "Chennai" },
  { value: "loire", label: "Loire" },
  { value: "daegu", label: "Daegu" },
  { value: "frankfort", label: "Frankfort" },
  { value: "galeana", label: "Galeana" },
  { value: "kunshan", label: "Kunshan" },
  { value: "monterrey", label: "Monterrey" },
  { value: "medina", label: "Medina" },
  { value: "poitiers", label: "Poitiers" },
  { value: "rayones", label: "Rayones" },
  { value: "carthage", label: "Carthage" },
  { value: "atlas", label: "Atlas" },
  { value: "tianjin", label: "Tianjin" },
];

const hardwareOptions = [
  "",
  "remote-eye.cn-anhui@example.com",
  "remote-eye.cn-tianjin@example.com",
  "remote-eye.de-frankfort@example.com",
  "remote-eye.fr-loire@example.com",
  "remote-eye.fr-poitiers@example.com",
  "remote-eye.in-chennai@example.com",
  "remote-eye.mx-galeana@example.com",
  "remote-eye.mx-monterrey@example.com",
  "remote-eye.mx-rayones@example.com",
  "remote-eye.tn-medina@example.com",
  "remote-eye.tn-carthage@example.com",
  "remote-eye.tn-atlas@example.com",
  "remote-eye.tn-sahel@example.com",
  "remote-eye.kr-daegu@example.com",
];

const serializeEmails = (emails?: string[]) => (emails ?? []).join(", ");
const validateEmail = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/i.test(email);

const formatSchedule = (start?: string, end?: string) => {
  if (!start || !end) return "Not scheduled";
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return "Not scheduled";
  }
  return `${format(startDate, "PPpp")} -> ${format(endDate, "p")}`;
};

const toAuditOverride = (
  audit: Audit,
  details: AuditPlanningDetails,
  eventCreated?: boolean,
  eventId?: string | null,
): Audit => {
  const plannedStart = `${details.audit_date} ${details.start_time}`;
  const plannedEnd = `${details.audit_date} ${details.end_time}`;

  return {
    ...audit,
    audit_number: details.audit_number || audit.audit_number,
    status: details.status || audit.status,
    plant: details.plant,
    sector: details.sector ?? "",
    auditees: details.auditee_emails,
    auditee_details: details.auditee_details ?? audit.auditee_details,
    questionnaire: audit.questionnaire
      ? {
          ...audit.questionnaire,
          name: details.questionnaire?.name || audit.questionnaire.name,
          type: details.questionnaire?.type || audit.questionnaire.type,
        }
      : {
          id: details.questionnaire_id,
          name: details.questionnaire?.name || "Questionnaire",
          type: details.questionnaire?.type || undefined,
        },
    planned_start_date: plannedStart,
    planned_end_date: plannedEnd,
    event_created: eventCreated ?? details.event_created ?? audit.event_created,
    event_id: eventId ?? details.event_id ?? audit.event_id,
    supervisor_email: details.supervisor_email ?? undefined,
    hardware_email: details.hardware_email ?? undefined,
  };
};

const AuditPlanningModal: React.FC<AuditPlanningModalProps> = ({
  audit,
  onClose,
  onSaved,
}) => {
  const { user } = useSelector((state: RootState) => state.auth);
  const [details, setDetails] = useState<AuditPlanningDetails | null>(null);
  const [form, setForm] = useState<PlanningFormState>({
    plant: audit.plant || "",
    sector: audit.sector || "",
    supervisorEmail: audit.supervisor_email || "",
    hardwareEmail: audit.hardware_email || "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        setLoading(true);
        setError("");
        const response = await apiGetAuditPlanningDetails(audit.id);
        if (!active) return;
        setDetails(response);
        setForm({
          plant: response.plant || "",
          sector: response.sector || "",
          supervisorEmail: response.supervisor_email || "",
          hardwareEmail: response.hardware_email || "",
        });
      } catch (err: unknown) {
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          (err as Error)?.message ||
          "Failed to load planning details.";
        if (active) setError(msg);
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [audit.id]);

  const buildPayload = (): AuditPlanningDetailsUpdate | null => {
    if (!details) {
      setError("Planning details are not loaded yet.");
      return null;
    }
    if (!form.plant || !form.sector.trim()) {
      setError("Plant and sector are required.");
      return null;
    }
    if (form.supervisorEmail && !validateEmail(form.supervisorEmail.trim())) {
      setError("Supervisor email is not valid.");
      return null;
    }
    if (form.hardwareEmail && !validateEmail(form.hardwareEmail.trim())) {
      setError("Hardware email is not valid.");
      return null;
    }

    return {
      auditee_emails: details.auditee_emails,
      // This modal never edits auditees itself — but AuditPlanningDetailsUpdate
      // deletes and recreates every AuditAuditee row on save (see
      // audit_service._validate_and_apply_planning_update), so omitting
      // `auditees` here would silently wipe any existing people_id links
      // just from saving plant/sector/supervisor changes. Passing the
      // already-fetched details through keeps them intact.
      auditees: details.auditee_details,
      plant: form.plant,
      sector: form.sector.trim(),
      supervisor_email: form.supervisorEmail.trim() || null,
      hardware_email: form.hardwareEmail.trim() || null,
      audit_date: details.audit_date,
      start_time: details.start_time,
      end_time: details.end_time,
    };
  };

  const handleSave = async () => {
    const payload = buildPayload();
    if (!payload) return null;

    try {
      setSaving(true);
      setError("");
      const updated = await apiUpdateAuditPlanningDetails(audit.id, payload);
      setDetails(updated);
      onSaved(toAuditOverride(audit, updated));
      toast.success("Planning details saved.");
      return updated;
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err as Error)?.message ||
        "Failed to save planning details.";
      setError(msg);
      return null;
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAndSend = async () => {
    if (!user?.email) {
      setError("User not found.");
      return;
    }

    const updated = await handleSave();
    if (!updated) return;

    try {
      setSending(true);
      setError("");
      const syncResult = await apiSendAuditPlanningCalendar(audit.id);
      const mergedAudit = toAuditOverride(audit, {
        ...updated,
        event_created: syncResult.event_created,
        event_id: syncResult.event_id,
      }, syncResult.event_created, syncResult.event_id);
      setDetails({
        ...updated,
        event_created: syncResult.event_created,
        event_id: syncResult.event_id,
      });
      onSaved(mergedAudit);
      toast.success(
        syncResult.event_action === "updated"
          ? "Calendar invite updated successfully."
          : "Calendar invite sent successfully.",
      );
      onClose();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err as Error)?.message ||
        "Failed to send calendar invite.";
      setError(msg);
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} className="max-w-[920px] p-0">
      <div className="rounded-3xl border border-[#064273]/15 bg-white dark:border-[#064273]/40 dark:bg-gray-900">
        <div className="rounded-t-3xl border-b border-[#064273]/15 bg-gradient-to-r from-[#064273] via-[#0a4f7f] to-[#0f628f] px-6 py-5 dark:border-[#064273]/40">
          <div className="flex items-start justify-between gap-3 pr-12">
            <div>
              <h2 className="text-xl font-semibold text-white">Planning Details</h2>
              <p className="mt-1 text-sm text-blue-100/90">
                Edit the audit data first, then send or update the Outlook invite from the saved record.
              </p>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-white/15 px-2.5 py-1 text-xs font-medium text-blue-100">
              <CalendarDays className="h-3.5 w-3.5" />
              {audit.audit_number || "Audit"}
            </span>
          </div>
        </div>

        <div className="space-y-5 px-6 py-5">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border border-[#064273]/10 bg-[#f3f9ff] p-3 dark:border-[#064273]/35 dark:bg-[#064273]/20">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-[#355f7f] dark:text-blue-200/90">Current Schedule</p>
              <p className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                {formatSchedule(audit.planned_start_date, audit.planned_end_date)}
              </p>
            </div>
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-800/40 dark:bg-emerald-900/15">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">Invite Status</p>
              <p className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                {details?.event_created ? "Calendar event already created" : "No calendar event sent yet"}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/40">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Questionnaire</p>
              <p className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                {details?.questionnaire?.name || audit.questionnaire?.name || "N/A"}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                {details?.questionnaire?.type || audit.questionnaire?.type || "Audit type unavailable"}
              </p>
            </div>
          </div>

          {loading ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-300">
              Loading planning details...
            </div>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">Plant</label>
                  <select
                    value={form.plant}
                    onChange={(e) => setForm((prev) => ({ ...prev, plant: e.target.value }))}
                    className="h-11 w-full rounded-lg border border-[#064273]/20 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-[#064273] focus:ring-2 focus:ring-[#064273]/20 dark:border-[#064273]/40 dark:bg-white/[0.04] dark:text-slate-200"
                  >
                    <option value="">Select plant</option>
                    {plantOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">Sector</label>
                  <input
                    type="text"
                    value={form.sector}
                    onChange={(e) => setForm((prev) => ({ ...prev, sector: e.target.value }))}
                    className="h-11 w-full rounded-lg border border-[#064273]/20 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-[#064273] focus:ring-2 focus:ring-[#064273]/20 dark:border-[#064273]/40 dark:bg-white/[0.04] dark:text-slate-200"
                    placeholder="Sector"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">Supervisor Email</label>
                  <DirectoryEmailField
                    value={form.supervisorEmail}
                    onChange={(email) => setForm((prev) => ({ ...prev, supervisorEmail: email }))}
                    placeholder="Search the Northwind directory, or type an email"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">Hardware Email</label>
                  <select
                    value={form.hardwareEmail}
                    onChange={(e) => setForm((prev) => ({ ...prev, hardwareEmail: e.target.value }))}
                    className="h-11 w-full rounded-lg border border-[#064273]/20 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-[#064273] focus:ring-2 focus:ring-[#064273]/20 dark:border-[#064273]/40 dark:bg-white/[0.04] dark:text-slate-200"
                  >
                    {hardwareOptions.map((option) => (
                      <option key={option || "none"} value={option}>
                        {option || "No hardware attendee"}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800/40">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Auditees</p>
                  <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
                    {serializeEmails(details?.auditee_emails) || "No auditees assigned"}
                  </p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Auditees are managed from the dedicated auditee action.
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800/40">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Schedule</p>
                  <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
                    {details ? `${details.audit_date} | ${details.start_time.slice(0, 5)} -> ${details.end_time.slice(0, 5)}` : "Not scheduled"}
                  </p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Date and time are managed from the reschedule action.
                  </p>
                </div>
              </div>
            </>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800/40 dark:bg-red-900/20 dark:text-red-300">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex flex-wrap justify-end gap-2 pt-1">
            <button
              onClick={onClose}
              className="rounded-lg border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              Cancel
            </button>
            <button
              onClick={() => {
                void handleSave();
              }}
              disabled={loading || saving || sending}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#064273]/25 bg-white px-4 py-2 text-sm font-semibold text-[#064273] transition hover:bg-[#f3f9ff] disabled:cursor-not-allowed disabled:opacity-60 dark:border-[#77b7de]/35 dark:bg-slate-900 dark:text-blue-200 dark:hover:bg-slate-800"
            >
              <Save className="h-4 w-4" />
              {saving ? "Saving..." : "Save Changes"}
            </button>
            <button
              onClick={() => {
                void handleSaveAndSend();
              }}
              disabled={loading || saving || sending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-[#0f628f] to-[#1b8bb4] px-4 py-2 text-sm font-semibold text-white transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <MailCheck className="h-4 w-4" />
              {sending
                ? "Sending..."
                : details?.event_created
                  ? "Save & Update Invite"
                  : "Save & Send Invite"}
            </button>
          </div>
        </div>
      </div>
      <div id="datepicker-portal"></div>
    </Modal>
  );
};

export default AuditPlanningModal;
