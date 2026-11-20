// components/modals/AuditCARsModal.tsx

import { useEffect, useState, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useSelector } from "react-redux";
import {
  XMarkIcon,
  PaperClipIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  ChevronDownIcon,
  ArrowDownTrayIcon,
  MagnifyingGlassPlusIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from "@heroicons/react/24/outline";
import axiosInstance from "../../services/axiosInstance";
import { CorrectiveAction } from "../../types";
import { RootState } from "../../redux/store";

/* ─── Types ─────────────────────────────────────────────── */
interface DocumentItem {
  id: number;
  filename: string;
  file_url: string;
  size: number;
  uploaded_at?: string | null;
  document_type?: "finding_evidence" | "car_solution";
}

interface AuditCARsModalProps {
  auditId: number;
  auditNumber: string;
  onClose: () => void;
}

/* ─── Constants ─────────────────────────────────────────── */
const STATUS_META: Record<
  string,
  { bg: string; text: string; ring: string; dot: string }
> = {
  Pending: {
    bg: "bg-amber-50 dark:bg-amber-900/20",
    text: "text-amber-700 dark:text-amber-400",
    ring: "ring-amber-300 dark:ring-amber-700/50",
    dot: "bg-amber-400",
  },
  Submitted: {
    bg: "bg-[#064273]/10 dark:bg-[#064273]/30",
    text: "text-[#064273] dark:text-blue-200",
    ring: "ring-[#064273]/25 dark:ring-[#77b7de]/35",
    dot: "bg-[#0a588a]",
  },
  Accepted: {
    bg: "bg-emerald-50 dark:bg-emerald-900/20",
    text: "text-emerald-700 dark:text-emerald-400",
    ring: "ring-emerald-300 dark:ring-emerald-700/50",
    dot: "bg-emerald-500",
  },
  Rejected: {
    bg: "bg-rose-50 dark:bg-rose-900/20",
    text: "text-rose-700 dark:text-rose-400",
    ring: "ring-rose-300 dark:ring-rose-700/50",
    dot: "bg-rose-500",
  },
};

const FINDING_META: Record<
  string,
  { bg: string; text: string; border: string }
> = {
  FAIL: {
    bg: "bg-rose-50 dark:bg-rose-900/20",
    text: "text-rose-700 dark:text-rose-400",
    border: "border-rose-300 dark:border-rose-700/50",
  },
  IMPROVE: {
    bg: "bg-amber-50 dark:bg-amber-900/20",
    text: "text-amber-700 dark:text-amber-400",
    border: "border-amber-300 dark:border-amber-700/50",
  },
  PASS: {
    bg: "bg-emerald-50 dark:bg-emerald-900/20",
    text: "text-emerald-700 dark:text-emerald-400",
    border: "border-emerald-300 dark:border-emerald-700/50",
  },
};

/* ─── Helpers ───────────────────────────────────────────── */
function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isImage(filename: string) {
  return /\.(png|jpe?g|gif|webp|svg)$/i.test(filename);
}

function isPDF(filename: string) {
  return /\.pdf$/i.test(filename);
}

function splitDocumentsByType(documents: DocumentItem[]) {
  const findingEvidence = documents.filter(
    (d) => d.document_type === "finding_evidence",
  );
  const carSolution = documents.filter(
    (d) => d.document_type !== "finding_evidence",
  );
  return { findingEvidence, carSolution };
}

function getFileIcon(filename: string) {
  if (isPDF(filename)) return "📄";
  if (isImage(filename)) return "🖼";
  if (/\.(xlsx?|csv)$/i.test(filename)) return "📊";
  if (/\.(docx?)$/i.test(filename)) return "📝";
  return "📎";
}

/* ─── Sub-components ─────────────────────────────────────── */

function StatusPill({ status }: { status: string }) {
  const m = STATUS_META[status];
  if (!m)
    return (
      <span className="text-xs text-gray-400 dark:text-gray-500">{status}</span>
    );
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${m.bg} ${m.text} ${m.ring}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${m.dot}`} />
      {status}
    </span>
  );
}

function FindingBadge({ type }: { type: string | null | undefined }) {
  if (!type) return null;
  const m = FINDING_META[type] ?? {
    bg: "bg-[#064273]/10 dark:bg-[#064273]/30",
    text: "text-[#064273] dark:text-blue-200",
    border: "border-[#064273]/25 dark:border-[#77b7de]/35",
  };
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[10.5px] font-bold tracking-wider ${m.bg} ${m.text} ${m.border}`}
    >
      {type}
    </span>
  );
}

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-xl border border-[#064273]/10 bg-white p-5 dark:border-[#064273]/35 dark:bg-slate-900">
      <div className="mb-4 flex items-center gap-3">
        <div className="h-4 w-24 rounded bg-[#064273]/10 dark:bg-[#064273]/35" />
        <div className="h-4 w-16 rounded bg-[#064273]/10 dark:bg-[#064273]/35" />
        <div className="ml-auto h-4 w-20 rounded bg-[#064273]/10 dark:bg-[#064273]/35" />
      </div>
      <div className="mb-2 h-3 w-full rounded bg-gray-100 dark:bg-gray-800" />
      <div className="h-3 w-3/4 rounded bg-gray-100 dark:bg-gray-800" />
    </div>
  );
}

