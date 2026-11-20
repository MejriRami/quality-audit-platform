import { useState, useEffect, useRef, useCallback } from "react";
import type { AxiosError } from "axios";
import {
  AlertTriangle,
  Plus,
  Trash2,
  Calendar,
  FileText,
  ArrowUp,
  ArrowDown,
  Edit2,
  CheckCircle2,
  X,
  Upload,
  Clock,
} from "lucide-react";
import toast from "react-hot-toast";
import { apiUploadFile } from "../../redux/audit/audit";

// ==================== TYPES ====================
type ClassificationMode = "IATF" | "ISO" | "OPEN";
type NCClassification =
  | "Minor"
  | "Major"
  | "Improvement"
  | "Major NC"
  | "Minor NC"
  | "OFI"
  | "Conformity"
  | "Observation"
  | "Nonconformity";

const toNCClassification = (
  value: unknown,
  mode: ClassificationMode,
): NCClassification => {
  if (
    value === "Minor" ||
    value === "Major" ||
    value === "Improvement" ||
    value === "Major NC" ||
    value === "Minor NC" ||
    value === "OFI" ||
    value === "Conformity" ||
    value === "Observation" ||
    value === "Nonconformity"
  ) {
    return value;
  }
  if (mode === "OPEN") return "Conformity";
  return mode === "ISO" ? "Minor NC" : "Minor";
};

const getErrorMessage = (error: unknown, fallback: string) => {
  const axiosErr = error as AxiosError<{ detail?: string }>;
  return (
    axiosErr?.response?.data?.detail ||
    (error instanceof Error ? error.message : fallback)
  );
};

interface NonConformity {
  id: string;
  ncNumber: string;
  identificationNumber: string;
  norm: string;
  normParagraph: string;
  process: string;
  classification: NCClassification;
  dueDateMax15Days?: string;
  dueDate60Days?: string;
  observedNonConformity: string;
  evaluatorDecision: string;
  findings: string;
  evidence: File[];
  uploadedDocs: Array<{
    filename: string;
    mimetype: string;
    size: number;
    file_url: string;
  }>;
  requestCAR: boolean;
  silentBox: boolean;
  // Open audits only: the question typed by the auditor.
  question: string;
}

interface IATFNonConformityManagerProps {
  plannedAuditId: number;
  questionnaireName: string;
  mode?: ClassificationMode;
  auditNumber?: string;
  auditeeName?: string;
  auditDate?: string;
  plannedStartTime?: string;
  plannedEndTime?: string;
  draftStartTime?: string | null;
  draftEndTime?: string | null;
  draftStrongPoints?: string | null;
  draftWeakPoints?: string | null;

  onFieldChange?: (field: string, value: string) => void;
  onNonConformitiesChange?: (ncs: NonConformity[]) => void;
  draftAnswers?: Array<{
    question_id?: number | null;
    draft_row_id?: string | null;
    value?: number | null;
    finding_text?: string;
    request_car?: boolean;
    car_reason?: string;
    silent_box?: boolean;
    process?: string;
    standard_paragraph?: string;
    classification?: string;
    question_text?: string;
    documents?: Array<{
      filename: string;
      mimetype: string;
      size: number;
      file_url: string;
    }>;
  }>;
  onSubmit?: (
    nonConformities: NonConformity[],
    auditDetails: {
      actualStartTime: string;
      actualEndTime: string;
      strongPoints: string;
      weakPoints: string;
    },
  ) => Promise<void>;
  readOnly?: boolean;
}

