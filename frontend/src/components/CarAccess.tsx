import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { AxiosError } from "axios";
import axiosInstance from "../services/axiosInstance";

interface CarFormData {
  action_type: string;
  linked_action: LinkedActionData | null;
  audit_number: string;
  auditee_name: string;
  audit_type: string;
  audit_plant: string;
  reason_why: string;
  due_date: string;
  finding: string;
  implemented_solution: string;
  root_cause: string;
  is_submitted: boolean;
  status: string;
  submitted_at: string | null;
  documents: DocumentInfo[];
  reassigned_at: string | null;
  reassigned_from_email: string | null;
  cc_emails: string[];
  can_reassign: boolean;
  // Immediate-action CARs carry accelerated 24h-submit / 48h-close
  // deadlines instead of the regular due date.
  immediate_action_required?: boolean;
  submission_due_at?: string | null;
  closure_due_at?: string | null;
}

interface LinkedActionData {
  car_id: number;
  action_type: string;
  implemented_solution: string;
  root_cause: string;
  is_submitted: boolean;
  status: string;
  submitted_at: string | null;
  submission_due_at: string | null;
  closure_due_at: string | null;
  documents: DocumentInfo[];
}

interface DocumentInfo {
  id: number;
  filename: string;
  file_url: string;
  size: number;
  uploaded_at: string | null;
}

const isFullySubmitted = (d: CarFormData) =>
  d.is_submitted && (!d.linked_action || d.linked_action.is_submitted);

/* ─── helpers ──────────────────────────────────────────────────────────────── */

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
};

const isPrefilled = (v: string | undefined | null) =>
  typeof v === "string" && v.trim().length > 0;

const splitWhys = (rootCause: string) => {
  const whyLines = (rootCause || "")
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*(why\s*\d*\s*[:\-.)]?\s*)/i, "").trim())
    .filter(Boolean)
    .slice(0, 5);

  return Array.from({ length: 5 }).map((_, index) => whyLines[index] || "");
};

const joinWhys = (whys: string[]) =>
  whys
    .map((why) => why.trim())
    .filter(Boolean)
    .map((why, index) => `Why ${index + 1}: ${why}`)
    .join("\n");

const countFilledWhys = (whys: string[]) =>
  whys.filter((why) => why.trim().length > 0).length;

const extractApiErrorDetail = (err: unknown): string => {
  const axiosErr = err as AxiosError<{ detail?: unknown }>;
  const detail = axiosErr?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  // FastAPI's automatic request-validation errors (422) shape `detail` as
  // an array of {msg, loc, ...} objects, not a string -- treating it as one
  // (e.g. passing it straight into a later .startsWith() call) crashes the
  // page. Every other call site in this file goes through this function, so
  // handling the non-string shape here is enough to make all of them safe.
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : String(item),
      )
      .join(" ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return "";
};

const stripAlertIconPrefix = (text: string): string => {
  if (text.startsWith("✅ ")) return text.slice(2).trimStart();
  if (text.startsWith("⚠️ ")) return text.slice(3).trimStart();
  if (text.startsWith("❌ ")) return text.slice(2).trimStart();
  return text;
};

/* ─── file icon ─────────────────────────────────────────────────────────────── */
const FileIcon: React.FC<{ filename: string; className?: string }> = ({
  filename,
  className = "w-5 h-5",
}) => {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (["jpg", "jpeg", "png", "gif", "webp"].includes(ext))
    return (
      <svg
        className={`${className} text-green-500`}
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        <path
          fillRule="evenodd"
          d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z"
          clipRule="evenodd"
        />
      </svg>
    );
  if (ext === "pdf")
    return (
      <svg
        className={`${className} text-red-500`}
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        <path
          fillRule="evenodd"
          d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z"
          clipRule="evenodd"
        />
      </svg>
    );
  if (["xls", "xlsx"].includes(ext))
    return (
      <svg
        className={`${className} text-emerald-600`}
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        <path
          fillRule="evenodd"
          d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
          clipRule="evenodd"
        />
      </svg>
    );
  return (
    <svg
      className={`${className} text-blue-400`}
      fill="currentColor"
      viewBox="0 0 20 20"
    >
      <path
        fillRule="evenodd"
        d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
        clipRule="evenodd"
      />
    </svg>
  );
};

/* ─── component ────────────────────────────────────────────────────────────── */

