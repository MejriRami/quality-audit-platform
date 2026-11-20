// AuditChecklistRefactored.tsx  (full replacement)
// Key changes:
//   1. useDraftAudit hook integrated — auto-save on every summary field change
//   2. Draft pre-filled on audit selection (loaded from server)
//   3. submitted_at is server-stamped; client just calls /execute (no timestamp sent)
//   4. IATF-NC path also uses the same draft hook for start/end/strong/weak fields
//   5. DraftStatusBadge shown in all modes
//   6. flushSave() called synchronously right before dispatching executeAuditThunk
//   7. VDA questions metadata now comes from backend and is passed to VdaExecution
//   8. VDA audits now use the new dedicated endpoint: /audits/{auditId}/vda-questions
//   FIX: VDA selectedIds now starts empty so only user-selected questions are evaluated
//   FIX2: VDA 2/3 rule enforced on frontend — canSubmit blocked and handleSubmit guarded
//   FIX3: Deselecting a VDA question now resets its value/findings/CAR so it is never
//         considered "fulfilled" after being unchecked (toggleVdaSelect + selectAllInSection)

import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import {
  Upload,
  X,
  Download,
  FileText,
  ClipboardList,
  ChevronDown,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Calendar,
} from "lucide-react";
import toast from "react-hot-toast";
import Select from "../form/Select";
import Enum from "../enum/Enum";
import VdaExecution, { VdaQuestionMeta } from "./VdaExecution";
import PotentialAnalysisExecution, {
  PaAnswerState,
  PaQuestionMeta,
} from "./PotentialAnalysisExecution";
import IATFNonConformityManager from "./IatfNonConformityManager";
import { useDispatch, useSelector } from "react-redux";
import { AppDispatch, RootState } from "../../redux/store";
import {
  executeAuditThunk,
  fetchPickableAuditsByAuditor,
  getAuditQuestions,
  removePickableAudit,
} from "../../redux/audit/audit-slice";
import { apiUploadFile } from "../../redux/audit/audit";
import { useDraftAudit, DraftPayload } from "../../hooks/useDraftAudit";
import DraftStatusBadge from "./DraftStatusBadge";
import axios, { type AxiosError } from "axios";

// ==================== TYPES ====================
type AuditValue = "" | -1 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10;

interface UploadedDoc {
  filename: string;
  mimetype: string;
  size: number;
  file_url: string;
}

interface AuditItem {
  row: number;
  uiId: string; // for React keying, since questionId can be duplicated in IATF-NC mode
  questionId: number;
  parentQuestionId?: number | null;
  requirementId?: number | null;
  isRequirement?: boolean;
  process?: string | null;
  question: string;
  requirementCode?: string;
  critical: number;
  weight: number;
  value: AuditValue;
  findings: string;
  carReason: string;
  evidence: File[];
  uploadedDocs: UploadedDoc[];
  requestCAR: boolean;
  silentBox: boolean;
  immediateActionRequired: boolean;
  errors: { value?: string; findings?: string; carReason?: string };
}

interface ValueOption {
  value: AuditValue;
  label: string;
  color: string;
}

interface AuditSummary {
  auditDate: string;
  startTime: string;
  endTime: string;
  strongPoints: string;
  weakPoints: string;
  questionnaireName: string;
}

type VdaSideMode = "product" | "process_support" | "both";

const hasText = (v?: string | null) => Boolean(v && v.trim().length > 0);

const getErrorMessage = (err: unknown, fallback: string) => {
  const axiosErr = err as AxiosError<{ detail?: string }>;
  return (
    axiosErr?.response?.data?.detail ||
    (err instanceof Error ? err.message : fallback)
  );
};

type SubmittedNonConformity = {
  classification?: string;
  uploadedDocs?: UploadedDoc[];
  evidence?: File[];
  findings?: string;
  observedNonConformity?: string;
  requestCAR?: boolean;
  silentBox?: boolean;
  process?: string;
  normParagraph?: string;
  question?: string;
};

const hasMeaningfulItemInput = (item: AuditItem) =>
  item.value !== "" ||
  hasText(item.findings) ||
  hasText(item.carReason) ||
  item.requestCAR ||
  item.evidence.length > 0 ||
  item.uploadedDocs.length > 0;

const hasMeaningfulAnswersInput = (answers?: DraftPayload["answers"]) =>
  Boolean(
    answers?.some(
      (a) =>
        a.value != null ||
        hasText(a.finding_text) ||
        Boolean(a.request_car) ||
        hasText(a.car_reason) ||
        (a.documents?.length ?? 0) > 0 ||
        hasText(a.process) ||
        hasText(a.standard_paragraph) ||
        hasText(a.classification),
    ),
  );

const hasMeaningfulDraftSummary = (summary: AuditSummary, today: string) =>
  hasText(summary.startTime) ||
  hasText(summary.endTime) ||
  hasText(summary.strongPoints) ||
  hasText(summary.weakPoints) ||
  (hasText(summary.auditDate) && summary.auditDate !== today);

// ==================== SCORING SYSTEMS ====================
const IATF_PLANT_MANAGER_VALUE_OPTIONS: ValueOption[] = [
  { value: -1, label: "Optional", color: "text-yellow-700" },
  { value: 1, label: "1 - Poor", color: "text-red-700" },
  { value: 2, label: "2 - Weak", color: "text-orange-700" },
  { value: 3, label: "3 - Acceptable", color: "text-amber-600" },
  { value: 4, label: "4 - Good", color: "text-emerald-600" },
  { value: 5, label: "5 - Excellent", color: "text-emerald-700" },
];

const ISO_VALUE_OPTIONS: ValueOption[] = [
  { value: -1, label: "Optional", color: "text-yellow-700" },
  { value: 1, label: "1 - Poor", color: "text-red-700" },
  { value: 2, label: "2 - Weak", color: "text-orange-700" },
  { value: 3, label: "3 - Acceptable", color: "text-amber-600" },
  { value: 4, label: "4 - Good", color: "text-emerald-600" },
  { value: 5, label: "5 - Excellent", color: "text-emerald-700" },
];

const INTERNAL_VALUE_OPTIONS: ValueOption[] = [
  { value: -1, label: "Optional", color: "text-yellow-700" },
  { value: 0, label: "0 - Inexistant", color: "text-red-700" },
  { value: 5, label: "5 - Improvement needed", color: "text-amber-700" },
  { value: 10, label: "10 - Good practice", color: "text-emerald-700" },
];

const LEGACY_STANDARD_VALUE_OPTIONS: ValueOption[] = [
  { value: -1, label: "Optional", color: "text-yellow-700" },
  { value: 0, label: "0 - Inexistant", color: "text-red-700" },
  { value: 3, label: "3 - Not sufficient", color: "text-orange-700" },
  { value: 5, label: "5 - Improvement needed", color: "text-amber-700" },
  { value: 8, label: "8 - Acceptable", color: "text-emerald-600" },
  { value: 10, label: "10 - Good practice", color: "text-emerald-700" },
];

const VDA_VALUE_OPTIONS: ValueOption[] = [
  { value: -1, label: "Optional", color: "text-yellow-700" },
  { value: 0, label: "0 - The requirements are not met", color: "text-red-700" },
  { value: 4, label: "4 - The requirements are insufficiently met; major deviations", color: "text-orange-700" },
  { value: 6, label: "6 - The requirements are partially met; significant deviations", color: "text-amber-600" },
  { value: 8, label: "8 - The requirements are mainly met; minor deviations", color: "text-emerald-600" },
  { value: 10, label: "10 - The requirements are fully met; no deviations", color: "text-emerald-700" },
];
const VDA_P1_VALUE_OPTIONS: ValueOption[] = [
  { value: -1, label: "n.e. - Not evaluated", color: "text-yellow-700" },
  { value: 0, label: "Red - Requirement not met", color: "text-red-700" },
  { value: 4, label: "Yellow - Requirement partially met", color: "text-amber-600" },
  { value: 10, label: "Green - Requirement met", color: "text-emerald-700" },
];

// Open audit result -> stored value (must match OPEN_RESULT_VALUE in audit_service.py).
const openResultValue = (result?: string) =>
  result === "Conformity" ? 10 : result === "Observation" ? 5 : 0;

// ==================== UTILITIES ====================
type EvaluationProfile =
  | "VDA_PROCESS"
  | "VDA_P1_POTENTIAL"
  | "IATF_PM"
  | "IATF_CLASSIFICATION"
  | "ISO_SYSTEM"
  | "INTERNAL"
  | "OPEN"
  | "LEGACY_STANDARD";

interface QuestionnaireProfileContext {
  scoreCalculation?: string | null;
  frameworkCode?: string | null;
  frameworkLabel?: string | null;
  auditTypeValue?: string | null;
}

const normalizeProfileKey = (value?: string | null) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const resolveEvaluationProfile = (
  name: string,
  ctx?: QuestionnaireProfileContext,
): EvaluationProfile => {
  const directKey = normalizeProfileKey(ctx?.scoreCalculation);
  if (
    directKey === "IATF_PM" ||
    directKey === "IATF_CLASSIFICATION" ||
    directKey === "ISO_SYSTEM" ||
    directKey === "VDA_PROCESS" ||
    directKey === "VDA_P1_POTENTIAL" ||
    directKey === "INTERNAL" ||
    directKey === "OPEN" ||
    directKey === "LEGACY_STANDARD"
  ) {
    return directKey;
  }

  const legacyKey = directKey.replace(/_/g, "");
  const explicitMap: Record<string, EvaluationProfile> = {
    FS1: "IATF_PM",
    FS2: "IATF_PM",
    FS3: "IATF_CLASSIFICATION",
    FS4: "LEGACY_STANDARD",
    IATFNC: "IATF_CLASSIFICATION",
    VDA: "VDA_PROCESS",
    VDA63: "VDA_PROCESS",
    VDAP1: "VDA_P1_POTENTIAL",
  };
  if (legacyKey in explicitMap) return explicitMap[legacyKey];

  const blob = [
    name,
    ctx?.frameworkCode,
    ctx?.frameworkLabel,
    ctx?.auditTypeValue,
  ]
    .map((v) => String(v ?? "").toLowerCase())
    .join(" ");

  if (blob.includes("vda") && blob.includes("potential")) return "VDA_P1_POTENTIAL";
  if (blob.includes("plant manager") && blob.includes("iatf")) return "IATF_PM";
  if (blob.includes("special process") || blob.includes("internal"))
    return "INTERNAL";
  if (blob.includes("iso")) return "ISO_SYSTEM";
  if (blob.includes("vda") || blob.includes("process")) return "VDA_PROCESS";
  if (blob.includes("iatf")) return "IATF_CLASSIFICATION";
  return "LEGACY_STANDARD";
};

const getValueOptions = (
  name: string,
  ctx?: QuestionnaireProfileContext,
): ValueOption[] => {
  const profile = resolveEvaluationProfile(name, ctx);
  if (profile === "VDA_P1_POTENTIAL") return VDA_P1_VALUE_OPTIONS;
  if (profile === "VDA_PROCESS") return VDA_VALUE_OPTIONS;
  if (profile === "IATF_PM") return IATF_PLANT_MANAGER_VALUE_OPTIONS;
  if (profile === "ISO_SYSTEM") return ISO_VALUE_OPTIONS;
  if (profile === "INTERNAL") return INTERNAL_VALUE_OPTIONS;
  return LEGACY_STANDARD_VALUE_OPTIONS;
};

const needsDetails = (
  v: AuditValue,
  name: string,
  ctx?: QuestionnaireProfileContext,
): boolean => {
  if (v === "" || v === -1) return false;
  const profile = resolveEvaluationProfile(name, ctx);
  if (profile === "VDA_P1_POTENTIAL") return v === 0 || v === 4;
  // Must match the backend rule in audit_service.py (submit_audit_execution):
  // VDA process scores of 0, 4, 6, or 8 require a CAR + supporting findings.
  // Only 10 ("fully met") and Optional/N.E. are exempt.
  if (profile === "VDA_PROCESS") return v === 0 || v === 4 || v === 6 || v === 8;
  if (profile === "IATF_PM" || profile === "ISO_SYSTEM") return v <= 3;
  return v <= 5;
};

const isVdaRemarkQuestion = (q: VdaQuestionMeta) => {
  const code = String(q.question_code ?? "").toLowerCase();
  const text = String(q.question_text_en ?? "").toLowerCase().trim();
  return (
    text.startsWith("remark") ||
    text.startsWith("remarks") ||
    text.includes("remarks to be fulfilled") ||
    code.includes("remark")
  );
};

const getVdaQuestionId = (q: VdaQuestionMeta) => {
  const n = Number(q.id ?? q.question_id);
  return Number.isFinite(n) ? n : null;
};

const getVdaItemByQuestionAndProcess = (
  arr: AuditItem[],
  qid: number | null,
  process?: string | null,
) =>
  qid == null
    ? undefined
    : arr.find(
        (i) =>
          i.questionId === qid && String(i.process ?? "") === String(process ?? ""),
      );