export default function IATFNonConformityManager({
  plannedAuditId,
  questionnaireName,
  mode = "IATF",
  auditNumber = "N/A",
  auditeeName = "N/A",
  auditDate,
  plannedStartTime,
  plannedEndTime,
  draftStartTime,
  draftEndTime,
  draftStrongPoints,
  draftWeakPoints,
  onSubmit,
  onFieldChange,
  onNonConformitiesChange,
  draftAnswers = [],
  readOnly = false,
}: IATFNonConformityManagerProps) {
  const [nonConformities, setNonConformities] = useState<NonConformity[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const safeText = (v: unknown) => (typeof v === "string" ? v : "");

  const suppressEmitRef = useRef(false);
  const lastAppliedDraftRef = useRef<string>("");
  const nonConformitiesRef = useRef<NonConformity[]>([]);
  useEffect(() => {
    nonConformitiesRef.current = nonConformities;
  }, [nonConformities]);

  const [actualStartTime, setActualStartTime] = useState(
    safeText(draftStartTime) ?? safeText(plannedStartTime) ?? "",
  );
  const [actualEndTime, setActualEndTime] = useState(
    safeText(draftEndTime) ?? safeText(plannedEndTime) ?? "",
  );
  const [strongPoints, setStrongPoints] = useState(
    safeText(draftStrongPoints) ?? "",
  );
  const [weakPoints, setWeakPoints] = useState(safeText(draftWeakPoints) ?? "");
  const isIsoMode = mode === "ISO";
  const isOpenMode = mode === "OPEN";
  const defaultNorm = isOpenMode
    ? "Open audit"
    : isIsoMode
      ? "ISO"
      : "IATF 16949:2016";
  const modeTitle = isOpenMode
    ? "Open Audit"
    : isIsoMode
      ? "ISO Classification Audit"
      : "IATF Classification Audit";
  const modeHint = isOpenMode
    ? "Type any question you ask and the answer you get. Mark each one Conformity, Observation or Nonconformity; a CAR can be requested for Observation or Nonconformity."
    : isIsoMode
      ? "Use Major NC / Minor NC / OFI / Conformity. CAR is auto-enabled for Major NC and Minor NC."
      : "Use Minor / Major / Improvement according to the IATF classification workflow.";
  const classificationOptions: NCClassification[] = isOpenMode
    ? ["Conformity", "Observation", "Nonconformity"]
    : isIsoMode
      ? ["Major NC", "Minor NC", "OFI", "Conformity"]
      : ["Minor", "Major", "Improvement"];
  const entryLabel = isOpenMode ? "Question" : "Non-Conformit";

  const generateId = () =>
    `nc-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;

  const buildEmptyNC = useCallback(
    (index: number): NonConformity => ({
      id: generateId(),
      ncNumber: String(index),
      identificationNumber: `ST0${index}`,
      norm: defaultNorm,
      normParagraph: "",
      process: "",
      classification: isOpenMode ? "Conformity" : isIsoMode ? "Minor NC" : "Minor",
      dueDate60Days: "",
      observedNonConformity: "",
      evaluatorDecision: "",
      findings: "",
      evidence: [],
      uploadedDocs: [],
      requestCAR: !isOpenMode,
      silentBox: false,
      question: "",
    }),
    [defaultNorm, isIsoMode, isOpenMode],
  );

  useEffect(() => {
    if (draftStartTime !== undefined)
      setActualStartTime(safeText(draftStartTime));
    if (draftEndTime !== undefined) setActualEndTime(safeText(draftEndTime));
    if (draftStrongPoints !== undefined)
      setStrongPoints(safeText(draftStrongPoints));
    if (draftWeakPoints !== undefined) setWeakPoints(safeText(draftWeakPoints));
  }, [draftStartTime, draftEndTime, draftStrongPoints, draftWeakPoints]);
  useEffect(() => {
    setHydrated(false);
    lastAppliedDraftRef.current = "";
    suppressEmitRef.current = false;
  }, [plannedAuditId]);

  useEffect(() => {
    const rawNormalized = (draftAnswers ?? []).map((a) => ({
      question_id: a.question_id ?? null,
      draft_row_id: typeof a.draft_row_id === "string" ? a.draft_row_id : null,
      value: a.value ?? null,
      finding_text: a.finding_text ?? "",
      request_car: Boolean(a.request_car),
      car_reason: a.car_reason ?? "",
      silent_box: Boolean(a.silent_box),
      process: a.process ?? "",
      standard_paragraph: a.standard_paragraph ?? "",
      classification: toNCClassification(a.classification, mode),
      question_text: a.question_text ?? "",
      documents: a.documents ?? [],
    }));

    // Defensive dedupe by stable row id only; question_id is not guaranteed
    // unique per NC row (e.g. ISO mode sends question_id: 0 for every row).
    const normalizedMap = new Map<string, (typeof rawNormalized)[number]>();
    rawNormalized.forEach((a, idx) => {
      const key = a.draft_row_id ? `rid-${a.draft_row_id}` : `row-${idx}`;
      normalizedMap.set(key, a);
    });
    const normalized = Array.from(normalizedMap.values());

    const incoming = JSON.stringify(normalized);

    if (!normalized.length) {
      suppressEmitRef.current = true;
      setNonConformities((prev) => {
        if (prev.length > 0) return prev;
        const first = buildEmptyNC(1);
        setExpandedId(first.id);
        return [first];
      });
      setHydrated(true);
      Promise.resolve().then(() => {
        suppressEmitRef.current = false;
      });
      return;
    }

    if (incoming === lastAppliedDraftRef.current) {
      setHydrated(true);
      return;
    }

    suppressEmitRef.current = true;

    const prevById = new Map(
      nonConformitiesRef.current.map((nc) => [nc.id, nc]),
    );
    const restored: NonConformity[] = normalized.map((a, idx) => {
      const id = a.draft_row_id || `draft-${idx}`;
      const existing = prevById.get(id);
      return {
        id,
        ncNumber: String(idx + 1),
        identificationNumber:
          existing?.identificationNumber ?? `ST0${idx + 1}`,
        norm: existing?.norm ?? defaultNorm,
        normParagraph: a.standard_paragraph,
        process: a.process,
        classification: a.classification,
        dueDate60Days: existing?.dueDate60Days ?? "",
        observedNonConformity: a.car_reason,
        evaluatorDecision: existing?.evaluatorDecision ?? "",
        findings: a.finding_text,
        evidence: existing?.evidence ?? [],
        uploadedDocs: a.documents,
        requestCAR: a.request_car,
        silentBox: a.silent_box,
        question: a.question_text,
      };
    });

    setNonConformities(restored);
    setExpandedId((prevExpandedId) =>
      prevExpandedId && restored.some((nc) => nc.id === prevExpandedId)
        ? prevExpandedId
        : (restored[0]?.id ?? null),
    );
    lastAppliedDraftRef.current = incoming;
    setHydrated(true);

    Promise.resolve().then(() => {
      suppressEmitRef.current = false;
    });
  }, [buildEmptyNC, defaultNorm, draftAnswers, mode, plannedAuditId]);

  useEffect(() => {
    if (!hydrated || suppressEmitRef.current) return;
    onNonConformitiesChange?.(nonConformities);
  }, [hydrated, nonConformities, onNonConformitiesChange]);

  const addNewNC = () => {
    const nextIndex = nonConformities.length + 1;
    const newNC = buildEmptyNC(nextIndex);
    setNonConformities((prev) => [...prev, newNC]);
    setExpandedId(newNC.id);
  };

  const removeNC = (id: string) => {
    if (nonConformities.length === 1) {
      toast.error("At least one non-conformity is required");
      return;
    }
    setNonConformities((prev) =>
      prev
        .filter((nc) => nc.id !== id)
        .map((nc, idx) => ({
          ...nc,
          ncNumber: String(idx + 1),
          identificationNumber: `ST0${idx + 1}`,
        })),
    );
    if (expandedId === id) setExpandedId(null);
  };

  const updateNC = <K extends keyof NonConformity>(
    id: string,
    field: K,
    value: NonConformity[K],
  ) => {
    setNonConformities((prev) =>
      prev.map((nc) => {
        if (nc.id !== id) return nc;
        const updated = { ...nc, [field]: value };

        if (field === "classification") {
          const newClassification = value as NCClassification;
          if (isOpenMode) {
            if (newClassification === "Conformity") updated.requestCAR = false;
          } else if (isIsoMode) {
            updated.requestCAR =
              newClassification === "Major NC" ||
              newClassification === "Minor NC";
          } else {
            if (
              newClassification === "Minor" ||
              newClassification === "Major" ||
              newClassification === "Improvement"
            ) {
              updated.requestCAR = true;
            }
          }
        }

        return updated;
      }),
    );
  };

  const moveNC = (id: string, direction: "up" | "down") => {
    setNonConformities((prev) => {
      const index = prev.findIndex((nc) => nc.id === id);
      if (
        index === -1 ||
        (direction === "up" && index === 0) ||
        (direction === "down" && index === prev.length - 1)
      ) {
        return prev;
      }

      const newNCs = [...prev];
      const targetIndex = direction === "up" ? index - 1 : index + 1;
      [newNCs[index], newNCs[targetIndex]] = [
        newNCs[targetIndex],
        newNCs[index],
      ];

      return newNCs.map((nc, idx) => ({
        ...nc,
        ncNumber: String(idx + 1),
        identificationNumber: `ST0${idx + 1}`,
      }));
    });
  };

  const addEvidence = async (id: string, files: FileList | null) => {
    if (!files) return;
    const imageFiles = Array.from(files).filter((f) =>
      f.type.startsWith("image/"),
    );
    if (imageFiles.length === 0) {
      toast.error("Please select image files only");
      return;
    }

    try {
      const uploadedDocs = await Promise.all(
        imageFiles.map(async (file) => {
          const up = await apiUploadFile(file);
          return {
            filename: up.filename,
            mimetype: up.mimetype,
            size: up.size,
            file_url: up.file_url,
          };
        }),
      );

      setNonConformities((prev) =>
        prev.map((nc) =>
          nc.id === id
            ? {
                ...nc,
                evidence: [...nc.evidence, ...imageFiles],
                uploadedDocs: [...nc.uploadedDocs, ...uploadedDocs],
              }
            : nc,
        ),
      );
    } catch {
      toast.error("Failed to upload evidence");
    }
  };

  const removeUploadedEvidence = (id: string, idx: number) => {
    setNonConformities((prev) =>
      prev.map((nc) =>
        nc.id === id
          ? {
              ...nc,
              uploadedDocs: nc.uploadedDocs.filter((_, i) => i !== idx),
            }
          : nc,
      ),
    );
  };

  const validateNC = (nc: NonConformity): string[] => {
    const errors: string[] = [];
    if (isOpenMode) {
      if (!nc.question.trim()) errors.push("Question is required");
      if (!nc.findings.trim()) errors.push("Answer is required");
      if (nc.requestCAR && !nc.observedNonConformity.trim())
        errors.push("CAR reason is required when requesting a CAR");
      return errors;
    }
    if (!nc.normParagraph.trim())
      errors.push("Clause / requirement reference is required");
    if (!nc.process.trim()) errors.push("Process / area is required");

    const observedRequired = isIsoMode
      ? nc.classification === "Major NC" || nc.classification === "Minor NC"
      : nc.classification === "Minor" || nc.classification === "Major";
    if (observedRequired && !nc.observedNonConformity.trim()) {
      errors.push(
        "Observed non-conformity is required for major/minor non-conformity classifications",
      );
    }

    return errors;
  };

  const handleSubmit = async () => {
    const allErrors: { [key: string]: string[] } = {};
    nonConformities.forEach((nc) => {
      const errors = validateNC(nc);
      if (errors.length > 0) allErrors[nc.id] = errors;
    });

    if (Object.keys(allErrors).length > 0) {
      toast.error("Please fix all validation errors before submitting");
      setExpandedId(Object.keys(allErrors)[0]);
      return;
    }

    if (!actualStartTime || !actualEndTime) {
      toast.error("Please provide actual start and end times for the audit");
      return;
    }

    setSubmitting(true);
    try {
      if (onSubmit) {
        await onSubmit(nonConformities, {
          actualStartTime,
          actualEndTime,
          strongPoints,
          weakPoints,
        });
      }
      toast.success(
        isOpenMode
          ? `${nonConformities.length} question${nonConformities.length > 1 ? "s" : ""} submitted successfully`
          : `${nonConformities.length} non-conformit${
              nonConformities.length > 1 ? "ies" : "y"
            } submitted successfully`,
      );
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, "Failed to submit non-conformities"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50/35 to-sky-50/25">
      <div className="max-w-7xl mx-auto p-6 space-y-6">
        <div className="bg-white/95 rounded-xl shadow-sm shadow-indigo-100/30 border border-indigo-100 overflow-hidden backdrop-blur-sm">
          <div className="bg-gradient-to-r from-[#064273] to-[#0a5f95] px-6 py-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-white/20 rounded-lg backdrop-blur-sm ring-1 ring-white/30">
                  <AlertTriangle className="text-white" size={28} />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-white">
                    Audit Execution - {modeTitle}
                  </h1>
                  <p className="text-indigo-100 text-sm mt-1">
                    {auditNumber} • Auditee: {auditeeName}
                  </p>
                </div>
              </div>
              <div className="px-4 py-2 bg-white/20 backdrop-blur-sm rounded-lg border border-white/30">
                <p className="text-white text-sm font-medium">
                  {questionnaireName}
                </p>
              </div>
            </div>
          </div>

          <div className="px-6 py-5 bg-gradient-to-r from-indigo-50/60 to-slate-50 border-b border-indigo-100">
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
                    Required before submission
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 px-3 py-2 bg-white border border-indigo-100 rounded-lg">
                <span className="text-sm font-medium text-slate-700">
                  {questionnaireName}
                </span>
                <span className="px-2 py-1 text-xs font-semibold rounded bg-indigo-100 text-indigo-700">
                  {isOpenMode
                    ? "Open (Conformity / Observation / Nonconformity)"
                    : isIsoMode
                      ? "ISO (Major NC / Minor NC / OFI / Conformity)"
                      : "IATF (Minor / Major / Improvement / Strong Point)"}
                </span>
              </div>
            </div>
            <div className="mb-4 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
              {modeHint}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-1.5">
                  <Calendar size={14} className="text-slate-500" />
                  Audit Date
                </label>
                <div className="px-3 py-2 bg-white border border-indigo-200 rounded-lg text-sm text-slate-700">
                  {auditDate || "N/A"}
                </div>
              </div>

              <div>
                <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-1.5">
                  <Clock size={14} className="text-slate-500" />
                  Actual Start Time <span className="text-red-500">*</span>
                </label>
                <input
                  type="time"
                  value={actualStartTime}
                  onChange={(e) => {
                    setActualStartTime(e.target.value);
                    onFieldChange?.("actualStartTime", e.target.value);
                  }}
                  disabled={readOnly}
                  className="w-full px-3 py-2 bg-white border border-indigo-200 rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all disabled:opacity-60"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-1.5">
                  <Clock size={14} className="text-slate-500" />
                  Actual End Time <span className="text-red-500">*</span>
                </label>
                <input
                  type="time"
                  value={actualEndTime}
                  onChange={(e) => {
                    setActualEndTime(e.target.value);
                    onFieldChange?.("actualEndTime", e.target.value);
                  }}
                  disabled={readOnly}
                  className="w-full px-3 py-2 bg-white border border-indigo-200 rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all disabled:opacity-60"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Strong Points
                </label>
                <textarea
                  rows={2}
                  value={strongPoints}
                  onChange={(e) => {
                    setStrongPoints(e.target.value);
                    onFieldChange?.("strongPoints", e.target.value);
                  }}
                  disabled={readOnly}
                  placeholder="Describe strengths observed..."
                  className="w-full px-3 py-2 bg-white border border-indigo-200 rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all resize-none disabled:opacity-60"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Weak Points
                </label>
                <textarea
                  rows={2}
                  value={weakPoints}
                  onChange={(e) => {
                    setWeakPoints(e.target.value);
                    onFieldChange?.("weakPoints", e.target.value);
                  }}
                  disabled={readOnly}
                  placeholder="Describe weaknesses or non-conformities..."
                  className="w-full px-3 py-2 bg-white border border-indigo-200 rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all resize-none disabled:opacity-60"
                />
              </div>
            </div>
          </div>

          <div className="px-6 py-4 bg-indigo-50/45 border-b border-indigo-100">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-700">
                <span className="font-semibold">
                  {nonConformities.length} {entryLabel}
                  {isOpenMode
                    ? nonConformities.length > 1
                      ? "s"
                      : ""
                    : nonConformities.length > 1
                      ? "ies"
                      : "y"}
                </span>{" "}
                recorded
              </p>
              {!readOnly && (
                <button
                  type="button"
                  onClick={addNewNC}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-[#064273] text-white rounded-lg hover:bg-[#05375f] transition-colors text-sm font-medium shadow-sm"
                >
                  <Plus size={16} />
                  {isOpenMode ? "Add question" : "Add NC"}
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          {nonConformities.map((nc, index) => {
            const isExpanded = expandedId === nc.id;
            const errors = validateNC(nc);
            const hasErrors = errors.length > 0;

            const getClassificationStyle = (
              classification: NCClassification,
            ) => {
              switch (classification) {
                case "Major":
                  return {
                    badge: "bg-red-100 text-red-700 ring-2 ring-red-200",
                    label: "bg-red-100 text-red-700",
                  };
                case "Minor":
                  return {
                    badge: "bg-amber-100 text-amber-700 ring-2 ring-amber-200",
                    label: "bg-amber-100 text-amber-700",
                  };
                case "Improvement":
                  return {
                    badge:
                      "bg-indigo-100 text-indigo-700 ring-2 ring-indigo-200",
                    label: "bg-indigo-100 text-indigo-700",
                  };

                case "Major NC":
                  return {
                    badge: "bg-red-100 text-red-700 ring-2 ring-red-200",
                    label: "bg-red-100 text-red-700",
                  };
                case "Minor NC":
                  return {
                    badge: "bg-amber-100 text-amber-700 ring-2 ring-amber-200",
                    label: "bg-amber-100 text-amber-700",
                  };
                case "OFI":
                  return {
                    badge:
                      "bg-indigo-100 text-indigo-700 ring-2 ring-indigo-200",
                    label: "bg-indigo-100 text-indigo-700",
                  };
                case "Nonconformity":
                  return {
                    badge: "bg-red-100 text-red-700 ring-2 ring-red-200",
                    label: "bg-red-100 text-red-700",
                  };
                case "Observation":
                  return {
                    badge: "bg-amber-100 text-amber-700 ring-2 ring-amber-200",
                    label: "bg-amber-100 text-amber-700",
                  };
                case "Conformity":
                  return {
                    badge:
                      "bg-emerald-100 text-emerald-700 ring-2 ring-emerald-200",
                    label: "bg-emerald-100 text-emerald-700",
                  };
                default:
                  return {
                    badge: "bg-slate-100 text-slate-700 ring-2 ring-slate-200",
                    label: "bg-slate-100 text-slate-700",
                  };
              }
            };

            const styles = getClassificationStyle(nc.classification);
            const canRequestCAR = isOpenMode || isIsoMode
              ? nc.classification !== "Conformity"
              : nc.classification === "Minor" ||
                nc.classification === "Major" ||
                nc.classification === "Improvement";

            const isObservedNCRequired = isOpenMode
              ? nc.requestCAR
              : isIsoMode
              ? nc.classification === "Minor NC" ||
                nc.classification === "Major NC"
              : nc.classification === "Minor" || nc.classification === "Major";

            return (
              <div
                key={nc.id}
                className={`bg-white rounded-xl shadow-sm border-2 transition-all ${
                  hasErrors
                    ? "border-red-300"
                    : isExpanded
                      ? "border-indigo-300"
                      : "border-slate-200"
                }`}
              >
                <div
                  className={`px-6 py-4 cursor-pointer transition-colors ${
                    isExpanded
                      ? "bg-gradient-to-r from-indigo-50 to-slate-50"
                      : "bg-slate-50 hover:bg-indigo-50/50"
                  }`}
                  onClick={() => setExpandedId(isExpanded ? null : nc.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div
                        className={`flex items-center justify-center w-12 h-12 rounded-lg font-bold text-lg ${styles.badge}`}
                      >
                        {nc.ncNumber}
                      </div>
                      <div>
                        <div className="flex items-center gap-3">
                          <h3 className="font-semibold text-slate-800">
                            {isOpenMode
                              ? `Question ${nc.ncNumber}`
                              : `NC N° ${nc.identificationNumber}`}
                          </h3>
                          <span
                            className={`px-3 py-1 rounded-full text-xs font-semibold ${styles.label}`}
                          >
                            {nc.classification}
                          </span>
                        </div>
                        <p className="text-sm text-slate-600 mt-1">
                          {(isOpenMode ? nc.question : "") ||
                            nc.observedNonConformity ||
                            nc.findings || (
                            <span className="italic">
                              No description yet...
                            </span>
                          )}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {hasErrors && (
                        <div className="px-3 py-1.5 bg-red-100 text-red-700 rounded-lg text-xs font-medium flex items-center gap-2">
                          <AlertTriangle size={14} />
                          {errors.length} error{errors.length > 1 ? "s" : ""}
                        </div>
                      )}

                      {!readOnly && (
                        <>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              moveNC(nc.id, "up");
                            }}
                            disabled={index === 0}
                            className="p-2 hover:bg-slate-200 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            <ArrowUp size={16} className="text-slate-600" />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              moveNC(nc.id, "down");
                            }}
                            disabled={index === nonConformities.length - 1}
                            className="p-2 hover:bg-slate-200 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            <ArrowDown size={16} className="text-slate-600" />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              removeNC(nc.id);
                            }}
                            className="p-2 hover:bg-red-100 rounded-lg transition-colors"
                          >
                            <Trash2 size={16} className="text-red-600" />
                          </button>
                        </>
                      )}

                      {isExpanded ? (
                        <X size={20} className="text-slate-400" />
                      ) : (
                        <Edit2 size={20} className="text-slate-400" />
                      )}
                    </div>
                  </div>
                </div>

                {isExpanded && (
                  <div className="px-6 py-6 border-t border-slate-200 bg-white">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                      <div className="space-y-5">
                        {isOpenMode && (
                          <div>
                            <label className="block text-sm font-semibold text-slate-700 mb-2">
                              Question <span className="text-red-500">*</span>
                            </label>
                            <textarea
                              value={nc.question}
                              onChange={(e) =>
                                updateNC(nc.id, "question", e.target.value)
                              }
                              disabled={readOnly}
                              rows={3}
                              placeholder="Type the question you asked..."
                              className={`w-full px-4 py-3 border rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all resize-none disabled:opacity-60 ${
                                !nc.question.trim() && hasErrors
                                  ? "border-red-400 bg-red-50"
                                  : "border-slate-300 bg-white"
                              }`}
                            />
                          </div>
                        )}
                        {!isOpenMode && (
                        <>
                        <div>
                          <label className="block text-sm font-semibold text-slate-700 mb-2">
                            NC Identification Number
                          </label>
                          <input
                            type="text"
                            value={nc.identificationNumber}
                            onChange={(e) =>
                              updateNC(
                                nc.id,
                                "identificationNumber",
                                e.target.value,
                              )
                            }
                            disabled={readOnly}
                            className="w-full px-4 py-2.5 bg-slate-50 border border-indigo-200 rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all disabled:opacity-60"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-slate-700 mb-2">
                            Reference Standard / Checklist
                          </label>
                          <input
                            type="text"
                            value={nc.norm}
                            onChange={(e) =>
                              updateNC(nc.id, "norm", e.target.value)
                            }
                            disabled={readOnly}
                            className="w-full px-4 py-2.5 bg-slate-50 border border-indigo-200 rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all disabled:opacity-60"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-slate-700 mb-2">
                            Clause / Requirement Reference{" "}
                            <span className="text-red-500">*</span>
                          </label>
                          <input
                            type="text"
                            value={nc.normParagraph}
                            onChange={(e) =>
                              updateNC(nc.id, "normParagraph", e.target.value)
                            }
                            disabled={readOnly}
                            placeholder="e.g., 9.3.2.1"
                            className={`w-full px-4 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all disabled:opacity-60 ${
                              !nc.normParagraph.trim() && hasErrors
                                ? "border-red-400 bg-red-50"
                                : "border-slate-300 bg-white"
                            }`}
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-slate-700 mb-2">
                            Process <span className="text-red-500">*</span>
                          </label>
                          <input
                            type="text"
                            value={nc.process}
                            onChange={(e) =>
                              updateNC(nc.id, "process", e.target.value)
                            }
                            disabled={readOnly}
                            placeholder="e.g., P1. Leadership"
                            className={`w-full px-4 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all disabled:opacity-60 ${
                              !nc.process.trim() && hasErrors
                                ? "border-red-400 bg-red-50"
                                : "border-slate-300 bg-white"
                            }`}
                          />
                        </div>
                        </>
                        )}

                        <div>
                          <label className="block text-sm font-semibold text-slate-700 mb-2">
                            {isOpenMode ? "Result" : "Classification"}{" "}
                            <span className="text-red-500">*</span>
                          </label>
                          <select
                            value={nc.classification}
                            onChange={(e) =>
                              updateNC(
                                nc.id,
                                "classification",
                                e.target.value as NCClassification,
                              )
                            }
                            disabled={readOnly}
                            className="w-full px-4 py-2.5 bg-white border border-indigo-200 rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all disabled:opacity-60"
                          >
                            {classificationOptions.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>

                      <div className="space-y-5">
                        {(!isOpenMode || nc.requestCAR) && (
                        <div>
                          <label className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-2">
                            <FileText size={16} className="text-slate-500" />
                            {isOpenMode
                              ? "CAR reason"
                              : isIsoMode
                              ? "Observed Non-Conformity"
                              : "Observed Non-Conformity in Process"}{" "}
                            {isObservedNCRequired && (
                              <span className="text-red-500">*</span>
                            )}
                          </label>
                          <textarea
                            value={nc.observedNonConformity}
                            onChange={(e) =>
                              updateNC(
                                nc.id,
                                "observedNonConformity",
                                e.target.value,
                              )
                            }
                            disabled={readOnly}
                            rows={4}
                            placeholder={
                              isObservedNCRequired
                                ? "Describe the observed non-conformity (required)..."
                                : "Describe the observation (optional)..."
                            }
                            className={`w-full px-4 py-3 border rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all resize-none disabled:opacity-60 ${
                              isObservedNCRequired &&
                              !nc.observedNonConformity.trim() &&
                              hasErrors
                                ? "border-red-400 bg-red-50"
                                : "border-slate-300 bg-white"
                            }`}
                          />
                        </div>
                        )}

                        <div>
                          <label className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-2">
                            <FileText size={16} className="text-slate-500" />
                            {isOpenMode ? "Answer" : "Findings / Details"}
                            {isOpenMode && <span className="text-red-500">*</span>}
                          </label>
                          <textarea
                            value={nc.findings}
                            onChange={(e) =>
                              updateNC(nc.id, "findings", e.target.value)
                            }
                            disabled={readOnly}
                            rows={3}
                            placeholder={
                              isOpenMode
                                ? "Type the answer / what you observed..."
                                : "Additional findings or details..."
                            }
                            className="w-full px-4 py-3 bg-white border border-indigo-200 rounded-lg text-sm focus:ring-2 focus:ring-[#064273] focus:border-transparent transition-all resize-none disabled:opacity-60"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-slate-700 mb-2">
                            <div className="flex items-center gap-2">
                              <Upload size={16} className="text-slate-500" />
                              Evidence / Attachments
                            </div>
                          </label>
                          <div className="space-y-3">
                            <label className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium bg-slate-50 hover:bg-indigo-50 border border-indigo-200 rounded-lg cursor-pointer transition-colors">
                              <Upload size={16} className="text-slate-600" />
                              <span className="text-slate-700">
                                Upload Images
                              </span>
                              <input
                                type="file"
                                accept="image/*"
                                multiple
                                className="hidden"
                                onChange={(e) =>
                                  addEvidence(nc.id, e.target.files)
                                }
                                disabled={readOnly}
                              />
                            </label>

                            {nc.uploadedDocs.length > 0 && (
                              <div className="grid grid-cols-3 gap-2">
                                {nc.uploadedDocs.map((doc, idx) => (
                                  <div
                                    key={`${nc.id}-uploaded-${idx}-${doc.file_url}`}
                                    className="relative group rounded-lg overflow-hidden border-2 border-slate-200 shadow-sm"
                                  >
                                    <img
                                      src={doc.file_url}
                                      alt={doc.filename}
                                      className="w-full h-24 object-cover"
                                    />
                                    {!readOnly && (
                                      <button
                                        type="button"
                                        onClick={() =>
                                          removeUploadedEvidence(nc.id, idx)
                                        }
                                        className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                                      >
                                        <X size={20} className="text-white" />
                                      </button>
                                    )}
                                    <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-2 py-1">
                                      <p className="text-xs text-white truncate">
                                        {doc.filename}
                                      </p>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>

                        {canRequestCAR && (
                          <div className="p-4 bg-amber-50 border-2 border-amber-200 rounded-lg">
                            <label className="flex items-center gap-2 cursor-pointer group/checkbox">
                              <input
                                type="checkbox"
                                checked={nc.requestCAR}
                                onChange={(e) =>
                                  updateNC(
                                    nc.id,
                                    "requestCAR",
                                    e.target.checked,
                                  )
                                }
                                disabled={readOnly}
                                className="w-5 h-5 text-amber-600 bg-white border-slate-300 rounded focus:ring-2 focus:ring-amber-500 cursor-pointer"
                              />
                              <span className="text-sm font-semibold text-amber-800 group-hover/checkbox:text-amber-900 transition-colors">
                                Request CAR (Corrective Action Request)
                              </span>
                            </label>
                          </div>
                        )}

                        <div className="p-4 bg-slate-50 border-2 border-slate-200 rounded-lg">
                          <label className="flex items-center gap-2 cursor-pointer group/checkbox">
                            <input
                              type="checkbox"
                              checked={nc.silentBox}
                              onChange={(e) =>
                                updateNC(nc.id, "silentBox", e.target.checked)
                              }
                              disabled={readOnly}
                              className="w-5 h-5 text-slate-700 bg-white border-slate-300 rounded focus:ring-2 focus:ring-slate-500 cursor-pointer"
                            />
                            <span className="text-sm font-semibold text-slate-700 group-hover/checkbox:text-slate-900 transition-colors">
                              Silent Box (SB) — track internally, exclude from printed Audit Report
                            </span>
                          </label>
                        </div>
                      </div>
                    </div>

                    {hasErrors && (
                      <div className="mt-5 p-4 bg-red-50 border border-red-200 rounded-lg">
                        <div className="flex items-start gap-3">
                          <AlertTriangle
                            size={20}
                            className="text-red-600 flex-shrink-0 mt-0.5"
                          />
                          <div className="flex-1">
                            <p className="text-sm font-semibold text-red-800 mb-2">
                              Validation Errors:
                            </p>
                            <ul className="list-disc list-inside space-y-1">
                              {errors.map((error, idx) => (
                                <li key={idx} className="text-sm text-red-700">
                                  {error}
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {!readOnly && (
          <div className="bg-white rounded-xl shadow-sm shadow-indigo-100/20 border border-indigo-100 p-6">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm font-medium text-slate-700">
                  {isOpenMode
                    ? "Ready to submit the audit?"
                    : "Ready to submit non-conformities?"}
                </p>
                <p className="text-xs text-slate-500">
                  Ensure all required fields are filled
                </p>
              </div>

              <button
                type="button"
                onClick={handleSubmit}
                disabled={
                  submitting ||
                  nonConformities.some((nc) => validateNC(nc).length > 0)
                }
                className="inline-flex items-center gap-3 px-8 py-3 bg-gradient-to-r from-indigo-600 to-indigo-500 text-white rounded-lg hover:from-indigo-700 hover:to-indigo-600 transition-all shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
              >
                {submitting ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Submitting...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={20} />
                    <span>{isOpenMode ? "Submit audit" : "Submit NCs"}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
