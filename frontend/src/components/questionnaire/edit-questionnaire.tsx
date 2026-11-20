import { Modal } from "../ui/modal";
import Label from "../form/Label";
import Input from "../form/input/InputField";
import Select from "../form/Select";
import { TimeIcon, TrashBinIcon } from "../../icons";
import { Questionnaire } from "../../redux/questionnaire/questionnaire-slice-types";
import QuestionnaireInitialForm from "../initialForms/QuestionnaireInitialForm";
import { useEffect, useState } from "react";
import {
  getQuestionnaireById,
  updateQuestionnaire,
} from "../../redux/questionnaire/questionnaire";
import { useDispatch, useSelector } from "react-redux";
import MultiSelectAuditors from "../form/MultiSelectAuditors";
import Button from "../ui/button/Button";
import toast from "react-hot-toast";

interface EditQuestionnaireModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedQuestionnaire: Questionnaire | null;
  frameworkOptions: { label: string; value: string }[];
  auditTypeOptions: { label: string; value: string }[];
  auditorOptions: { label: string; value: string }[];
}

export default function EditQuestionnaireModal({
  isOpen,
  onClose,
  selectedQuestionnaire,
  frameworkOptions,
  auditTypeOptions,
  auditorOptions,
}: EditQuestionnaireModalProps) {
  const dispatch = useDispatch();
  const {
    formQuestionnaire,
    handleInputValue,
    handleSelectChange,
    setFormQuestionnaire,
    handleMultiSelectInput,
  } = QuestionnaireInitialForm();

  const { questionnaire } = useSelector((state: any) => state.questionnaire);
  const { user } = useSelector((state: any) => state.auth); // Get user from auth state
  const roles = useSelector((state: any) => state.auth.role || []);
  const normalizedRoles = roles.map((r: string) => String(r).trim().toLowerCase());
  const isAuditorOnly =
    normalizedRoles.includes("auditor") &&
    !normalizedRoles.some((r: string) =>
      ["admin", "quality_manager", "quality manager", "quality-manager"].includes(r),
    );

  // File upload state
  const [guidelineFile, setGuidelineFile] = useState<File | null>(null);
  const [removeGuideline, setRemoveGuideline] = useState(false);
  const [currentGuideline, setCurrentGuideline] = useState<any>(null);

  // Status options
  const statusOptions = [
    { label: "Ready to Use", value: "Ready to Use" },
    { label: "Under Revision", value: "Under Revision" },
  ];
  useEffect(() => {
    if (isOpen && selectedQuestionnaire?.id) {
      getQuestionnaireById(selectedQuestionnaire.id, dispatch);
    }
  }, [isOpen, selectedQuestionnaire?.id, dispatch]);

  useEffect(() => {
    if (questionnaire) {
      setFormQuestionnaire(questionnaire);
      // Set current guideline from API response
      if (questionnaire.guideline) {
        setCurrentGuideline(questionnaire.guideline);
      }
      // Reset file state
      setGuidelineFile(null);
      setRemoveGuideline(false);
    }
  }, [questionnaire, setFormQuestionnaire]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setGuidelineFile(file);
    setRemoveGuideline(false); // Reset remove flag when new file is selected
  };

  const handleRemoveGuideline = () => {
    setRemoveGuideline(true);
    setGuidelineFile(null);
    setCurrentGuideline(null);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + " KB";
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
  };

  const handleUpdateQuestionnaire = async (
    e: React.FormEvent<HTMLFormElement>,
  ) => {
    e.preventDefault();

    // Check if user is available
    if (!user || !user.id) {
      console.error("User not found in state");
      alert("Please log in again");
      return;
    }

    // Prepare data
    const adjustedFormQuestionnaire = {
      name: formQuestionnaire.name,
      status: isAuditorOnly ? "Under Revision" : formQuestionnaire.status,
      target_duration: formQuestionnaire.target_duration.endsWith(":00")
        ? formQuestionnaire.target_duration
        : formQuestionnaire.target_duration + ":00",
      type_id: formQuestionnaire.type_id
        ? Number(formQuestionnaire.type_id)
        : undefined,
      framework_id: formQuestionnaire.framework_id
        ? Number(formQuestionnaire.framework_id)
        : undefined,
      auditor_emails: formQuestionnaire.auditors.map((a) => a.email),
    };

    const result = await updateQuestionnaire(
      formQuestionnaire?.id,
      adjustedFormQuestionnaire,
      guidelineFile,
      removeGuideline,
      dispatch,
      user.id,
    );

    if (result.success) {
      toast.success(
        result.message ||
          (result.requiresApproval
            ? "Approval request sent to Quality Manager."
            : "Questionnaire updated successfully"),
      );
      onClose();
    } else {
      toast.error("Failed to update questionnaire");
    }
  };

  if (!selectedQuestionnaire) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      className="max-w-[820px] p-0 overflow-hidden rounded-2xl border border-indigo-100 dark:border-white/10"
    >
      <form className="flex max-h-[85vh] flex-col" onSubmit={handleUpdateQuestionnaire}>
        <div className="bg-gradient-to-r from-[#064273] to-[#0a5f95] px-6 py-5">
          <h5 className="mb-1 text-2xl font-semibold text-white">Edit Questionnaire</h5>
          <p className="text-sm text-indigo-100">
            Modify questionnaire details and guideline document.
          </p>
        </div>

        <div className="overflow-y-auto px-6 py-5 custom-scrollbar bg-gradient-to-br from-slate-50 via-indigo-50/20 to-white dark:from-gray-900 dark:to-gray-900">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* NAME */}
            <div className="space-y-2">
              <Label>Questionnaire Name</Label>
              <Input
                type="text"
                value={formQuestionnaire?.name}
                onChange={handleInputValue}
                name="name"
                className="border-indigo-200 focus:border-indigo-500"
              />
            </div>

            {/* FRAMEWORK */}
            <div className="space-y-2">
              <Label>Select Framework</Label>
              <Select
                options={frameworkOptions}
                defaultValue={formQuestionnaire?.framework_id}
                onChange={(e: any) => handleSelectChange("framework_id", e)}
              />
            </div>

            {/* STATUS */}
            {!isAuditorOnly ? (
              <div className="space-y-2">
                <Label className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide">
                  Status
                </Label>
                <Select
                  options={statusOptions}
                  defaultValue={formQuestionnaire?.status}
                  onChange={(value: string) =>
                    handleSelectChange("status", value)
                  }
                  className="h-11 border-gray-300 dark:border-gray-600 rounded-lg focus:border-[#064273] focus:ring-1 focus:ring-[#064273]"
                />
              </div>
            ) : (
              <div className="space-y-2">
                <Label className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide">
                  Status
                </Label>
                <div className="h-11 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                  Under Revision (set automatically for auditor submissions)
                </div>
              </div>
            )}

            {/* TYPE */}
            <div className="space-y-2">
              <Label>Select Type</Label>
              <Select
                options={auditTypeOptions}
                defaultValue={formQuestionnaire?.type_id || ""}
                onChange={(e: any) => handleSelectChange("type_id", e)}
              />
            </div>

            {/* TARGET TIME */}
            <div className="space-y-2">
              <Label>Target Duration</Label>
              <div className="relative">
                <Input
                  type="time"
                  value={formQuestionnaire?.target_duration}
                  onChange={handleInputValue}
                  name="target_duration"
                  className="border-indigo-200 focus:border-indigo-500"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2">
                  <TimeIcon className="size-6 text-gray-500" />
                </span>
              </div>
            </div>

            {/* FILE UPLOAD */}
            <div className="space-y-4 col-span-3 rounded-xl border border-indigo-100 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
              <Label>Upload Guideline File</Label>

              {/* Current Guideline Display */}
              {currentGuideline && !removeGuideline && (
                <div className="mb-3 p-3 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded-md">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <svg
                        className="w-5 h-5 text-indigo-500"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" />
                      </svg>
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {currentGuideline.filename}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {formatFileSize(currentGuideline.size)} • Uploaded{" "}
                          {currentGuideline.uploaded_at}
                        </p>
                      </div>
                    </div>
                    <div className="flex space-x-2">
                      {/* <a
                        href={currentGuideline.file_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 text-sm flex items-center gap-1"
                      >
                        <span>⬇️</span>
                        View
                      </a> */}
                      <button
                        type="button"
                        onClick={handleRemoveGuideline}
                        className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 text-sm flex items-center gap-1"
                      >
                        {" "}
                        <TrashBinIcon className="w-4 h-4" /> Remove{" "}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* File Input */}
              <div className="flex items-center justify-center w-full">
                <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-indigo-200 dark:border-indigo-800 border-dashed rounded-lg cursor-pointer bg-indigo-50/40 dark:bg-gray-800 hover:bg-indigo-50 dark:hover:bg-gray-700">
                  <div className="flex flex-col items-center justify-center pt-5 pb-6">
                    <svg
                      className="w-8 h-8 mb-3 text-gray-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                      />
                    </svg>
                    <p className="mb-2 text-sm text-gray-500 dark:text-gray-400">
                      <span className="font-semibold">Click to upload</span> or
                      drag and drop
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      PDF, DOC, DOCX, XLS, XLSX (Max 10MB)
                    </p>
                  </div>
                  <input
                    type="file"
                    onChange={handleFileChange}
                    accept=".pdf,.doc,.docx,.xls,.xlsx"
                    className="hidden"
                  />
                </label>
              </div>

              {/* Selected New File Display */}
              {guidelineFile && (
                <div className="mt-3 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <svg
                        className="w-5 h-5 text-green-500"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" />
                      </svg>
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {guidelineFile.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {formatFileSize(guidelineFile.size)} • Ready to upload
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setGuidelineFile(null)}
                      className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 text-sm"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* AUDITORS */}
            <div className="space-y-4 col-span-3 rounded-xl border border-indigo-100 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
              <MultiSelectAuditors
                label="Auditors"
                options={auditorOptions.map((a) => ({
                  value: String(a.value),
                  text: a.label,
                }))}
                defaultSelected={
                  formQuestionnaire?.auditors?.map((a) => String(a.id)) ?? []
                }
                onChange={(selectedIds) =>
                  handleMultiSelectInput("auditors", selectedIds)
                }
              />
            </div>
          </div>
        </div>

        {/* FOOTER */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-indigo-100 bg-white dark:border-white/10 dark:bg-gray-900">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
          >
            Close
          </button>

          <Button className="px-4 py-2 rounded-lg text-white bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-700 hover:to-indigo-600">
            Update Questionnaire
          </Button>
        </div>
      </form>
    </Modal>
  );
}
