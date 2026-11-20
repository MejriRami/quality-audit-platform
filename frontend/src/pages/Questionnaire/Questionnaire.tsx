import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { useDispatch, useSelector } from "react-redux";
import {
  deleteQuestionnaire,
  getQuestionnaires,
} from "../../redux/questionnaire/questionnaire";
import {
  Questionnaire,
  GuidelineDocument,
} from "../../redux/questionnaire/questionnaire-slice-types";
import ConfirmDialog from "../../components/form/ConfirmDialogProps";
import EditQuestionnaireModal from "../../components/questionnaire/edit-questionnaire";
import { getFrameworks } from "../../redux/framework/framework";
import Enum from "../../components/enum/Enum";
import {
  clearDeleteState,
  resetQuestioannairesState,
} from "../../redux/questionnaire/questionnaire-slice";
import QuestionsModal from "../../components/Questions.tsx/QuestionsModal";
import toast from "react-hot-toast";
import GuidelineViewerModal from "./GuidelineViewerModal";
import axiosInstance from "../../services/axiosInstance";
import AddQuestionnaireModal from "../../components/questionnaire/add-questionnaire-modal";
import { useWebSocket, WebSocketMessage } from "../../hooks/useWebsocket";
import {
  canManageQuestionnaires,
  hasAuditorRole,
  hasQualityManagerRole,
  hasSystemAdminRole,
} from "../../utils/roleAccess";

type RequestStatus = "pending" | "approved" | "rejected";
type QuestionnairePageTab = "questionnaires" | "requests";
type ScoreFormulaMeta = {
  label: string;
  formula: string;
  explanation: string;
  details?: string[];
};

type RequestQuestionPreview = {
  id?: number;
  description?: string;
  chapter?: string;
  weight?: number;
  critical_value?: number;
};

type RequestQuestionnaireContext = {
  id?: number | null;
  name?: string | null;
  version?: number | null;
  status?: string | null;
  target_duration?: string | null;
  framework?: {
    id?: number | null;
    code?: string | null;
    label?: string | null;
  } | null;
  audit_type?: {
    id?: number | null;
    value?: string | null;
  } | null;
  auditor_emails?: string[];
  questions_count?: number | null;
  questions_preview?: RequestQuestionPreview[];
};

type ChangeRequestItem = {
  id: number;
  entity_type: string;
  action_type: string;
  status: RequestStatus | string;
  status_label?: string;
  summary?: string;
  questionnaire_id?: number | null;
  target_id?: number | null;
  payload?: Record<string, any> | null;
  questionnaire_context?: RequestQuestionnaireContext | null;
  request_comment?: string | null;
  review_comment?: string | null;
  created_at?: string | null;
  reviewed_at?: string | null;
  applied_at?: string | null;
  requested_by?: { id?: number; email?: string | null; name?: string | null };
  reviewed_by?: {
    id?: number;
    email?: string | null;
    name?: string | null;
  } | null;
};

const scoreFormulaCatalog: Record<string, ScoreFormulaMeta> = {
  iatfpm: {
    label: "IATF PM",
    formula: "(100*Pass + 50*Improve) / (Pass + Improve + Fail)",
    explanation: "Plant Manager IATF value mode with weighted score.",
    details: [
      "Value triage in execution: 1-2 = Fail, 3 = Improve, 4-5 = Pass.",
      "Mandatory questions (weight=1) cannot be answered as optional.",
      // "Final rating bands: A >= 80, B >= 60, C >= 50, D < 50.",
    ],
  },
  internal: {
    label: "Internal",
    formula: "(100*Pass + 50*Improve) / (Pass + Improve + Fail)",
    explanation:
      "Same weighted formula used for internal audits to balance pass and improvement findings.",
    // details: ["Final rating bands: A >= 80, B >= 60, C >= 50, D < 50."],
  },
  open: {
    label: "Open audit",
    formula: "(100*Conformity + 50*Observation) / (all answered questions)",
    explanation:
      "No fixed questions: the auditor types each question and answer and marks it Conformity, Observation or Nonconformity.",
  },
  legacystandard: {
    label: "Legacy Standard",
    formula: "(100*Pass + 50*Improve) / (Pass + Improve + Fail)",
    explanation:
      "Legacy fallback profile using the weighted pass/improve/fail scoring method.",
    details: ["Score is computed on a 0..100 scale from pass/improve/fail."],
  },
  iatfclassification: {
    label: "IATF Classification",
    formula: "max(0, 100 - (20*MajorNC + 8*MinorNC + 2*OFI))",
    explanation:
      "Severity-weighted demerit model that reduces score based on nonconformity severity.",
    details: [
      "Demerits are based on Major NC, Minor NC, and OFI counts.",
      "Score is clamped to 0..100 after demerits.",
      // "Final rating bands: A >= 80, B >= 60, C >= 50, D < 50.",
    ],
  },
  isosystem: {
    label: "ISO System",
    formula: "max(0, 100 - (20*MajorNC + 8*MinorNC + 2*OFI))",
    explanation:
      "ISO profile uses severity demerits to penalize major/minor findings and improvement items.",
    details: [
      "Demerits are based on Major NC, Minor NC, and OFI counts.",
      "Score is clamped to 0..100 after demerits.",
      // "Final rating bands: A >= 80, B >= 60, C >= 50, D < 50.",
    ],
  },
  vdaprocess: {
    label: "VDA Process",
    formula: "(sum(question_scores) / (10 * applicable_questions)) * 100",
    explanation: "Dedicated VDA EG% model computed from VDA question scores.",
    details: [
      "Accepted VDA scores: 0, 4, 6, 8, 10.",
      "VDA EG% rating: A >= 90, B >= 80, C < 80.",
      "Asterisk rules: score 0 forces C; score 4 blocks A (max B).",
    ],
  },
};

const scoreKeyAliases: Record<string, string> = {
  fs1: "iatfpm",
  fs2: "iatfpm",
  fs3: "iatfclassification",
  fs4: "legacystandard",
  vda: "vdaprocess",
  vda63: "vdaprocess",
  "vda6.3": "vdaprocess",
  iatfnc: "iatfclassification",
};

