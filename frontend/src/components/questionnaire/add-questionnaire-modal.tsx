import { useCallback, useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import toast from "react-hot-toast";
import { Modal } from "../ui/modal";
import Label from "../form/Label";
import Input from "../form/input/InputField";
import Select from "../form/Select";
import MultiSelectAuditors from "../form/MultiSelectAuditors";
import Button from "../ui/button/Button";
import { Spinner } from "../common/Spinner";
import { TimeIcon } from "../../icons";
import QuestionnaireInitialForm from "../initialForms/QuestionnaireInitialForm";
import { addQuestionnaire } from "../../redux/questionnaire/questionnaire";
import { resetQuestioannairesState } from "../../redux/questionnaire/questionnaire-slice";
import { Questionnaire } from "../../redux/questionnaire/questionnaire-slice-types";

interface AddQuestionnaireModalProps {
  isOpen: boolean;
  onClose: () => void;
  frameworkOptions: { label: string; value: string }[];
  auditTypeOptions: { label: string; value: string }[];
  auditorOptions: { label: string; value: string }[];
}

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

const normalizeDuration = (t?: string) => {
  if (!t) return "";
  if (/^\d{2}:\d{2}$/.test(t)) return `${t}:00`;
  if (/^\d{2}:\d{2}:\d{2}$/.test(t)) return t;
  return t;
};

const getDefaultQuestionnaireForm = (): Questionnaire =>
  ({
    id: 0,
    name: "",
    version: 1,
    status: "Under Revision",
    target_duration: "",
    score_calculation: "",
    guideline_file: "",
    type_id: "",
    framework_id: "",
    framework: {
      id: "",
      label: "",
      code: "",
    },
    auditors: [],
    questions: [],
  }) as Questionnaire;

export default function AddQuestionnaireModal({
  isOpen,
  onClose,
  frameworkOptions,
  auditTypeOptions,
  auditorOptions,
}: AddQuestionnaireModalProps) {
  const dispatch = useDispatch();
  const {
    formQuestionnaire,
    handleInputValue,
    handleSelectChange,
    handleMultiSelectInput,
    setFormQuestionnaire,
  } = QuestionnaireInitialForm();

  const { toast: feedback, loading, error } = useSelector(
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
    if (!formQuestionnaire?.type_id) newErrors.type_id = "Audit type is required";
    if (!isAuditorOnly && !formQuestionnaire?.status?.trim()) {
      newErrors.status = "Status is required";
    }
    if (!formQuestionnaire?.version || Number(formQuestionnaire.version) < 1)
      newErrors.version = "Version must be at least 1";
    if (!formQuestionnaire?.target_duration)
      newErrors.target_duration = "Target duration is required";

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [formQuestionnaire, isAuditorOnly]);

  const handleSubmit = useCallback(
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

  const handleModalClose = useCallback(() => {
    if (loading) return;
    setErrors({});
    setFormQuestionnaire(getDefaultQuestionnaireForm());
    dispatch(resetQuestioannairesState());
    onClose();
  }, [dispatch, loading, onClose, setFormQuestionnaire]);

  useEffect(() => {
    if (!isOpen) return;
    setErrors({});
    setFormQuestionnaire(getDefaultQuestionnaireForm());
    dispatch(resetQuestioannairesState());
  }, [dispatch, isOpen, setFormQuestionnaire]);

  useEffect(() => {
    if (!isOpen) return;
    if (feedback && !error) {
      toast.success(feedback);
      handleModalClose();
    }
  }, [feedback, error, handleModalClose, isOpen]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleModalClose}
      className="max-w-[920px] p-0 overflow-hidden rounded-2xl border border-[#064273]/20 dark:border-white/10"
    >
      <form className="flex max-h-[88vh] flex-col" onSubmit={handleSubmit}>
        <div className="bg-gradient-to-r from-[#064273] to-[#0a5f95] px-6 py-5">
          <h5 className="mb-1 text-2xl font-semibold text-white">
            Add Questionnaire
          </h5>
          <p className="text-sm text-blue-100">
            Configure framework, type, duration and assigned auditors.
          </p>
        </div>

        <div className="overflow-y-auto px-6 py-5 custom-scrollbar bg-gradient-to-br from-slate-50 via-blue-50/20 to-white dark:from-gray-900 dark:to-gray-900">
          {feedback && (
            <div
              className={`mb-4 rounded-lg px-4 py-3 text-sm ${
                error
                  ? "bg-red-50 text-red-700 border border-red-200"
                  : "bg-emerald-50 text-emerald-700 border border-emerald-200"
              }`}
            >
              {feedback}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
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
                className={errors.name ? "border-red-500" : "border-[#064273]/30"}
              />
              {errors.name && <p className="text-sm text-red-500">{errors.name}</p>}
            </div>

            <div className="space-y-2">
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

            <div className="space-y-2 md:col-span-2">
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
              />
              {errors.type_id && <p className="text-sm text-red-500">{errors.type_id}</p>}
            </div>

            {!isAuditorOnly ? (
              <div className="space-y-2">
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
                {errors.status && <p className="text-sm text-red-500">{errors.status}</p>}
              </div>
            ) : (
              <div className="space-y-2">
                <Label>Status</Label>
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                  Under Revision (set automatically for auditor submissions)
                </div>
              </div>
            )}

            <div className="space-y-2">
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
                className={errors.version ? "border-red-500" : "border-[#064273]/30"}
              />
              {errors.version && (
                <p className="text-sm text-red-500">{errors.version}</p>
              )}
            </div>

            <div className="space-y-2">
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
                    errors.target_duration ? "border-red-500" : "border-[#064273]/30"
                  }
                />
                <span className="absolute text-gray-500 -translate-y-1/2 pointer-events-none right-3 top-1/2 dark:text-gray-400">
                  <TimeIcon className="size-6" />
                </span>
              </div>
              {errors.target_duration && (
                <p className="text-sm text-red-500">{errors.target_duration}</p>
              )}
            </div>

            <div className="space-y-2 md:col-span-2 rounded-xl border border-[#064273]/15 bg-[#064273]/5 p-4">
              <MultiSelectAuditors
                label="Auditors (optional)"
                options={auditorOptions.map((a: any) => ({
                  value: String(a.value),
                  text: a.label,
                }))}
                defaultSelected={
                  formQuestionnaire?.auditors?.map((a: any) => String(a.id)) ?? []
                }
                onChange={(selectedIds) =>
                  handleMultiSelectInput("auditors", selectedIds)
                }
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-[#064273]/15 bg-white dark:border-white/10 dark:bg-gray-900">
          <button
            type="button"
            onClick={handleModalClose}
            className="px-4 py-2 rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
          >
            Cancel
          </button>
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
      </form>
    </Modal>
  );
}