export const CarAccess: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tokenParam = searchParams.get("token") || "";
  // Set by the "Fill Immediate Action" / "Fill Corrective Action" buttons in
  // the notification email -- each one opens a form dedicated to just that
  // section, not a combined page. Defaults to "corrective" when a linked
  // immediate action exists but no section was specified.
  const sectionParam = searchParams.get("section");
  const switchSection = (section: "immediate" | "corrective") => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("section", section);
      return next;
    });
  };

  const [step, setStep] = useState<"email" | "otp" | "form" | "submitted">(
    "email",
  );
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [carData, setCarData] = useState<CarFormData | null>(null);
  const [implementedSolution, setImplementedSolution] = useState("");
  const [rootCauseWhys, setRootCauseWhys] = useState<string[]>(
    Array.from({ length: 5 }, () => ""),
  );
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [submittedDate, setSubmittedDate] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  /* ── linked immediate action (containment, no 5-Whys, 24h/48h) ─────────── */
  const [immSolution, setImmSolution] = useState("");
  const [immFiles, setImmFiles] = useState<File[]>([]);
  const [immLoading, setImmLoading] = useState(false);
  const [immMessage, setImmMessage] = useState("");
  const [immSubmitted, setImmSubmitted] = useState(false);
  const [immSubmittedDate, setImmSubmittedDate] = useState<string | null>(
    null,
  );
  // Tracks the corrective section's own submitted state -- carData.is_submitted
  // is a snapshot from the last fetch and never updates after a successful
  // submit within this session, so the "are both sections done now" checks
  // below need this instead.
  const [correctiveDone, setCorrectiveDone] = useState(false);

  /* ── reassign / cc ──────────────────────────────────────────────────────── */
  const [reassignEmail, setReassignEmail] = useState("");
  const [reassignReason, setReassignReason] = useState("");
  const [reassignLoading, setReassignLoading] = useState(false);
  const [reassignMessage, setReassignMessage] = useState("");
  const [reassignedNow, setReassignedNow] = useState(false);
  const [ccEmailInput, setCcEmailInput] = useState("");
  const [ccLoading, setCcLoading] = useState(false);
  const [ccMessage, setCcMessage] = useState("");

  /* ── email ──────────────────────────────────────────────────────────────── */
  const isValidEmail = (v: string) =>
    // Hyphenated names are valid (jordan.marin@example.com).
    /^[A-Za-z]+(?:-[A-Za-z]+)*\.[A-Za-z]+(?:-[A-Za-z]+)*@northwind\.com$/i.test(v.trim());
  const emailError =
    email && !isValidEmail(email)
      ? "Email must be in the format first.last@example.com"
      : null;
  const isEmailValid = isValidEmail(email);

  /* ── files ──────────────────────────────────────────────────────────────── */
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    const files = Array.from(e.target.files);
    const invalid = files.filter((f) => f.size > 10 * 1024 * 1024);
    if (invalid.length) {
      setMessage(
        `⚠️ File(s) too large: ${invalid.map((f) => f.name).join(", ")}. Max 10 MB.`,
      );
      return;
    }
    setSelectedFiles((prev) => [...prev, ...files]);
    setMessage("");
    e.target.value = "";
  };
  const removeNewFile = (i: number) =>
    setSelectedFiles((prev) => prev.filter((_, idx) => idx !== i));
  const applyCarData = (d: CarFormData) => {
    setCarData(d);
    setImplementedSolution(d.implemented_solution || "");
    setRootCauseWhys(splitWhys(d.root_cause || ""));
    setCorrectiveDone(d.is_submitted);
    if (d.linked_action) {
      setImmSolution(d.linked_action.implemented_solution || "");
      setImmSubmitted(d.linked_action.is_submitted);
      setImmSubmittedDate(d.linked_action.submitted_at);
    }
  };

  const fetchCarForm = async (): Promise<CarFormData> => {
    const res = await axiosInstance.get<CarFormData>("/car/form", {
      params: {
        token: tokenParam,
        email,
        _t: Date.now(), // ← cache buster
      },
      headers: {
        "Cache-Control": "no-cache, no-store",
        Pragma: "no-cache",
      },
    });
    return res.data;
  };
  /* ── steps ──────────────────────────────────────────────────────────────── */
  const requestOtp = async () => {
    if (loading) return;
    if (!isValidEmail(email)) {
      setMessage(
        "⚠️ Please use an email in the format first.last@example.com",
      );
      return;
    }
    const friendly = (err: unknown) => {
      const d = extractApiErrorDetail(err);

      if (d.includes("This access link has expired")) {
        return "This access link has expired. Please contact the Quality team.";
      }
      if (d.includes("Session expired")) {
        return "Your verification session expired. Please request a new OTP code.";
      }
      if (d.includes("OTP code expired")) {
        return "Your OTP code expired. Please request a new one.";
      }
      if (d.includes("Invalid") || d.includes("invalid")) {
        return "This access link is invalid.";
      }
      return (
        d || "An error occurred. Please try again or contact the Quality team."
      );
    };
    try {
      setLoading(true);
      setMessage("");
      const res = await axiosInstance.post("/car/request-otp", {
        token: tokenParam,
        email,
      });

      if (res.data.already_submitted) {
        setSubmittedDate(res.data.submitted_at);
        setStep("submitted");
      } else if (res.data.already_verified) {
        const d = await fetchCarForm(); // ← use helper

        applyCarData(d);

        if (isFullySubmitted(d)) {
          setStep("submitted");
          setSubmittedDate(d.submitted_at);
        } else {
          setStep("form");
          setMessage("");
        }
      } else {
        setStep("otp");
        setMessage("✅ OTP code sent to your email.");
      }
    } catch (err: unknown) {
      setMessage(friendly(err));
    } finally {
      setLoading(false);
    }
  };

  const verifyOtp = async () => {
    try {
      setLoading(true);
      setMessage("");
      await axiosInstance.post("/car/verify-otp", {
        token: tokenParam,
        email,
        code: otp,
      });
      const d = await fetchCarForm(); // ← use helper

      applyCarData(d);
      if (isFullySubmitted(d)) {
        setStep("submitted");
        setSubmittedDate(d.submitted_at);
      } else {
        setStep("form");
        setMessage("");
      }
    } catch (err: unknown) {
      setMessage(extractApiErrorDetail(err) || "Invalid OTP code.");
    } finally {
      setLoading(false);
    }
  };

  const submitForm = async () => {
    if (!implementedSolution.trim()) {
      setMessage("⚠️ Please describe the implemented solution");
      return;
    }
    const composedRootCause = joinWhys(rootCauseWhys);
    if (countFilledWhys(rootCauseWhys) < 3) {
      setMessage("⚠️ Please fill at least 3 of the 5 Why fields.");
      return;
    }
    const hasExisting = (carData?.documents ?? []).length > 0;
    if (!hasExisting && selectedFiles.length === 0) {
      setMessage("⚠️ Please attach at least one supporting document.");
      return;
    }
    try {
      setLoading(true);
      setMessage("");
      const fd = new FormData();
      fd.append("token", tokenParam);
      fd.append("email", email);
      fd.append("implemented_solution", implementedSolution);
      fd.append("root_cause", composedRootCause);
      fd.append("target_action_type", carData?.action_type || "corrective");
      selectedFiles.forEach((f) => fd.append("files", f));
      const res = await axiosInstance.post("/car/submit", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setCorrectiveDone(true);
      // The immediate section (if any) may still be pending -- only show the
      // full "submitted" screen once nothing is left to do.
      if (!carData?.linked_action || immSubmitted) {
        setStep("submitted");
      }
      setSubmittedDate(res.data.submitted_at);
    } catch (err: unknown) {
      setMessage(extractApiErrorDetail(err) || "Error submitting the form.");
    } finally {
      setLoading(false);
    }
  };

  /* ── immediate action (linked, no 5-Whys) ──────────────────────────────── */
  const handleImmFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    const files = Array.from(e.target.files);
    const invalid = files.filter((f) => f.size > 10 * 1024 * 1024);
    if (invalid.length) {
      setImmMessage(
        `⚠️ File(s) too large: ${invalid.map((f) => f.name).join(", ")}. Max 10 MB.`,
      );
      return;
    }
    setImmFiles((prev) => [...prev, ...files]);
    setImmMessage("");
    e.target.value = "";
  };
  const removeNewImmFile = (i: number) =>
    setImmFiles((prev) => prev.filter((_, idx) => idx !== i));

  const submitImmediateForm = async () => {
    if (!immSolution.trim()) {
      setImmMessage("⚠️ Please describe the immediate/containment action taken");
      return;
    }
    const existingImmDocs = carData?.linked_action?.documents ?? [];
    if (existingImmDocs.length === 0 && immFiles.length === 0) {
      setImmMessage("⚠️ Please attach at least one supporting document.");
      return;
    }
    try {
      setImmLoading(true);
      setImmMessage("");
      const fd = new FormData();
      fd.append("token", tokenParam);
      fd.append("email", email);
      fd.append("implemented_solution", immSolution);
      // The immediate row has no root cause requirement, so root_cause is
      // omitted entirely -- an empty multipart field is indistinguishable
      // from a missing one to the backend's request parser, so sending ""
      // here would 422 before the request even reaches app code.
      fd.append("target_action_type", "immediate");
      immFiles.forEach((f) => fd.append("files", f));
      const res = await axiosInstance.post("/car/submit", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setImmSubmitted(true);
      setImmSubmittedDate(res.data.submitted_at);
      // Corrective side may already be done -- only then show the full
      // "submitted" screen.
      if (correctiveDone) {
        setStep("submitted");
        setSubmittedDate((prev) => prev ?? res.data.submitted_at);
      }
    } catch (err: unknown) {
      setImmMessage(
        extractApiErrorDetail(err) || "Error submitting the immediate action.",
      );
    } finally {
      setImmLoading(false);
    }
  };

  const reassignCar = async () => {
    if (!isValidEmail(reassignEmail)) {
      setReassignMessage(
        "⚠️ Please use an email in the format first.last@example.com",
      );
      return;
    }
    try {
      setReassignLoading(true);
      setReassignMessage("");
      await axiosInstance.post("/car/reassign", {
        token: tokenParam,
        email,
        new_email: reassignEmail,
        reason: reassignReason || undefined,
      });
      setReassignedNow(true);
      setReassignMessage(
        `✅ Reassigned to ${reassignEmail} — they've been notified.`,
      );
    } catch (err: unknown) {
      setReassignMessage(
        extractApiErrorDetail(err) || "Error reassigning this corrective action.",
      );
    } finally {
      setReassignLoading(false);
    }
  };

  const addCc = async () => {
    if (!isValidEmail(ccEmailInput)) {
      setCcMessage(
        "⚠️ Please use an email in the format first.last@example.com",
      );
      return;
    }
    try {
      setCcLoading(true);
      setCcMessage("");
      const res = await axiosInstance.post("/car/add-cc", {
        token: tokenParam,
        email,
        cc_emails: [ccEmailInput],
      });
      setCarData((prev) =>
        prev ? { ...prev, cc_emails: res.data.cc_emails } : prev,
      );
      setCcEmailInput("");
    } catch (err: unknown) {
      setCcMessage(extractApiErrorDetail(err) || "Error adding this address.");
    } finally {
      setCcLoading(false);
    }
  };

  /* ── derived ────────────────────────────────────────────────────────────── */
  const solutionPrefilled = isPrefilled(carData?.implemented_solution);
  const rootCausePrefilled = isPrefilled(carData?.root_cause);
  const existingDocs = carData?.documents ?? [];
  const totalDocCount = existingDocs.length + selectedFiles.length;
  const hasAnyDoc = totalDocCount > 0;
  const canSubmit =
    !loading &&
    !reassignedNow &&
    implementedSolution.trim() &&
    countFilledWhys(rootCauseWhys) >= 3 &&
    hasAnyDoc;

  // Which single section is actually shown: each email button opens a form
  // dedicated to just its own section, not a combined page with both.
  const activeSection: "immediate" | "corrective" =
    carData?.linked_action && sectionParam === "immediate"
      ? "immediate"
      : "corrective";

  /* ════════════════════════════════════════════════════════════════════════ */
  return (
    <div
      className="min-h-screen bg-gradient-to-br from-blue-50 via-teal-50 to-cyan-50 py-12 px-4 sm:px-6 lg:px-8 relative overflow-hidden notranslate"
      translate="no"
    >
      {/* translate="no" / notranslate: the browser's built-in page translator
          (e.g. Edge Translate) rewrites text nodes directly in the DOM,
          which fights with React's reconciliation and can crash mid-submit
          with "NotFoundError: Failed to execute 'removeChild' on 'Node'"
          when a non-English-locale user has the page auto-translated. This
          is the token-based entry point opened from the notification email,
          so it's the page external auditees hit most often. */}
      <div className="absolute inset-0 bg-[url('assets/images/northwind-brushes.jpg')] bg-cover bg-center" />
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-teal-200 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob animation-delay-2000" />
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-80 h-80 bg-cyan-200 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob animation-delay-4000" />
      </div>
      <style>{`
        @keyframes blob{0%,100%{transform:translate(0,0) scale(1)}25%{transform:translate(20px,-20px) scale(1.05)}50%{transform:translate(-20px,20px) scale(.95)}75%{transform:translate(20px,20px) scale(1.05)}}
        .animate-blob{animation:blob 7s infinite}.animation-delay-2000{animation-delay:2s}.animation-delay-4000{animation-delay:4s}
        @keyframes fadeInUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}.fade-in-up{animation:fadeInUp 0.6s ease-out forwards}
      `}</style>

      <div className="max-w-2xl mx-auto relative z-10">
        {/* Header */}
        <div className="text-center mb-8 fade-in-up">
          <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-blue-800 to-blue-900 rounded-2xl mb-4 shadow-lg">
            <svg
              className="w-12 h-12 text-white"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div className="relative inline-block">
            <div className="text-4xl font-bold flex items-center">
              <span className="text-blue-900 uppercase">Northwind</span>
              <span className="text-gray-500">Carbon</span>
            </div>
            <div className="w-full border-t border-gray-300 my-1" />
            <div className="absolute right-0 -bottom-6 text-orange-500 font-semibold tracking-wide">
              SAHEL
            </div>
          </div>
        </div>

        {/* Card */}
        <div
          className="bg-white/90 backdrop-blur-sm rounded-3xl shadow-2xl p-8 sm:p-10 border border-white/20 fade-in-up"
          style={{ animationDelay: "0.2s" }}
        >
          {/* Progress */}
          {step !== "submitted" && (
            <div className="mb-8">
              <div className="flex items-center justify-between mb-2">
                {(["email", "otp", "form"] as const).map((s, i) => (
                  <span
                    key={s}
                    className={`flex items-center gap-2 text-sm font-medium ${step === s ? "text-blue-600" : "text-gray-400"}`}
                  >
                    <span
                      className={`flex items-center justify-center w-8 h-8 rounded-full ${step === s ? "bg-blue-100 text-blue-600" : "bg-gray-100 text-gray-400"}`}
                    >
                      {i + 1}
                    </span>
                    {s.charAt(0).toUpperCase() + s.slice(1)}
                  </span>
                ))}
              </div>
              <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="absolute top-0 left-0 h-full bg-gradient-to-r from-blue-500 to-blue-700 transition-all duration-500 ease-out"
                  style={{
                    width:
                      step === "email"
                        ? "33.33%"
                        : step === "otp"
                          ? "66.66%"
                          : "100%",
                  }}
                />
              </div>
            </div>
          )}

          {/* Alert */}
          {message && (
            <div
              className={`mb-6 p-4 rounded-xl flex items-start gap-3 ${message.includes("✅") ? "bg-blue-50 text-blue-800 border border-blue-200" : message.includes("⚠️") ? "bg-amber-50 text-amber-800 border border-amber-200" : "bg-red-50 text-red-800 border border-red-200"}`}
            >
              <span className="text-xl flex-shrink-0">
                {message.includes("✅")
                  ? "✅"
                  : message.includes("⚠️")
                    ? "⚠️"
                    : "❌"}
              </span>
              <span className="text-sm font-medium">
                {stripAlertIconPrefix(message)}
              </span>
            </div>
          )}

          {/* ══ STEP 1 ══ */}
          {step === "email" && (
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Professional Email Address
                </label>
                <div className="relative">
                  <input
                    type="email"
                    placeholder="elliot.martin@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    onKeyPress={(e) => {
                      if (e.key === "Enter" && isEmailValid && !loading)
                        requestOtp();
                    }}
                    className={`w-full px-4 py-4 pl-12 border-2 rounded-xl focus:outline-none transition-all ${emailError ? "border-red-300 focus:border-red-500 focus:ring-4 focus:ring-red-100" : isEmailValid ? "border-blue-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-100" : "border-gray-200 focus:border-blue-500 focus:ring-4 focus:ring-blue-100"}`}
                    disabled={loading}
                    autoFocus
                  />
                  <div className="absolute left-4 top-1/2 -translate-y-1/2">
                    <svg
                      className="w-5 h-5 text-gray-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                      />
                    </svg>
                  </div>
                  {isEmailValid && (
                    <div className="absolute right-4 top-1/2 -translate-y-1/2">
                      <svg
                        className="w-5 h-5 text-blue-500"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </div>
                  )}
                </div>
                {emailError && (
                  <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                    <svg
                      className="w-4 h-4"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path
                        fillRule="evenodd"
                        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                        clipRule="evenodd"
                      />
                    </svg>
                    {emailError}
                  </p>
                )}
                <p className="mt-2 text-sm text-gray-500">
                  Use your work email address to access the form.
                </p>
              </div>
              <button
                onClick={requestOtp}
                disabled={loading || !isEmailValid}
                className={`w-full py-4 rounded-xl font-semibold text-white transition-all transform ${loading || !isEmailValid ? "bg-gray-300 cursor-not-allowed" : "bg-gradient-to-r from-blue-800 to-blue-900 hover:from-blue-700 hover:to-blue-800 hover:shadow-lg hover:-translate-y-0.5"}`}
              >
                {loading ? (
                  <Spinner label="Verification in progress..." />
                ) : (
                  <BtnLabel label="Continue" icon="arrow" />
                )}
              </button>
            </div>
          )}

          {/* ══ STEP 2 ══ */}
          {step === "otp" && (
            <div className="space-y-6">
              <div className="text-center mb-6">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mb-3">
                  <svg
                    className="w-8 h-8 text-blue-600"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                    />
                  </svg>
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-1">
                  Security Verification
                </h3>
                <p className="text-sm text-gray-600">
                  A 6-digit code has been sent to
                  <br />
                  <span className="font-semibold text-blue-600">{email}</span>
                </p>
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2 text-center">
                  Verification Code
                </label>
                <input
                  type="text"
                  placeholder="000000"
                  value={otp}
                  onChange={(e) =>
                    setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))
                  }
                  onKeyPress={(e) => {
                    if (e.key === "Enter" && otp.length === 6 && !loading)
                      verifyOtp();
                  }}
                  maxLength={6}
                  className="w-full px-4 py-5 border-2 border-gray-200 rounded-xl focus:border-blue-500 focus:ring-4 focus:ring-blue-100 focus:outline-none text-center text-3xl tracking-[0.5em] font-bold transition-all"
                  disabled={loading}
                  autoFocus
                />
                <p className="text-center text-sm text-gray-500 mt-2">
                  Enter the 6-digit code
                </p>
              </div>
              <div className="space-y-3">
                <button
                  onClick={verifyOtp}
                  disabled={loading || otp.length !== 6}
                  className={`w-full py-4 rounded-xl font-semibold text-white transition-all transform ${loading || otp.length !== 6 ? "bg-gray-300 cursor-not-allowed" : "bg-gradient-to-r from-blue-800 to-blue-900 hover:from-blue-700 hover:to-teal-700 hover:shadow-lg hover:-translate-y-0.5"}`}
                >
                  {loading ? (
                    <Spinner label="Verification in progress..." />
                  ) : (
                    "Verify code"
                  )}
                </button>
                <button
                  onClick={() => {
                    setStep("email");
                    setOtp("");
                    setMessage("");
                  }}
                  disabled={loading}
                  className="w-full py-3 rounded-xl font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 transition-colors"
                >
                  ← Return
                </button>
              </div>
            </div>
          )}

          {/* ══ STEP 3 – Form ══ */}
          {step === "form" && carData && (
            <div className="space-y-6">
              {(reassignedNow || carData.reassigned_at) && (
                <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
                  {reassignedNow
                    ? `✅ You've reassigned this corrective action to ${reassignEmail}. No further action is needed from you.`
                    : "This corrective action has already been reassigned and is no longer editable from this link."}
                </div>
              )}
              {/* Portal / AI Assistant callout — this page only handles this
                  one CAR; the portal lists every non-conformity assigned to
                  the auditee and embeds the AI Assistant that helps draft
                  root-cause / corrective-action content. */}
              <a
                href="/auditee-portal"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 rounded-xl border border-teal-200 bg-gradient-to-r from-teal-50 to-cyan-50 px-4 py-3 text-sm text-teal-900 transition-colors hover:from-teal-100 hover:to-cyan-100"
              >
                <svg
                  className="h-5 w-5 flex-shrink-0 text-teal-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-4 4v-4z"
                  />
                </svg>
                <span className="flex-1">
                  <span className="font-semibold">
                    See all your related non-conformities
                  </span>{" "}
                  in your portal and use the AI Assistant to help resolve
                  them.
                </span>
                <span className="flex-shrink-0 font-semibold text-teal-700">
                  Open My Portal →
                </span>
              </a>
              {/* CAR info card */}
              <div className="bg-gradient-to-br from-blue-50 via-blue-50 to-cyan-50 rounded-2xl p-6 space-y-4 border border-blue-200 shadow-lg">
                {carData.immediate_action_required && (
                  <div className="flex items-start gap-2 rounded-xl border-2 border-red-300 bg-red-50 p-4">
                    <svg
                      className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path
                        fillRule="evenodd"
                        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                        clipRule="evenodd"
                      />
                    </svg>
                    <div>
                      <p className="text-sm font-bold text-red-800">
                        Immediate action required
                      </p>
                      <p className="mt-1 text-xs text-red-700">
                        Submit within 24h
                        {carData.submission_due_at
                          ? ` (by ${carData.submission_due_at})`
                          : ""}{" "}
                        · close within 48h
                        {carData.closure_due_at
                          ? ` (by ${carData.closure_due_at})`
                          : ""}
                      </p>
                    </div>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-4">
                  {[
                    ["Audit Number", carData.audit_number],
                    ["Auditee Name", carData.auditee_name],
                    ["Plant", carData.audit_plant],
                    ["Questionnaire", carData.audit_type],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <h3 className="font-semibold text-gray-600 text-xs uppercase tracking-wide mb-1">
                        {label}
                      </h3>
                      <p className="text-gray-900 font-medium">{value}</p>
                    </div>
                  ))}
                </div>
                <div className="border-t border-blue-200/60" />
                <div className="bg-gradient-to-r from-blue-300 to-blue-300 rounded-lg p-4 border border-blue-200">
                  <div className="flex items-start gap-2">
                    <div className="bg-blue-600 rounded p-1.5 flex-shrink-0">
                      <svg
                        className="w-4 h-4 text-white"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </div>
                    <div>
                      <h3 className="font-bold text-gray-900 text-sm mb-1">
                        Reason of the Non-Conformity
                      </h3>
                      <p className="text-gray-700 text-sm leading-relaxed">
                        {carData.reason_why}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-white/60 backdrop-blur-sm rounded-lg p-4 border border-blue-200">
                    <div className="flex items-center gap-2 mb-1">
                      <div className="bg-blue-600 rounded p-1.5">
                        <svg
                          className="w-3.5 h-3.5 text-white"
                          fill="currentColor"
                          viewBox="0 0 20 20"
                        >
                          <path
                            fillRule="evenodd"
                            d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </div>
                      <h3 className="font-bold text-gray-900 text-xs">
                        Due Date
                      </h3>
                    </div>
                    <p className="text-gray-900 font-semibold ml-7">
                      {carData.due_date}
                    </p>
                  </div>
                  <div className="bg-gradient-to-r from-amber-50 to-orange-50 rounded-lg p-4 border border-amber-200 md:col-span-2">
                    <div className="flex items-start gap-2">
                      <div className="bg-amber-600 rounded p-1.5 flex-shrink-0">
                        <svg
                          className="w-4 h-4 text-white"
                          fill="currentColor"
                          viewBox="0 0 20 20"
                        >
                          <path
                            fillRule="evenodd"
                            d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </div>
                      <div>
                        <h3 className="font-bold text-gray-900 text-sm mb-1">
                          Finding
                        </h3>
                        <p className="text-gray-700 text-sm leading-relaxed">
                          {carData.finding}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Corrective Action — its own dedicated view, shown only when
                  the "Fill Corrective Action" link was used (or there's no
                  linked immediate action at all, i.e. today's single-form
                  CARs, unchanged). */}
              {(!carData.linked_action || activeSection === "corrective") && (
                <>
                  {carData.linked_action && (
                    <div className="rounded-2xl border-2 border-blue-200 bg-blue-50/40 p-4 sm:p-5">
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="text-base font-bold text-blue-900">
                          Corrective Action — Root Cause Fix
                        </h3>
                        <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700 whitespace-nowrap">
                          Due {carData.due_date}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-blue-800">
                        This is the permanent fix for the root cause of this
                        finding.
                      </p>
                      <button
                        type="button"
                        onClick={() => switchSection("immediate")}
                        className="mt-2 text-xs font-semibold text-blue-700 underline decoration-blue-300 underline-offset-2 hover:text-blue-900"
                      >
                        Need to fill the Immediate / Containment Action
                        instead? Switch here →
                      </button>
                    </div>
                  )}

                  {/* Pre-fill notice */}
              {(solutionPrefilled || rootCausePrefilled) && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-start gap-3">
                  <svg
                    className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                      clipRule="evenodd"
                    />
                  </svg>
                  <p className="text-sm text-blue-800 font-medium">
                    Your previous answers have been pre-filled below. Review and
                    update them if needed before resubmitting.
                  </p>
                </div>
              )}

              {/* Root Cause */}
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:p-5 shadow-sm">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <label className="block text-sm font-bold text-gray-900">
                    Root Cause - 5 Whys *
                    {rootCausePrefilled && (
                      <span className="ml-2 text-xs font-normal text-blue-600 bg-blue-100 px-2 py-0.5 rounded-full">
                        Pre-filled
                      </span>
                    )}
                  </label>
                  <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700">
                    {countFilledWhys(rootCauseWhys)}/5 filled
                  </span>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {rootCauseWhys.map((why, index) => (
                    <div
                      key={index}
                      className={index === 4 ? "sm:col-span-2" : ""}
                    >
                      <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Why {index + 1}
                      </label>
                      <input
                        type="text"
                        value={why}
                        onChange={(e) => {
                          const next = [...rootCauseWhys];
                          next[index] = e.target.value;
                          setRootCauseWhys(next);
                        }}
                        placeholder={`Cause detail for Why ${index + 1}`}
                        className={`w-full px-4 py-4 border-2 rounded-xl focus:outline-none transition-all focus:ring-4 ${rootCausePrefilled ? "border-blue-300 focus:border-blue-500 focus:ring-blue-100 bg-blue-50/40" : "border-gray-200 focus:border-blue-500 focus:ring-blue-100"}`}
                        disabled={loading}
                      />
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap justify-between gap-2 mt-2">
                  <p className="text-xs text-gray-500">
                    Fill at least Why 1, Why 2, and Why 3. Five entries are
                    available for a full 5 Whys.
                  </p>
                  <p
                    className={`text-xs font-medium ${countFilledWhys(rootCauseWhys) < 3 ? "text-amber-600" : "text-blue-600"}`}
                  >
                    {countFilledWhys(rootCauseWhys)} Why lines
                  </p>
                </div>
              </div>

              {/* Implemented Solution */}
              <div>
                <label className="block text-sm font-bold text-gray-900 mb-1">
                  Implemented Solution *
                  {solutionPrefilled && (
                    <span className="ml-2 text-xs font-normal text-blue-600 bg-blue-100 px-2 py-0.5 rounded-full">
                      Pre-filled
                    </span>
                  )}
                </label>
                <textarea
                  value={implementedSolution}
                  onChange={(e) => setImplementedSolution(e.target.value)}
                  rows={5}
                  placeholder={`Describe in detail the actions taken…\nExample:\n- Actions taken\n- People involved\n- Implementation timeline\n- Expected outcomes`}
                  className={`w-full px-4 py-4 border-2 rounded-xl focus:outline-none resize-none transition-all focus:ring-4 ${solutionPrefilled ? "border-blue-300 focus:border-blue-500 focus:ring-blue-100 bg-blue-50/40" : "border-gray-200 focus:border-blue-500 focus:ring-blue-100"}`}
                  disabled={loading}
                />
                <div className="flex justify-between mt-1">
                  <p className="text-xs text-gray-500">
                    Describe the actions taken to address the issue.
                  </p>
                  <p
                    className={`text-xs font-medium ${implementedSolution.length < 50 ? "text-gray-400" : "text-blue-600"}`}
                  >
                    {implementedSolution.length} characters
                  </p>
                </div>
              </div>

              {/* ══ Documents — unified section ══ */}
              <div>
                {/* Section header */}
                <div className="flex items-center justify-between mb-3">
                  <label className="text-sm font-bold text-gray-900">
                    Justify the implemented solution with supporting documents *
                  </label>
                  {hasAnyDoc && (
                    <span className="text-xs font-semibold text-blue-700 bg-blue-100 px-2.5 py-1 rounded-full">
                      {totalDocCount} file{totalDocCount !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>

                {/* Already-uploaded files (from server) */}
                {existingDocs.length > 0 && (
                  <div className="mb-3">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <svg
                        className="w-3.5 h-3.5"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                          clipRule="evenodd"
                        />
                      </svg>
                      Already uploaded
                    </p>
                    <div className="space-y-2">
                      {existingDocs.map((doc) => (
                        <div
                          key={doc.id}
                          className="flex items-center gap-3 bg-white border border-blue-200 rounded-xl px-4 py-3 shadow-sm"
                        >
                          <FileIcon
                            filename={doc.filename}
                            className="w-5 h-5 flex-shrink-0"
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 truncate">
                              {doc.filename}
                            </p>
                            <p className="text-xs text-gray-400">
                              {formatFileSize(doc.size)}
                              {doc.uploaded_at ? ` · ${doc.uploaded_at}` : ""}
                            </p>
                          </div>
                          <a
                            href={doc.file_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Open"
                            className="flex-shrink-0 text-blue-500 hover:text-blue-700 p-1.5 rounded-lg hover:bg-blue-50 transition-colors"
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
                                d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                              />
                            </svg>
                          </a>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Newly selected files (pending upload) */}
                {selectedFiles.length > 0 && (
                  <div className="mb-3">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <svg
                        className="w-3.5 h-3.5 text-green-500"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
                        />
                      </svg>
                      Ready to upload
                    </p>
                    <div className="space-y-2">
                      {selectedFiles.map((file, idx) => (
                        <div
                          key={idx}
                          className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl px-4 py-3"
                        >
                          <FileIcon
                            filename={file.name}
                            className="w-5 h-5 flex-shrink-0"
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 truncate">
                              {file.name}
                            </p>
                            <p className="text-xs text-gray-400">
                              {formatFileSize(file.size)}
                            </p>
                          </div>
                          <button
                            onClick={() => removeNewFile(idx)}
                            disabled={loading}
                            className="flex-shrink-0 text-red-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-red-50 transition-colors"
                            title="Remove"
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
                                d="M6 18L18 6M6 6l12 12"
                              />
                            </svg>
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Drop zone */}
                <label
                  className={`w-full flex flex-col items-center px-4 py-6 border-2 border-dashed rounded-xl cursor-pointer transition-all ${loading ? "opacity-50 cursor-not-allowed" : "hover:border-blue-500 hover:bg-blue-50"} ${hasAnyDoc ? "border-gray-200 bg-white" : "border-amber-300 bg-amber-50/30"}`}
                >
                  <svg
                    className={`w-9 h-9 ${hasAnyDoc ? "text-gray-400" : "text-amber-400"}`}
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
                  <span className="mt-2 text-sm font-medium text-gray-600">
                    {hasAnyDoc
                      ? "Add more files"
                      : "Click to upload supporting documents"}
                  </span>
                  <span className="mt-1 text-xs text-gray-400">
                    PDF, JPG, PNG, DOC, XLS — max 10 MB each
                  </span>
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx"
                    onChange={handleFileSelect}
                    className="hidden"
                    disabled={loading}
                  />
                </label>

                {!hasAnyDoc && (
                  <p className="mt-2 text-xs text-amber-600 flex items-center gap-1.5">
                    <svg
                      className="w-4 h-4 flex-shrink-0"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path
                        fillRule="evenodd"
                        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                        clipRule="evenodd"
                      />
                    </svg>
                    At least one supporting document is required before
                    submitting.
                  </p>
                )}
              </div>

              {/* Submit */}
              <button
                onClick={submitForm}
                disabled={!canSubmit}
                className={`w-full py-4 rounded-xl font-semibold text-white transition-all transform ${!canSubmit ? "bg-gray-300 cursor-not-allowed" : "bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700 hover:shadow-lg hover:-translate-y-0.5"}`}
              >
                {loading ? (
                  <Spinner label="Submission in progress..." />
                ) : (
                  <BtnLabel label="Submit Solution" icon="check" />
                )}
              </button>
                </>
              )}

              {/* ══ Immediate / Containment Action — its own dedicated view,
                  shown only when the "Fill Immediate Action" link was used ══ */}
              {carData.linked_action && activeSection === "immediate" && (
                <div className="rounded-2xl border-2 border-red-200 bg-red-50/40 p-5 sm:p-6 space-y-4">
                  <button
                    type="button"
                    onClick={() => switchSection("corrective")}
                    className="text-xs font-semibold text-red-700 underline decoration-red-300 underline-offset-2 hover:text-red-900"
                  >
                    ← Need to fill the Corrective Action instead? Switch here
                  </button>
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-base font-bold text-red-900">
                      Immediate / Containment Action — due within 48h
                    </h3>
                    {carData.linked_action.closure_due_at && (
                      <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-700 whitespace-nowrap">
                        Close by {carData.linked_action.closure_due_at}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-red-800">
                    Describe the immediate containment action taken to control
                    the issue right away. No root-cause analysis is required
                    here — that's the separate Corrective Action.
                  </p>

                  {immSubmitted ? (
                    <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
                      ✅ Immediate action submitted
                      {immSubmittedDate ? ` on ${immSubmittedDate}` : ""}.
                    </div>
                  ) : (
                    <>
                      {immMessage && (
                        <p className="text-xs font-medium text-amber-700">
                          {stripAlertIconPrefix(immMessage)}
                        </p>
                      )}
                      <div>
                        <label className="block text-sm font-bold text-gray-900 mb-1">
                          Immediate Action Taken *
                        </label>
                        <textarea
                          value={immSolution}
                          onChange={(e) => setImmSolution(e.target.value)}
                          rows={4}
                          placeholder="Describe the immediate/containment action taken to control the issue…"
                          className="w-full px-4 py-4 border-2 border-gray-200 rounded-xl focus:outline-none resize-none transition-all focus:ring-4 focus:border-red-500 focus:ring-red-100"
                          disabled={immLoading}
                        />
                      </div>

                      {(carData.linked_action.documents.length > 0 ||
                        immFiles.length > 0) && (
                        <div className="space-y-2">
                          {carData.linked_action.documents.map((doc) => (
                            <div
                              key={doc.id}
                              className="flex items-center gap-3 bg-white border border-red-200 rounded-xl px-4 py-3 shadow-sm"
                            >
                              <FileIcon
                                filename={doc.filename}
                                className="w-5 h-5 flex-shrink-0"
                              />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-gray-900 truncate">
                                  {doc.filename}
                                </p>
                                <p className="text-xs text-gray-400">
                                  {formatFileSize(doc.size)}
                                </p>
                              </div>
                            </div>
                          ))}
                          {immFiles.map((file, idx) => (
                            <div
                              key={idx}
                              className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl px-4 py-3"
                            >
                              <FileIcon
                                filename={file.name}
                                className="w-5 h-5 flex-shrink-0"
                              />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-gray-900 truncate">
                                  {file.name}
                                </p>
                                <p className="text-xs text-gray-400">
                                  {formatFileSize(file.size)}
                                </p>
                              </div>
                              <button
                                onClick={() => removeNewImmFile(idx)}
                                disabled={immLoading}
                                className="flex-shrink-0 text-red-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-red-50 transition-colors"
                                title="Remove"
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
                                    d="M6 18L18 6M6 6l12 12"
                                  />
                                </svg>
                              </button>
                            </div>
                          ))}
                        </div>
                      )}

                      <label
                        className={`w-full flex flex-col items-center px-4 py-5 border-2 border-dashed rounded-xl cursor-pointer transition-all ${immLoading ? "opacity-50 cursor-not-allowed" : "hover:border-red-500 hover:bg-red-50"} border-red-200 bg-white`}
                      >
                        <span className="text-sm font-medium text-gray-600">
                          Click to upload supporting documents
                        </span>
                        <span className="mt-1 text-xs text-gray-400">
                          PDF, JPG, PNG, DOC, XLS — max 10 MB each
                        </span>
                        <input
                          type="file"
                          multiple
                          accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx"
                          onChange={handleImmFileSelect}
                          className="hidden"
                          disabled={immLoading}
                        />
                      </label>

                      <button
                        onClick={submitImmediateForm}
                        disabled={
                          immLoading ||
                          !immSolution.trim() ||
                          (carData.linked_action.documents.length === 0 &&
                            immFiles.length === 0)
                        }
                        className={`w-full py-3.5 rounded-xl font-semibold text-white transition-all transform ${immLoading || !immSolution.trim() || (carData.linked_action.documents.length === 0 && immFiles.length === 0) ? "bg-gray-300 cursor-not-allowed" : "bg-gradient-to-r from-red-600 to-orange-600 hover:from-red-700 hover:to-orange-700 hover:shadow-lg hover:-translate-y-0.5"}`}
                      >
                        {immLoading ? (
                          <Spinner label="Submission in progress..." />
                        ) : (
                          <BtnLabel label="Submit Immediate Action" icon="check" />
                        )}
                      </button>
                    </>
                  )}
                </div>
              )}

              {/* Reassign responsible */}
              {carData.can_reassign && !reassignedNow && (
                <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-5 space-y-3">
                  <h3 className="text-sm font-semibold text-amber-900">
                    Not your responsibility?
                  </h3>
                  <p className="text-xs text-amber-800">
                    You can reassign this corrective action to someone else.
                    This can only be done once.
                  </p>
                  <input
                    type="email"
                    value={reassignEmail}
                    onChange={(e) => setReassignEmail(e.target.value)}
                    placeholder="first.last@example.com"
                    disabled={reassignLoading}
                    className="w-full p-2.5 text-sm border border-amber-300 rounded-lg bg-white"
                  />
                  <textarea
                    value={reassignReason}
                    onChange={(e) => setReassignReason(e.target.value)}
                    placeholder="Reason (optional)"
                    rows={2}
                    disabled={reassignLoading}
                    className="w-full p-2.5 text-sm border border-amber-300 rounded-lg bg-white resize-none"
                  />
                  {reassignMessage && (
                    <p className="text-xs text-amber-900">{reassignMessage}</p>
                  )}
                  <button
                    onClick={reassignCar}
                    disabled={reassignLoading || !reassignEmail.trim()}
                    className="w-full py-2.5 rounded-lg font-medium text-sm text-white bg-amber-600 hover:bg-amber-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                  >
                    {reassignLoading ? "Reassigning..." : "Reassign"}
                  </button>
                </div>
              )}
              {!carData.can_reassign && carData.reassigned_from_email && (
                <p className="text-xs text-gray-500">
                  Originally assigned to {carData.reassigned_from_email}
                </p>
              )}

              {/* Add someone in copy */}
              <div className="rounded-2xl border border-gray-200 bg-gray-50 p-5 space-y-3">
                <h3 className="text-sm font-semibold text-gray-800">
                  Add someone in copy
                </h3>
                <p className="text-xs text-gray-600">
                  They'll be kept informed of updates on this corrective action,
                  without needing to take action.
                </p>
                {carData.cc_emails.length > 0 && (
                  <ul className="text-xs text-gray-700 space-y-1">
                    {carData.cc_emails.map((cc) => (
                      <li key={cc} className="flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
                        {cc}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="flex gap-2">
                  <input
                    type="email"
                    value={ccEmailInput}
                    onChange={(e) => setCcEmailInput(e.target.value)}
                    placeholder="first.last@example.com"
                    disabled={ccLoading}
                    className="flex-1 p-2.5 text-sm border border-gray-300 rounded-lg bg-white"
                  />
                  <button
                    onClick={addCc}
                    disabled={ccLoading || !ccEmailInput.trim()}
                    className="px-4 py-2.5 rounded-lg font-medium text-sm text-white bg-gray-700 hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                  >
                    {ccLoading ? "Adding..." : "Add"}
                  </button>
                </div>
                {ccMessage && (
                  <p className="text-xs text-gray-700">{ccMessage}</p>
                )}
              </div>
            </div>
          )}

          {/* ══ STEP 4 – Submitted ══ */}
          {step === "submitted" && (
            <div className="text-center space-y-6 py-8">
              <div className="inline-flex items-center justify-center w-24 h-24 bg-gradient-to-br from-blue-800 to-blue-900 rounded-full mb-4">
                <svg
                  className="w-14 h-14 text-blue-200"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={3}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
              <div>
                <h3 className="text-3xl font-bold text-gray-900 mb-2">
                  Form submitted
                </h3>
                <p className="text-gray-600">
                  Your corrective action has been recorded on{" "}
                  <span className="font-bold text-blue-600">
                    {submittedDate}
                  </span>
                </p>
              </div>
              {(implementedSolution || carData?.implemented_solution) && (
                <div className="bg-gray-50 rounded-2xl p-6 text-left border border-gray-200">
                  <h4 className="font-bold text-gray-900 mb-3">
                    Solution submitted
                  </h4>
                  <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
                    {implementedSolution || carData?.implemented_solution}
                  </p>
                </div>
              )}
              {carData?.documents && carData.documents.length > 0 && (
                <div className="bg-gray-50 rounded-2xl p-6 text-left border border-gray-200">
                  <h4 className="font-bold text-gray-900 mb-3">
                    Attached documents ({carData.documents.length})
                  </h4>
                  <div className="space-y-2">
                    {carData.documents.map((doc) => (
                      <div
                        key={doc.id}
                        className="flex items-center gap-3 bg-white p-3 rounded-lg border border-gray-100"
                      >
                        <FileIcon filename={doc.filename} />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">
                            {doc.filename}
                          </p>
                          <p className="text-xs text-gray-500">
                            {formatFileSize(doc.size)}
                          </p>
                        </div>
                        <a
                          href={doc.file_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 p-1.5 rounded hover:bg-blue-50"
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
                              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                            />
                          </svg>
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {carData?.linked_action && (
                <div className="bg-red-50 rounded-2xl p-6 text-left border border-red-200">
                  <h4 className="font-bold text-gray-900 mb-3">
                    Immediate action
                    {immSubmitted || carData.linked_action.is_submitted
                      ? " — submitted"
                      : " — still pending"}
                  </h4>
                  {(immSolution || carData.linked_action.implemented_solution) ? (
                    <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
                      {immSolution || carData.linked_action.implemented_solution}
                    </p>
                  ) : (
                    <p className="text-sm text-red-800">
                      The immediate/containment action for this finding has not
                      been submitted yet — use the link from your email to
                      complete it.
                    </p>
                  )}
                </div>
              )}
              <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4 flex items-start gap-3">
                <svg
                  className="w-6 h-6 text-blue-600 flex-shrink-0 mt-0.5"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                    clipRule="evenodd"
                  />
                </svg>
                <p className="text-sm text-blue-800 font-medium text-left">
                  If you need to modify your response, please contact the
                  Northwind Quality team.
                </p>
              </div>
            </div>
          )}
        </div>
        <div className="text-center mt-8">
          <p className="text-sm text-white">
            © 2025 Northwind - Audit Track - équipe Qualité
          </p>
        </div>
      </div>
    </div>
  );
};

const Spinner: React.FC<{ label: string }> = ({ label }) => (
  <span className="flex items-center justify-center gap-2">
    <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
    {label}
  </span>
);
const BtnLabel: React.FC<{ label: string; icon: "arrow" | "check" }> = ({
  label,
  icon,
}) => (
  <span className="flex items-center justify-center gap-2">
    {label}
    {icon === "arrow" ? (
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 7l5 5m0 0l-5 5m5-5H6"
        />
      </svg>
    ) : (
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M5 13l4 4L19 7"
        />
      </svg>
    )}
  </span>
);