const getVdaScoringScopeItem = (item: AuditItem | undefined, selectedIds: Set<string>) => {
  if (!item || !selectedIds.has(item.uiId)) return false;
  return item.value !== "" && item.value !== -1;
};
const getVdaBaseCode = (code?: string) => {
  const c = String(code ?? "").trim().toUpperCase().replace(/\*$/, "");
  const parts = c.split(".");
  return parts.length >= 2 ? `${parts[0]}.${parts[1]}` : c;
};
const buildVdaRequirementCode = (
  parentCode: string,
  requirementCode?: string | null,
  fallbackIndex?: number,
) => {
  const parent = String(parentCode ?? "").trim().replace(/\.+$/, "");
  let rawRequirement = String(requirementCode ?? "")
    .trim()
    .replace(/^\.+|\.+$/g, "");

  if (!rawRequirement) {
    return parent ? `${parent}.${fallbackIndex ?? 1}` : `Q-${fallbackIndex ?? 1}`;
  }

  if (!parent) {
    return rawRequirement;
  }

  const normalizedParent = parent.toUpperCase();
  let normalizedRequirement = rawRequirement.toUpperCase();

  // Source data sometimes has the parent code duplicated at the start of
  // the requirement code (e.g. "P2.1.P2.1.1"). Collapse that back down to
  // "P2.1.1" before the normal parent-prefix check below.
  const doubledPrefix = `${normalizedParent}.${normalizedParent}`;
  if (
    normalizedRequirement === doubledPrefix ||
    normalizedRequirement.startsWith(`${doubledPrefix}.`)
  ) {
    rawRequirement = rawRequirement.slice(parent.length + 1);
    normalizedRequirement = normalizedRequirement.slice(normalizedParent.length + 1);
  }

  if (
    normalizedRequirement === normalizedParent ||
    normalizedRequirement.startsWith(`${normalizedParent}.`)
  ) {
    return rawRequirement;
  }

  return `${parent}.${rawRequirement}`;
};
const getVdaProcessType = (process?: string | null) => {
  const raw = String(process ?? "").toLowerCase();
  if (raw.includes("product")) return "product";
  if (raw.includes("process") || raw.includes("support")) return "process_support";
  return "";
};
const shouldSplitP3P4 = (element?: string | null) => {
  const e = String(element ?? "").toUpperCase();
  return e === "P3" || e === "P4";
};

const getVdaSectionKey = (q: VdaQuestionMeta, isP1Potential: boolean) => {
  const normalizedElement = String(q.element ?? "").trim().toUpperCase();
  if (normalizedElement) return normalizedElement;
  return isP1Potential ? "P1" : "";
};

const isProcessOnlyP4Question = (
  element?: string | null,
  questionCode?: string | null,
) => {
  if (String(element ?? "").toUpperCase() !== "P4") return false;
  const raw = String(questionCode ?? "").trim().toUpperCase();
  const normalized = raw.replace(/^P4\./, "4.");
  return normalized.startsWith("4.6") || normalized.startsWith("4.7");
};

const getValueColor = (v: AuditValue, opts: ValueOption[]) =>
  v === ""
    ? "text-slate-700"
    : (opts.find((o) => o.value === v)?.color ?? "text-slate-700");

const getCriticalClass = (c: number) =>
  c >= 8
    ? "bg-red-100 text-red-700 ring-1 ring-red-200"
    : c >= 5
      ? "bg-amber-100 text-amber-700 ring-1 ring-amber-200"
      : "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200";

const validateItem = (
  item: AuditItem,
  name: string,
  ctx?: QuestionnaireProfileContext,
): AuditItem["errors"] => {
  const errors: AuditItem["errors"] = {};
  const profile = resolveEvaluationProfile(name, ctx);
  const isVdaProfile = profile === "VDA_PROCESS" || profile === "VDA_P1_POTENTIAL";
  const isVdaP1Profile = profile === "VDA_P1_POTENTIAL";
  const isPlantManagerMandatory = profile === "IATF_PM" && item.weight === 1;
  if (item.value === "") errors.value = "Required";
  if (isPlantManagerMandatory && item.value === -1) {
    errors.value = "Mandatory question cannot be optional";
  }
  if (needsDetails(item.value, name, ctx)) {
    if (!item.findings.trim()) errors.findings = "Required";
    if (!isVdaProfile && item.requestCAR && !item.carReason.trim())
      errors.carReason = "Required for CAR request";
  }
  if (
    isVdaP1Profile &&
    (item.value === 0 || item.value === 4) &&
    (item.uploadedDocs.length + item.evidence.length) === 0
  ) {
    errors.findings = errors.findings || "Evidence is required for Red/Yellow in P1";
  }
  return errors;
};

const getQuestionnaireType = (
  name: string,
  ctx?: QuestionnaireProfileContext,
) => {
  const profile = resolveEvaluationProfile(name, ctx);
  if (profile === "VDA_PROCESS" || profile === "VDA_P1_POTENTIAL") return "VDA";
  if (profile === "IATF_PM") return "IATF PM (Internal Checklist)";
  if (profile === "IATF_CLASSIFICATION") return "IATF Standard (NC)";
  if (profile === "ISO_SYSTEM") return "ISO";
  if (profile === "INTERNAL") return "Internal";
  if (profile === "OPEN") return "Open audit";
  return "Standard";
};

const getScaleDescription = (
  name: string,
  ctx?: QuestionnaireProfileContext,
) => {
  const profile = resolveEvaluationProfile(name, ctx);
  if (profile === "VDA_PROCESS") return "VDA (0/4/6/8/10)";
  if (profile === "VDA_P1_POTENTIAL") return "VDA P1 traffic light (Red/Yellow/Green/n.e.)";
  if (profile === "IATF_PM") return "Internal checklist scoring (1/2/3/4/5)";
  if (profile === "IATF_CLASSIFICATION")
    return "IATF classification (Minor/Major/Improvement/Strong Point)";
  if (profile === "ISO_SYSTEM")
    return "ISO classification (Major NC/Minor NC/OFI/Conformity)";
  if (profile === "INTERNAL") return "Internal (0/5/10)";
  if (profile === "OPEN") return "Open (Conformity / Observation / Nonconformity)";
  return "Standard (0/3/5/8/10)";
};

const getFooterMessage = (name: string, ctx?: QuestionnaireProfileContext) => {
  const profile = resolveEvaluationProfile(name, ctx);
  if (profile === "VDA_PROCESS")
    return "Values 0, 4, 6, or 8 require findings and create a CAR from those findings.";
  if (profile === "VDA_P1_POTENTIAL")
    return "P1: max 3 n.e. allowed. Red/Yellow require findings and evidence.";
  if (profile === "IATF_CLASSIFICATION")
    return "Use classification entries and attach evidence as needed.";
  if (profile === "ISO_SYSTEM")
    return "Use Major NC / Minor NC / OFI / Conformity classification.";
  if (profile === "IATF_PM") return "Values <=3 require findings.";
  if (profile === "OPEN") return "Type each question and its answer.";
  return "Values <=5 require findings.";
};

const getModeGuidance = (name: string, ctx?: QuestionnaireProfileContext) => {
  const profile = resolveEvaluationProfile(name, ctx);
  if (profile === "IATF_PM") {
    return "This is an internal Plant Manager checklist, not an IATF standard NC classification audit.";
  }
  if (profile === "IATF_CLASSIFICATION") {
    return "IATF standard audits are recorded by NC classification, not by numeric score.";
  }
  if (profile === "ISO_SYSTEM") {
    return "ISO system audits are recorded by classification (Major NC, Minor NC, OFI, Conformity).";
  }
  if (profile === "INTERNAL") {
    return "Internal checklists use value scoring: 0 / 5 / 10.";
  }
  if (profile === "OPEN") {
    return "Open audit: write your own questions and answers, and mark each one Conformity, Observation or Nonconformity.";
  }
  if (profile === "VDA_PROCESS") {
    return "VDA / process audits use value scoring: 0 / 4 / 6 / 8 / 10.";
  }
  if (profile === "VDA_P1_POTENTIAL") {
    return "VDA P1 potential analysis uses traffic-light evaluation (Red/Yellow/Green/n.e.).";
  }
  return "Legacy fallback uses value scoring: 0 / 3 / 5 / 8 / 10.";
};

const isClassificationMode = (
  name: string,
  ctx?: QuestionnaireProfileContext,
) => {
  const profile = resolveEvaluationProfile(name, ctx);
  return (
    profile === "IATF_CLASSIFICATION" ||
    profile === "ISO_SYSTEM" ||
    profile === "OPEN"
  );
};

// ==================== SUB-COMPONENTS ====================

const DraftIndicator = ({
  saving,
  lastSavedAt,
  isDirty,
}: {
  saving: boolean;
  lastSavedAt: Date | null;
  isDirty: boolean;
}) => (
  <div className="flex items-center">
    <DraftStatusBadge
      saving={saving}
      lastSavedAt={lastSavedAt}
      isDirty={isDirty}
    />
  </div>
);

