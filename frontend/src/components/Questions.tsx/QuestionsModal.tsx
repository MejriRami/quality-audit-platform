import { Modal } from "../ui/modal";
import { useState, useEffect } from "react";
import { useSelector } from "react-redux";
import toast from "react-hot-toast";
import { useNavigate } from "react-router";
import ConfirmDialog from "../form/ConfirmDialogProps";
import { Question } from "../../types";
import {
  createQuestion,
  deleteQuestion,
  updateQuestion,
} from "../../api/questions";
import { Questionnaire } from "../../redux/questionnaire/questionnaire-slice-types";
import { RootState } from "../../redux/store";
import {
  hasAuditorRole,
  hasQualityManagerRole,
  hasSystemAdminRole,
} from "../../utils/roleAccess";

interface QuestionsModalProps {
  isOpen: boolean;
  onClose: () => void;
  questionnaire: Questionnaire | null;
  onRequestSubmitted?: (requestId: number) => void | Promise<void>;
}

type PendingApprovalResponse = {
  message: string;
  requires_approval: boolean;
  request_id: number;
};

const isPendingApprovalResponse = (
  value: unknown,
): value is PendingApprovalResponse =>
  Boolean(
    value &&
      typeof value === "object" &&
      "requires_approval" in value &&
      (value as { requires_approval?: unknown }).requires_approval === true,
  );