export default function FormElements() {
  const dispatch = useDispatch();
  const { questionnairesList } = useSelector(
    (state: any) => state.questionnaire,
  );

  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const { frameworkOptions, auditTypeOptions, auditorOptions } = Enum();
  const [selectedQuestionnaire, setSelectedQuestionnaire] =
    useState<Questionnaire>({} as Questionnaire);
  const [isModalOpenQuestions, setIsModalOpenQuestions] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    new Set(),
  );
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Guideline viewer state
  const [isGuidelineViewerOpen, setIsGuidelineViewerOpen] = useState(false);
  const [selectedGuideline, setSelectedGuideline] =
    useState<GuidelineDocument | null>(null);

  // Guideline delete state
  const [isDeleteGuidelineOpen, setIsDeleteGuidelineOpen] = useState(false);
  const [guidelineToDelete, setGuidelineToDelete] = useState<{
    questionnaireId: number;
    guideline: GuidelineDocument;
  } | null>(null);
  const [deletingGuideline, setDeletingGuideline] = useState(false);
  const [changeRequests, setChangeRequests] = useState<ChangeRequestItem[]>([]);
  const [requestActionLoadingId, setRequestActionLoadingId] = useState<
    number | null
  >(null);
  const [requestComments, setRequestComments] = useState<
    Record<number, string>
  >({});
  const [requestStatusFilter, setRequestStatusFilter] = useState<
    "pending" | "approved" | "rejected" | "all"
  >("pending");
  const [activeTab, setActiveTab] =
    useState<QuestionnairePageTab>("questionnaires");
  const [focusedRequestId, setFocusedRequestId] = useState<number | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const roles = useSelector((state: any) => state.auth.role || []);
  const currentUser = useSelector((state: any) => state.auth.user);
  const isSystemAdmin = hasSystemAdminRole(roles);
  const isQualityManager = hasQualityManagerRole(roles);
  const canReviewRequests = isSystemAdmin || isQualityManager;
  const canSeeScoreFormulas = canReviewRequests;
  const canOpenCreateQuestionnaire = canManageQuestionnaires(roles);
  const isAuditorOnly = hasAuditorRole(roles) && !canReviewRequests;
  const currentUserId = currentUser?.id as number | undefined;
  const [submitLoadingId, setSubmitLoadingId] = useState<number | null>(null);

  const handleClick = () => {
    if (!canOpenCreateQuestionnaire) {
      toast.error("You are not allowed to create questionnaires.");
      return;
    }
    setDeleteError(null);
    setIsAddModalOpen(true);
  };

  const closeAddModal = () => {
    setIsAddModalOpen(false);
  };

  const openQuestionnairesTab = () => {
    setActiveTab("questionnaires");
    setFocusedRequestId(null);
    if (location.search) {
      navigate("/questionnaire", { replace: true });
    }
  };

  const openRequestsTab = () => {
    setActiveTab("requests");
    const params = new URLSearchParams(location.search);
    params.set("tab", "requests");
    if (!params.get("status")) {
      params.set("status", requestStatusFilter);
    }
    navigate(`/questionnaire?${params.toString()}`, { replace: true });
  };

  const openDeleteConfirm = (q: Questionnaire) => {
    setSelectedQuestionnaire(q);
    dispatch(clearDeleteState());
    setIsConfirmOpen(true);
  };

  const handleConfirmDelete = async () => {
    const result = await deleteQuestionnaire(
      selectedQuestionnaire?.id,
      dispatch,
    );

    if (result.success) {
      setIsConfirmOpen(false);
      setDeleteError(null);
      toast.success(
        result.request_submitted
          ? result.message || "Approval request sent to Quality Manager."
          : "Questionnaire deleted successfully",
      );
      if (result.request_submitted) {
        await loadChangeRequests();
      }
    } else {
      setDeleteError(result.error || "Failed to delete questionnaire");
    }
  };

  const loadChangeRequests = useCallback(async () => {
    try {
      const { data } = await axiosInstance.get(
        "/questionnaire/change-requests",
      );
      setChangeRequests(Array.isArray(data) ? data : []);
    } catch {
      setChangeRequests([]);
    }
  }, []);

  const approveRequest = async (requestId: number) => {
    setRequestActionLoadingId(requestId);
    try {
      const { data } = await axiosInstance.post(
        `/questionnaire/change-requests/${requestId}/approve`,
        { comment: requestComments[requestId] || undefined },
      );
      toast.success(data?.message || "Request approved successfully.");
      await loadChangeRequests();
      await getQuestionnaires(dispatch);
      setRequestComments((prev) => ({ ...prev, [requestId]: "" }));
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail || "Failed to approve request.",
      );
    } finally {
      setRequestActionLoadingId(null);
    }
  };

  const rejectRequest = async (requestId: number) => {
    setRequestActionLoadingId(requestId);
    try {
      const { data } = await axiosInstance.post(
        `/questionnaire/change-requests/${requestId}/reject`,
        { comment: requestComments[requestId] || undefined },
      );
      toast.success(data?.message || "Request rejected.");
      await loadChangeRequests();
      await getQuestionnaires(dispatch);
      setRequestComments((prev) => ({ ...prev, [requestId]: "" }));
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "Failed to reject request.");
    } finally {
      setRequestActionLoadingId(null);
    }
  };

  const canManageDraft = (q: Questionnaire) => {
    if (!canOpenCreateQuestionnaire) return false;
    if (canReviewRequests) return true;
    if (!isAuditorOnly) return false;
    return q.status === "Under Revision" && q.created_by === currentUserId;
  };

  const hasPendingSubmissionRequest = (q: Questionnaire) =>
    changeRequests.some((req) => {
      if (req.status !== "pending") return false;
      if (req.entity_type !== "questionnaire" || req.action_type !== "submit") {
        return false;
      }
      const contextId = req.questionnaire_context?.id;
      return (
        req.questionnaire_id === q.id ||
        req.target_id === q.id ||
        contextId === q.id
      );
    });

  const canSubmitDraft = (q: Questionnaire) =>
    isAuditorOnly &&
    q.status === "Under Revision" &&
    q.created_by === currentUserId &&
    !hasPendingSubmissionRequest(q);

  const requestsByStatus = useMemo(() => {
    const pending = changeRequests.filter((req) => req.status === "pending");
    const approved = changeRequests.filter((req) => req.status === "approved");
    const rejected = changeRequests.filter((req) => req.status === "rejected");
    return {
      pending,
      approved,
      rejected,
    };
  }, [changeRequests]);

  const filteredReviewRequests = useMemo(() => {
    if (requestStatusFilter === "all") return changeRequests;
    return changeRequests.filter((req) => req.status === requestStatusFilter);
  }, [changeRequests, requestStatusFilter]);

  const myRequests = useMemo(() => {
    if (!canReviewRequests) return changeRequests;
    if (!currentUserId) return [] as ChangeRequestItem[];
    return changeRequests.filter(
      (req) => req.requested_by?.id === currentUserId,
    );
  }, [canReviewRequests, changeRequests, currentUserId]);

  const requestTabTitle = canReviewRequests ? "Review Queue" : "My Requests";
  const requestTabCount = canReviewRequests
    ? changeRequests.length
    : myRequests.length;
  const hasRequestTab = canReviewRequests || requestTabCount > 0;

  const formatRequestDate = (dateValue?: string | null) =>
    dateValue ? new Date(dateValue).toLocaleString() : "-";
  const formatLifecycleDate = (dateValue?: string | null) =>
    dateValue ? new Date(dateValue).toLocaleString() : "-";
  const looksIso = (blob: string) =>
    blob.includes("iso14001") ||
    blob.includes("iso 14001") ||
    blob.includes("iso45001") ||
    blob.includes("iso 45001") ||
    blob.includes("iso50001") ||
    blob.includes("iso 50001") ||
    blob.includes("iso");
  const normalizeScoreKey = (raw?: string | null) =>
    (raw || "")
      .trim()
      .toLowerCase()
      .replace(/[\s_-]/g, "");
  const inferScoreKeyFromQuestionnaire = (questionnaire: Questionnaire) => {
    const blob = [
      questionnaire.name,
      questionnaire.auditType?.value,
      questionnaire.framework?.code,
      questionnaire.framework?.label,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    if (
      blob.includes("special process") ||
      blob.includes("internal") ||
      blob.includes("standard respect")
    ) {
      return "internal";
    }
    if (blob.includes("plant manager") && blob.includes("iatf")) {
      return "iatfpm";
    }
    if (looksIso(blob)) {
      return "isosystem";
    }
    if (blob.includes("vda") || blob.includes("process")) {
      return "vdaprocess";
    }
    if (blob.includes("iatf")) {
      return "iatfclassification";
    }
    return "legacystandard";
  };
  const resolveScoreKeyForDisplay = (questionnaire: Questionnaire) => {
    const configured = normalizeScoreKey(questionnaire.score_calculation);
    if (configured) {
      return {
        key: scoreKeyAliases[configured] || configured,
        source: "configured" as const,
      };
    }
    return {
      key: inferScoreKeyFromQuestionnaire(questionnaire),
      source: "inferred" as const,
    };
  };
  const getScoreFormulaMeta = (questionnaire: Questionnaire) => {
    const resolved = resolveScoreKeyForDisplay(questionnaire);
    const meta = scoreFormulaCatalog[resolved.key] || {
      label: questionnaire.score_calculation || "Custom",
      formula: questionnaire.score_calculation || "Not configured",
      explanation:
        "Custom profile configured in backend. Review scoring service for exact implementation.",
    };
    return {
      ...meta,
      resolvedKey: resolved.key,
      source: resolved.source,
    } as ScoreFormulaMeta & {
      resolvedKey: string;
      source: "configured" | "inferred";
    };
  };

  const getRequestQuestionnaireName = (req: ChangeRequestItem) => {
    const contextName = req.questionnaire_context?.name?.trim();
    if (contextName) return contextName;
    const payloadName = req.payload?.name;
    if (typeof payloadName === "string" && payloadName.trim())
      return payloadName;
    const sourceId =
      req.questionnaire_context?.id || req.questionnaire_id || req.target_id;
    return sourceId
      ? `Questionnaire #${sourceId}`
      : "Questionnaire not specified";
  };

  const toTitle = (value?: string | null) => {
    if (!value) return "";
    return value
      .replace(/_/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  };

  const requestStatusStyles: Record<string, string> = {
    pending:
      "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
    approved:
      "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
    rejected: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  };

  const openRequestQuestionnaire = (req: ChangeRequestItem) => {
    const sourceId =
      req.questionnaire_context?.id || req.questionnaire_id || req.target_id;
    if (!sourceId) return;
    const match = questionnairesList.find(
      (q: Questionnaire) => q.id === sourceId,
    );
    if (match) {
      openModalQuestions(match);
      return;
    }
    toast("Questionnaire details are not currently available in your list.");
  };

  const submitForApproval = async (questionnaireId: number) => {
    setSubmitLoadingId(questionnaireId);
    try {
      const { data } = await axiosInstance.post(
        `/questionnaire/${questionnaireId}/submit-for-approval`,
      );
      toast.success(data?.message || "Submitted for Quality Manager review.");
      await loadChangeRequests();
      await getQuestionnaires(dispatch);
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail || "Failed to submit questionnaire.",
      );
    } finally {
      setSubmitLoadingId(null);
    }
  };

  const handleCancelDelete = () => {
    setIsConfirmOpen(false);
    dispatch(clearDeleteState());
  };

  const handleEditQuestionnaire = (q: Questionnaire) => {
    setIsOpen(true);
    setSelectedQuestionnaire(q);
  };

  const closeEditModal = () => {
    setIsOpen(false);
  };

  const closeModalQuestions = () => {
    setIsModalOpenQuestions(false);
  };

  const openModalQuestions = (q: Questionnaire) => {
    setSelectedQuestionnaire(q);
    setIsModalOpenQuestions(true);
  };

  // Open guideline viewer
  const openGuidelineViewer = (guideline: GuidelineDocument) => {
    setSelectedGuideline(guideline);
    setIsGuidelineViewerOpen(true);
  };

  const closeGuidelineViewer = () => {
    setIsGuidelineViewerOpen(false);
    setSelectedGuideline(null);
  };

  // Open delete guideline confirmation
  const openDeleteGuideline = (
    questionnaireId: number,
    guideline: GuidelineDocument,
    event: React.MouseEvent,
  ) => {
    event.stopPropagation(); // Prevent opening the viewer
    setGuidelineToDelete({ questionnaireId, guideline });
    setIsDeleteGuidelineOpen(true);
  };

  // Delete guideline
  const handleDeleteGuideline = async () => {
    if (!guidelineToDelete) return;

    setDeletingGuideline(true);
    try {
      await axiosInstance.delete(
        `/questionnaire/documents/${guidelineToDelete.questionnaireId}/guideline`,
      );
      toast.success("Guideline deleted successfully");
      setIsDeleteGuidelineOpen(false);
      setGuidelineToDelete(null);
      // Refresh questionnaires list
      await getQuestionnaires(dispatch);
    } catch (error: any) {
      console.error("Delete guideline error:", error);
      toast.error(error.response?.data?.detail || "Failed to delete guideline");
    } finally {
      setDeletingGuideline(false);
    }
  };

  const toggleGroup = (status: string) => {
    setCollapsedGroups((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(status)) {
        newSet.delete(status);
      } else {
        newSet.add(status);
      }
      return newSet;
    });
  };

  useEffect(() => {
    getQuestionnaires(dispatch);
    getFrameworks(dispatch);
    dispatch(resetQuestioannairesState());
  }, [dispatch]);

  useEffect(() => {
    loadChangeRequests();
  }, [canReviewRequests, currentUserId, loadChangeRequests]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      loadChangeRequests();
    }, 30000);
    return () => window.clearInterval(intervalId);
  }, [loadChangeRequests]);

  const handleLiveChecklistNotification = useCallback(
    (message: WebSocketMessage) => {
      if (
        message.type !== "checklist_change_request" &&
        message.type !== "checklist_change_request_decision"
      ) {
        return;
      }
      loadChangeRequests();
      getQuestionnaires(dispatch);
    },
    [dispatch, loadChangeRequests],
  );

  useWebSocket(handleLiveChecklistNotification);

  const handleQuestionRequestSubmitted = useCallback(
    async (requestId: number) => {
      await loadChangeRequests();
      await getQuestionnaires(dispatch);
      setFocusedRequestId(requestId);
    },
    [dispatch, loadChangeRequests],
  );

  useEffect(() => {
    if (!hasRequestTab && activeTab !== "questionnaires") {
      setActiveTab("questionnaires");
      if (location.search) {
        navigate("/questionnaire", { replace: true });
      }
    }
  }, [activeTab, hasRequestTab, location.search, navigate]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const tabParam = (params.get("tab") || "").trim().toLowerCase();
    const statusParam = (params.get("status") || "").trim().toLowerCase();
    const requestIdRaw = params.get("request_id");
    const parsedRequestId = requestIdRaw ? Number(requestIdRaw) : NaN;
    const hasValidRequestId =
      Number.isFinite(parsedRequestId) && parsedRequestId > 0;

    if (tabParam === "requests" && hasRequestTab) {
      setActiveTab("requests");
    }

    if (
      statusParam === "pending" ||
      statusParam === "approved" ||
      statusParam === "rejected" ||
      statusParam === "all"
    ) {
      setRequestStatusFilter(statusParam);
    }

    if (hasValidRequestId) {
      setFocusedRequestId(parsedRequestId);
      if (hasRequestTab) {
        setActiveTab("requests");
      }
      if (!statusParam) {
        const matched = changeRequests.find(
          (req) => req.id === parsedRequestId,
        );
        if (
          matched &&
          (matched.status === "pending" ||
            matched.status === "approved" ||
            matched.status === "rejected")
        ) {
          setRequestStatusFilter(matched.status);
        } else {
          setRequestStatusFilter("all");
        }
      }
    } else if (!requestIdRaw) {
      setFocusedRequestId(null);
    }
  }, [location.search, hasRequestTab, changeRequests]);

  // Group questionnaires by status
  const groupedQuestionnaires = questionnairesList.reduce(
    (groups: Record<string, Questionnaire[]>, q: Questionnaire) => {
      const status = q.status || "Unknown";
      if (!groups[status]) {
        groups[status] = [];
      }
      groups[status].push(q);
      return groups;
    },
    {},
  );

  // Sort groups by priority
  const statusOrder = ["Ready to Use", "Under Revision"];
  const sortedStatuses = Object.keys(groupedQuestionnaires).sort((a, b) => {
    const indexA = statusOrder.indexOf(a);
    const indexB = statusOrder.indexOf(b);
    return (indexA === -1 ? 999 : indexA) - (indexB === -1 ? 999 : indexB);
  });

  // Status color mapping
  const getStatusColor = (status: string) => {
    const colors: Record<string, { bg: string; text: string; border: string }> =
      {
        "Ready to Use": {
          bg: "bg-green-50 dark:bg-green-900/20",
          text: "text-green-700 dark:text-green-400",
          border: "border-green-300 dark:border-green-700",
        },
        "Under Revision": {
          bg: "bg-orange-50 dark:bg-orange-900/20",
          text: "text-orange-700 dark:text-orange-400",
          border: "border-orange-300 dark:border-orange-700",
        },
      };
    return (
      colors[status] || {
        bg: "bg-gray-50 dark:bg-gray-900/20",
        text: "text-gray-700 dark:text-gray-400",
        border: "border-gray-300 dark:border-gray-700",
      }
    );
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + " KB";
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
  };

  const totalQuestionnaires = questionnairesList.length;
  const visibleRequests = useMemo(() => {
    const base = canReviewRequests ? filteredReviewRequests : myRequests;
    if (!focusedRequestId) return base;
    const targetIndex = base.findIndex((req) => req.id === focusedRequestId);
    if (targetIndex <= 0) return base;
    const ordered = [...base];
    const [focused] = ordered.splice(targetIndex, 1);
    ordered.unshift(focused);
    return ordered;
  }, [canReviewRequests, filteredReviewRequests, myRequests, focusedRequestId]);
  const tableMinWidthClass = canSeeScoreFormulas
    ? "min-w-[2200px]"
    : "min-w-[1820px]";

  const renderQuestionnaireRow = (q: Questionnaire, index: number) => (
    <tr
      key={q.id}
      className={`border-b border-gray-100 dark:border-gray-800 group hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-all duration-200
        ${
          index % 2 === 0
            ? "bg-white dark:bg-gray-900"
            : "bg-gray-50/30 dark:bg-gray-900/50"
        }`}
    >
      {/* Name - Sticky */}
      <td className="sticky left-0 z-20 w-[320px] min-w-[320px] max-w-[320px] border-r border-indigo-100 px-6 py-5 bg-white dark:border-gray-700 dark:bg-gray-900 group-hover:bg-gray-50 dark:group-hover:bg-gray-800/50 shadow-[10px_0_18px_-14px_rgba(15,23,42,0.45)]">
        <button
          className="block w-full truncate text-left text-sm font-semibold text-[#064273] hover:text-[#05375f] hover:underline transition-colors"
          title={q.name}
          onClick={() => openModalQuestions(q)}
        >
          {q.name}
        </button>
      </td>

      {/* Version */}
      <td className="px-6 py-5">
        <div className="text-sm text-gray-700 dark:text-gray-300">
          {q.version}
        </div>
      </td>

      {/* Lifecycle */}
      <td className="px-6 py-5">
        <div className="space-y-1.5 text-xs text-slate-700 dark:text-slate-300">
          <div>
            <span className="font-semibold">Created on:</span>{" "}
            {formatLifecycleDate(q.created_at)} by{" "}
            {q.created_by_user?.name || q.created_by_user?.email || "-"}
          </div>
          <div>
            <span className="font-semibold">Approved by:</span>{" "}
            {q.approved_by_user?.name || q.approved_by_user?.email
              ? `${q.approved_by_user?.name || q.approved_by_user?.email} on ${formatLifecycleDate(q.approved_at)}`
              : q.creation_method === "Direct Creation"
                ? "Not applicable (direct creation)"
                : "Not yet approved"}
          </div>
        </div>
      </td>

      {/* Framework */}
      <td className="px-6 py-5">
        <div className="inline-flex items-center px-3 py-1.5 bg-purple-50 dark:bg-purple-900/20 rounded-full border border-purple-200 dark:border-purple-800">
          <span className="text-xs font-semibold text-purple-900 dark:text-purple-300">
            {q.framework?.code.toUpperCase() || "N/A"}
          </span>
        </div>
      </td>

      {/* Type */}
      <td className="px-6 py-5">
        <div className="inline-flex items-center px-3 py-1.5 bg-blue-300 dark:bg-blue-900/20 rounded-full border border-blue-200 dark:border-blue-800">
          <span className="text-xs font-semibold text-blue-900 dark:text-blue-300">
            {q.auditType?.value.replace(/\b\w/g, (char: string) =>
              char.toUpperCase(),
            ) || "N/A"}
          </span>
        </div>
      </td>

      {/* Auditors */}
      <td className="px-6 py-5">
        <div className="space-y-1">
          {q.auditors?.length > 0 ? (
            q.auditors.map((p: any) => (
              <div
                key={p.email}
                className="text-sm text-gray-700 dark:text-gray-300"
              >
                {p.email}
              </div>
            ))
          ) : (
            <span className="text-sm text-gray-400">-</span>
          )}
        </div>
      </td>

      {/* Target Duration */}
      <td className="px-6 py-5">
        <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {q.target_duration || "-"}
        </div>
      </td>

      {canSeeScoreFormulas && (
        <td className="px-6 py-5">
          {/* <td className="px-6 py-5 bg-blue-50 dark:bg-blue-800/50"> */}

          {(() => {
            const scoreMeta = getScoreFormulaMeta(q);
            return (
              <div className="max-w-[370px] rounded-lg border border-[#8fc1df] bg-gradient-to-br from-[#e8f4fb] to-[#d7ebf8] p-3 text-xs dark:border-[#0d5a87] dark:bg-gradient-to-br dark:from-[#0a496f] dark:to-[#073b59]">
                <p className="font-semibold text-[#0a3550] dark:text-[#d8efff]">
                  {scoreMeta.label}
                </p>
                <p className="mt-1 text-[#184966] dark:text-[#d0e8f8]">
                  {scoreMeta.explanation}
                </p>
                <p className="mt-2 rounded bg-white/95 px-2 py-1 font-mono text-[11px] text-slate-700 dark:bg-[#083a58] dark:text-slate-100">
                  {scoreMeta.formula}
                </p>
                {scoreMeta.details?.length ? (
                  <ul className="mt-2 space-y-1 text-[11px] text-[#1f4f6b] dark:text-[#d0e8f8]">
                    {scoreMeta.details.map((detail) => (
                      <li key={`${q.id}-${detail}`}>- {detail}</li>
                    ))}
                  </ul>
                ) : null}
                {/* {q.score_calculation ? (
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                    Key: {q.score_calculation}
                  </p>
                ) : (
                  <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-300">
                    Key inferred from questionnaire name/type/framework: {scoreMeta.resolvedKey}
                  </p>
                )} */}
              </div>
            );
          })()}
        </td>
      )}

      {/* Guideline - Updated with click to view and delete */}
      <td className="px-6 py-5">
        {q.guideline ? (
          <div className="flex items-center gap-2">
            <button
              onClick={() => openGuidelineViewer(q.guideline!)}
              className="flex items-center gap-2 px-3 py-1.5 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors cursor-pointer group/file flex-1"
            >
              <svg
                className="w-4 h-4 text-green-600 flex-shrink-0"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" />
              </svg>
              <div className="flex flex-col items-start min-w-0">
                <span className="text-xs font-medium text-gray-900 dark:text-gray-100 group-hover/file:text-green-600 dark:group-hover/file:text-green-400 truncate max-w-[200px]">
                  {q.guideline.filename}
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {formatFileSize(q.guideline.size)} • Click to view
                </span>
              </div>
            </button>
            {canManageDraft(q) && (
              <button
                onClick={(e) => openDeleteGuideline(q.id, q.guideline!, e)}
                className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors flex-shrink-0"
                title="Delete guideline"
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
            )}
          </div>
        ) : (
          <span className="text-sm text-gray-400 dark:text-gray-500">
            No file
          </span>
        )}
      </td>

      {/* Actions - Sticky */}
      <td className="sticky right-0 z-20 min-w-[160px] border-l border-indigo-100 px-6 py-5 bg-white dark:border-gray-700 dark:bg-gray-900 group-hover:bg-gray-50 dark:group-hover:bg-gray-800/50 shadow-[-10px_0_18px_-14px_rgba(15,23,42,0.45)]">
        <div className="flex gap-2 justify-center opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
          {canSubmitDraft(q) && (
            <button
              onClick={() => submitForApproval(q.id)}
              disabled={submitLoadingId === q.id}
              className="rounded-md bg-emerald-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
              title="Submit for approval"
            >
              {submitLoadingId === q.id ? "Submitting..." : "Submit"}
            </button>
          )}
          {isAuditorOnly && hasPendingSubmissionRequest(q) && (
            <span className="rounded-md bg-amber-100 px-2.5 py-1.5 text-xs font-semibold text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              Pending Review
            </span>
          )}
          {canManageDraft(q) ? (
            <>
              <button
                onClick={() => handleEditQuestionnaire(q)}
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
                onClick={() => openDeleteConfirm(q)}
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
            </>
          ) : (
            <span className="text-[11px] font-medium text-slate-400">
              Read only
            </span>
          )}
        </div>
      </td>
    </tr>
  );

  return (
    <div className="space-y-4">
      <PageMeta title="Questionnaire" description="..." />
      <PageBreadcrumb
        kicker="Library"
        pageTitle="Questionnaire Overview"
        description="Manage versions, guidelines and assigned auditors in one place."
        actions={
          canOpenCreateQuestionnaire ? (
            <button
              onClick={handleClick}
              className="inline-flex items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-300/60 focus:ring-offset-2 dark:bg-white dark:text-slate-900"
            >
              Create New Questionnaire
            </button>
          ) : null
        }
      />
      {/* Summary */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-lg border border-slate-200/70 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700 dark:border-slate-800/70 dark:bg-slate-900/60 dark:text-slate-200">
          Total: {totalQuestionnaires}
        </span>
        {sortedStatuses.map((status) => {
          const s = getStatusColor(status);
          const count = groupedQuestionnaires[status]?.length ?? 0;
          return (
            <span
              key={`summary-${status}`}
              className={`rounded-lg border px-2.5 py-1 text-xs font-semibold ${s.bg} ${s.text} ${s.border}`}
            >
              {status}: {count}
            </span>
          );
        })}
        {isAuditorOnly && (
          <span className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-300">
            Auditor mode: create and update drafts, then submit for review
          </span>
        )}
        {canReviewRequests && (
          <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-900/20 dark:text-emerald-300">
            Reviewer mode: approve or reject pending change requests
          </span>
        )}
        {!canOpenCreateQuestionnaire && (
          <span className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
            Read-only mode: questionnaire creation and edits are restricted for
            your role
          </span>
        )}
      </div>
      {hasRequestTab && (
        <div className="mt-4 inline-flex items-center rounded-xl border border-slate-200/70 bg-slate-50 p-1 shadow-sm dark:border-slate-800/70 dark:bg-slate-900/60">
          <button
            onClick={openQuestionnairesTab}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              activeTab === "questionnaires"
                ? "bg-slate-900 text-white shadow-sm dark:bg-white dark:text-slate-900"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            Questionnaires
          </button>
          <button
            onClick={openRequestsTab}
            className={`ml-1 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              activeTab === "requests"
                ? "bg-slate-900 text-white shadow-sm dark:bg-white dark:text-slate-900"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {requestTabTitle} ({requestTabCount})
          </button>
        </div>
      )}

      {hasRequestTab && activeTab === "requests" && (
        <div className="rounded-2xl border border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50/80 px-5 py-4 shadow-sm dark:border-amber-900/40 dark:from-amber-900/10 dark:to-orange-900/10">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-300">
                {canReviewRequests
                  ? "Checklist Review Queue"
                  : "My Approval Requests"}
              </h3>
              <p className="mt-1 text-xs text-amber-800/90 dark:text-amber-200/90">
                {canReviewRequests
                  ? "Review submitted questionnaire and question changes with full checklist context."
                  : "Track your submissions and reviewer feedback."}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {canReviewRequests && (
                <>
                  {[
                    {
                      key: "pending",
                      label: `Pending (${requestsByStatus.pending.length})`,
                    },
                    {
                      key: "approved",
                      label: `Approved (${requestsByStatus.approved.length})`,
                    },
                    {
                      key: "rejected",
                      label: `Rejected (${requestsByStatus.rejected.length})`,
                    },
                    { key: "all", label: `All (${changeRequests.length})` },
                  ].map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() =>
                        setRequestStatusFilter(
                          tab.key as
                            | "pending"
                            | "approved"
                            | "rejected"
                            | "all",
                        )
                      }
                      className={`rounded-full px-2.5 py-1 text-xs font-semibold transition ${
                        requestStatusFilter === tab.key
                          ? "bg-amber-600 text-white"
                          : "bg-white text-amber-800 hover:bg-amber-100 dark:bg-gray-900 dark:text-amber-200 dark:hover:bg-amber-900/20"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </>
              )}
              <button
                onClick={loadChangeRequests}
                className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-amber-700 hover:bg-amber-100 dark:bg-gray-900 dark:text-amber-300 dark:hover:bg-amber-900/20"
              >
                Refresh
              </button>
            </div>
          </div>

          {visibleRequests.length === 0 ? (
            <div className="rounded-xl border border-amber-200/80 bg-white px-4 py-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-gray-900 dark:text-amber-200">
              {canReviewRequests
                ? "No requests match the current filter."
                : "No requests yet. Submit a checklist or question change request to start the review process."}
            </div>
          ) : (
            <div className="space-y-3">
              {visibleRequests.map((req) => {
                const context = req.questionnaire_context;
                const frameworkLabel =
                  context?.framework?.label || context?.framework?.code || "-";
                const auditTypeLabel = context?.audit_type?.value || "-";
                const auditors = context?.auditor_emails || [];
                const questionsPreview = context?.questions_preview || [];
                const questionCount =
                  context?.questions_count ?? questionsPreview.length ?? 0;
                const statusClass =
                  requestStatusStyles[req.status] ||
                  "bg-slate-100 text-slate-800 dark:bg-slate-900/40 dark:text-slate-200";
                const isFocusedRequest = focusedRequestId === req.id;

                return (
                  <div
                    key={req.id}
                    className={`rounded-xl border px-4 py-3 dark:bg-gray-900 ${
                      isFocusedRequest
                        ? "border-[#0a5f95] ring-2 ring-[#0a5f95]/35 bg-[#f0f8ff] dark:border-[#58a6ff] dark:ring-[#58a6ff]/35"
                        : "border-amber-200/90 bg-white dark:border-amber-900/40"
                    }`}
                  >
                    <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusClass}`}
                      >
                        {req.status_label || toTitle(req.status) || "Unknown"}
                      </span>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700 dark:bg-gray-800 dark:text-gray-300">
                        #{req.id}
                      </span>
                      <span className="font-semibold text-slate-900 dark:text-white">
                        {req.summary ||
                          `${toTitle(req.action_type)} ${toTitle(req.entity_type)}`}
                      </span>
                    </div>

                    <div className="mb-3 grid grid-cols-1 gap-2 rounded-lg border border-slate-200 bg-slate-50/70 p-3 text-xs text-slate-700 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-300 md:grid-cols-2">
                      <div>
                        <span className="font-semibold">Questionnaire:</span>{" "}
                        {getRequestQuestionnaireName(req)}
                      </div>
                      <div>
                        <span className="font-semibold">Requested by:</span>{" "}
                        {req.requested_by?.name ||
                          req.requested_by?.email ||
                          "Unknown"}
                      </div>
                      <div>
                        <span className="font-semibold">Submitted:</span>{" "}
                        {formatRequestDate(req.created_at)}
                      </div>
                      <div>
                        <span className="font-semibold">Action:</span>{" "}
                        {toTitle(req.action_type)} {toTitle(req.entity_type)}
                      </div>
                      <div>
                        <span className="font-semibold">Framework:</span>{" "}
                        {frameworkLabel}
                      </div>
                      <div>
                        <span className="font-semibold">Audit Type:</span>{" "}
                        {auditTypeLabel}
                      </div>
                      <div>
                        <span className="font-semibold">Status:</span>{" "}
                        {context?.status || "-"}
                      </div>
                      <div>
                        <span className="font-semibold">Version:</span>{" "}
                        {context?.version ?? "-"}
                      </div>
                      <div>
                        <span className="font-semibold">Target Duration:</span>{" "}
                        {context?.target_duration || "-"}
                      </div>
                      <div>
                        <span className="font-semibold">Questions:</span>{" "}
                        {questionCount}
                      </div>
                      <div className="md:col-span-2">
                        <span className="font-semibold">Auditors:</span>{" "}
                        {auditors.length ? auditors.join(", ") : "-"}
                      </div>
                      {req.request_comment ? (
                        <div className="md:col-span-2">
                          <span className="font-semibold">Request Note:</span>{" "}
                          {req.request_comment}
                        </div>
                      ) : null}
                      {req.review_comment ? (
                        <div className="md:col-span-2">
                          <span className="font-semibold">Review Note:</span>{" "}
                          {req.review_comment}
                        </div>
                      ) : null}
                    </div>

                    {questionsPreview.length > 0 ? (
                      <details className="mb-3 rounded-md border border-slate-200 bg-white p-2 text-xs dark:border-gray-700 dark:bg-gray-900">
                        <summary className="cursor-pointer font-semibold text-slate-700 dark:text-slate-200">
                          View Proposed Questions ({questionCount})
                        </summary>
                        <div className="mt-2 max-h-40 overflow-auto space-y-1.5">
                          {questionsPreview.map((question) => (
                            <div
                              key={`req-${req.id}-question-${question.id || question.description}`}
                              className="rounded border border-slate-100 bg-slate-50 px-2 py-1 dark:border-gray-700 dark:bg-gray-800/70"
                            >
                              <p className="font-medium text-slate-800 dark:text-gray-100">
                                {question.description || "-"}
                              </p>
                              <p className="text-[11px] text-slate-600 dark:text-gray-400">
                                Chapter: {question.chapter || "-"} | Weight:{" "}
                                {question.weight ?? "-"} | Critical:{" "}
                                {question.critical_value ?? "-"}
                              </p>
                            </div>
                          ))}
                        </div>
                      </details>
                    ) : null}

                    <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                      <button
                        onClick={() => openRequestQuestionnaire(req)}
                        disabled={
                          !(
                            req.questionnaire_context?.id ||
                            req.questionnaire_id ||
                            req.target_id
                          )
                        }
                        className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                      >
                        Open Questionnaire
                      </button>

                      {canReviewRequests && req.status === "pending" ? (
                        <div className="flex w-full flex-col gap-2 md:w-auto md:flex-row md:items-center">
                          <input
                            type="text"
                            value={requestComments[req.id] || ""}
                            onChange={(e) =>
                              setRequestComments((prev) => ({
                                ...prev,
                                [req.id]: e.target.value,
                              }))
                            }
                            placeholder="Optional review comment"
                            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-700 focus:border-[#064273] focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 md:w-72"
                          />
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => approveRequest(req.id)}
                              disabled={requestActionLoadingId === req.id}
                              className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => rejectRequest(req.id)}
                              disabled={requestActionLoadingId === req.id}
                              className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-60"
                            >
                              Reject
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="text-xs text-slate-600 dark:text-slate-300">
                          {req.reviewed_by
                            ? `Reviewed by ${
                                req.reviewed_by.name ||
                                req.reviewed_by.email ||
                                "Reviewer"
                              } on ${formatRequestDate(req.reviewed_at)}`
                            : "Awaiting reviewer decision"}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {activeTab === "questionnaires" && (
        <>
          {/* Table Container - Scrollable */}
          <div className="flex-1" style={{ minHeight: 0 }}>
            <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-[#b8d3e6] bg-white/95 shadow-sm dark:border-[#0a5f95] dark:bg-[#072f4a]/80">
              {/* Table Wrapper */}
              <div
                className="flex-1 overflow-auto bg-white p-4 dark:bg-[#05263b]"
                style={{ minHeight: 0 }}
              >
                {questionnairesList.length > 0 ? (
                  <div className="space-y-4">
                    {sortedStatuses.map((status) => {
                      const items = groupedQuestionnaires[status].sort(
                        (a: Questionnaire, b: Questionnaire) => a.id - b.id,
                      );
                      const isCollapsed = collapsedGroups.has(status);
                      const statusColors = getStatusColor(status);

                      return (
                        <div
                          key={status}
                          className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-indigo-100 dark:border-gray-700 overflow-hidden divide-y divide-indigo-100/80 dark:divide-gray-800"
                        >
                          {/* Group Header */}
                          <button
                            onClick={() => toggleGroup(status)}
                            className={`w-full px-6 py-4 flex items-center justify-between bg-gradient-to-r from-white to-indigo-50/40 dark:from-gray-900 dark:to-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors border-l-4 ${statusColors.border}`}
                          >
                            <div className="flex items-center gap-3">
                              <svg
                                className={`w-4 h-4 text-gray-500 dark:text-gray-400 transition-transform duration-200 ${
                                  isCollapsed ? "-rotate-90" : ""
                                }`}
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
                              <div
                                className={`px-3 py-1.5 rounded-full ${statusColors.bg} border ${statusColors.border}`}
                              >
                                <span
                                  className={`text-sm font-semibold ${statusColors.text}`}
                                >
                                  {status}
                                </span>
                              </div>
                              <span className="rounded-full bg-white/80 px-2.5 py-1 text-xs font-semibold text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                                {items.length}{" "}
                                {items.length === 1 ? "item" : "items"}
                              </span>
                            </div>
                          </button>

                          {/* Group Content */}
                          <div
                            className={`transition-all duration-300 ease-in-out overflow-hidden ${
                              isCollapsed ? "max-h-0" : "max-h-[10000px]"
                            }`}
                          >
                            <div className="overflow-x-auto">
                              <table
                                className={`w-full ${tableMinWidthClass} border-collapse`}
                              >
                                <thead className="bg-indigo-50/80 dark:bg-gray-800">
                                  <tr>
                                    <th className="sticky left-0 z-30 w-[320px] min-w-[320px] max-w-[320px] text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-r border-gray-200 dark:border-gray-700 bg-indigo-50/80 dark:bg-gray-800 shadow-[10px_0_18px_-14px_rgba(15,23,42,0.45)]">
                                      Name
                                    </th>
                                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 min-w-[120px]">
                                      Version
                                    </th>
                                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 min-w-[320px]">
                                      Lifecycle
                                    </th>
                                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 min-w-[150px]">
                                      Framework
                                    </th>
                                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 min-w-[150px]">
                                      Type
                                    </th>
                                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 min-w-[250px]">
                                      Auditors
                                    </th>
                                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 min-w-[180px]">
                                      Target Duration
                                    </th>
                                    {canSeeScoreFormulas && (
                                      <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 min-w-[390px]">
                                        Score Calculation
                                      </th>
                                    )}
                                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 min-w-[300px]">
                                      Guideline
                                    </th>
                                    <th className="sticky right-0 z-30 min-w-[160px] text-center px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider border-b border-l border-gray-200 dark:border-gray-700 bg-indigo-50/80 dark:bg-gray-800 shadow-[-10px_0_18px_-14px_rgba(15,23,42,0.45)]">
                                      Actions
                                    </th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {items.map(
                                    (q: Questionnaire, index: number) =>
                                      renderQuestionnaireRow(q, index),
                                  )}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="h-full flex items-center justify-center">
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
                        No questionnaires yet
                      </p>
                      <p className="text-sm">
                        Click "create a new" to get started
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Modals */}
      <AddQuestionnaireModal
        isOpen={isAddModalOpen}
        onClose={closeAddModal}
        frameworkOptions={frameworkOptions}
        auditTypeOptions={auditTypeOptions}
        auditorOptions={auditorOptions}
      />

      <QuestionsModal
        isOpen={isModalOpenQuestions}
        onClose={closeModalQuestions}
        questionnaire={selectedQuestionnaire}
        onRequestSubmitted={handleQuestionRequestSubmitted}
      />

      <EditQuestionnaireModal
        isOpen={isOpen}
        onClose={closeEditModal}
        selectedQuestionnaire={selectedQuestionnaire}
        frameworkOptions={frameworkOptions}
        auditTypeOptions={auditTypeOptions}
        auditorOptions={auditorOptions}
      />

      <GuidelineViewerModal
        isOpen={isGuidelineViewerOpen}
        onClose={closeGuidelineViewer}
        guideline={selectedGuideline}
      />

      {/* Questionnaire Delete Confirmation */}
      <ConfirmDialog
        isOpen={isConfirmOpen}
        title={deleteError ? "Delete Failed" : "Confirm Deletion"}
        message={
          deleteError ||
          `Are you sure you want to delete "${selectedQuestionnaire?.name}"? This action cannot be undone.`
        }
        onConfirm={deleteError ? handleCancelDelete : handleConfirmDelete}
        onCancel={deleteError ? undefined : handleCancelDelete}
        isError={!!deleteError}
        confirmText={deleteError ? "Close" : "Delete"}
        cancelText={deleteError ? "" : "Cancel"}
      />

      {/* Guideline Delete Confirmation */}
      <ConfirmDialog
        isOpen={isDeleteGuidelineOpen}
        title="Delete Guideline"
        message={`Are you sure you want to delete "${guidelineToDelete?.guideline.filename}"? This action cannot be undone.`}
        onConfirm={handleDeleteGuideline}
        onCancel={() => {
          setIsDeleteGuidelineOpen(false);
          setGuidelineToDelete(null);
        }}
        confirmText={deletingGuideline ? "Deleting..." : "Delete"}
        cancelText="Cancel"
        isError={false}
      />
    </div>
  );
}