const EvidenceUpload = ({
  evidence,
  uploadedDocs,
  previews,
  questionId,
  onAdd,
  onRemoveLocal,
  onRemoveUploaded,
}: {
  evidence: File[];
  uploadedDocs: UploadedDoc[];
  previews: Map<string, string>;
  questionId: number;
  onAdd: (files: FileList | null) => void;
  onRemoveLocal: (idx: number) => void;
  onRemoveUploaded: (idx: number) => void;
}) => {
  const hasLocal = evidence.length > 0;
  const hasUploaded = uploadedDocs.length > 0;

  return (
    <div className="space-y-2">
      <label className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg cursor-pointer transition-colors">
        <Upload size={14} className="text-slate-600" />
        <span className="text-slate-700">Upload Image</span>
        <input
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => onAdd(e.target.files)}
        />
      </label>

      {hasLocal && (
        <div className="flex flex-wrap gap-2">
          {evidence.map((file, idx) => {
            const key = `${questionId}-${file.name}-${file.size}-${file.lastModified}-${idx}`;
            return (
              <div
                key={key}
                className="relative group rounded-lg overflow-hidden border border-slate-200 shadow-sm"
              >
                <img
                  src={previews.get(key)}
                  alt={file.name}
                  className="h-16 w-16 object-cover"
                />
                <button
                  type="button"
                  onClick={() => onRemoveLocal(idx)}
                  className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-rose-600 text-white flex items-center justify-center shadow-md hover:bg-rose-700 transition-colors"
                  aria-label="Remove uploaded image"
                >
                  <X size={12} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {!hasLocal && hasUploaded && (
        <div className="flex flex-wrap gap-2">
          {uploadedDocs.map((doc, idx) => (
            <div
              key={`${questionId}-uploaded-${idx}-${doc.file_url}`}
              className="relative group rounded-lg overflow-hidden border border-slate-200 shadow-sm"
            >
              <img
                src={doc.file_url}
                alt={doc.filename}
                className="h-16 w-16 object-cover"
              />
              <button
                type="button"
                onClick={() => onRemoveUploaded(idx)}
                className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-rose-600 text-white flex items-center justify-center shadow-md hover:bg-rose-700 transition-colors"
                aria-label="Remove uploaded image"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const AuditRow = ({
  item,
  previews,
  valueOptions,
  questionnaireName,
  profileContext,
  onUpdateField,
  onToggleCAR,
  onAddEvidence,
  onRemoveLocalEvidence,
  onRemoveUploadedEvidence,
}: {
  item: AuditItem;
  previews: Map<string, string>;
  valueOptions: ValueOption[];
  questionnaireName: string;
  profileContext?: QuestionnaireProfileContext;
  onUpdateField: <K extends keyof AuditItem>(
    uiId: string,
    f: K,
    v: AuditItem[K],
  ) => void;
  onToggleCAR: (uiId: string) => void;
  onAddEvidence: (uiId: string, files: FileList | null) => void;
  onRemoveLocalEvidence: (uiId: string, idx: number) => void;
  onRemoveUploadedEvidence: (uiId: string, idx: number) => void;
}) => {
  const hasErrors = Object.keys(item.errors).length > 0;
  const detailsRequired = needsDetails(item.value, questionnaireName, profileContext);
  const isPlantManagerMandatory =
    resolveEvaluationProfile(questionnaireName, profileContext) === "IATF_PM" &&
    item.weight === 1;
  const canRequestCAR = item.value !== "" && item.value !== -1;

  return (
    <tr
      className={`group hover:bg-indigo-50/50 transition-colors ${hasErrors ? "bg-rose-50/40" : ""} ${item.requestCAR ? "bg-amber-50/50" : ""}`}
    >
      <td className="px-4 py-4 align-top">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-slate-100 group-hover:bg-slate-200 transition-colors">
          <span className="text-sm font-semibold text-slate-700">
            {item.row}
          </span>
        </div>
      </td>
      <td className="px-4 py-4 align-top">
        <p className="text-sm text-slate-800 leading-relaxed">
          {item.question}
        </p>
        {isPlantManagerMandatory && (
          <p className="mt-1 text-[11px] font-semibold text-rose-700">
            Mandatory question (optional not allowed)
          </p>
        )}
      </td>
      <td className="px-4 py-4 align-top text-center">
        <span
          className={`inline-flex items-center justify-center w-10 h-10 rounded-xl text-sm font-bold ${getCriticalClass(item.critical)}`}
        >
          {item.critical}
        </span>
      </td>
      <td className="px-4 py-4 align-top">
        <select
          value={item.value}
          onChange={(e) => {
            const val =
              e.target.value === ""
                ? ""
                : (Number(e.target.value) as AuditValue);
            onUpdateField(item.uiId, "value", val);
          }}
          className={`w-full p-2.5 text-sm border rounded-lg appearance-none focus:outline-none focus:ring-2 focus:ring-[#064273] transition-all ${item.errors?.value ? "border-red-400 bg-red-50" : "border-slate-300 bg-white hover:border-slate-400"} ${getValueColor(item.value, valueOptions)} font-medium`}
        >
          <option value="">Select value...</option>
          {valueOptions.map((opt) => (
            <option key={String(opt.value)} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {item.errors?.value && (
          <p className="text-xs text-red-600 mt-1 font-medium">
            {item.errors.value}
          </p>
        )}
      </td>
      <td className="px-4 py-4 align-top">
        <textarea
          value={item.findings}
          onChange={(e) => onUpdateField(item.uiId, "findings", e.target.value)}
          rows={3}
          placeholder={
            detailsRequired ? "Required details..." : "Optional notes..."
          }
          className={`w-full p-2.5 text-sm border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-[#064273] transition-all ${item.errors?.findings ? "border-red-400 bg-red-50" : "border-slate-300 hover:border-slate-400"}`}
        />
        {item.errors?.findings && (
          <p className="text-xs text-red-600 mt-1 font-medium">
            {item.errors.findings}
          </p>
        )}
      </td>
      <td className="px-4 py-4 align-top">
        <EvidenceUpload
          evidence={item.evidence}
          uploadedDocs={item.uploadedDocs}
          previews={previews}
          questionId={item.questionId}
          onAdd={(f) => onAddEvidence(item.uiId, f)}
          onRemoveLocal={(i) => onRemoveLocalEvidence(item.uiId, i)}
          onRemoveUploaded={(i) => onRemoveUploadedEvidence(item.uiId, i)}
        />
      </td>
      <td className="px-4 py-4 align-top">
        {canRequestCAR ? (
          <div className="space-y-3">
            <label className="flex items-center gap-2 cursor-pointer group/checkbox">
              <input
                type="checkbox"
                checked={item.requestCAR}
                onChange={() => onToggleCAR(item.uiId)}
                className="w-4 h-4 text-amber-600 bg-white border-slate-300 rounded focus:ring-2 focus:ring-amber-500 cursor-pointer"
              />
              <span className="text-sm font-medium text-slate-700 group-hover/checkbox:text-amber-700 transition-colors">
                Request CAR
              </span>
            </label>
            {item.requestCAR && (
              <>
                <textarea
                  value={item.carReason}
                  onChange={(e) =>
                    onUpdateField(item.uiId, "carReason", e.target.value)
                  }
                  rows={3}
                  placeholder="Indicate the issue (required)..."
                  className={`w-full p-2.5 text-sm border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-amber-500 transition-all ${item.errors?.carReason ? "border-red-400 bg-red-50" : "border-amber-300 hover:border-amber-400"}`}
                />
                {item.errors?.carReason && (
                  <p className="text-xs text-red-600 font-medium">
                    {item.errors.carReason}
                  </p>
                )}
              </>
            )}
          </div>
        ) : (
          <div className="text-xs text-slate-500 italic py-2">
            {item.value === ""
              ? "Select a value first"
              : item.value === -1
                ? "Optional - No CAR"
                : "No CAR needed"}
          </div>
        )}
        <label className="mt-2 flex items-center gap-2 cursor-pointer group/checkbox">
          <input
            type="checkbox"
            checked={item.silentBox}
            onChange={(e) =>
              onUpdateField(item.uiId, "silentBox", e.target.checked)
            }
            className="w-4 h-4 text-slate-700 bg-white border-slate-300 rounded focus:ring-2 focus:ring-slate-500 cursor-pointer"
          />
          <span className="text-xs font-medium text-slate-600 group-hover/checkbox:text-slate-800 transition-colors">
            Silent Box (SB) — exclude from printed report
          </span>
        </label>
      </td>
    </tr>
  );
};

// ==================== MAIN COMPONENT ====================
export default function AuditChecklistRefactored() {
  const today = new Date().toISOString().split("T")[0];
  const lastNcDraftSigRef = useRef("");
  const draftStartedRef = useRef(false);
  const draftSummaryHydratedAuditIdRef = useRef<number | null>(null);
  const draftAnswersHydratedAuditIdRef = useRef<number | null>(null);

  const [selectedAuditor, setSelectedAuditor] = useState<string | number>("");
  const [selectedPlannedAuditId, setSelectedPlannedAuditId] = useState<
    number | ""
  >("");
  const [questionnaireName, setQuestionnaireName] = useState<string>("");
  const [auditee_name, setAuditeeName] = useState<string>("");
  const [items, setItems] = useState<AuditItem[]>([]);
  const [vdaQuestions, setVdaQuestions] = useState<VdaQuestionMeta[]>([]);
  const [potentialAnalysisQuestions, setPotentialAnalysisQuestions] = useState<
    PaQuestionMeta[]
  >([]);
  const [paAnswers, setPaAnswers] = useState<Map<number, PaAnswerState>>(
    new Map(),
  );
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [previews, setPreviews] = useState<Map<string, string>>(new Map());
  const [vdaSelectedIds, setVdaSelectedIds] = useState<Set<string>>(new Set());
  const [vdaSideModeByBase, setVdaSideModeByBase] = useState<Record<string, VdaSideMode>>({});
  const [vdaEnabledSections, setVdaEnabledSections] = useState<Set<string>>(
    () => new Set(),
  );
  const [isDirty, setIsDirty] = useState(false);
  const [plannedAuditOpen, setPlannedAuditOpen] = useState(false);
  const [plannedAuditSearch, setPlannedAuditSearch] = useState("");
  const plannedAuditMenuRef = useRef<HTMLDivElement | null>(null);
  const plannedAuditSearchInputRef = useRef<HTMLInputElement | null>(null);

  const [summary, setSummary] = useState<AuditSummary>({
    auditDate: today,
    startTime: "",
    endTime: "",
    strongPoints: "",
    weakPoints: "",
    questionnaireName: "",
  });

  const { auditorOptions } = Enum();
  const dispatch = useDispatch<AppDispatch>();
  const { pickableAudits, pickableLoading } = useSelector(
    (s: RootState) => s.audit,
  );
  const selectedAuditMeta = useMemo(
    () =>
      pickableAudits.find((a) => a.id === selectedPlannedAuditId) ?? null,
    [pickableAudits, selectedPlannedAuditId],
  );
  const profileContext = useMemo<QuestionnaireProfileContext>(
    () => ({
      scoreCalculation: selectedAuditMeta?.score_calculation,
      frameworkCode: selectedAuditMeta?.framework_code,
      frameworkLabel: selectedAuditMeta?.framework_label,
      auditTypeValue: selectedAuditMeta?.audit_type_value,
    }),
    [selectedAuditMeta],
  );

  const auditorId = useMemo(
    () => Number(selectedAuditor) || 0,
    [selectedAuditor],
  );
  const valueOptions = useMemo(
    () => getValueOptions(questionnaireName, profileContext),
    [questionnaireName, profileContext],
  );
  const isVda = useMemo(
    () => {
      const p = resolveEvaluationProfile(questionnaireName, profileContext);
      return p === "VDA_PROCESS" || p === "VDA_P1_POTENTIAL";
    },
    [questionnaireName, profileContext],
  );
  const isVdaP1 = useMemo(
    () => resolveEvaluationProfile(questionnaireName, profileContext) === "VDA_P1_POTENTIAL",
    [questionnaireName, profileContext],
  );
  const defaultVdaSection = useMemo(() => (isVdaP1 ? "P1" : "P2"), [isVdaP1]);
  const showClassificationInterface = useMemo(
    () => isClassificationMode(questionnaireName, profileContext),
    [questionnaireName, profileContext],
  );

  const draft = useDraftAudit(selectedPlannedAuditId || null);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!plannedAuditMenuRef.current) return;
      if (!plannedAuditMenuRef.current.contains(e.target as Node)) {
        setPlannedAuditOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => {
    if (plannedAuditOpen) {
      plannedAuditSearchInputRef.current?.focus();
    } else {
      setPlannedAuditSearch("");
    }
  }, [plannedAuditOpen]);

  useEffect(() => {
    if (!draft.data || !selectedPlannedAuditId) return;
    if (draftSummaryHydratedAuditIdRef.current === selectedPlannedAuditId) return;
    setSummary((prev) => ({
      ...prev,
      auditDate: draft.data!.audit_date ?? prev.auditDate,
      startTime: draft.data!.start_time ?? prev.startTime,
      endTime: draft.data!.end_time ?? prev.endTime,
      strongPoints: draft.data!.strong_points ?? prev.strongPoints,
      weakPoints: draft.data!.weak_points ?? prev.weakPoints,
    }));
    draftSummaryHydratedAuditIdRef.current = selectedPlannedAuditId;
  }, [draft.data, selectedPlannedAuditId]);

  useEffect(() => {
    if (!isVda) return;
    const sections = Array.from(
      new Set(
        vdaQuestions
          .map((q) => String(q.element ?? "").trim().toUpperCase())
          .filter(Boolean),
      ),
    );
    const firstSection = sections[0] ?? defaultVdaSection;
    setVdaEnabledSections((prev) => (prev.size > 0 ? prev : new Set([firstSection])));
  }, [isVda, vdaQuestions, defaultVdaSection]);

  useEffect(() => {
    if (!draft.data) {
      draftStartedRef.current = false;
      return;
    }
    const draftSummary: AuditSummary = {
      auditDate: draft.data.audit_date ?? today,
      startTime: draft.data.start_time ?? "",
      endTime: draft.data.end_time ?? "",
      strongPoints: draft.data.strong_points ?? "",
      weakPoints: draft.data.weak_points ?? "",
      questionnaireName: "",
    };
    draftStartedRef.current =
      hasMeaningfulDraftSummary(draftSummary, today) ||
      hasMeaningfulAnswersInput(draft.data.answers);
  }, [draft.data, today]);

  useEffect(() => {
    setVdaSideModeByBase({});
  }, [selectedPlannedAuditId]);

  const summaryToDraftPayload = useCallback(
    (s: AuditSummary): DraftPayload => ({
      audit_date: s.auditDate,
      start_time: s.startTime,
      end_time: s.endTime,
      strong_points: s.strongPoints,
      weak_points: s.weakPoints,
    }),
    [],
  );

  useEffect(() => {
    if (!auditorId) {
      draftStartedRef.current = false;
      draftSummaryHydratedAuditIdRef.current = null;
      draftAnswersHydratedAuditIdRef.current = null;
      setSelectedPlannedAuditId("");
      setItems([]);
      setVdaQuestions([]);
      setPotentialAnalysisQuestions([]);
      setPaAnswers(new Map());
      setSubmitted(false);
      setQuestionnaireName("");
      setVdaSelectedIds(new Set());
      setVdaEnabledSections(new Set([defaultVdaSection]));
      setAuditeeName("");
      setIsDirty(false);
      return;
    }
    dispatch(fetchPickableAuditsByAuditor(auditorId))
      .unwrap()
      .catch((err) => {
        toast.error(String(err ?? "Failed to fetch pickable audits"));
      });
    draftStartedRef.current = false;
    draftSummaryHydratedAuditIdRef.current = null;
    draftAnswersHydratedAuditIdRef.current = null;
    setSelectedPlannedAuditId("");
    setItems([]);
    setVdaQuestions([]);
    setPotentialAnalysisQuestions([]);
    setPaAnswers(new Map());
    setSubmitted(false);
    setQuestionnaireName("");
    setVdaSelectedIds(new Set());
      setVdaEnabledSections(new Set([defaultVdaSection]));
    setAuditeeName("");
    setIsDirty(false);
  }, [auditorId, dispatch]);

  const handleAuditSelection = async (auditId: number | "") => {
    draftStartedRef.current = false;
    draftSummaryHydratedAuditIdRef.current = null;
    draftAnswersHydratedAuditIdRef.current = null;
    setSelectedPlannedAuditId(auditId);
    lastNcDraftSigRef.current = "";
    setSubmitted(false);
    setIsDirty(false);
    setPotentialAnalysisQuestions([]);
    setPaAnswers(new Map());
    setSummary({
      auditDate: today,
      startTime: "",
      endTime: "",
      strongPoints: "",
      weakPoints: "",
      questionnaireName: "",
    });

    if (auditId === "") {
      setItems([]);
      setVdaQuestions([]);
      setQuestionnaireName("");
      setVdaSelectedIds(new Set());
      setVdaEnabledSections(new Set([defaultVdaSection]));
      setAuditeeName("");
      return;
    }

    const selectedAudit = pickableAudits.find((a) => a.id === auditId);
    const auditQName = selectedAudit?.questionnaire_name ?? "";
    setQuestionnaireName(auditQName);
    setAuditeeName(selectedAudit?.auditees?.[0]?.email ?? "");

    if (
      isClassificationMode(auditQName, {
        scoreCalculation: selectedAudit?.score_calculation,
        frameworkCode: selectedAudit?.framework_code,
        frameworkLabel: selectedAudit?.framework_label,
        auditTypeValue: selectedAudit?.audit_type_value,
      })
    ) {
      setItems([]);
      setVdaQuestions([]);
      setVdaSelectedIds(new Set());
      setVdaEnabledSections(new Set([defaultVdaSection]));
      return;
    }

    if (auditQName.toLowerCase().includes("vda")) {
      try {
        const token = localStorage.getItem("token");
        const apiBaseUrl =
          (import.meta.env.VITE_API_URL as string | undefined) ||
          (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
          "http://localhost:8000";
        const res = await axios.get(
          `${apiBaseUrl.replace(/\/+$/, "")}/audits/${auditId}/vda-questions`,
          {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          },
        );

        const allQuestions = res.data as Array<{
          id: number;
          description?: string;
          question_text_en?: string;
          critical_value: number;
          weight?: number | null;
          question_code?: string | null;
          standard_paragraph?: string | null;
          element?: string | null;
          chapter?: string | null;
          process?: string | null;
          requirements?: VdaQuestionMeta["requirements"];
          is_asterisk?: boolean | null;
          is_potential_analysis?: boolean | null;
        }>;

        const questions = allQuestions.filter((q) => !q.is_potential_analysis);
        const paQuestions = allQuestions.filter((q) => q.is_potential_analysis);

        setPotentialAnalysisQuestions(
          paQuestions.map((q) => ({
            id: q.id,
            question_code:
              q.question_code ?? q.standard_paragraph ?? `Q-${q.id}`,
            question_text_en: q.question_text_en ?? q.description ?? "",
            critical_value: q.critical_value,
          })),
        );
        setPaAnswers((prev) => {
          const next = new Map<number, PaAnswerState>();
          for (const q of paQuestions) {
            next.set(q.id, prev.get(q.id) ?? { value: "", findings: "", evidence: [] });
          }
          return next;
        });

        const derivedVdaQuestions: VdaQuestionMeta[] = questions.flatMap((q) => {
          const rawCode = q.question_code ?? q.standard_paragraph ?? "";

          const derivedElement =
            q.element ??
            q.chapter ??
            (() => {
              const match = String(rawCode).match(/^(P[2-7])/i);
              return match ? match[1].toUpperCase() : "";
            })();

          const baseMeta = {
            id: q.id,
            question_id: q.id,
            element: derivedElement || "",
            question_code: rawCode || `Q-${q.id}`,
            question_text_en: q.question_text_en ?? q.description ?? "",
            requirements: q.requirements ?? [],
            process: q.process ?? null,
            is_asterisk: Boolean(q.is_asterisk),
            critical_value: q.critical_value,
            weight: Number(q.weight ?? 0),
          };
          if (
            shouldSplitP3P4(baseMeta.element) &&
            !baseMeta.process &&
            isProcessOnlyP4Question(baseMeta.element, baseMeta.question_code)
          ) {
            return [{ ...baseMeta, process: "process_support" }];
          }
          if (shouldSplitP3P4(baseMeta.element) && !baseMeta.process) {
            return [
              { ...baseMeta, process: "product" },
              { ...baseMeta, process: "process_support" },
            ];
          }
          const requirementMetas = (q.requirements ?? []).map((req, idx) => ({
            ...baseMeta,
            id: Number(`${q.id}${idx + 1}`),
            question_id: q.id,
            question_code: buildVdaRequirementCode(
              rawCode,
              req.requirement_code,
              idx + 1,
            ),
            question_text_en: req.description ?? req.requirement_code ?? "",
            requirement_id: req.id,
            requirement_code: req.requirement_code ?? "",
            requirement_sort_order: req.sort_order ?? idx + 1,
            is_requirement: true,
            parent_question_id: q.id,
          }));
          return [baseMeta, ...requirementMetas];
        });

        setVdaQuestions(derivedVdaQuestions);

        const newItems: AuditItem[] = derivedVdaQuestions.map((q, idx) => ({
          uiId: `${q.id}-${String(q.process ?? "na")}-${idx}`,
          row: idx + 1,
          questionId: Number(q.id),
          parentQuestionId: q.parent_question_id ?? null,
          requirementId: q.requirement_id ?? null,
          isRequirement: Boolean(q.is_requirement),
          process: q.process ?? null,
          question: q.question_text_en ?? "",
          requirementCode: q.requirement_code ?? "",
          critical: Number(q.critical_value ?? 0),
          weight: Number(q.weight ?? 0),
          value: "",
          findings: "",
          carReason: "",
          evidence: [],
          uploadedDocs: [],
          requestCAR: false,
          silentBox: false,
          immediateActionRequired: false,
          errors: {},
        }));

        setItems(newItems);
        // FIX: start with empty selection — user picks which chapters/questions to answer
        setVdaSelectedIds(new Set());
      setVdaEnabledSections(new Set([defaultVdaSection]));
      } catch (err) {
        console.error(err);
        setItems([]);
        setVdaQuestions([]);
        setPotentialAnalysisQuestions([]);
        setPaAnswers(new Map());
        setQuestionnaireName("");
        setVdaSelectedIds(new Set());
      setVdaEnabledSections(new Set([defaultVdaSection]));
        toast.error("Failed to load VDA questions");
      }

      return;
    }

    const result = await dispatch(getAuditQuestions(auditId));
    if (getAuditQuestions.fulfilled.match(result)) {
      const questions = result.payload as Array<{
          id: number;
          description?: string;
          question_text_en?: string;
          critical_value: number;
          weight?: number | null;
          question_code?: string | null;
          standard_paragraph?: string | null;
          element?: string | null;
          chapter?: string | null;
          process?: string | null;
          requirements?: VdaQuestionMeta["requirements"];
          is_asterisk?: boolean | null;
        }>;

      const derivedVdaQuestions: VdaQuestionMeta[] = questions.flatMap((q) => {
        const rawCode = q.question_code ?? q.standard_paragraph ?? "";

        const derivedElement =
          q.element ??
          q.chapter ??
          (() => {
            const match = String(rawCode).match(/^(P[2-7])/i);
            return match ? match[1].toUpperCase() : "";
          })();

        const baseMeta = {
          id: q.id,
          question_id: q.id,
          element: derivedElement || "",
          question_code: rawCode || `Q-${q.id}`,
          question_text_en: q.question_text_en ?? q.description ?? "",
          requirements: q.requirements ?? [],
          process: q.process ?? null,
          is_asterisk: Boolean(q.is_asterisk),
          critical_value: q.critical_value,
          weight: Number(q.weight ?? 0),
        };
        if (
          shouldSplitP3P4(baseMeta.element) &&
          !baseMeta.process &&
          isProcessOnlyP4Question(baseMeta.element, baseMeta.question_code)
        ) {
          return [{ ...baseMeta, process: "process_support" }];
        }
        if (shouldSplitP3P4(baseMeta.element) && !baseMeta.process) {
          return [
            { ...baseMeta, process: "product" },
            { ...baseMeta, process: "process_support" },
          ];
        }
        const requirementMetas = (q.requirements ?? []).map((req, idx) => ({
          ...baseMeta,
          id: Number(`${q.id}${idx + 1}`),
          question_id: q.id,
          question_code: buildVdaRequirementCode(
            rawCode,
            req.requirement_code,
            idx + 1,
          ),
          question_text_en: req.description ?? req.requirement_code ?? "",
          requirement_id: req.id,
          requirement_code: req.requirement_code ?? "",
          requirement_sort_order: req.sort_order ?? idx + 1,
          is_requirement: true,
          parent_question_id: q.id,
        }));
        return [baseMeta, ...requirementMetas];
      });

      setVdaQuestions(derivedVdaQuestions);

        const newItems: AuditItem[] = derivedVdaQuestions.map((q, idx) => ({
          uiId: `${q.id}-${String(q.process ?? "na")}-${idx}`,
          row: idx + 1,
          questionId: Number(q.id),
          parentQuestionId: q.parent_question_id ?? null,
          requirementId: q.requirement_id ?? null,
          isRequirement: Boolean(q.is_requirement),
          process: q.process ?? null,
          question: q.question_text_en ?? "",
          requirementCode: q.requirement_code ?? "",
          critical: Number(q.critical_value ?? 0),
        weight: Number(q.weight ?? 0),
        value: "",
        findings: "",
        carReason: "",
        evidence: [],
        uploadedDocs: [],
        requestCAR: false,
        silentBox: false,
        immediateActionRequired: false,
        errors: {},
      }));

      setItems(newItems);
      // FIX: start with empty selection for VDA — user picks which chapters/questions to answer
      setVdaSelectedIds(new Set());
      setVdaEnabledSections(new Set([defaultVdaSection]));
    } else {
      setItems([]);
      setVdaQuestions([]);
      setQuestionnaireName("");
      setVdaSelectedIds(new Set());
      setVdaEnabledSections(new Set([defaultVdaSection]));
      toast.error("Failed to load audit questions");
    }
  };

  const handleIATFNCSubmission = async (
    nonConformities: SubmittedNonConformity[],
    auditDetails: {
      actualStartTime: string;
      actualEndTime: string;
      strongPoints: string;
      weakPoints: string;
    },
  ) => {
    if (!selectedPlannedAuditId) {
      toast.error("No audit selected");
      return;
    }

    setSubmitting(true);
    try {
      await draft.flushSave({
        audit_date: summary.auditDate,
        start_time: auditDetails.actualStartTime,
        end_time: auditDetails.actualEndTime,
        strong_points: auditDetails.strongPoints,
        weak_points: auditDetails.weakPoints,
      });

      const profile = resolveEvaluationProfile(questionnaireName, profileContext);
      const isIatfClassification = profile === "IATF_CLASSIFICATION";
      const isOpen = profile === "OPEN";

      const classificationToValue = (classification?: string): number => {
        if (isOpen) return openResultValue(classification);
        if (isIatfClassification) {
          if (classification === "Minor") return 1;
          if (classification === "Major") return 2;
          if (classification === "Improvement") return 3;
          if (classification === "Strong Point") return 4;
          return 1;
        }
        if (classification === "Major NC" || classification === "Minor NC")
          return 0;
        if (classification === "OFI") return 5;
        if (classification === "Conformity") return 10;
        return 0;
      };

      const answers = await Promise.all(
        nonConformities.map(async (nc, index) => {
          const uploadedEvidence =
            nc.uploadedDocs && nc.uploadedDocs.length > 0
              ? nc.uploadedDocs
              : await Promise.all(
                  (nc.evidence || []).map(async (file: File) => {
                    const r = await apiUploadFile(file);
                    return {
                      filename: r.filename,
                      mimetype: r.mimetype,
                      size: r.size,
                      file_url: r.file_url,
                    };
                  }),
                );
          return {
            question_id: isIatfClassification ? -(index + 1) : 0,
            value: classificationToValue(nc.classification),
            finding_text: nc.findings,
            documents: uploadedEvidence,
            car_reason: nc.observedNonConformity,
            request_car: Boolean(nc.requestCAR),
            silent_box: Boolean(nc.silentBox),
            critical_value: 0,
            process: nc.process,
            standard_paragraph: nc.normParagraph,
            classification: nc.classification,
            question_text: isOpen ? nc.question : undefined,
          };
        }),
      );

      const resultAction = await dispatch(
        executeAuditThunk({
          auditId: selectedPlannedAuditId,
          data: {
            answers,
            audit_date: summary.auditDate,
            start_time: auditDetails.actualStartTime,
            end_time: auditDetails.actualEndTime,
            strong_points: auditDetails.strongPoints ?? "",
            weak_points: auditDetails.weakPoints ?? "",
          },
        }),
      );

      if (!executeAuditThunk.fulfilled.match(resultAction)) {
        toast.error(
          String(resultAction.payload ?? "Failed to submit non-conformities"),
        );
        return;
      }

      const carsCreated = nonConformities.filter((nc) => nc.requestCAR).length;
      toast.success(
        carsCreated > 0
          ? `${nonConformities.length} NC(s) submitted. ${carsCreated} CAR(s) created.`
          : `${nonConformities.length} NC(s) submitted successfully.`,
      );

      draft.clearDraft();
      draftStartedRef.current = false;
      dispatch(removePickableAudit(selectedPlannedAuditId));
      setSubmitted(true);
      setSelectedPlannedAuditId("");
      setQuestionnaireName("");
      setAuditeeName("");
      setVdaQuestions([]);
      setIsDirty(false);
    } catch (err: unknown) {
      console.error("IATF NC submission error:", err);
      toast.error(getErrorMessage(err, "Failed to submit non-conformities"));
      throw err;
    } finally {
      setSubmitting(false);
    }
  };

  const itemsToDraftAnswers = useCallback(
    (arr: AuditItem[]): NonNullable<DraftPayload["answers"]> =>
      arr.filter((i) => !i.isRequirement).filter(hasMeaningfulItemInput).map((i) => {
        const requirements = arr
          .filter((r) => r.isRequirement && r.parentQuestionId === i.questionId)
          .map((r) => ({
            question_requirement_id: r.requirementId ?? 0,
            value: r.value === "" ? null : Number(r.value),
            fulfilled: r.value !== "" && r.value !== -1,
            finding_text: r.findings || "",
            evidence: r.uploadedDocs ?? [],
          }))
          .filter((req) => req.question_requirement_id > 0);
        const isVdaProfile =
          resolveEvaluationProfile(questionnaireName, profileContext) ===
          "VDA_PROCESS";
        const vdaCarTriggered =
          isVdaProfile &&
          (i.value === 0 || i.value === 4 || i.value === 6 || i.value === 8) &&
          Boolean(i.findings?.trim());
        return {
          question_id: i.questionId,
          draft_row_id: i.uiId,
          value: i.value === "" ? null : Number(i.value),
          finding_text: i.findings || "",
          request_car: vdaCarTriggered ? true : i.requestCAR,
          car_reason: vdaCarTriggered ? i.findings.trim() : i.carReason || "",
          silent_box: i.silentBox,
          documents: i.uploadedDocs ?? [],
          process: i.process ?? undefined,
          requirements,
        };
      }),
    [questionnaireName, profileContext],
  );

  const queueDraftSave = useCallback(
    (nextSummary: AuditSummary, nextItems: AuditItem[]) => {
      if (!selectedPlannedAuditId) return;
      const hasMeaningfulInput =
        hasMeaningfulDraftSummary(nextSummary, today) ||
        nextItems.some(hasMeaningfulItemInput);
      if (!draftStartedRef.current && !hasMeaningfulInput) return;
      if (hasMeaningfulInput) draftStartedRef.current = true;
      draft.saveDraft({
        ...summaryToDraftPayload(nextSummary),
        answers: itemsToDraftAnswers(nextItems),
      });
      setIsDirty(true);
    },
    [
      selectedPlannedAuditId,
      draft,
      summaryToDraftPayload,
      itemsToDraftAnswers,
      today,
    ],
  );

  const handleSummaryChange = useCallback(
    (field: keyof AuditSummary, value: string) => {
      setSummary((prev) => {
        const next = { ...prev, [field]: value };
        queueDraftSave(next, items);
        return next;
      });
    },
    [queueDraftSave, items],
  );

  useEffect(() => {
    setPreviews((prev) => {
      const next = new Map<string, string>();
      const stillUsed = new Set<string>();
      items.forEach((item) => {
        item.evidence.forEach((file, idx) => {
          const key = `${item.uiId}-${file.name}-${file.size}-${file.lastModified}-${idx}`;
          stillUsed.add(key);
          next.set(key, prev.get(key) ?? URL.createObjectURL(file));
        });
      });
      prev.forEach((url, key) => {
        if (!stillUsed.has(key)) URL.revokeObjectURL(url);
      });
      return next;
    });
  }, [items]);

  useEffect(() => {
    return () => {
      setPreviews((prev) => {
        prev.forEach((url) => URL.revokeObjectURL(url));
        return new Map();
      });
    };
  }, []);

  useEffect(() => {
    if (!selectedPlannedAuditId) return;
    if (draftAnswersHydratedAuditIdRef.current === selectedPlannedAuditId) return;
    const draftAnswers = draft.data?.answers;
    if (!draftAnswers?.length || items.length === 0) return;

    setItems((prev) =>
      prev.map((it) => {
        const d = draftAnswers.find((a) => a.draft_row_id === it.uiId);
        if (!d) return it;

        return {
          ...it,
          value: d.value == null ? "" : (Number(d.value) as AuditValue),
          findings: d.finding_text ?? "",
          requestCAR: Boolean(d.request_car),
          silentBox: Boolean(d.silent_box),
          carReason: d.car_reason ?? "",
          uploadedDocs: d.documents ?? [],
        };
      }),
    );
    draftAnswersHydratedAuditIdRef.current = selectedPlannedAuditId;
  }, [draft.data?.answers, items.length, selectedPlannedAuditId]);

  const resolveUiId = (rowRef: string | number, source: AuditItem[]) => {
    if (typeof rowRef === "string") return rowRef;
    const byQuestionId = source.find((i) => i.questionId === rowRef);
    return byQuestionId?.uiId ?? String(rowRef);
  };

  const updateField = <K extends keyof AuditItem>(
    rowRef: string | number,
    field: K,
    value: AuditItem[K],
  ) => {
    setItems((prev) => {
      const uiId = resolveUiId(rowRef, prev);
      const next = prev.map((item) => {
        if (item.uiId !== uiId) return item;
        const updated: AuditItem = {
          ...item,
          [field]: value,
          errors: { ...item.errors, [field]: undefined },
        };
        if (field === "value") {
          const nv = value as AuditValue;
          const isVdaProfile = resolveEvaluationProfile(questionnaireName, profileContext) === "VDA_PROCESS";
          if (nv === "" || nv === -1 || nv === 10) {
            updated.requestCAR = false;
            updated.carReason = "";
          } else if (isVdaProfile) {
            updated.requestCAR = false;
            updated.carReason = "";
          } else if (!isVdaProfile && !needsDetails(nv, questionnaireName, profileContext)) {
            updated.requestCAR = false;
            updated.carReason = "";
          }
        }
        return updated;
      });
      queueDraftSave(summary, next);
      return next;
    });
  };

  const toggleCARRequest = (rowRef: string | number) =>
    setItems((prev) => {
      const uiId = resolveUiId(rowRef, prev);
      const next = prev.map((i) =>
        i.uiId === uiId ? { ...i, requestCAR: !i.requestCAR } : i,
      );
      queueDraftSave(summary, next);
      return next;
    });

  const addEvidence = async (uiId: string, files: FileList | null) => {
    if (!files) return;
    const imgs = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (!imgs.length) return;

    try {
      const uploadedDocs: UploadedDoc[] = await Promise.all(
        imgs.map(async (file) => {
          const up = await apiUploadFile(file);
          return {
            filename: up.filename,
            mimetype: up.mimetype,
            size: up.size,
            file_url: up.file_url,
          };
        }),
      );

      setItems((prev) => {
        const next = prev.map((i) =>
          i.uiId === uiId
            ? {
                ...i,
                evidence: [...i.evidence, ...imgs],
                uploadedDocs: [...i.uploadedDocs, ...uploadedDocs],
              }
            : i,
        );
        queueDraftSave(summary, next);
        return next;
      });
    } catch (e) {
      console.error(e);
      toast.error("Failed to upload evidence");
    }
  };

  const resetSelectedAuditContext = useCallback(() => {
    lastNcDraftSigRef.current = "";
    draftStartedRef.current = false;
    draftSummaryHydratedAuditIdRef.current = null;
    draftAnswersHydratedAuditIdRef.current = null;
    setSelectedPlannedAuditId("");
    setItems([]);
    setVdaQuestions([]);
    setQuestionnaireName("");
    setVdaSelectedIds(new Set());
      setVdaEnabledSections(new Set([defaultVdaSection]));
    setAuditeeName("");
    setSubmitted(false);
    setIsDirty(false);
    setPlannedAuditOpen(false);
    setSummary({
      auditDate: today,
      startTime: "",
      endTime: "",
      strongPoints: "",
      weakPoints: "",
      questionnaireName: "",
    });
  }, [today, defaultVdaSection]);

  const removeLocalEvidence = (uiId: string, idx: number) =>
    setItems((prev) => {
      const next = prev.map((i) =>
        i.uiId === uiId
          ? {
              ...i,
              evidence: i.evidence.filter((_, j) => j !== idx),
              uploadedDocs: i.uploadedDocs.filter((_, j) => j !== idx),
            }
          : i,
      );
      queueDraftSave(summary, next);
      return next;
    });

  const removeUploadedEvidence = (uiId: string, idx: number) =>
    setItems((prev) => {
      const next = prev.map((i) =>
        i.uiId === uiId
          ? { ...i, uploadedDocs: i.uploadedDocs.filter((_, j) => j !== idx) }
          : i,
      );
      queueDraftSave(summary, next);
      return next;
    });

  const handlePaChange = (
    questionId: number,
    patch: Partial<PaAnswerState>,
  ) =>
    setPaAnswers((prev) => {
      const next = new Map(prev);
      const current = next.get(questionId) ?? {
        value: "" as PaAnswerState["value"],
        findings: "",
        evidence: [],
      };
      next.set(questionId, { ...current, ...patch });
      return next;
    });

  const handlePaAddEvidence = (questionId: number, files: FileList | null) => {
    if (!files || files.length === 0) return;
    setPaAnswers((prev) => {
      const next = new Map(prev);
      const current = next.get(questionId) ?? {
        value: "" as PaAnswerState["value"],
        findings: "",
        evidence: [],
      };
      next.set(questionId, {
        ...current,
        evidence: [...current.evidence, ...Array.from(files)],
      });
      return next;
    });
  };

  const handlePaRemoveEvidence = (questionId: number, idx: number) =>
    setPaAnswers((prev) => {
      const next = new Map(prev);
      const current = next.get(questionId);
      if (!current) return prev;
      next.set(questionId, {
        ...current,
        evidence: current.evidence.filter((_, j) => j !== idx),
      });
      return next;
    });

  // ── FIX3: When a question is deselected, reset its item data so it is never
  //    treated as "fulfilled". Without this, a previously-answered question keeps
  //    its value/findings/CAR in `items` state even after the checkbox is cleared,
  //    which can make the 2/3 counter and canSubmit behave incorrectly on re-select.
  const toggleVdaSelect = (uiId: string) =>
    setVdaSelectedIds((prev) => {
      const n = new Set(prev);
      if (n.has(uiId)) {
        n.delete(uiId);
        // Reset the item's state so it is truly blank when deselected
        setItems((prevItems) =>
          prevItems.map((item) =>
            item.uiId === uiId
              ? { ...item, value: "", findings: "", carReason: "", requestCAR: false, silentBox: false, immediateActionRequired: false, errors: {} }
              : item,
          ),
        );
      } else {
        n.add(uiId);
      }
      return n;
    });

  // ── FIX3 (continued): Same reset when an entire section is unchecked.
  const selectAllInSection = (sectionKey: string, checked: boolean) => {
    const ids = vdaQuestions
      .filter((q) => getVdaSectionKey(q, isVdaP1) === sectionKey && !isVdaRemarkQuestion(q))
      .map((q, idx) => {
        const qid = getVdaQuestionId(q);
        if (qid == null) return null;
        const linked = getVdaItemByQuestionAndProcess(
          items,
          qid,
          q.process ?? null,
        );
        return linked?.uiId ?? `${qid}-${idx}`;
      })
      .filter((id): id is string => id !== null);

    setVdaSelectedIds((prev) => {
      const n = new Set(prev);
      ids.forEach((id) => {
        if (checked) n.add(id);
        else n.delete(id);
      });
      return n;
    });

    // Reset item data for every question that was just deselected
    if (!checked) {
      setItems((prev) =>
        prev.map((item) =>
          ids.includes(item.uiId)
            ? { ...item, value: "", findings: "", carReason: "", requestCAR: false, silentBox: false, immediateActionRequired: false, errors: {} }
            : item,
        ),
      );
    }
  };

  const toggleVdaSection = (sectionKey: string) => {
    setVdaEnabledSections((prev) => {
      const next = new Set(prev);
      if (next.has(sectionKey)) {
        next.delete(sectionKey);
        selectAllInSection(sectionKey, false);
      } else {
        next.add(sectionKey);
      }
      return next;
    });
  };

  const toggleImmediateAction = (rowRef: string | number) =>
    setItems((prev) => {
      const uiId = resolveUiId(rowRef, prev);
      const next = prev.map((i) =>
        i.uiId === uiId
          ? { ...i, immediateActionRequired: !i.immediateActionRequired }
          : i,
      );
      queueDraftSave(summary, next);
      return next;
    });

  const isVdaItemActiveForCurrentMode = useCallback(
    (item: AuditItem) => {
      if (!isVda) return true;
      const meta = vdaQuestions.find(
        (q) =>
          getVdaQuestionId(q) === item.questionId &&
          String(q.process ?? "") === String(item.process ?? ""),
      );
      if (!meta) return true;
      if (meta.element !== "P3" && meta.element !== "P4") return true;

      const processType = getVdaProcessType(item.process);
      if (!processType) return true;

      const mode = vdaSideModeByBase[getVdaBaseCode(meta.question_code)] ?? "both";
      return mode === "both" || mode === processType;
    },
    [isVda, vdaQuestions, vdaSideModeByBase],
  );

  const effectiveItems = useMemo(
    () =>
      isVda
        ? items.filter(
            (it) => vdaSelectedIds.has(it.uiId) && isVdaItemActiveForCurrentMode(it),
          )
        : items,
    [items, isVda, vdaSelectedIds, isVdaItemActiveForCurrentMode],
  );

  // VDA validation:
  // - Optional / N.E. (-1) is excluded from the score denominator.
  // - The 2/3 rule is applied at full P3/P4 element level, not separately by Product/Support.
  // - Asterisk questions are optional. If answered, their downgrade rules still apply in backend scoring.
  const vdaSectionKeys = useMemo(() => {
    if (!isVda) return [];
    const active = new Set<string>();
    for (const q of vdaQuestions) {
      const sectionKey = getVdaSectionKey(q, isVdaP1);
      if (!vdaEnabledSections.has(sectionKey) || isVdaRemarkQuestion(q)) continue;
      const qid = getVdaQuestionId(q);
      if (qid == null) continue;
      const item = getVdaItemByQuestionAndProcess(items, qid, q.process ?? null);
      if (item && vdaSelectedIds.has(item.uiId) && isVdaItemActiveForCurrentMode(item)) {
        active.add(q.element);
      }
    }
    return Array.from(active);
  }, [isVda, vdaEnabledSections, vdaQuestions, items, vdaSelectedIds, isVdaItemActiveForCurrentMode]);


  const vdaCarViolations = useMemo(() => {
    // VDA currently relies on findings for low scores; separate CAR blocking is disabled.
    return [];
  }, [isVda, effectiveItems]);

  const vdaRuleViolations = useMemo(() => {
    if (isVdaP1) return [];
    if (!isVda || vdaSectionKeys.length === 0) return [];
    const violations: { section: string; answered: number; required: number; total: number }[] = [];

    for (const sec of vdaSectionKeys) {
      // IMPORTANT: If a P chapter is active because at least one question in it
      // is selected/submitted, the VDA 2/3 rule is checked against the FULL
      // chapter scope, not only the selected rows. This prevents submitting
      // P3 with only one answered question. P3/P4 Product and Process/Support
      // stay combined here.
      const allQuestionsInSection = vdaQuestions.filter((q) => {
        if (q.element !== sec || isVdaRemarkQuestion(q)) return false;
        const qid = getVdaQuestionId(q);
        if (qid == null) return false;
        const item = getVdaItemByQuestionAndProcess(
          items,
          qid,
          q.process ?? null,
        );
        const isActiveItem = item ? isVdaItemActiveForCurrentMode(item) : false;
        // Optional / N.E. is excluded only when the auditor explicitly selected
        // that question and set it to Optional. Unselected questions still count
        // as part of the active chapter denominator.
        if (item && !isActiveItem) return false;
        return !(item && vdaSelectedIds.has(item.uiId) && item.value === -1);
      });

      const total =
        sec === "P3" || sec === "P4"
          ? new Set(allQuestionsInSection.map((q) => getVdaBaseCode(q.question_code))).size
          : allQuestionsInSection.length;
      if (total === 0) continue;

      const required = Math.ceil((2 * total) / 3);
      const answered =
        sec === "P3" || sec === "P4"
          ? new Set(
              allQuestionsInSection
                .filter((q) => {
                  const item = getVdaItemByQuestionAndProcess(
                    items,
                    getVdaQuestionId(q),
                    q.process ?? null,
                  );
                  return (
                    getVdaScoringScopeItem(item, vdaSelectedIds) &&
                    (!item || isVdaItemActiveForCurrentMode(item))
                  );
                })
                .map((q) => getVdaBaseCode(q.question_code)),
            ).size
          : allQuestionsInSection.filter((q) => {
              const item = getVdaItemByQuestionAndProcess(
                items,
                getVdaQuestionId(q),
                q.process ?? null,
              );
              return (
                getVdaScoringScopeItem(item, vdaSelectedIds) &&
                (!item || isVdaItemActiveForCurrentMode(item))
              );
            }).length;

      if (answered < required) violations.push({ section: sec, answered, required, total });
    }

    return violations;
  }, [isVda, isVdaP1, vdaQuestions, vdaSelectedIds, items, vdaSectionKeys, isVdaItemActiveForCurrentMode]);

  const vdaRuleValid = useMemo(() => {
    if (isVdaP1) return true;
    if (!isVda) return true;
    if (vdaSectionKeys.length === 0) return false;
    return vdaRuleViolations.length === 0 && vdaCarViolations.length === 0;
  }, [isVda, isVdaP1, vdaSectionKeys.length, vdaRuleViolations, vdaCarViolations]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitted || submitting) return;
    setSubmitAttempted(true);

    if (selectedPlannedAuditId === "") {
      toast.error("Select an audit first");
      return;
    }
    if (auditorId <= 0) {
      toast.error("Select an auditor first");
      return;
    }
    if (effectiveItems.length === 0) {
      toast.error(
        isVda ? "Select at least one VDA question" : "Select at least one question",
      );
      return;
    }

    const scrollToField = (id: string) => {
      requestAnimationFrame(() => {
        document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    };
    if (summary.auditDate.trim() === "") {
      toast.error("Audit date is required");
      scrollToField("summary-auditDate");
      return;
    }
    if (summary.startTime.trim() === "") {
      toast.error("Start time is required");
      scrollToField("summary-startTime");
      return;
    }
    if (summary.endTime.trim() === "") {
      toast.error("End time is required");
      scrollToField("summary-endTime");
      return;
    }
    if (summary.strongPoints.trim() === "") {
      toast.error("Strong points are required");
      scrollToField("summary-strongPoints");
      return;
    }
    if (summary.weakPoints.trim() === "") {
      toast.error("Weak points are required");
      scrollToField("summary-weakPoints");
      return;
    }

    // ── FIX2: guard against the 2/3 rule being unmet (safety net in case
    //    canSubmit was somehow bypassed)
    if (isVda && !isVdaP1 && !vdaRuleValid) {
      toast.error(
        `Each selected VDA chapter requires at least 2/3 answered: ${vdaRuleViolations
          .map((v) => `${v.section} ${v.answered}/${v.required}`)
          .join(", ")}`,
      );
      return;
    }

    if (potentialAnalysisQuestions.length > 0) {
      const paNe = potentialAnalysisQuestions.filter(
        (q) => paAnswers.get(q.id)?.value === -1,
      ).length;
      if (paNe > 3) {
        toast.error("Potential Analysis allows at most 3 n.e. answers.");
        return;
      }
      const paIncomplete = potentialAnalysisQuestions.some((q) => {
        const a = paAnswers.get(q.id);
        if (!a || (a.value !== 0 && a.value !== 4)) return false;
        return !a.findings.trim() || a.evidence.length === 0;
      });
      if (paIncomplete) {
        toast.error(
          "Findings and evidence are required for Red/Yellow Potential Analysis answers.",
        );
        return;
      }
    }

    const validated = effectiveItems.map((item) => ({
      ...item,
      errors: validateItem(item, questionnaireName, profileContext),
    }));
    setItems((prev) =>
      prev.map((it) => {
        const v = validated.find((x) => x.uiId === it.uiId);
        return v ? { ...it, errors: v.errors } : it;
      }),
    );

    const invalidItems = validated.filter(
      (item) => Object.keys(item.errors).length > 0,
    );
    if (invalidItems.length > 0) {
      const labels = invalidItems
        .slice(0, 5)
        .map((item) => item.requirementCode || item.question.slice(0, 40));
      const extra = invalidItems.length > 5 ? ` and ${invalidItems.length - 5} more` : "";
      toast.error(
        `${invalidItems.length} question${invalidItems.length === 1 ? "" : "s"} ` +
          `still need${invalidItems.length === 1 ? "s" : ""} required details: ` +
          `${labels.join(", ")}${extra}`,
      );
      requestAnimationFrame(() => {
        document
          .getElementById(`audit-item-${invalidItems[0].uiId}`)
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      return;
    }

    setSubmitting(true);
    try {
      await draft.flushSave({
        ...summaryToDraftPayload(summary),
        answers: itemsToDraftAnswers(validated),
      });

      const parentItems = validated.filter((item) => !item.isRequirement);

      const answers = await Promise.all(
        parentItems.map(async (item) => {
          const documents =
            item.uploadedDocs && item.uploadedDocs.length > 0
              ? item.uploadedDocs
              : await Promise.all(
                  item.evidence.map(async (file) => {
                    const up = await apiUploadFile(file);
                    return {
                      filename: up.filename,
                      mimetype: up.mimetype,
                      size: up.size,
                      file_url: up.file_url,
                    };
                  }),
                );

          return {
            question_id: item.questionId,
            process: item.process ?? null,
            value: item.value === "" ? -1 : (item.value as number),
            finding_text: item.findings?.trim() || null,
            documents,
            critical_value: item.critical,
            request_car:
              !isVdaP1 &&
              isVda &&
              (item.value === 0 || item.value === 4 || item.value === 6 || item.value === 8) &&
              item.findings.trim()
                ? true
                : item.requestCAR,
            car_reason:
              !isVdaP1 &&
              isVda &&
              (item.value === 0 || item.value === 4 || item.value === 6 || item.value === 8) &&
              item.findings.trim()
                ? item.findings.trim()
                : item.requestCAR && item.carReason?.trim()
                  ? item.carReason.trim()
                  : null,
            silent_box: Boolean(item.silentBox),
            immediate_action_required: isVda ? Boolean(item.immediateActionRequired) : false,
            requirements: validated
              .filter((r) => r.isRequirement && r.parentQuestionId === item.questionId)
              .map((r) => ({
                question_requirement_id: r.requirementId ?? 0,
                value: r.value === "" ? null : Number(r.value),
                fulfilled: r.value !== "" && r.value !== -1,
                finding_text: r.findings || "",
                evidence: r.uploadedDocs ?? [],
              }))
              .filter((req) => req.question_requirement_id > 0),
          };
        }),
      );

      const paAnswerEntries = await Promise.all(
        potentialAnalysisQuestions.map(async (q) => {
          const a = paAnswers.get(q.id) ?? {
            value: "" as PaAnswerState["value"],
            findings: "",
            evidence: [],
          };
          const documents = await Promise.all(
            a.evidence.map(async (file) => {
              const up = await apiUploadFile(file);
              return {
                filename: up.filename,
                mimetype: up.mimetype,
                size: up.size,
                file_url: up.file_url,
              };
            }),
          );
          return {
            question_id: q.id,
            process: null,
            value: a.value === "" ? -1 : a.value,
            finding_text: a.findings?.trim() || null,
            documents,
            critical_value: q.critical_value,
            request_car: false,
            car_reason: null,
            silent_box: false,
            immediate_action_required: false,
            requirements: [],
          };
        }),
      );
      const paAnswered = paAnswerEntries.filter((a) => a.value !== -1);

      const resultAction = await dispatch(
        executeAuditThunk({
          auditId: selectedPlannedAuditId,
          data: {
            answers: [...answers, ...paAnswered],
            audit_date: summary.auditDate,
            start_time: summary.startTime,
            end_time: summary.endTime,
            strong_points: summary.strongPoints,
            weak_points: summary.weakPoints,
          },
        }),
      );

      if (!executeAuditThunk.fulfilled.match(resultAction)) {
        toast.error(String(resultAction.payload ?? "Failed to execute audit"));
        setSubmitted(false);
        return;
      }

      const res = resultAction.payload as {
        cars_created?: number;
        status?: string;
      };
      toast.success(
        (res.cars_created ?? 0) > 0
          ? `Audit executed. Status: ${res.status ?? "Unknown"}. ${res.cars_created} CAR(s) created.`
          : `Audit executed. Status: ${res.status ?? "Unknown"}. No CAR needed.`,
      );

      draft.clearDraft();
      draftStartedRef.current = false;
      dispatch(removePickableAudit(selectedPlannedAuditId));
      setSubmitted(true);
      setSelectedPlannedAuditId("");
      setItems([]);
      setVdaQuestions([]);
      setPotentialAnalysisQuestions([]);
      setPaAnswers(new Map());
      setQuestionnaireName("");
      setVdaSelectedIds(new Set());
      setVdaEnabledSections(new Set([defaultVdaSection]));
      setAuditeeName("");
      setIsDirty(false);
      setSummary({
        auditDate: today,
        startTime: "",
        endTime: "",
        strongPoints: "",
        weakPoints: "",
        questionnaireName: "",
      });
    } catch (err: unknown) {
      console.error(err);
      toast.error(getErrorMessage(err, "Execution failed. Please try again."));
      setSubmitted(false);
    } finally {
      setSubmitting(false);
    }
  };

  const downloadCSV = () => {
    const rows = [
      [
        "#",
        "Question",
        "Critical",
        "Value",
        "Findings",
        "CAR Requested",
        "CAR Reason",
        "Evidence",
      ],
      ...effectiveItems.map((item) => [
        item.row,
        item.question,
        item.critical,
        item.value,
        item.findings.replace(/\n/g, " "),
        item.requestCAR ? "Yes" : "No",
        item.carReason.replace(/\n/g, " "),
        item.evidence.map((f) => f.name).join("|"),
      ]),
    ];
    const csv = rows
      .map((row) =>
        row.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","),
      )
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const progress = effectiveItems.length
    ? Math.round(
        (effectiveItems.filter((i) => i.value !== "").length /
          effectiveItems.length) *
          100,
      )
    : 0;

  const carCount = isVda
    ? effectiveItems.filter(
        (item) =>
          (item.value === 0 || item.value === 4 || item.value === 6 || item.value === 8) &&
          Boolean(item.findings.trim()),
      ).length
    : effectiveItems.filter(
        (item) => item.requestCAR && item.value !== "" && item.value !== -1,
      ).length;
  const p1NeCount = useMemo(
    () => (isVdaP1 ? effectiveItems.filter((item) => item.value === -1).length : 0),
    [isVdaP1, effectiveItems],
  );

  const canSubmit =
    selectedPlannedAuditId !== "" &&
    auditorId > 0 &&
    effectiveItems.length > 0 &&
    // ── FIX2: block submission when the 2/3 rule is not satisfied
    vdaRuleValid &&
    (!isVdaP1 || p1NeCount <= 3) &&
    effectiveItems.every(
      (item) =>
        item.value !== "" &&
        !(
          resolveEvaluationProfile(questionnaireName, profileContext) ===
            "IATF_PM" &&
          item.weight === 1 &&
          item.value === -1
        ) &&
        (!needsDetails(item.value, questionnaireName, profileContext) ||
          item.findings.trim()) &&
        (
          !isVdaP1 ||
          !(item.value === 0 || item.value === 4) ||
          (item.uploadedDocs.length + item.evidence.length) > 0
        ) &&
        (isVda || !item.requestCAR || item.carReason.trim()),
    ) &&
    summary.auditDate.trim() !== "" &&
    summary.strongPoints.trim() !== "" &&
    summary.weakPoints.trim() !== "" &&
    summary.startTime.trim() !== "" &&
    summary.endTime.trim() !== "";

  const submitBlockers = useMemo(() => {
    const blockers: string[] = [];
    if (selectedPlannedAuditId === "") blockers.push("Select an audit first.");
    if (auditorId <= 0) blockers.push("Select an auditor.");
    if (effectiveItems.length === 0) blockers.push("Select at least one active question.");
    if (summary.auditDate.trim() === "") blockers.push("Audit date is required.");
    if (summary.startTime.trim() === "") blockers.push("Start time is required.");
    if (summary.endTime.trim() === "") blockers.push("End time is required.");
    if (summary.strongPoints.trim() === "") blockers.push("Strong points are required.");
    if (summary.weakPoints.trim() === "") blockers.push("Weak points are required.");
    if (isVda && !isVdaP1 && vdaRuleViolations.length > 0) {
      blockers.push("The VDA 2/3 rule is not satisfied for one or more active chapters.");
    }
    if (isVdaP1 && p1NeCount > 3) {
      blockers.push("P1 allows at most 3 n.e. answers.");
    }
    const missingItems = effectiveItems.filter(
      (item) =>
        item.value === "" ||
        (needsDetails(item.value, questionnaireName, profileContext) &&
          !item.findings.trim()) ||
        (isVdaP1 &&
          (item.value === 0 || item.value === 4) &&
          (item.uploadedDocs.length + item.evidence.length) === 0) ||
        (!isVda && item.requestCAR && !item.carReason.trim()),
    );
    if (missingItems.length > 0) {
      const labels = missingItems
        .slice(0, 5)
        .map((item) => item.requirementCode || item.question.slice(0, 40));
      const extra = missingItems.length > 5 ? ` and ${missingItems.length - 5} more` : "";
      blockers.push(
        `${missingItems.length} question${missingItems.length === 1 ? "" : "s"} ` +
          `missing required details (value, findings, evidence, or CAR reason): ` +
          `${labels.join(", ")}${extra}.`,
      );
    }
    return blockers;
  }, [
    selectedPlannedAuditId,
    auditorId,
    effectiveItems,
    summary.auditDate,
    summary.startTime,
    summary.endTime,
    summary.strongPoints,
    summary.weakPoints,
    isVda,
    isVdaP1,
    p1NeCount,
    vdaCarViolations,
    vdaRuleViolations,
    questionnaireName,
    profileContext,
  ]);

  const auditOptions = pickableAudits.map((a) => {
    const statusLabel =
      a.status === "rescheduled"
        ? "🔁 RESCHEDULED"
        : `🗓️ ${(a.status || "planned").replace(/_/g, " ").toUpperCase()}`;
    const questionnaire = a.questionnaire_name || "N/A";
    const plant = a.plant || "N/A";
    const auditees = a.auditees?.map((au) => au.email).join(", ") || "N/A";
    return {
      value: a.id,
      statusLabel,
      auditNumber: a.audit_number,
      plannedDate: a.planned_date,
      timeRange: `${a.planned_start_time}-${a.planned_end_time}`,
      questionnaire,
      auditees,
      plant,
      status: (a.status || "planned").toLowerCase(),
    };
  });

  const selectedAuditOption = auditOptions.find(
    (o) => String(o.value) === String(selectedPlannedAuditId),
  );

  const filteredAuditOptions = useMemo(() => {
    const q = plannedAuditSearch.trim().toLowerCase();
    if (!q) return auditOptions;
    return auditOptions.filter((opt) =>
      [opt.auditNumber, opt.questionnaire, opt.plant, opt.auditees]
        .some((field) => String(field ?? "").toLowerCase().includes(q)),
    );
  }, [auditOptions, plannedAuditSearch]);

  const questionnaireProfile = resolveEvaluationProfile(
    questionnaireName,
    profileContext,
  );
  const questionnaireType = getQuestionnaireType(
    questionnaireName,
    profileContext,
  );
  const scaleDescription = getScaleDescription(
    questionnaireName,
    profileContext,
  );
  const modeGuidance = getModeGuidance(questionnaireName, profileContext);

  if (showClassificationInterface && selectedPlannedAuditId) {
    const selectedAudit = pickableAudits.find(
      (a) => a.id === selectedPlannedAuditId,
    );
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50/35 to-sky-50/25 p-4 md:p-8">
        <div className="max-w-[1600px] mx-auto mb-6 flex items-center gap-4">
          <button
            type="button"
            onClick={() => {
              resetSelectedAuditContext();
            }}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm bg-white border border-indigo-200 rounded-lg hover:bg-indigo-50 transition-colors"
          >
            <ChevronDown size={16} className="rotate-90" />
            Back to Audit Selection
          </button>
          <DraftIndicator
            saving={draft.saving}
            lastSavedAt={draft.lastSavedAt}
            isDirty={isDirty}
          />
        </div>
        <div className="max-w-[1600px] mx-auto mb-4 rounded-lg border border-sky-200 bg-sky-50 px-4 py-2 text-sm text-sky-800">
          {modeGuidance}
        </div>

        <IATFNonConformityManager
          plannedAuditId={selectedPlannedAuditId}
          questionnaireName={questionnaireName}
          mode={
            {
              ISO_SYSTEM: "ISO" as const,
              OPEN: "OPEN" as const,
            }[resolveEvaluationProfile(questionnaireName, profileContext) as string] ??
            "IATF"
          }
          auditNumber={selectedAudit?.audit_number}
          auditeeName={auditee_name}
          auditDate={selectedAudit?.planned_date}
          plannedStartTime={selectedAudit?.planned_start_time}
          plannedEndTime={selectedAudit?.planned_end_time}
          draftStartTime={draft.data?.start_time}
          draftEndTime={draft.data?.end_time}
          draftStrongPoints={draft.data?.strong_points}
          draftWeakPoints={draft.data?.weak_points}
          onFieldChange={(field, value) => {
            const map: Record<string, keyof DraftPayload> = {
              actualStartTime: "start_time",
              actualEndTime: "end_time",
              strongPoints: "strong_points",
              weakPoints: "weak_points",
            };
            const draftKey = map[field];
            if (draftKey && selectedPlannedAuditId) {
              const hasMeaningfulInput = hasText(value);
              if (!draftStartedRef.current && !hasMeaningfulInput) return;
              if (hasMeaningfulInput) draftStartedRef.current = true;
              draft.saveDraft({ [draftKey]: value });
              setIsDirty(true);
            }
          }}
          draftAnswers={draft.data?.answers}
          onNonConformitiesChange={(ncs) => {
            if (!selectedPlannedAuditId) return;

            const profile = resolveEvaluationProfile(
              questionnaireName,
              profileContext,
            );
            const isIatfClassification = profile === "IATF_CLASSIFICATION";
            const isOpen = profile === "OPEN";

            const classificationToValue = (c?: string) => {
              if (isOpen) return openResultValue(c);
              if (isIatfClassification) {
                if (c === "Minor") return 1;
                if (c === "Major") return 2;
                if (c === "Improvement") return 3;
                if (c === "Strong Point") return 4;
                return 1;
              }
              if (c === "Major NC" || c === "Minor NC") return 0;
              if (c === "OFI") return 5;
              if (c === "Conformity") return 10;
              return 0;
            };

            const answers = ncs
              .filter((nc) => {
                const hasContent =
                  Boolean(nc.classification?.trim()) ||
                  Boolean(nc.requestCAR) ||
                  Boolean(nc.normParagraph?.trim()) ||
                  Boolean(nc.process?.trim()) ||
                  Boolean(nc.observedNonConformity?.trim()) ||
                  Boolean(nc.findings?.trim()) ||
                  Boolean(nc.question?.trim()) ||
                  (nc.uploadedDocs?.length ?? 0) > 0;
                return hasContent;
              })
              .map((nc, idx) => ({
                question_id: isIatfClassification ? -(idx + 1) : 0,
                draft_row_id: nc.id,
                value: classificationToValue(nc.classification),
                finding_text: nc.findings,
                request_car: nc.requestCAR,
                car_reason: nc.observedNonConformity,
                silent_box: nc.silentBox,
                process: nc.process,
                standard_paragraph: nc.normParagraph,
                classification: nc.classification,
                question_text: isOpen ? nc.question : undefined,
                documents: nc.uploadedDocs ?? [],
              }));

            const sig = JSON.stringify(answers);
            if (sig === lastNcDraftSigRef.current) return;
            lastNcDraftSigRef.current = sig;

            if (!draftStartedRef.current && answers.length === 0) return;
            if (answers.length > 0) draftStartedRef.current = true;
            draft.saveDraft({ answers });
            setIsDirty(true);
          }}
          onSubmit={handleIATFNCSubmission}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50/35 to-sky-50/25 p-4 md:p-8">
      <div className="max-w-[1600px] mx-auto">
        <form onSubmit={handleSubmit} className="space-y-6">
          {selectedPlannedAuditId !== "" && (
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => {
                  resetSelectedAuditContext();
                }}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm bg-white border border-indigo-200 rounded-lg hover:bg-indigo-50 transition-colors"
              >
                <ChevronDown size={16} className="rotate-90" />
                Back to Audit Selection
              </button>
              <DraftIndicator
                saving={draft.saving}
                lastSavedAt={draft.lastSavedAt}
                isDirty={isDirty}
              />
            </div>
          )}

          <div className="bg-white/95 border border-indigo-100 rounded-xl shadow-sm shadow-indigo-100/30 overflow-visible backdrop-blur-sm">
            <div className="p-4 border-b border-indigo-200/30 bg-gradient-to-r from-[#064273] to-[#0a5f95] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/20 rounded-lg backdrop-blur-sm ring-1 ring-white/30">
                  <ClipboardList className="text-white" size={20} />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-white">
                    Audit Execution - {questionnaireType}
                  </h1>
                  {selectedAuditOption && (
                    <p className="text-xs text-indigo-100 mt-0.5">
                      {selectedAuditOption.auditNumber} •{" "}
                      {selectedAuditOption.questionnaire}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={downloadCSV}
                  disabled={!canSubmit}
                  className="inline-flex items-center gap-2 px-3 py-2 text-sm bg-white/15 border border-white/30 text-white rounded-lg hover:bg-white/25 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Download size={16} className="text-white" />
                  Export CSV
                </button>
              </div>
            </div>

            {selectedPlannedAuditId === "" ? (
              <div className="relative z-20 p-6 bg-gradient-to-r from-indigo-50/45 to-white border-b border-indigo-100">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-2">
                      Auditor
                    </label>
                    <div className="relative">
                      <Select
                        placeholder="Select an auditor..."
                        options={auditorOptions}
                        defaultValue={auditorId || ""}
                        onChange={setSelectedAuditor}
                        className="w-full p-3 pr-10 bg-white border border-indigo-200 rounded-lg text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-[#064273]"
                        disabled={submitting}
                      />
                      <ChevronDown
                        size={18}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
                      />
                    </div>
                  </div>
                  <div className="lg:col-span-2">
                    <label className="block text-sm font-semibold text-slate-700 mb-2">
                      Planned Audit
                    </label>
                    <div className="relative" ref={plannedAuditMenuRef}>
                      <button
                        type="button"
                        onClick={() => setPlannedAuditOpen((v) => !v)}
                        disabled={!auditorId || pickableLoading || submitting}
                        className="h-11 w-full rounded-lg border border-indigo-200 bg-white px-3 text-left text-sm shadow-theme-xs transition hover:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-[#064273]/20 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {selectedAuditOption ? (
                          <div className="flex items-center gap-2 overflow-hidden pr-7">
                            <span
                              className={`shrink-0 rounded px-2 py-0.5 text-[10px] font-semibold ${
                                selectedAuditOption.status === "rescheduled"
                                  ? "bg-amber-100 text-amber-700"
                                  : "bg-indigo-100 text-indigo-700"
                              }`}
                            >
                              {selectedAuditOption.statusLabel}
                            </span>
                            <span className="shrink-0 font-semibold text-slate-800">
                              {selectedAuditOption.auditNumber}
                            </span>
                            <span className="truncate text-indigo-700 font-medium">
                              {selectedAuditOption.questionnaire}
                            </span>
                            <span className="shrink-0 rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                              {selectedAuditOption.plant}
                            </span>
                          </div>
                        ) : (
                          <span className="text-slate-400">
                            {pickableLoading
                              ? "Loading audits..."
                              : !auditorId
                                ? "Select auditor first..."
                                : "Select planned audit..."}
                          </span>
                        )}
                        <ChevronDown
                          size={18}
                          className={`absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 transition-transform ${plannedAuditOpen ? "rotate-180" : ""}`}
                        />
                      </button>

                      {plannedAuditOpen && (
                        <div className="absolute z-[80] mt-2 w-full overflow-hidden rounded-xl border border-indigo-100 bg-white shadow-xl shadow-indigo-100/50">
                          <div className="sticky top-0 z-10 border-b border-indigo-100 bg-white p-2">
                            <input
                              ref={plannedAuditSearchInputRef}
                              type="text"
                              value={plannedAuditSearch}
                              onChange={(e) => setPlannedAuditSearch(e.target.value)}
                              onClick={(e) => e.stopPropagation()}
                              onKeyDown={(e) => e.stopPropagation()}
                              placeholder="Search by audit ID, questionnaire, plant..."
                              className="h-9 w-full rounded-lg border border-indigo-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#064273]/20"
                            />
                          </div>
                          <div className="max-h-72 overflow-auto p-1">
                          {filteredAuditOptions.length === 0 ? (
                            <div className="px-3 py-2 text-sm text-slate-500">
                              {auditOptions.length === 0
                                ? "No planned audits"
                                : "No audits match your search"}
                            </div>
                          ) : (
                            filteredAuditOptions.map((opt) => (
                              <button
                                key={opt.value}
                                type="button"
                                onClick={() => {
                                  setPlannedAuditOpen(false);
                                  handleAuditSelection(Number(opt.value));
                                }}
                                className="mb-1 w-full rounded-lg border border-transparent px-3 py-2 text-left transition hover:border-indigo-100 hover:bg-indigo-50/60"
                              >
                                <div className="flex items-center gap-2">
                                  <span
                                    className={`rounded px-2 py-0.5 text-[10px] font-semibold ${
                                      opt.status === "rescheduled"
                                        ? "bg-amber-100 text-amber-700"
                                        : "bg-indigo-100 text-indigo-700"
                                    }`}
                                  >
                                    {opt.statusLabel}
                                  </span>
                                  <span className="font-semibold text-slate-800">
                                    {opt.auditNumber}
                                  </span>
                                  <span className="rounded bg-sky-100 px-2 py-0.5 text-[10px] font-semibold text-sky-700">
                                    {opt.plannedDate}
                                  </span>
                                  <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                                    {opt.timeRange}
                                  </span>
                                </div>
                                <div className="mt-1 flex items-center gap-2">
                                  <span className="truncate text-sm font-medium text-indigo-700">
                                    {opt.questionnaire}
                                  </span>
                                  <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                                    {opt.plant}
                                  </span>
                                </div>
                                <div className="mt-1 truncate text-xs text-slate-500">
                                  {opt.auditees}
                                </div>
                              </button>
                            ))
                          )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="relative z-20 p-4 bg-indigo-50/50 border-b border-indigo-100">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="rounded bg-indigo-100 px-2 py-1 font-semibold text-indigo-700">
                    Selected Audit
                  </span>
                  <span className="rounded bg-white px-2 py-1 font-semibold text-slate-700 border border-indigo-100">
                    {selectedAuditOption?.auditNumber ?? "—"}
                  </span>
                  <span className="rounded bg-white px-2 py-1 text-indigo-700 border border-indigo-100">
                    {selectedAuditOption?.questionnaire ?? "—"}
                  </span>
                  <span className="rounded bg-emerald-100 px-2 py-1 font-semibold text-emerald-700">
                    {selectedAuditOption?.plant ?? "—"}
                  </span>
                </div>
                {questionnaireName && (
                  <div className="mt-3 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
                    {modeGuidance}
                  </div>
                )}
              </div>
            )}

            {items.length > 0 && !showClassificationInterface && (
              <div className="p-6 bg-gradient-to-r from-indigo-50/60 to-slate-50 border-b border-indigo-100">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-indigo-100 rounded-lg ring-1 ring-indigo-200">
                      <FileText className="text-indigo-700" size={18} />
                    </div>
                    <div>
                      <h2 className="text-base font-semibold text-slate-800">
                        Audit Summary
                      </h2>
                      <p className="text-xs text-slate-600">
                        Required before submission • auto-saved as draft
                      </p>
                    </div>
                  </div>
                  {questionnaireName && (
                    <div className="flex items-center gap-2 px-3 py-2 bg-white border border-indigo-100 rounded-lg">
                      <ClipboardList size={16} className="text-[#064273]" />
                      <span className="text-sm font-medium text-slate-700">
                        {questionnaireName}
                      </span>
                      <span
                        className={`px-2 py-1 text-xs font-semibold rounded ${
                          questionnaireProfile === "VDA_PROCESS"
                            ? "bg-sky-100 text-sky-700"
                            : questionnaireProfile === "IATF_PM" ||
                                questionnaireProfile === "IATF_CLASSIFICATION"
                              ? "bg-indigo-100 text-indigo-700"
                              : questionnaireProfile === "ISO_SYSTEM"
                                ? "bg-cyan-100 text-cyan-700"
                                : questionnaireProfile === "INTERNAL"
                                  ? "bg-teal-100 text-teal-700"
                                  : "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {scaleDescription}
                      </span>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div>
                    <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-1.5">
                      <Calendar size={14} className="text-slate-500" />
                      Audit Date
                    </label>
                    <input
                      id="summary-auditDate"
                      type="date"
                      value={summary.auditDate}
                      onChange={(e) =>
                        handleSummaryChange("auditDate", e.target.value)
                      }
                      className={`w-full p-2.5 bg-white border rounded-lg text-sm focus:ring-2 focus:ring-[#064273] ${
                        submitAttempted && !summary.auditDate.trim()
                          ? "border-red-400 ring-1 ring-red-200"
                          : "border-indigo-200"
                      }`}
                    />
                  </div>
                  <div>
                    <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-1.5">
                      <Clock size={14} className="text-slate-500" />
                      Start Time
                    </label>
                    <input
                      id="summary-startTime"
                      type="time"
                      value={summary.startTime}
                      onChange={(e) =>
                        handleSummaryChange("startTime", e.target.value)
                      }
                      className={`w-full p-2.5 bg-white border rounded-lg text-sm focus:ring-2 focus:ring-[#064273] ${
                        submitAttempted && !summary.startTime.trim()
                          ? "border-red-400 ring-1 ring-red-200"
                          : "border-indigo-200"
                      }`}
                    />
                  </div>
                  <div>
                    <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-1.5">
                      <Clock size={14} className="text-slate-500" />
                      End Time
                    </label>
                    <input
                      id="summary-endTime"
                      type="time"
                      value={summary.endTime}
                      onChange={(e) =>
                        handleSummaryChange("endTime", e.target.value)
                      }
                      className={`w-full p-2.5 bg-white border rounded-lg text-sm focus:ring-2 focus:ring-[#064273] ${
                        submitAttempted && !summary.endTime.trim()
                          ? "border-red-400 ring-1 ring-red-200"
                          : "border-indigo-200"
                      }`}
                    />
                  </div>
                  <div className="hidden lg:block" />
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                      Strong Points
                    </label>
                    <textarea
                      id="summary-strongPoints"
                      rows={2}
                      value={summary.strongPoints}
                      onChange={(e) =>
                        handleSummaryChange("strongPoints", e.target.value)
                      }
                      placeholder="Describe strengths observed..."
                      className={`w-full p-2.5 bg-white border rounded-lg text-sm focus:ring-2 focus:ring-[#064273] resize-none ${
                        submitAttempted && !summary.strongPoints.trim()
                          ? "border-red-400 ring-1 ring-red-200"
                          : "border-indigo-200"
                      }`}
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                      Weak Points
                    </label>
                    <textarea
                      id="summary-weakPoints"
                      rows={2}
                      value={summary.weakPoints}
                      onChange={(e) =>
                        handleSummaryChange("weakPoints", e.target.value)
                      }
                      placeholder="Describe weaknesses or non-conformities..."
                      className={`w-full p-2.5 bg-white border rounded-lg text-sm focus:ring-2 focus:ring-[#064273] resize-none ${
                        submitAttempted && !summary.weakPoints.trim()
                          ? "border-red-400 ring-1 ring-red-200"
                          : "border-indigo-200"
                      }`}
                    />
                  </div>
                </div>
              </div>
            )}

            {items.length > 0 && !showClassificationInterface && (
              <div className="p-5 bg-white border-b border-indigo-100">
                <div className="flex items-center gap-4 mb-3">
                  <span className="text-sm font-semibold text-slate-700">
                    Progress:
                  </span>
                  <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden shadow-inner">
                    <div
                      className="h-full bg-gradient-to-r from-indigo-500 to-indigo-600 rounded-full transition-all duration-500 ease-out"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <span className="text-sm font-bold text-slate-700 min-w-[3rem] text-right">
                    {progress}%
                  </span>
                </div>
                {carCount > 0 && (
                  <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg">
                    <AlertTriangle
                      size={16}
                      className="text-amber-600 flex-shrink-0"
                    />
                    <span className="text-sm text-amber-700 font-medium">
                      {carCount} CAR{carCount > 1 ? "s" : ""} will be requested
                      upon submission
                    </span>
                  </div>
                )}
                
                {/* ── FIX2: show per-section 2/3 rule violations to the user */}
                {isVda && vdaRuleViolations.length > 0 && (
                  <div className="mt-2 flex items-start gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg">
                    <AlertTriangle
                      size={16}
                      className="text-red-600 flex-shrink-0 mt-0.5"
                    />
                    <div className="text-sm text-red-700">
                      <p className="font-medium">
                        VDA 2/3 rule not met — each selected chapter requires at
                        least ⅔ of its questions to be answered:
                      </p>
                      <ul className="mt-1 list-disc pl-4 space-y-0.5">
                        {vdaRuleViolations.map((v) => (
                          <li key={v.section}>
                            <span className="font-semibold">{v.section}</span>:{" "}
                            {v.answered} answered out of {v.total} total
                            (minimum {v.required} required)
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {isVda ? (
            <div className="space-y-4">
              {potentialAnalysisQuestions.length > 0 && (
                <PotentialAnalysisExecution
                  questions={potentialAnalysisQuestions}
                  answers={paAnswers}
                  onChange={handlePaChange}
                  onAddEvidence={handlePaAddEvidence}
                  onRemoveEvidence={handlePaRemoveEvidence}
                />
              )}
              <VdaExecution
                items={items}
                valueOptions={valueOptions}
                questionnaireName={questionnaireName}
                vdaQuestions={vdaQuestions}
                selectedIds={vdaSelectedIds}
                enabledSections={vdaEnabledSections}
                onToggleSection={toggleVdaSection}
                onToggleSelect={toggleVdaSelect}
                onSelectAllInSection={selectAllInSection}
                onUpdateField={updateField}
                onToggleImmediateAction={toggleImmediateAction}
                previews={previews}
                onAddEvidence={addEvidence}
                onRemoveLocalEvidence={removeLocalEvidence}
                onRemoveUploadedEvidence={removeUploadedEvidence}
                sideModeByBase={vdaSideModeByBase}
                onSetSideMode={(baseCode, mode) =>
                  setVdaSideModeByBase((prev) => ({ ...prev, [baseCode]: mode }))
                }
              />
              {!canSubmit && submitBlockers.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100">
                  <p className="font-semibold mb-1">
                    {submitBlockers.length === 1
                      ? "1 thing needed before you can submit:"
                      : `${submitBlockers.length} things needed before you can submit:`}
                  </p>
                  <ul className="list-disc list-inside space-y-0.5">
                    {submitBlockers.map((blocker, idx) => (
                      <li key={idx}>{blocker}</li>
                    ))}
                  </ul>
                </div>
              )}
              {effectiveItems.length > 0 && (
                <SubmitFooter
                  footerMsg={getFooterMessage(
                    questionnaireName,
                    profileContext,
                  )}
                  carCount={carCount}
                  canSubmit={canSubmit}
                  submitting={submitting}
                  submitted={submitted}
                  showCarHint={!isVda}
                />
              )}
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-indigo-100 shadow-sm shadow-indigo-100/20 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gradient-to-r from-indigo-100/80 to-slate-50 border-b border-indigo-100">
                      {[
                        "#",
                        "Question",
                        "Critical",
                        "Value",
                        "Findings",
                        "Evidence",
                        "CAR Reason",
                      ].map((h, i) => (
                        <th
                          key={h}
                          className={`px-4 py-4 text-left text-xs font-bold text-slate-700 uppercase tracking-wider ${i === 2 ? "text-center w-24" : i === 0 ? "w-16" : i === 1 ? "min-w-[280px]" : i === 3 ? "w-52" : i === 4 ? "w-56" : i === 5 ? "w-40" : "w-56"}`}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {items.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-20 text-center">
                          <div className="flex flex-col items-center gap-4">
                            <div className="p-4 bg-slate-100 rounded-full">
                              <FileText className="text-slate-400" size={40} />
                            </div>
                            <div>
                              <p className="text-base font-medium text-slate-700 mb-1">
                                No Audit Selected
                              </p>
                              <p className="text-sm text-slate-500">
                                Select a planned audit to load questions
                              </p>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      items.map((item) => (
                        <AuditRow
                          key={item.uiId}
                          item={item}
                          previews={previews}
                          valueOptions={valueOptions}
                          questionnaireName={questionnaireName}
                          profileContext={profileContext}
                          onUpdateField={updateField}
                          onToggleCAR={toggleCARRequest}
                          onAddEvidence={addEvidence}
                          onRemoveLocalEvidence={removeLocalEvidence}
                          onRemoveUploadedEvidence={removeUploadedEvidence}
                        />
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {items.length > 0 && (
                <SubmitFooter
                  footerMsg={getFooterMessage(
                    questionnaireName,
                    profileContext,
                  )}
                  carCount={carCount}
                  canSubmit={canSubmit}
                  submitting={submitting}
                  submitted={submitted}
                  showCarHint={!isVda}
                />
              )}
            </div>
          )}
        </form>
      </div>
    </div>
  );
}

function SubmitFooter({
  footerMsg,
  carCount,
  canSubmit,
  submitting,
  submitted,
  showCarHint,
}: {
  footerMsg: string;
  carCount: number;
  canSubmit: boolean;
  submitting: boolean;
  submitted: boolean;
  showCarHint: boolean;
}) {
  return (
    <div className="px-6 py-5 bg-gradient-to-r from-indigo-50/60 to-slate-50 border-t border-indigo-100">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="space-y-1">
          <p className="text-sm text-slate-600">
            {footerMsg}
            {showCarHint ? " Check 'Request CAR' for corrective actions." : ""}
          </p>
          {carCount > 0 && (
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className="text-amber-600" />
              <p className="text-sm text-amber-700 font-medium">
                {carCount} CAR{carCount > 1 ? "s" : ""} will be submitted
              </p>
            </div>
          )}
        </div>
        <button
          type="submit"
          disabled={submitting || submitted}
          title={
            canSubmit
              ? undefined
              : "Some required fields are missing — click to see what's needed"
          }
          className={`inline-flex items-center gap-2 px-8 py-3 text-sm font-semibold rounded-lg transition-all shadow-sm ${
            submitted
              ? "bg-emerald-600 text-white cursor-default"
              : canSubmit
                ? "bg-[#064273] text-white hover:bg-[#05375f] hover:shadow-md active:scale-95"
                : "bg-amber-100 text-amber-700 border border-amber-300 hover:bg-amber-200 active:scale-95"
          }`}
        >
          {submitted ? (
            <>
              <CheckCircle2 size={18} />
              <span>Submitted</span>
            </>
          ) : submitting ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <span>Submitting…</span>
            </>
          ) : (
            "Submit Audit"
          )}
        </button>
      </div>
    </div>
  );
}



