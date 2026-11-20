// ✅ FULL FILE: PlanAudit.tsx (timezone-safe planning + supervisor_email support + clean typings)

import { useEffect, useMemo, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";

import { Modal } from "../../components/ui/modal";
import Input from "../../components/form/input/InputField";
import { DatePickerOnly } from "../../components/calendar/DatePickerOnly";
import { TimePicker } from "../../components/calendar/TimePicker";
import Select from "../../components/form/Select";

import { getQuestionnairesByNames } from "../../redux/questionnaire/questionnaire";
import { QuestionnairesNames } from "../../redux/questionnaire/questionnaire-slice-types";

import { AppDispatch, RootState } from "../../redux/store";
import { AuditPlanCreate } from "../../redux/audit/audit-types";
import { planAuditThunk } from "../../redux/audit/audit-slice";
import { getAuditors } from "../../redux/users/user";
import toast from "react-hot-toast";
import {
  MemberDirectoryPicker,
  PickedAuditee,
} from "../../components/common/MemberDirectoryPicker";
import { DirectoryEmailField } from "../../components/common/DirectoryEmailField";
import {
  AlertTriangle,
  CalendarClock,
  CalendarPlus,
  ClipboardList,
  UserPlus,
  Clock,
  Globe2,
  Layers,
  Loader2,
  MapPin,
  Users,
  Video,
} from "lucide-react";

/**
 * ✅ date-fns-tz compatibility:
 * - old versions: formatInTimeZone, utcToZonedTime, zonedTimeToUtc
 * - newer versions: formatInTimeZone, toZonedTime, fromZonedTime
 */
import * as tz from "date-fns-tz";

interface PlanModalProps {
  isAuditModalOpen: boolean;
  closeAuditModalOpen: () => void;
  onAuditCreated?: () => void;
}

interface AuditPlanForm {
  auditees: PickedAuditee[]; // picked from the Northwind directory, or typed manually
  secondAuditorId: string; // optional co-auditor (user id), "" when none
  supervisorEmail: string; // ✅ NEW (required)
  plant: string | null;
  sector: string;
  questionnaireId: string | number | null;
  auditDate: Date | null;
  startTime: Date | null;
  endTime: Date | null;
  hardwareEmail?: string | null;
}

type TzFunctions = {
  formatInTimeZone?: (d: Date, tzName: string, format: string) => string;
  fromZonedTime?: (d: Date, tzName: string) => Date;
  zonedTimeToUtc?: (d: Date | string, tzName: string) => Date;
};

/** Consistent icon + label card wrapper for one form field, matching the
 * gradient-header / sectioned-card style already used in ManageAuditeesModal
 * and AuditPlanningModal. */
function FieldCard({
  icon: Icon,
  label,
  required,
  hint,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50/60 p-4 dark:border-white/5 dark:bg-white/[0.02]">
      <div className="mb-2.5 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-[#064273]/10 text-[#064273] dark:bg-[#064273]/25 dark:text-blue-200">
          <Icon className="h-3.5 w-3.5" />
        </span>
        <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">
          {label}
          {required && <span className="ml-1 text-red-500">*</span>}
        </span>
      </div>
      {children}
      {hint && (
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{hint}</p>
      )}
    </div>
  );
}

export default function PlanAudit({
  isAuditModalOpen,
  closeAuditModalOpen,
  onAuditCreated,
}: PlanModalProps) {
  const dispatch = useDispatch<AppDispatch>();

  const { questionnaireListName } = useSelector(
    (state: RootState) => state.questionnaire
  );
  const { user } = useSelector((state: RootState) => state.auth);
  // /users/auditors returns { id, fullName, email } rows
  const auditorsList = useSelector(
    (state: RootState) =>
      state.user.usersList as unknown as {
        id: number;
        fullName?: string;
        email: string;
      }[]
  );
  const planningLoading = useSelector(
    (state: RootState) => state.audit.planningLoading
  );
  // Blocks a second click synchronously: `planningLoading` only disables the
  // buttons after a re-render, so a fast double-click used to plan twice.
  const submittingRef = useRef(false);
  const runOnce = async (fn: () => Promise<void>) => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      await fn();
    } finally {
      submittingRef.current = false;
    }
  };

  const [questionnaires, setQuestionnaires] = useState<QuestionnairesNames[]>(
    []
  );
  const [errorMessage, setErrorMessage] = useState("");
  const [showUnavailableConfirm, setShowUnavailableConfirm] = useState(false);
  const [confirmUnavailableMessage, setConfirmUnavailableMessage] = useState("");
  const [pendingPlanPayload, setPendingPlanPayload] = useState<AuditPlanCreate | null>(null);

  /** Plant timezone (anchor) */
  const [plantTz, setPlantTz] = useState<string>("UTC");

  /** Auditor timezone (browser) */
  const auditorTz = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone,
    []
  );

  /** Auditee timezone (placeholder; later load from profile) */
  const auditeeTz = auditorTz;

  const [form, setForm] = useState<AuditPlanForm>({
    auditees: [],
    secondAuditorId: "",
    supervisorEmail: "",
    plant: null,
    sector: "",
    questionnaireId: null,
    auditDate: null,
    startTime: null,
    endTime: null,
    hardwareEmail: null,
  });

  // ---- Static Options ----
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

  const glasses = [
    { value: "remote-eye.cn-anhui@example.com", label: "remote-eye.cn-anhui@example.com" },
    { value: "remote-eye.cn-tianjin@example.com", label: "remote-eye.cn-tianjin@example.com" },
    { value: "remote-eye.de-frankfort@example.com", label: "remote-eye.de-frankfort@example.com" },
    { value: "remote-eye.fr-loire@example.com", label: "remote-eye.fr-loire@example.com" },
    { value: "remote-eye.fr-poitiers@example.com", label: "remote-eye.fr-poitiers@example.com" },
    { value: "remote-eye.in-chennai@example.com", label: "remote-eye.in-chennai@example.com" },
    { value: "remote-eye.mx-galeana@example.com", label: "remote-eye.mx-galeana@example.com" },
    { value: "remote-eye.mx-monterrey@example.com", label: "remote-eye.mx-monterrey@example.com" },
    { value: "remote-eye.mx-rayones@example.com", label: "remote-eye.mx-rayones@example.com" },
    { value: "remote-eye.tn-medina@example.com", label: "remote-eye.tn-medina@example.com" },
    { value: "remote-eye.tn-carthage@example.com", label: "remote-eye.tn-carthage@example.com" },
    { value: "remote-eye.tn-atlas@example.com", label: "remote-eye.tn-atlas@example.com" },
    { value: "remote-eye.tn-sahel@example.com", label: "remote-eye.tn-sahel@example.com" },
    { value: "remote-eye.kr-daegu@example.com", label: "remote-eye.kr-daegu@example.com" },
  ];

  const blockedSlots = [
    { date: "2025-11-20", start: "08:00", end: "09:00" },
    { date: "2025-11-20", start: "09:00", end: "10:00" },
    { date: "2025-11-20", start: "10:00", end: "11:00" },
    { date: "2025-11-20", start: "11:00", end: "12:00" },
    { date: "2025-11-20", start: "12:00", end: "13:00" },
    { date: "2025-11-20", start: "13:00", end: "14:00" },
    { date: "2025-11-20", start: "14:00", end: "15:00" },
    { date: "2025-11-20", start: "15:00", end: "16:00" },
    { date: "2025-11-20", start: "16:00", end: "17:00" },
    { date: "2025-11-19", start: "08:00", end: "09:00" },
  ];

  /** map plant => timezone */
  const plantToTz = useMemo<Record<string, string>>(
    () => ({
      anhui: "Asia/Shanghai",
      tianjin: "Asia/Shanghai",
      kunshan: "Asia/Shanghai",
      chennai: "Asia/Kolkata",
      daegu: "Asia/Seoul",
      loire: "Europe/Paris",
      poitiers: "Europe/Paris",
      frankfort: "Europe/Berlin",
      monterrey: "America/Monterrey",
      galeana: "America/Monterrey",
      rayones: "America/Monterrey",
      medina: "Africa/Tunis",
      carthage: "Africa/Tunis",
      atlas: "Africa/Tunis",
    }),
    [],
  );
  const tzFns = tz as unknown as TzFunctions;

  // ---- Fetch questionnaires ----
  useEffect(() => {
    getQuestionnairesByNames(dispatch);
    getAuditors(dispatch);
  }, [dispatch]);

  // Every auditor except the logged-in user (who is the lead auditor).
  const secondAuditorOptions = useMemo(
    () =>
      (auditorsList || [])
        .filter((a) => a.id !== user?.id)
        .map((a) => ({
          value: String(a.id),
          label: a.fullName?.trim() ? `${a.fullName} (${a.email})` : a.email,
        })),
    [auditorsList, user?.id]
  );

  useEffect(() => {
    setQuestionnaires(questionnaireListName || []);
  }, [questionnaireListName]);

  /** update plant timezone when plant changes */
  useEffect(() => {
    const p = form.plant ?? "";
    setPlantTz(plantToTz[p] ?? "UTC");
  }, [form.plant, plantToTz]);

  // ---- Validate end time > start time ----
  useEffect(() => {
    if (form.startTime && form.endTime && form.endTime <= form.startTime) {
      toast.error("End time must be AFTER start time.");
      setForm((prev) => ({ ...prev, endTime: null }));
    }
  }, [form.startTime, form.endTime]);

  // ---- Email validation ----
  const isNorthwindEmail = (email: string) =>
    /^[^\s@]+@northwind\.com$/i.test(email.trim());

  const validateSingleNorthwindEmail = (email: string) => {
    const e = (email ?? "").trim();
    if (!e) return false;
    return /^[^\s@]+@northwind\.com$/i.test(e);
  };

  const isAuditeeUnavailableError = (msg: string) => {
    const lower = (msg || "").toLowerCase();
    return (
      (lower.includes("auditee") && lower.includes("not available")) ||
      (lower.includes("auditee") && lower.includes("approved leave")) ||
      (lower.includes("auditor") && lower.includes("conflicting audit"))
    );
  };

  /** timezone preview renderer */
  const renderPreview = (label: string, tzName: string, time: Date | null) => {
    if (!time) return null;

    const fmt = tzFns.formatInTimeZone;

    if (!fmt) {
      return (
        <div className="flex justify-between text-sm">
          <span className="text-gray-600 dark:text-gray-400">{label}</span>
          <span className="font-mono dark:text-gray-200">
            {time.toLocaleString()}
          </span>
        </div>
      );
    }

    return (
      <div className="flex justify-between text-sm">
        <span className="text-gray-600 dark:text-gray-400">{label}</span>
        <span className="font-mono dark:text-gray-200">
          {fmt(time, tzName, "EEE HH:mm (zzz)")}
        </span>
      </div>
    );
  };

  /**
   * ✅ Convert Plant "wall-clock" selection to an absolute Date (UTC instant)
   * Works with BOTH old and new date-fns-tz versions:
   * - new: fromZonedTime(localDate, tz)
   * - old: zonedTimeToUtc(localDate, tz)
   */
  const toUtcInstantFromPlantLocal = (plantLocalDate: Date, tzName: string) => {
    const fromZonedTime = tzFns.fromZonedTime;
    const zonedTimeToUtc = tzFns.zonedTimeToUtc;

    if (fromZonedTime) return fromZonedTime(plantLocalDate, tzName);
    if (zonedTimeToUtc) return zonedTimeToUtc(plantLocalDate, tzName);

    // last resort fallback: treat given Date as already UTC (not ideal)
    return plantLocalDate;
  };

  /**
   * Build a Date representing "auditDate + time" in Plant local wall-clock,
   * then convert it to a UTC instant.
   */
  const combineDateAndTimeInPlantTz = (date: Date, time: Date, tzName: string) => {
    const y = date.getFullYear();
    const m = date.getMonth();
    const d = date.getDate();
    const hh = time.getHours();
    const mm = time.getMinutes();
    const ss = time.getSeconds();

    const plantLocalWallClock = new Date(y, m, d, hh, mm, ss);
    return toUtcInstantFromPlantLocal(plantLocalWallClock, tzName);
  };

  // ---- Submit handler ----
  const handleSubmit = () => runOnce(submitPlan);
  const handleConfirmPlanAnyway = () => runOnce(confirmPlanAnyway);

  const submitPlan = async () => {
    setErrorMessage("");

    if (
      form.auditees.length === 0 ||
      !form.supervisorEmail ||
      !form.plant ||
      !form.questionnaireId ||
      !form.auditDate ||
      !form.startTime ||
      !form.endTime ||
      !form.sector
    ) {
      setErrorMessage("Please fill all required fields.");
      return;
    }

    if (!form.auditees.every((a) => isNorthwindEmail(a.email))) {
      setErrorMessage("All auditee emails must end with @northwind.com");
      return;
    }

    if (!validateSingleNorthwindEmail(form.supervisorEmail)) {
      setErrorMessage("Supervisor email must be a valid @northwind.com email");
      return;
    }

    if (!user) {
      setErrorMessage("User not found");
      return;
    }

    try {
      const startUtc = combineDateAndTimeInPlantTz(
        form.auditDate,
        form.startTime,
        plantTz
      );
      const endUtc = combineDateAndTimeInPlantTz(
        form.auditDate,
        form.endTime,
        plantTz
      );

      const fmt = tzFns.formatInTimeZone;

      if (!fmt) throw new Error("date-fns-tz formatInTimeZone not available");

      // ✅ send snake_case keys expected by backend
      const payload: AuditPlanCreate & { supervisor_email: string } = {
        auditee_emails: form.auditees.map((a) => a.email),
        auditees: form.auditees,
        auditor_id: user.id,
        second_auditor_id: form.secondAuditorId
          ? Number(form.secondAuditorId)
          : null,
        plant: form.plant,
        sector: form.sector,
        questionnaire_id: Number(form.questionnaireId),
        allow_unavailable_auditee: false,

        supervisor_email: form.supervisorEmail.trim(),

        // ✅ send Plant-local strings (stable regardless of auditor timezone)
        audit_date: fmt(startUtc, plantTz, "yyyy-MM-dd"),
        start_time: fmt(startUtc, plantTz, "HH:mm:ss"),
        end_time: fmt(endUtc, plantTz, "HH:mm:ss"),

        ...(form.hardwareEmail && { hardware_email: form.hardwareEmail }),
      };

      try {
        await dispatch(planAuditThunk(payload)).unwrap();
      } catch (firstErr: unknown) {
        const firstMsg =
          (firstErr as { response?: { data?: { detail?: string } } })?.response
            ?.data?.detail ||
          (firstErr as { detail?: string })?.detail ||
          (firstErr as Error)?.message ||
          (typeof firstErr === "string" ? firstErr : "Failed to plan audit.");

        if (!isAuditeeUnavailableError(firstMsg)) {
          throw firstErr;
        }

        setPendingPlanPayload(payload);
        setConfirmUnavailableMessage(firstMsg);
        setShowUnavailableConfirm(true);
        return;
      }

      toast.success("Audit planned successfully!", { duration: 10000 });

      onAuditCreated?.();

      setForm({
        auditees: [],
        secondAuditorId: "",
        supervisorEmail: "",
        plant: null,
        sector: "",
        questionnaireId: null,
        auditDate: null,
        startTime: null,
        endTime: null,
        hardwareEmail: null,
      });

      closeAuditModalOpen();
    } catch (err: unknown) {
      const e = err as {
        response?: { data?: { detail?: string } };
        detail?: string;
        message?: string;
      };
      const msg =
        e?.response?.data?.detail ||
        e?.detail ||
        e?.message ||
        (typeof err === "string" ? err : "Failed to plan audit.");

      setErrorMessage(msg);
    }
  };

  const confirmPlanAnyway = async () => {
    if (!pendingPlanPayload) return;
    try {
      await dispatch(
        planAuditThunk({
          ...pendingPlanPayload,
          allow_unavailable_auditee: true,
        }),
      ).unwrap();
      toast.success("Audit planned successfully!", { duration: 10000 });
      onAuditCreated?.();
      setForm({
        auditees: [],
        secondAuditorId: "",
        supervisorEmail: "",
        plant: null,
        sector: "",
        questionnaireId: null,
        auditDate: null,
        startTime: null,
        endTime: null,
        hardwareEmail: null,
      });
      setShowUnavailableConfirm(false);
      setPendingPlanPayload(null);
      closeAuditModalOpen();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ||
        (err as { detail?: string })?.detail ||
        (err as Error)?.message ||
        (typeof err === "string" ? err : "Failed to plan audit.");
      setErrorMessage(msg);
      setShowUnavailableConfirm(false);
    }
  };

  return (
    <Modal
      isOpen={isAuditModalOpen}
      onClose={closeAuditModalOpen}
      className="max-w-[980px] p-0"
    >
      <div className="rounded-3xl">
        {/* Header */}
        <div className="rounded-t-3xl border-b border-[#064273]/15 bg-gradient-to-r from-[#064273] via-[#0a4f7f] to-[#0f628f] px-6 py-5 dark:border-[#064273]/40">
          <div className="flex items-center gap-3 pr-12">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/15">
              <CalendarPlus className="h-5 w-5 text-white" />
            </span>
            <div>
              <h2 className="text-xl font-semibold text-white">
                Add New Audit Plan
              </h2>
              <p className="mt-0.5 text-sm text-blue-100/90">
                Date &amp; time are selected in{" "}
                <strong className="font-semibold text-white">
                  Plant local time
                </strong>{" "}
                — live previews on the right show other timezones.
              </p>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="max-h-[75vh] overflow-y-auto px-6 py-6 custom-scrollbar">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* LEFT: Form */}
            <div className="space-y-6 lg:col-span-2">
              {/* Section: Participants */}
              <div>
                <p className="mb-3 text-[11px] font-bold uppercase tracking-widest text-[#064273] dark:text-blue-300">
                  Participants
                </p>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <FieldCard icon={Users} label="Auditee(s)" required>
                    <MemberDirectoryPicker
                      value={form.auditees}
                      onChange={(next) =>
                        setForm((prev) => ({ ...prev, auditees: next }))
                      }
                      isValidManualEmail={isNorthwindEmail}
                      placeholder="Search the Northwind directory, or type an @northwind.com email"
                    />
                  </FieldCard>

                  <FieldCard
                    icon={UserPlus}
                    label="Second Auditor"
                    hint="Optional. You are the lead auditor; the second auditor is invited to the Outlook event and can fill the audit."
                  >
                    <select
                      value={form.secondAuditorId}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          secondAuditorId: e.target.value,
                        }))
                      }
                      className="h-11 w-full appearance-none rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 pr-11 text-sm shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:focus:border-brand-800"
                    >
                      <option value="">No second auditor</option>
                      {secondAuditorOptions.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </FieldCard>

                  <FieldCard
                    icon={Users}
                    label="Supervisor Email"
                    required
                    hint="Used for CAR escalation CC (supervisor)."
                  >
                    <DirectoryEmailField
                      id="supervisor_email"
                      placeholder="Search the Northwind directory, or type an @northwind.com email"
                      value={form.supervisorEmail}
                      onChange={(email) =>
                        setForm((prev) => ({
                          ...prev,
                          supervisorEmail: email,
                        }))
                      }
                    />
                  </FieldCard>
                </div>
              </div>

              {/* Section: Location & sector */}
              <div>
                <p className="mb-3 text-[11px] font-bold uppercase tracking-widest text-[#064273] dark:text-blue-300">
                  Location &amp; Sector
                </p>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <FieldCard
                    icon={MapPin}
                    label="Plant (Anchor)"
                    required
                    hint={`Plant timezone: ${plantTz}`}
                  >
                    <Select
                      options={plantOptions}
                      placeholder="Select a plant"
                      defaultValue={form.plant || ""}
                      onChange={(value) =>
                        setForm((prev) => ({ ...prev, plant: value }))
                      }
                      className="dark:bg-dark-900"
                    />
                  </FieldCard>

                  <FieldCard icon={Layers} label="Sector" required>
                    <Input
                      placeholder="Enter sector name"
                      value={form.sector}
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, sector: e.target.value }))
                      }
                      className="dark:bg-dark-900"
                    />
                  </FieldCard>
                </div>
              </div>

              {/* Section: Audit setup */}
              <div>
                <p className="mb-3 text-[11px] font-bold uppercase tracking-widest text-[#064273] dark:text-blue-300">
                  Audit Setup
                </p>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <FieldCard icon={ClipboardList} label="Questionnaire" required>
                    <Select
                      options={
                        questionnaires?.map((q) => ({
                          value: q.id.toString(),
                          label: q.name,
                        })) || []
                      }
                      placeholder="Select a questionnaire"
                      defaultValue={
                        form.questionnaireId ? String(form.questionnaireId) : ""
                      }
                      onChange={(value) => {
                        setForm((prev) => ({
                          ...prev,
                          questionnaireId: value,
                        }));
                      }}
                      className="dark:bg-dark-900"
                    />
                  </FieldCard>

                  <FieldCard icon={Video} label="Hardware">
                    <Select
                      options={glasses}
                      placeholder="Select a hardware email"
                      defaultValue={form.hardwareEmail || ""}
                      onChange={(value) =>
                        setForm((prev) => ({ ...prev, hardwareEmail: value }))
                      }
                      className="dark:bg-dark-900"
                    />
                  </FieldCard>
                </div>

                {questionnaires?.find(
                  (q) => q.id.toString() === String(form.questionnaireId),
                )?.has_potential_analysis && (
                  <p className="mt-3 flex items-start gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800 dark:border-sky-800/40 dark:bg-sky-950/20 dark:text-sky-200">
                    <ClipboardList className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    This questionnaire includes Potential Analysis (P1) — it
                    will be automatically included in this audit.
                  </p>
                )}
              </div>

              {/* Section: Schedule */}
              <div>
                <p className="mb-3 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-widest text-[#064273] dark:text-blue-300">
                  <CalendarClock className="h-3.5 w-3.5" />
                  Schedule (Plant local time)
                </p>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <DatePickerOnly
                    id="auditDate"
                    label="Audit Date (Plant)"
                    value={form.auditDate}
                    onChange={(date) =>
                      setForm((prev) => ({ ...prev, auditDate: date }))
                    }
                  />

                  <TimePicker
                    label="Start Time (Plant)"
                    value={form.startTime}
                    onChange={(time) =>
                      setForm((prev) => ({ ...prev, startTime: time }))
                    }
                    selectedDate={form.auditDate}
                    blockedSlots={blockedSlots}
                    compareTime={form.endTime}
                    mode="start"
                  />

                  <TimePicker
                    label="End Time (Plant)"
                    value={form.endTime}
                    onChange={(time) =>
                      setForm((prev) => ({ ...prev, endTime: time }))
                    }
                    selectedDate={form.auditDate}
                    blockedSlots={blockedSlots}
                    compareTime={form.startTime}
                    mode="end"
                  />
                </div>
              </div>

              {errorMessage && (
                <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700 dark:border-red-800/40 dark:bg-red-900/20 dark:text-red-300">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{errorMessage}</span>
                </div>
              )}
              {showUnavailableConfirm && (
                <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 text-amber-900 dark:border-amber-700 dark:bg-amber-950/20 dark:text-amber-200">
                  <p className="flex items-center gap-2 text-sm font-semibold">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    Auditee availability conflict
                  </p>
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
                      onClick={handleConfirmPlanAnyway}
                      disabled={planningLoading}
                      className="rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {planningLoading ? "Processing..." : "Plan Anyway"}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* RIGHT: Time synchronization / timezone previews */}
            <div className="space-y-4">
              <div className="rounded-xl border border-[#064273]/10 bg-[#f3f9ff] p-4 dark:border-[#064273]/35 dark:bg-[#064273]/10">
                <div className="mb-2.5 flex items-center gap-2">
                  <Globe2 className="h-4 w-4 text-[#064273] dark:text-blue-300" />
                  <span className="text-sm font-semibold text-[#064273] dark:text-blue-200">
                    Live clocks
                  </span>
                </div>
                <div className="space-y-2 text-sm">
                  {renderPreview("🏭 Plant", plantTz, new Date())}
                  {renderPreview("🧑‍💼 You", auditorTz, new Date())}
                  {renderPreview("👤 Auditee", auditeeTz, new Date())}
                </div>
              </div>

              <div className="rounded-xl border border-gray-100 bg-gray-50/60 p-4 dark:border-white/5 dark:bg-white/[0.02]">
                <div className="mb-2.5 flex items-center gap-2">
                  <Clock className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                  <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                    Selected start time
                  </span>
                </div>
                <div className="space-y-2">
                  {renderPreview("🏭 Plant", plantTz, form.startTime)}
                  {renderPreview("🧑‍💼 You", auditorTz, form.startTime)}
                  {renderPreview("👤 Auditee", auditeeTz, form.startTime)}
                </div>
              </div>

              {form.endTime && (
                <div className="rounded-xl border border-gray-100 bg-gray-50/60 p-4 dark:border-white/5 dark:bg-white/[0.02]">
                  <div className="mb-2.5 flex items-center gap-2">
                    <Clock className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                    <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                      Selected end time
                    </span>
                  </div>
                  <div className="space-y-2">
                    {renderPreview("🏭 Plant", plantTz, form.endTime)}
                    {renderPreview("🧑‍💼 You", auditorTz, form.endTime)}
                    {renderPreview("👤 Auditee", auditeeTz, form.endTime)}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 rounded-b-3xl border-t border-gray-100 px-6 py-4 dark:border-white/5">
          <button
            onClick={closeAuditModalOpen}
            type="button"
            className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={planningLoading}
            className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-[#064273] to-[#0f628f] px-4 py-2 text-sm font-semibold text-white transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {planningLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CalendarPlus className="h-4 w-4" />
            )}
            {planningLoading ? "Processing..." : "Add Audit Plan"}
          </button>
        </div>
      </div>

      <div id="datepicker-portal"></div>
    </Modal>
  );
}