/* ─── Document Preview Lightbox ─────────────────────────── */
function DocumentLightbox({
  docs,
  initialIndex,
  onClose,
}: {
  docs: DocumentItem[];
  initialIndex: number;
  onClose: () => void;
}) {
  const [idx, setIdx] = useState(initialIndex);
  const doc = docs[idx];

  const prev = useCallback(() => setIdx((i) => Math.max(0, i - 1)), []);
  const next = useCallback(
    () => setIdx((i) => Math.min(docs.length - 1, i + 1)),
    [docs.length],
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") prev();
      if (e.key === "ArrowRight") next();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose, prev, next]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      // ↑ sits above modal (100001) and header (99999)
      className="fixed inset-0 z-[100002] flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.93, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.93, opacity: 0 }}
        transition={{ duration: 0.18, ease: "easeOut" }}
        onClick={(e) => e.stopPropagation()}
        className="relative flex w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-gray-950 shadow-2xl"
        style={{ maxHeight: "90vh" }}
      >
        {/* ── Header bar ── */}
        <div className="flex shrink-0 items-center gap-3 border-b border-white/10 bg-gray-900 px-4 py-3">
          <span className="text-xl leading-none">
            {getFileIcon(doc.filename)}
          </span>

          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-white">
              {doc.filename}
            </p>
            <p className="text-xs text-gray-400">{formatBytes(doc.size)}</p>
          </div>

          {/* Nav + actions always visible, never clipped */}
          <div className="flex shrink-0 items-center gap-1.5">
            {docs.length > 1 && (
              <>
                <button
                  onClick={prev}
                  disabled={idx === 0}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 transition hover:bg-white/10 hover:text-white disabled:opacity-30"
                  title="Previous (←)"
                >
                  <ChevronLeftIcon className="h-4 w-4" />
                </button>
                <span className="min-w-[36px] text-center text-xs tabular-nums text-gray-400">
                  {idx + 1}/{docs.length}
                </span>
                <button
                  onClick={next}
                  disabled={idx === docs.length - 1}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 transition hover:bg-white/10 hover:text-white disabled:opacity-30"
                  title="Next (→)"
                >
                  <ChevronRightIcon className="h-4 w-4" />
                </button>
                {/* Divider */}
                <span className="mx-1 h-5 w-px bg-white/10" />
              </>
            )}

            {/* Download */}
            <a
              href={doc.file_url}
              download={doc.filename}
              target="_blank"
              rel="noopener noreferrer"
              className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 transition hover:bg-white/10 hover:text-white"
              title="Download"
            >
              <ArrowDownTrayIcon className="h-4 w-4" />
            </a>

            {/* ── Close — high contrast, impossible to miss ── */}
            <button
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15 text-white ring-1 ring-white/20 transition hover:bg-white/25 hover:ring-white/40"
              title="Close (Esc)"
            >
              <XMarkIcon className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* ── Preview area ── */}
        <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-gray-900 p-4">
          {isPDF(doc.filename) ? (
            <iframe
              src={doc.file_url}
              title={doc.filename}
              className="h-[62vh] w-full rounded-lg border border-white/10"
            />
          ) : isImage(doc.filename) ? (
            <img
              src={doc.file_url}
              alt={doc.filename}
              className="max-h-[70vh] max-w-full rounded-lg object-contain"
            />
          ) : (
            <div className="flex flex-col items-center gap-4 py-16 text-center">
              <span className="text-6xl">{getFileIcon(doc.filename)}</span>
              <p className="text-sm text-gray-300">{doc.filename}</p>
              <p className="text-xs text-gray-500">
                Preview not available for this file type.
              </p>
              <a
                href={doc.file_url}
                download={doc.filename}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-[#064273] to-[#0a4f7f] px-4 py-2 text-sm font-semibold text-white transition hover:from-[#05375f] hover:to-[#064273]"
              >
                <ArrowDownTrayIcon className="h-4 w-4" />
                Download file
              </a>
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Document Strip ─────────────────────────────────────── */
function DocumentStrip({
  title,
  documents,
  onPreview,
}: {
  title: string;
  documents: DocumentItem[];
  onPreview: (doc: DocumentItem) => void;
}) {
  if (!documents.length) return null;

  return (
    <div className="mt-4">
      <p className="mb-2.5 text-[10px] font-bold uppercase tracking-widest text-[#355f7f] dark:text-blue-200/85">
        {title} ({documents.length})
      </p>
      <div className="flex flex-wrap gap-2">
        {documents.map((doc, i) => (
          <button
            key={`doc-${doc.id ?? "na"}-${doc.filename ?? "file"}-${i}`}
            onClick={() => onPreview(doc)}
            title={doc.filename}
            className="group relative flex items-center gap-2.5 overflow-hidden rounded-xl border border-[#064273]/10 bg-white py-2 pl-3 pr-4 text-left shadow-sm transition hover:border-[#064273]/30 hover:shadow-md dark:border-[#064273]/35 dark:bg-slate-800 dark:hover:border-[#77b7de]/40"
          >
            {/* Thumbnail for images, icon otherwise */}
            <div className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-[#064273]/10 dark:bg-[#064273]/30">
              {isImage(doc.filename) ? (
                <img
                  src={doc.file_url}
                  alt=""
                  className="h-full w-full object-cover"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              ) : (
                <span className="text-base leading-none">
                  {getFileIcon(doc.filename)}
                </span>
              )}
            </div>

            <div className="min-w-0">
              <p className="max-w-[140px] truncate text-xs font-semibold text-gray-700 dark:text-gray-200">
                {doc.filename}
              </p>
              <p className="text-[10px] text-gray-400 dark:text-gray-500">
                {formatBytes(doc.size)}
              </p>
            </div>

            {/* Hover overlay */}
            <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-[#064273]/0 transition group-hover:bg-[#064273]/10">
              <MagnifyingGlassPlusIcon className="h-4 w-4 scale-0 text-[#064273] transition group-hover:scale-100 dark:text-blue-200" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ─── CAR Card ───────────────────────────────────────────── */
function CARCard({
  car,
  isAuditor,
}: {
  car: CorrectiveAction;
  isAuditor: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const docs = useMemo(
    () => (car.documents ?? []) as DocumentItem[],
    [car.documents],
  );
  const { findingEvidence, carSolution } = splitDocumentsByType(docs);
  const visibleDocs = isAuditor ? docs : carSolution;
  const handlePreviewDoc = useCallback(
    (doc: DocumentItem) => {
      const index = visibleDocs.findIndex((d) => d.id === doc.id);
      if (index >= 0) setLightboxIndex(index);
    },
    [visibleDocs],
  );

  const hasDetail =
    car.root_cause ||
    car.implemented_solution ||
    (isAuditor && car.finding_text) ||
    car.reason_why ||
    car.process ||
    car.standard_paragraph ||
    car.classification;

  return (
    <>
      <div className="overflow-hidden rounded-xl border border-[#064273]/10 bg-white shadow-sm transition hover:shadow-md dark:border-[#064273]/35 dark:bg-slate-900">
        {/* Card header */}
        <div className="flex items-start gap-3 px-5 py-4">
          {/* Left accent */}
          <div
            className={`mt-0.5 h-full w-1 self-stretch rounded-full ${
              car.status === "Accepted"
                ? "bg-emerald-400"
                : car.status === "Rejected"
                  ? "bg-rose-400"
                  : car.status === "Submitted"
                    ? "bg-[#0a588a]"
                    : "bg-amber-400"
            }`}
          />

          <div className="flex min-w-0 flex-1 flex-col gap-2">
            {/* Top row: ID + finding + status */}
            <div className="flex flex-wrap items-center gap-2">
              {car.identifier ? (
                <span className="font-mono text-xs font-bold text-[#064273] dark:text-blue-200">
                  {car.identifier}
                </span>
              ) : (
                <span className="font-mono text-xs text-[#0a588a] dark:text-blue-300/80">
                  #{car.id}
                </span>
              )}
              <FindingBadge type={car.finding_type} />
              {car.escalated && (
                <span className="inline-flex items-center gap-1 rounded-full border border-rose-300 bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-600 dark:border-rose-800/40 dark:bg-rose-900/20 dark:text-rose-400">
                  <ExclamationTriangleIcon className="h-3 w-3" />
                  Escalated
                </span>
              )}
              <div className="ml-auto">
                <StatusPill status={car.status} />
              </div>
            </div>

            {/* Question / Action text */}
            {car.corrective_action && (
              <p className="text-sm leading-relaxed text-gray-700 dark:text-gray-300">
                {car.corrective_action}
              </p>
            )}

            {/* Meta row */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
              {car.auditee && <span>Auditee: {car.auditee}</span>}
              {car.due_date && <span>Due: {car.due_date}</span>}
              {car.process && <span>Process: {car.process}</span>}
              {car.chapter && <span>Chapter: {car.chapter}</span>}
            </div>
          </div>
        </div>

        {/* Expandable detail */}
        {(hasDetail || visibleDocs.length > 0) && (
          <>
            <button
              onClick={() => setExpanded((v) => !v)}
              className="flex w-full items-center justify-between border-t border-[#064273]/10 px-5 py-2.5 text-left transition hover:bg-[#064273]/[0.06] dark:border-[#064273]/35 dark:hover:bg-[#064273]/15"
            >
              <span className="flex items-center gap-2 text-xs font-semibold text-[#064273] dark:text-blue-200">
                {visibleDocs.length > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <PaperClipIcon className="h-3.5 w-3.5" />
                    {visibleDocs.length} file{visibleDocs.length !== 1 ? "s" : ""}
                  </span>
                )}
                {hasDetail && (
                  <span className="text-[#355f7f] dark:text-blue-200/85">
                    {docs.length > 0 ? "· " : ""}Details
                  </span>
                )}
              </span>
              <motion.span
                animate={{ rotate: expanded ? 180 : 0 }}
                transition={{ duration: 0.2 }}
                className="text-[#064273] dark:text-blue-200"
              >
                <ChevronDownIcon className="h-4 w-4" />
              </motion.span>
            </button>

            <AnimatePresence initial={false}>
              {expanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2, ease: "easeInOut" }}
                  className="overflow-hidden"
                >
                  <div className="border-t-2 border-[#064273]/15 bg-[#f4f9fd] px-5 py-4 dark:border-[#064273]/35 dark:bg-[#064273]/14">
                    {/* Text fields grid */}
                    {hasDetail && (
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        {isAuditor && car.finding_text && (
                          <TextBlock label="Finding" value={car.finding_text} />
                        )}
                        {car.reason_why && (
                          <TextBlock
                            label="Reason why"
                            value={car.reason_why}
                          />
                        )}
                        {car.root_cause && (
                          <TextBlock
                            label="Root cause"
                            value={car.root_cause}
                          />
                        )}
                        {car.implemented_solution && (
                          <TextBlock
                            label="Implemented solution"
                            value={car.implemented_solution}
                          />
                        )}
                        {car.standard_paragraph && (
                          <TextBlock
                            label="Standard section"
                            value={car.standard_paragraph}
                          />
                        )}
                        {car.classification && (
                          <TextBlock
                            label="Classification"
                            value={car.classification}
                          />
                        )}
                      </div>
                    )}

                    {/* Documents */}
                    {isAuditor && (
                      <DocumentStrip
                        title="Finding evidence"
                        documents={findingEvidence}
                        onPreview={handlePreviewDoc}
                      />
                    )}
                    <DocumentStrip
                      title="CAR solution attachments"
                      documents={carSolution}
                      onPreview={handlePreviewDoc}
                    />

                    {/* Rejection reason */}
                    {car.status === "Rejected" && car.review_comment && (
                      <div className="mt-4 flex gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-800/40 dark:bg-rose-900/20">
                        <XCircleIcon className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />
                        <div>
                          <p className="mb-1 text-xs font-bold text-rose-600 dark:text-rose-400">
                            Rejection reason
                          </p>
                          <p className="text-sm leading-relaxed text-rose-700 dark:text-rose-300">
                            {car.review_comment}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </>
        )}
      </div>

      {/* Lightbox */}
      <AnimatePresence>
        {lightboxIndex !== null && (
          <DocumentLightbox
            docs={visibleDocs}
            initialIndex={lightboxIndex}
            onClose={() => setLightboxIndex(null)}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function TextBlock({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-[#355f7f] dark:text-blue-200/85">
        {label}
      </p>
      <p className="rounded-lg border border-[#064273]/10 bg-white px-3.5 py-2.5 text-sm leading-relaxed text-gray-700 dark:border-[#064273]/35 dark:bg-white/[0.04] dark:text-gray-300">
        {value}
      </p>
    </div>
  );
}

/* ─── Summary bar ────────────────────────────────────────── */
function SummaryBar({
  cars,
  isAuditor,
}: {
  cars: CorrectiveAction[];
  isAuditor: boolean;
}) {
  const counts = cars.reduce<Record<string, number>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1;
    return acc;
  }, {});
  const carsWithVisibleFiles = cars.filter((car) => {
    const visibleDocuments = isAuditor
      ? car.documents ?? []
      : (car.documents ?? []).filter(
          (doc) => doc.document_type !== "finding_evidence",
        );
    return visibleDocuments.length > 0;
  }).length;

  const statuses = ["Accepted", "Submitted", "Pending", "Rejected"] as const;

  return (
    <div className="flex flex-wrap gap-2 rounded-xl border border-[#064273]/10 bg-[#edf5fb] px-4 py-3 dark:border-[#064273]/35 dark:bg-[#064273]/14">
      <span className="mr-1 text-xs font-bold text-[#355f7f] dark:text-blue-200/85">
        Summary:
      </span>
      {statuses.map((s) => {
        const count = counts[s];
        if (!count) return null;
        const m = STATUS_META[s];
        return (
          <span
            key={s}
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${m.bg} ${m.text} ${m.ring}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${m.dot}`} />
            {count} {s}
          </span>
        );
      })}
      <span className="ml-auto text-xs text-[#355f7f] dark:text-blue-200/85">
        {carsWithVisibleFiles} CAR
        {carsWithVisibleFiles !== 1 ? "s" : ""}{" "}
        with files
      </span>
    </div>
  );
}

/* ─── Main modal ─────────────────────────────────────────── */
export default function AuditCARsModal({
  auditId,
  auditNumber,
  onClose,
}: AuditCARsModalProps) {
  const roles = useSelector((state: RootState) => state.auth.role || []);
  const isAuditor = roles
    .map((role) => String(role).trim().toLowerCase())
    .includes("auditor");
  const [cars, setCars] = useState<CorrectiveAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    axiosInstance
      .get(`/car/admin/${auditId}/corrective-actions`)
      .then((res) => {
        if (!cancelled) setCars(res.data.items ?? []);
      })
      .catch(() => {
        if (!cancelled) setError("Failed to load corrective actions.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [auditId]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const showEmptyState = !loading && !error && cars.length === 0;
  const showErrorState = !loading && !!error;

  const totalDocs = cars.reduce(
    (sum, c) =>
      sum +
      (isAuditor
        ? c.documents?.length ?? 0
        : (c.documents ?? []).filter(
            (doc) => doc.document_type !== "finding_evidence",
          ).length),
    0,
  );

  return (
    <AnimatePresence>
      {/* Backdrop */}
      <motion.div
        key="audit-cars-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100000] bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <motion.div
        key="audit-cars-panel"
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 24, scale: 0.97 }}
        transition={{ duration: 0.22, ease: "easeOut" }}
        onClick={(e) => e.stopPropagation()}
        className="fixed z-[100001] mx-auto flex w-full flex-col overflow-hidden rounded-2xl border border-[#064273]/20 bg-white shadow-2xl dark:border-[#064273]/40 dark:bg-slate-950
    /* mobile: bottom sheet */
    bottom-0 left-0 right-0 top-[20vh] rounded-b-none
    /* sm+: centered dialog */
    sm:bottom-auto sm:left-1/2 sm:right-auto sm:top-1/2 sm:w-[90vw] sm:max-w-6xl sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl"
        style={{ maxHeight: "75vh" }}
      >
        {/* Modal header */}
        <div className="flex items-center gap-4 bg-gradient-to-r from-[#064273] via-[#0a4f7f] to-[#0f628f] px-6 py-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-blue-100/85">
              Corrective Actions
            </p>
            <h2 className="text-base font-bold text-white">{auditNumber}</h2>
          </div>

          {/* Stats chips */}
          {!loading && (
            <div className="ml-2 flex items-center gap-2">
              <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold text-white">
                {cars.length} CAR{cars.length !== 1 ? "s" : ""}
              </span>
              {totalDocs > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold text-white">
                  <PaperClipIcon className="h-3 w-3" />
                  {totalDocs} file{totalDocs !== 1 ? "s" : ""}
                </span>
              )}
            </div>
          )}

          <button
            onClick={onClose}
            className="ml-auto flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 text-blue-100 transition hover:bg-white/20 hover:text-white"
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div
          className={`flex-1 overflow-y-auto px-5 py-4 ${
            showEmptyState || showErrorState
              ? "flex items-center justify-center"
              : ""
          }`}
        >
          {loading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <SkeletonCard key={i} />
              ))}
            </div>
          ) : error ? (
            <div className="flex max-w-sm flex-col items-center gap-3 text-center">
              <ExclamationTriangleIcon className="h-10 w-10 text-rose-400" />
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {error}
              </p>
              <button
                onClick={() => window.location.reload()}
                className="rounded-lg bg-gradient-to-r from-[#064273] to-[#0a4f7f] px-4 py-2 text-sm font-semibold text-white transition hover:from-[#05375f] hover:to-[#064273]"
              >
                Retry
              </button>
            </div>
          ) : cars.length === 0 ? (
            <div className="flex max-w-sm flex-col items-center gap-3 text-center">
              <CheckCircleIcon className="h-10 w-10 text-emerald-400" />
              <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">
                No corrective actions for this audit
              </p>
              <p className="text-xs text-gray-400">
                This audit completed without any CARs raised.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <SummaryBar cars={cars} isAuditor={isAuditor} />
              {cars.map((car, i) => (
                <CARCard
                  key={`car-${car.id ?? "na"}-${car.identifier ?? "noid"}-${i}`}
                  car={car}
                  isAuditor={isAuditor}
                />
              ))}
            </div>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
