import ComponentCard from "../common/ComponentCard";
import Label from "../form/Label";
import Input from "../form/input/InputField";
import { TimeIcon } from "../../icons";
import Select from "../form/Select";
import QuestionnaireInitialForm from "../initialForms/QuestionnaireInitialForm";
import Enum from "../enum/Enum";
import MultiSelectAuditors from "../form/MultiSelectAuditors";
import Button from "../ui/button/Button";
import { addQuestionnaire } from "../../redux/questionnaire/questionnaire";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Spinner } from "../common/Spinner";
import { resetQuestioannairesState } from "../../redux/questionnaire/questionnaire-slice";
import { ArrowLeft, ClipboardList, Sparkles } from "lucide-react";
// import PageMeta from "../common/PageMeta";
// import PageBreadcrumb from "../common/PageBreadCrumb";

type AnySelectValue =
  | string
  | number
  | { value: string | number; label?: string }
  | null
  | undefined;

const getSelectRawValue = (v: AnySelectValue) =>
  typeof v === "object" && v !== null && "value" in v ? v.value : v;

const toIntOrNull = (v: AnySelectValue) => {
  const raw = getSelectRawValue(v);
  if (raw === null || raw === undefined || raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
};

const toStringOrEmpty = (v: AnySelectValue) => {
  const raw = getSelectRawValue(v);
  return raw === null || raw === undefined ? "" : String(raw);
};

// Ensures backend time format "HH:MM:SS"
const normalizeDuration = (t?: string) => {
  if (!t) return "";
  // input type="time" typically returns "HH:MM"
  if (/^\d{2}:\d{2}$/.test(t)) return `${t}:00`;
  if (/^\d{2}:\d{2}:\d{2}$/.test(t)) return t;
  return t;
};

export default function AddQuestionnaire() {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const {
    formQuestionnaire,
    handleInputValue,
    handleSelectChange,
    handleMultiSelectInput,
  } = QuestionnaireInitialForm();

  const { frameworkOptions, auditTypeOptions, auditorOptions } = Enum();

  const { toast, loading, error } = useSelector(
    (state: any) => state.questionnaire,
  );
  const roles = useSelector((state: any) => state.auth.role || []);
  const normalizedRoles = roles.map((r: string) => String(r).trim().toLowerCase());
  const isAuditorOnly =
    normalizedRoles.includes("auditor") &&
    !normalizedRoles.some((r: string) =>
      ["admin", "quality_manager", "quality manager", "quality-manager"].includes(r),
    );

  const [errors, setErrors] = useState<Record<string, string>>({});
  const fieldCardClass =
    "space-y-2 rounded-xl border border-[#064273]/15 bg-white/80 p-4 shadow-sm backdrop-blur-sm dark:border-[#0a5f95]/60 dark:bg-[#0b3a5c]/45";

  const statusOptions = useMemo(
    () => [
      { label: "Ready to Use", value: "Ready to Use" },
      { label: "Under Revision", value: "Under Revision" },
    ],
    [],
  );

  const clearError = useCallback((field: string) => {
    setErrors((prev) => {
      if (!prev[field]) return prev;
      const copy = { ...prev };
      delete copy[field];
      return copy;
    });
  }, []);

  const validateForm = useCallback(() => {
    const newErrors: Record<string, string> = {};

    if (!formQuestionnaire?.name?.trim())
      newErrors.name = "Questionnaire name is required";

    if (!formQuestionnaire?.framework_id)
      newErrors.framework_id = "Framework is required";

    if (!formQuestionnaire?.type_id)
      newErrors.type_id = "Audit type is required";

    if (!isAuditorOnly && !formQuestionnaire?.status?.trim())
      newErrors.status = "Status is required";

    if (!formQuestionnaire?.version || Number(formQuestionnaire.version) < 1)
      newErrors.version = "Version must be at least 1";

    if (!formQuestionnaire?.target_duration)
      newErrors.target_duration = "Target duration is required";

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [formQuestionnaire, isAuditorOnly]);

  const backToQuestionnaire = useCallback(
    () => navigate("/questionnaire"),
    [navigate],
  );

  const handleQuestionnaireSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (loading) return;
      if (!validateForm()) return;

      const adjustedFormQuestionnaire = {
        ...formQuestionnaire,

        framework_id: toIntOrNull(formQuestionnaire.framework_id) ?? undefined,
        type_id: toIntOrNull(formQuestionnaire.type_id) ?? undefined,

        status: isAuditorOnly
          ? "Under Revision"
          : String(formQuestionnaire.status || "").trim(),

        target_duration: normalizeDuration(formQuestionnaire.target_duration),

        auditor_emails: (formQuestionnaire.auditors ?? [])
          .map((a: any) => a?.email)
          .filter(Boolean),
      };

      await addQuestionnaire(adjustedFormQuestionnaire, dispatch);
    },
    [dispatch, formQuestionnaire, isAuditorOnly, loading, validateForm],
  );
  useEffect(() => {
    dispatch(resetQuestioannairesState());
  }, [dispatch]);
  useEffect(() => {
    if (toast && !error) {
      const t = setTimeout(() => {
        dispatch(resetQuestioannairesState());
        navigate("/questionnaire");
      }, 800);

      return () => clearTimeout(t);
    }
  }, [toast, error, dispatch, navigate]);

  return (
    <div className="space-y-5">
      {/* <PageMeta
        title="Add Questionnaire"
        description="Create a new questionnaire"
      /> */}
      {/* <PageBreadcrumb pageTitle="Add Questionnaire" /> */}

      <div className="mx-auto my-4 max-w-5xl space-y-5">
        <div className="relative overflow-hidden rounded-2xl border border-[#b8d3e6] bg-gradient-to-r from-[#f5fbff] via-[#eef7ff] to-[#f8fcff] px-5 py-4 shadow-sm dark:border-[#0a5f95] dark:from-[#072f4a] dark:via-[#083857] dark:to-[#072f4a]">
          <div className="pointer-events-none absolute -right-5 -top-8 h-28 w-28 rounded-full bg-[#9bd6ff]/30 blur-2xl" />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="mb-1.5 inline-flex items-center gap-1.5 rounded-full border border-[#0a5f95]/20 bg-white/65 px-2.5 py-1 text-xs font-medium text-[#0a5f95] dark:border-[#7ec7ff]/25 dark:bg-[#0c4369]/55 dark:text-[#a9ddff]">
                <Sparkles className="h-3.5 w-3.5" />
                Questionnaire Setup
              </div>
              <h1 className="text-xl font-semibold text-[#064273] dark:text-[#e1f2ff]">
                Add Questionnaire
              </h1>
              <p className="mt-0.5 text-sm text-[#3b7395] dark:text-[#b9dcf2]">
                Configure framework, type, duration and assigned auditors.
              </p>
            </div>
            <Button
              onClick={backToQuestionnaire}
              variant="primary"
              startIcon={<ArrowLeft className="h-4 w-4" />}
              disabled={loading}
              className="px-5 py-2.5 rounded-lg text-white font-semibold transition bg-gradient-to-r from-[#064273] to-[#0E5B93] hover:from-[#05375f] hover:to-[#0A4A78] disabled:opacity-60 disabled:cursor-not-allowed"
            >
              Back to Questionnaire List
            </Button>
          </div>
        </div>

        <ComponentCard
          title="Questionnaire Details"
          desc="Fields marked with * are required."
          className="rounded-3xl border border-[#b8d3e6] bg-white/95 shadow-[0_16px_40px_rgba(6,66,115,0.08)] dark:border-[#0a5f95] dark:bg-[#072f4a]/80"
        >
          {toast && (
            <div
              className={`mb-4 rounded-lg px-4 py-3 text-sm ${
                error
                  ? "bg-red-50 text-red-700 border border-red-200"
                  : "bg-emerald-50 text-emerald-700 border border-emerald-200"
              }`}
            >
              {toast}
            </div>
          )}

          <form onSubmit={handleQuestionnaireSubmit} className="space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-[#064273]/20 bg-[#064273]/5 px-3 py-1 text-xs font-medium text-[#064273] dark:border-[#89cdfa]/25 dark:bg-[#0a5f95]/20 dark:text-[#b9dcf2]">
              <ClipboardList className="h-3.5 w-3.5" />
              Basic Information
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Name */}
              <div className={fieldCardClass}>
                <Label htmlFor="name">
                  Questionnaire Name <span className="text-red-500">*</span>
                </Label>
                <Input
                  disabled={loading}
                  type="text"
                  id="name"
                  value={formQuestionnaire.name}
                  onChange={(e: any) => {
                    clearError("name");
                    handleInputValue(e);
                  }}
                  name="name"
                  className={
                    errors.name ? "border-red-500" : "border-[#064273]/30"
                  }
                />
                {errors.name && (
                  <p className="text-sm text-red-500">{errors.name}</p>
                )}
              </div>

              {/* Framework */}
              <div className={fieldCardClass}>
                <Label>
                  Select Framework <span className="text-red-500">*</span>
                </Label>
                <Select
                  options={frameworkOptions}
                  disabled={loading}
                  onChange={(value: AnySelectValue) => {
                    clearError("framework_id");
                    handleSelectChange("framework_id", toIntOrNull(value));
                  }}
                />
                {errors.framework_id && (
                  <p className="text-sm text-red-500">{errors.framework_id}</p>
                )}
              </div>

              {/* Type */}
              <div className={`${fieldCardClass} md:col-span-2`}>
                <Label>
                  Select Audit Type <span className="text-red-500">*</span>
                </Label>
                <Select
                  options={auditTypeOptions}
                  placeholder="Select a Type"
                  disabled={loading}
                  onChange={(value: AnySelectValue) => {
                    clearError("type_id");
                    handleSelectChange("type_id", toIntOrNull(value));
                  }}
                  className="dark:bg-dark-900"
                />
                {errors.type_id && (
                  <p className="text-sm text-red-500">{errors.type_id}</p>
                )}
              </div>

              {/* Status */}
              {!isAuditorOnly ? (
                <div className={fieldCardClass}>
                  <Label htmlFor="status">
                    Status <span className="text-red-500">*</span>
                  </Label>
                  <Select
                    options={statusOptions}
                    disabled={loading}
                    onChange={(value: AnySelectValue) => {
                      clearError("status");
                      handleSelectChange("status", toStringOrEmpty(value));
                    }}
                  />
                  {errors.status && (
                    <p className="text-sm text-red-500">{errors.status}</p>
                  )}
                </div>
              ) : (
                <div className={fieldCardClass}>
                  <Label>Status</Label>
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    Under Revision (set automatically for auditor submissions)
                  </div>
                </div>
              )}

              {/* Version */}
              <div className={fieldCardClass}>
                <Label htmlFor="version">
                  Version <span className="text-red-500">*</span>
                </Label>
                <Input
                  disabled={loading}
                  type="number"
                  id="version"
                  placeholder="1"
                  min="1"
                  value={formQuestionnaire.version}
                  onChange={(e: any) => {
                    clearError("version");
                    handleInputValue(e);
                  }}
                  name="version"
                  className={
                    errors.version ? "border-red-500" : "border-[#064273]/30"
                  }
                />
                {errors.version && (
                  <p className="text-sm text-red-500">{errors.version}</p>
                )}
              </div>

              {/* Target Duration */}
              <div className={fieldCardClass}>
                <Label htmlFor="tm">
                  Target Duration Time <span className="text-red-500">*</span>
                </Label>
                <div className="relative">
                  <Input
                    disabled={loading}
                    type="time"
                    id="tm"
                    value={formQuestionnaire.target_duration}
                    onChange={(e: any) => {
                      clearError("target_duration");
                      handleInputValue(e);
                    }}
                    name="target_duration"
                    className={
                      errors.target_duration
                        ? "border-red-500"
                        : "border-[#064273]/30"
                    }
                  />
                  <span className="absolute text-gray-500 -translate-y-1/2 pointer-events-none right-3 top-1/2 dark:text-gray-400">
                    <TimeIcon className="size-6" />
                  </span>
                </div>
                {errors.target_duration && (
                  <p className="text-sm text-red-500">
                    {errors.target_duration}
                  </p>
                )}
              </div>

              {/* Auditors (optional) */}
              <div className={`${fieldCardClass} md:col-span-2`}>
                <MultiSelectAuditors
                  label="Auditors (optional)"
                  options={auditorOptions.map((a: any) => ({
                    value: String(a.value),
                    text: a.label,
                  }))}
                  defaultSelected={
                    formQuestionnaire?.auditors?.map((a: any) =>
                      String(a.id),
                    ) ?? []
                  }
                  onChange={(selectedIds) =>
                    handleMultiSelectInput("auditors", selectedIds)
                  }
                />
              </div>

              {/* Submit */}
              <div className="md:col-span-2 flex justify-end pt-2">
                <Button
                  disabled={loading}
                  className="px-5 py-2.5 rounded-lg text-white font-semibold transition bg-gradient-to-r from-[#064273] to-[#0E5B93] hover:from-[#05375f] hover:to-[#0A4A78] disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <span className="flex items-center gap-2">
                      <Spinner className="text-white" />
                      Saving...
                    </span>
                  ) : (
                    "Save Questionnaire"
                  )}
                </Button>
              </div>
            </div>
          </form>
        </ComponentCard>
      </div>
    </div>
  );
}