export default function QuestionsModal({
  isOpen,
  onClose,
  questionnaire,
  onRequestSubmitted,
}: QuestionsModalProps) {
  const navigate = useNavigate();
  const roles = useSelector((s: RootState) => s.auth.role || []);
  const currentUser = useSelector((s: RootState) => s.auth.user);
  const canDirectManageQuestions =
    hasSystemAdminRole(roles) || hasQualityManagerRole(roles);
  const questionnaireStatus = String(questionnaire?.status || "")
    .trim()
    .toLowerCase();
  const isRestrictedAuditor =
    hasAuditorRole(roles) && !canDirectManageQuestions;
  const isOwnedDraft =
    questionnaireStatus === "under revision" &&
    questionnaire?.created_by === currentUser?.id;
  const canRequestReadyToUseChanges =
    isRestrictedAuditor &&
    questionnaireStatus === "ready to use";
  const canRequestNewQuestion =
    isRestrictedAuditor && (isOwnedDraft || canRequestReadyToUseChanges);
  const canAddNewQuestion = canDirectManageQuestions || canRequestNewQuestion;
  const canEditDraft =
    canDirectManageQuestions || isOwnedDraft || canRequestReadyToUseChanges;
  const mutationMode = canRequestNewQuestion ? "request" : "direct";

  const isPlantManagerIatf = Boolean(
    questionnaire?.name?.toLowerCase().includes("plant manager") &&
      questionnaire?.name?.toLowerCase().includes("iatf"),
  );
  const [localQuestions, setLocalQuestions] = useState<Question[]>(
    questionnaire?.questions || []
  );

  useEffect(() => {
    setLocalQuestions(questionnaire?.questions || []);
  }, [questionnaire]);

  const [editRowId, setEditRowId] = useState<number | null>(null);
  const [editedRow, setEditedRow] = useState<Partial<Question>>({});
  const [isAdding, setIsAdding] = useState(false);
  const [newQuestion, setNewQuestion] = useState<Partial<Question>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastSubmittedRequestId, setLastSubmittedRequestId] = useState<
    number | null
  >(null);

  /* UPDATE INPUT */
  const handleInputChange = (e: any) => {
    const { name } = e.target;
    let { value } = e.target;
    if (name === "weight" && isPlantManagerIatf) {
      value = String(value === "" ? "" : Math.max(0, Math.min(1, Number(value))));
    }
    setEditedRow((prev) => ({ ...prev, [name]: value }));
  };

  const handleNewInputChange = (e: any) => {
    const { name } = e.target;
    let { value } = e.target;
    if (name === "weight" && isPlantManagerIatf) {
      value = String(value === "" ? "" : Math.max(0, Math.min(1, Number(value))));
    }
    setNewQuestion((prev) => ({ ...prev, [name]: value }));
  };

  /* EDIT QUESTION */
  const handleEdit = (row: Question) => {
    setEditRowId(row.id);
    setEditedRow(row);
  };

  const handleSave = async () => {
    if (!questionnaire || !editRowId || !canEditDraft || isSubmitting) return;

    try {
      setIsSubmitting(true);
      const result = await updateQuestion(editRowId, editedRow);
      if (isPendingApprovalResponse(result)) {
        setLastSubmittedRequestId(result.request_id);
        await onRequestSubmitted?.(result.request_id);
        toast.success(result.message || "Change request submitted for review.");
        setEditRowId(null);
        setEditedRow({});
        return;
      }
      setLocalQuestions((prev) =>
        prev.map((q) => (q.id === editRowId ? { ...q, ...editedRow } : q))
      );
      toast.success("Question updated successfully.");

      setEditRowId(null);
      setEditedRow({});
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update question.";
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    setEditRowId(null);
    setEditedRow({});
  };

  /* ADD NEW QUESTION */
  const handleAddNew = () => {
    if (!canAddNewQuestion) return;
    setIsAdding(true);
    setNewQuestion({
      description: "",
      chapter: "",
      weight: 0,
      critical_value: 0,
    });
  };

  const handleSaveNew = async () => {
    if (!questionnaire || !canAddNewQuestion || isSubmitting) return;

    try {
      setIsSubmitting(true);
      const created = await createQuestion(newQuestion, questionnaire.id);
      if (isPendingApprovalResponse(created)) {
        setLastSubmittedRequestId(created.request_id);
        await onRequestSubmitted?.(created.request_id);
        toast.success(created.message || "Question creation request submitted.");
        setIsAdding(false);
        setNewQuestion({});
        return;
      }
      const createdQuestion = created as Question;

      setLocalQuestions((prev) => [...prev, createdQuestion]);
      toast.success("Question added successfully.");

      setIsAdding(false);
      setNewQuestion({});
    } catch (err: any) {
      toast.error(err?.message || "Failed to create question.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancelNew = () => {
    setIsAdding(false);
    setNewQuestion({});
  };

  /* DELETE QUESTION */
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);

  const handleDeleteClick = (id: number) => {
    setDeleteId(id);
    setIsConfirmOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!deleteId || !canEditDraft || isSubmitting) return;

    try {
      setIsSubmitting(true);
      const result = await deleteQuestion(deleteId);
      if (isPendingApprovalResponse(result)) {
        setLastSubmittedRequestId(result.request_id);
        await onRequestSubmitted?.(result.request_id);
        toast.success(result.message || "Question deletion request submitted.");
        setDeleteId(null);
        setIsConfirmOpen(false);
        return;
      }
      setLocalQuestions((prev) => prev.filter((q) => q.id !== deleteId));

      if (editRowId === deleteId) {
        setEditRowId(null);
        setEditedRow({});
      }

      setDeleteId(null);
      setIsConfirmOpen(false);
      toast.success("Question deleted successfully.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete question.";
      toast.error(message);
      setIsConfirmOpen(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancelDelete = () => {
    setDeleteId(null);
    setIsConfirmOpen(false);
  };

  const handleViewSubmittedRequest = () => {
    if (!lastSubmittedRequestId) return;
    onClose();
    navigate(
      `/questionnaire?tab=requests&request_id=${lastSubmittedRequestId}&status=pending`,
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      className="!max-w-[96vw] !w-full !h-[92vh] !p-0 !m-0"
    >
      <div className="flex flex-col h-[92vh] w-full">
        {/* Header - Fixed */}
        <div className="px-8 py-6 border-b border-[#064273]/20 bg-gradient-to-r from-[#064273] via-[#0A4A78] to-[#0E5B93] flex-shrink-0">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-2xl font-bold text-white mb-1">
                {questionnaire?.name || "Questionnaire Details"}
              </h2>
              <p className="text-sm text-blue-100/90">
                Manage your questions with ease
              </p>
            </div>
          </div>

          {/* Meta Info - Compact Pills */}
          <div className="flex gap-3 flex-wrap items-center">
            {isRestrictedAuditor && (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-amber-400/20 rounded-full border border-amber-200/40">
                <span className="text-xs font-semibold text-amber-100">
                  {isOwnedDraft
                    ? "Auditor draft mode: you can edit this Under Revision checklist before submitting."
                    : canRequestReadyToUseChanges
                      ? "Auditor request mode: your question changes will be submitted to Quality Manager for approval."
                    : "Read only: this checklist is not your editable Under Revision draft."}
                </span>
              </div>
            )}
            {lastSubmittedRequestId && (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-emerald-300/20 rounded-full border border-emerald-100/40">
                <span className="text-xs font-semibold text-emerald-100">
                  Request #{lastSubmittedRequestId} submitted for Quality Manager review.
                </span>
                <button
                  type="button"
                  onClick={handleViewSubmittedRequest}
                  className="rounded bg-white/95 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 hover:bg-white"
                >
                  View Request
                </button>
              </div>
            )}
            {/* Status Section */}
            <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-white/12 rounded-full border border-white/25">
              <span className="text-xs font-medium text-blue-100">
                Status:
              </span>
              <span className="text-xs font-semibold text-white">
                {questionnaire?.status || "N/A"}
              </span>
            </div>

            {/* Framework Section */}
            <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-white/12 rounded-full border border-white/25">
              <span className="text-xs font-medium text-blue-100">
                Framework:
              </span>
              <span className="text-xs font-semibold text-white">
                {questionnaire?.framework?.label.toUpperCase() || "N/A"}
              </span>
            </div>

            {/* Type Section */}
            <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-white/12 rounded-full border border-white/25">
              <span className="text-xs font-medium text-blue-100">
                Type:
              </span>
              <span className="text-xs font-semibold text-white">
                {questionnaire?.auditType?.value || "N/A"}
              </span>
            </div>

            {/* New Question Button */}
            <div className="ml-auto">
              <button
                onClick={handleAddNew}
                disabled={!canAddNewQuestion}
                className="px-5 py-2.5 text-sm font-semibold text-[#064273] rounded-lg 
               bg-white hover:bg-slate-100 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500
               transition-all duration-200 flex items-center gap-2 shadow-sm"
              >
                <span className="text-lg font-bold">+</span>
                {mutationMode === "request" ? "Request New Question" : "New Question"}
              </button>
            </div>
          </div>
        </div>

        {/* Table Container - Scrollable */}
        <div
          className="flex-1 bg-white dark:bg-gray-950 p-6 overflow-y-auto"
          style={{ minHeight: 0 }}
        >
          <div className="bg-white dark:bg-gray-900 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead className="sticky top-0 z-10">
                  <tr className="bg-[#f6f7fb] dark:bg-gray-800">
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b-2 border-gray-200 dark:border-gray-700 w-[45%]">
                      Question
                    </th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b-2 border-gray-200 dark:border-gray-700 w-[20%]">
                      Chapter
                    </th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b-2 border-gray-200 dark:border-gray-700 w-[12%]">
                      {isPlantManagerIatf ? "Mandatory (0/1)" : "Weight"}
                    </th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b-2 border-gray-200 dark:border-gray-700 w-[12%]">
                      Critical
                    </th>
                    <th className="text-center px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b-2 border-gray-200 dark:border-gray-700 w-[11%]">
                      Actions
                    </th>
                  </tr>
                </thead>

                <tbody className="bg-white dark:bg-gray-900">
                  {isAdding && (
                    <tr className="border-b border-gray-100 dark:border-gray-800 bg-blue-50/30 dark:bg-blue-900/10 group">
                      <td className="px-6 py-4">
                        <textarea
                          name="description"
                          value={newQuestion.description || ""}
                          onChange={handleNewInputChange}
                          placeholder="Type your question here..."
                          className="w-full min-h-[100px] border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2.5 text-sm
                                   focus:border-[#064273] focus:ring-1 focus:ring-[#064273] focus:outline-none
                                   dark:bg-gray-800 dark:text-white resize-none"
                          required
                        />
                      </td>

                      <td className="px-6 py-4">
                        <input
                          name="chapter"
                          value={newQuestion.chapter || ""}
                          onChange={handleNewInputChange}
                          placeholder="Enter chapter"
                          className="w-full h-[44px] border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2.5 text-sm
                                   focus:border-[#064273] focus:ring-1 focus:ring-[#064273] focus:outline-none
                                   dark:bg-gray-800 dark:text-white"
                        />
                      </td>

                      <td className="px-6 py-4">
                        <input
                          type="number"
                          name="weight"
                          value={newQuestion.weight}
                          onChange={handleNewInputChange}
                          placeholder="0"
                          className="w-full h-[44px] border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2.5 text-sm
                                   focus:border-[#064273] focus:ring-1 focus:ring-[#064273] focus:outline-none
                                  dark:bg-gray-800 dark:text-white"
                          min={0}
                          max={isPlantManagerIatf ? 1 : undefined}
                          step={1}
                        />
                      </td>

                      <td className="px-6 py-4">
                        <input
                          type="number"
                          name="critical_value"
                          value={newQuestion.critical_value ?? ""}
                          onChange={handleNewInputChange}
                          placeholder="0"
                          className="w-full h-[44px] border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2.5 text-sm
                                   focus:border-[#064273] focus:ring-1 focus:ring-[#064273] focus:outline-none
                                   dark:bg-gray-800 dark:text-white"
                          min={0}
                        />
                      </td>

                      <td className="px-6 py-4">
                        <div className="flex gap-2 justify-center">
                          <button
                            onClick={handleSaveNew}
                            disabled={!newQuestion.description?.trim() || isSubmitting}
                            className={`px-4 py-2 rounded-md text-xs font-medium transition-all
                              ${
                                newQuestion.description?.trim() && !isSubmitting
                                  ? "bg-[#064273] text-white hover:bg-[#05375f]"
                                  : "bg-gray-200 text-gray-400 cursor-not-allowed"
                              }
                            `}
                          >
                            {isSubmitting ? "Saving..." : "Save"}
                          </button>

                          <button
                            onClick={handleCancelNew}
                            className="px-4 py-2 rounded-md text-xs font-medium bg-gray-100 dark:bg-gray-700 
                                     text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 
                                     transition-all"
                          >
                            Cancel
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}

                  {localQuestions?.length ? (
                    localQuestions?.map((q, index) => (
                      <tr
                        key={q.id}
                        className={`border-b border-gray-100 dark:border-gray-800 group hover:bg-[#f4f9ff] dark:hover:bg-gray-800/50 transition-colors
                          ${
                            index % 2 === 0
                              ? "bg-white dark:bg-gray-900"
                              : "bg-gray-50/30 dark:bg-gray-900/50"
                          }`}
                      >
                        <td className="px-6 py-5">
                          {editRowId === q.id ? (
                            <textarea
                              name="description"
                              value={editedRow.description || ""}
                              onChange={handleInputChange}
                              className="w-full min-h-[100px] border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2.5 text-sm
                                       focus:border-[#064273] focus:ring-1 focus:ring-[#064273] focus:outline-none
                                       dark:bg-gray-800 dark:text-white resize-none"
                            />
                          ) : (
                            <div className="text-sm text-gray-900 dark:text-gray-100 leading-relaxed whitespace-pre-wrap break-words py-1">
                              {q.description}
                            </div>
                          )}
                        </td>

                        <td className="px-6 py-5">
                          {editRowId === q.id ? (
                            <input
                              name="chapter"
                              value={editedRow.chapter || ""}
                              onChange={handleInputChange}
                              className="w-full h-[44px] border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2.5 text-sm
                                       focus:border-[#064273] focus:ring-1 focus:ring-[#064273] focus:outline-none
                                       dark:bg-gray-800 dark:text-white"
                            />
                          ) : (
                            <div className="text-sm text-gray-700 dark:text-gray-300 py-1">
                              {q.chapter || "-"}
                            </div>
                          )}
                        </td>

                        <td className="px-6 py-5">
                          {editRowId === q.id ? (
                            <input
                              type="number"
                              name="weight"
                              value={editedRow.weight ?? ""}
                              onChange={handleInputChange}
                              className="w-full h-[44px] border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2.5 text-sm
                                       focus:border-[#064273] focus:ring-1 focus:ring-[#064273] focus:outline-none
                                       dark:bg-gray-800 dark:text-white"
                              min={0}
                              max={isPlantManagerIatf ? 1 : undefined}
                              step={1}
                            />
                          ) : (
                            <div className="text-sm font-medium text-gray-700 dark:text-gray-300 py-1">
                              {isPlantManagerIatf
                                ? q.weight === 1
                                  ? "Mandatory"
                                  : "Non-mandatory"
                                : q.weight}
                            </div>
                          )}
                        </td>

                        <td className="px-6 py-5">
                          {editRowId === q.id ? (
                            <input
                              type="number"
                              name="critical_value"
                              value={editedRow.critical_value ?? ""}
                              onChange={handleInputChange}
                              className="w-full h-[44px] border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2.5 text-sm
                                       focus:border-[#064273] focus:ring-1 focus:ring-[#064273] focus:outline-none
                                       dark:bg-gray-800 dark:text-white"
                              min={0}
                            />
                          ) : (
                            <div className="text-sm font-medium text-gray-700 dark:text-gray-300 py-1">
                              {q.critical_value}
                            </div>
                          )}
                        </td>

                        <td className="px-6 py-5">
                          {editRowId === q.id ? (
                            <div className="flex gap-2 justify-center">
                              <button
                                onClick={handleSave}
                                disabled={isSubmitting}
                                className="px-4 py-2 rounded-md text-xs font-medium bg-[#064273] text-white 
                                         hover:bg-[#05375f] transition-all disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                {isSubmitting ? "Updating..." : "Update"}
                              </button>
                              <button
                                onClick={handleCancel}
                                className="px-4 py-2 rounded-md text-xs font-medium bg-gray-100 dark:bg-gray-700 
                                         text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 
                                         transition-all"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div className="flex gap-2 justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                              <button
                                onClick={() => handleEdit(q)}
                                disabled={!canEditDraft}
                                className="px-3 py-1.5 rounded text-xs font-medium text-[#064273] hover:bg-[#064273]/10 dark:hover:bg-[#064273]/20 transition-all"
                                title="Edit"
                              >
                                <svg
                                  className="w-4 h-4"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                                  />
                                </svg>
                              </button>
                              <button
                                onClick={() => handleDeleteClick(q.id)}
                                disabled={!canEditDraft}
                                className="px-3 py-1.5 rounded text-xs font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                                title="Delete"
                              >
                                <svg
                                  className="w-4 h-4"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                                  />
                                </svg>
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="px-6 py-20 text-center">
                        <div className="flex flex-col items-center justify-center text-gray-400 dark:text-gray-600">
                          <svg
                            className="w-16 h-16 mb-4 opacity-50"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={1.5}
                              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                            />
                          </svg>
                          <p className="text-lg font-medium mb-1">
                            No questions yet
                          </p>
                          <p className="text-sm">
                            {canAddNewQuestion
                              ? mutationMode === "request"
                                ? 'Click "Request New Question" to submit a proposed question for approval'
                                : 'Click "New Question" to add your first question'
                              : "Your role can view this checklist, but cannot create new questions here"}
                          </p>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Footer - Fixed */}
        <div className="px-8 py-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 flex justify-end flex-shrink-0">
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="px-6 py-2.5 text-sm font-medium border border-gray-300 dark:border-gray-600 rounded-lg 
                     bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300
                     hover:bg-gray-50 dark:hover:bg-gray-700 transition-all disabled:cursor-not-allowed disabled:opacity-60"
          >
            Close
          </button>
        </div>
      </div>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Question"
        message="Are you sure you want to delete this question?"
        confirmText="Yes, Delete"
        cancelText="Cancel"
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelDelete}
      />
    </Modal>
  );
}
