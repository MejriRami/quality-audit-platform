// components/modals/AuditAnswersModal.tsx

import { useEffect, useState, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  XMarkIcon,
  PaperClipIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ArrowDownTrayIcon,
  MagnifyingGlassPlusIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  StarIcon,
} from "@heroicons/react/24/outline";
import axiosInstance from "../../services/axiosInstance";

/* ─── Types ──────────────────────────────────────────────── */
interface DocumentItem {
  id: number;
  filename: string;
  file_url: string;
  size: number;
  uploaded_at?: string | null;
  document_type?: string;
}

interface QuestionItem {
  id: number;
  description: string;
  chapter?: string | null;
  weight?: number | null;
  critical_value?: number | null;
  question_code?: string | null;
  element?: string | null;
  is_asterisk?: boolean | null;
}

interface AnswerItem {
  id: number;
  identifier?: string | null;
  value: number;
  finding_text?: string | null;
  fail?: boolean | null;
  improve?: boolean | null;
  pass_?: boolean | null;
  process?: string | null;
  standard_paragraph?: string | null;
  classification?: string | null;
  silent_box?: boolean | null;
  created_at?: string | null;
  question?: QuestionItem | null;
  documents: DocumentItem[];
}

interface AnswersResponse {
  audit_id: number;
  audit_number: string;
  total_answers: number;
  total_pass: number;
  total_improve: number;
  total_fail: number;
  items: AnswerItem[];
}

interface AuditAnswersModalProps {
  auditId: number;
  auditNumber: string;
  onClose: () => void;
}

/* ─── Constants ──────────────────────────────────────────── */
const TRIAGE_META = {
  pass: {
    bg: "bg-emerald-50 dark:bg-emerald-900/20",
    text: "text-emerald-700 dark:text-emerald-400",
    ring: "ring-emerald-300 dark:ring-emerald-700/50",
    dot: "bg-emerald-500",
    accent: "bg-emerald-400",
    label: "Pass",
  },
  improve: {
    bg: "bg-amber-50 dark:bg-amber-900/20",
    text: "text-amber-700 dark:text-amber-400",
    ring: "ring-amber-300 dark:ring-amber-700/50",
    dot: "bg-amber-400",
    accent: "bg-amber-400",
    label: "Improve",
  },
  fail: {
    bg: "bg-rose-50 dark:bg-rose-900/20",
    text: "text-rose-700 dark:text-rose-400",
    ring: "ring-rose-300 dark:ring-rose-700/50",
    dot: "bg-rose-500",
    accent: "bg-rose-400",
    label: "Fail",
  },
};

/* ─── Helpers ─────────────────────────────────────────────── */
function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
function isImage(f: string) {
  return /\.(png|jpe?g|gif|webp|svg)$/i.test(f);
}
function isPDF(f: string) {
  return /\.pdf$/i.test(f);
}
function getFileIcon(f: string) {
  if (isPDF(f)) return "📄";
  if (isImage(f)) return "🖼";
  if (/\.(xlsx?|csv)$/i.test(f)) return "📊";
  if (/\.(docx?)$/i.test(f)) return "📝";
  return "📎";
}
function getTriage(a: AnswerItem): "pass" | "improve" | "fail" | null {
  if (a.fail) return "fail";
  if (a.improve) return "improve";
  if (a.pass_) return "pass";
  return null;
}

function inferAuditStyle(items: AnswerItem[]) {
  if (items.some((item) => !item.question)) {
    return "IATF plant manager / direct-entry audit";
  }
  if (items.some((item) => item.classification)) {
    return "IATF / ISO classification audit";
  }
  if (
    items.some(
      (item) =>
        item.question?.element ||
        item.question?.critical_value != null ||
        item.question?.weight != null,
    )
  ) {
    return "VDA-style scored audit";
  }
  return "Standard questionnaire audit";
}

function describeRecordedAnswer(answer: AnswerItem) {
  if (answer.classification) return answer.classification;
  if (answer.value > 0) {
    const critical =
      answer.question?.critical_value != null
        ? ` / critical ${answer.question.critical_value}`
        : "";
    return `Score ${answer.value}${critical}`;
  }
  const triage = getTriage(answer);
  if (triage) return TRIAGE_META[triage].label;
  return "Recorded";
}

/* ─── Sub-components ─────────────────────────────────────── */

function TriagePill({ answer }: { answer: AnswerItem }) {
  const t = getTriage(answer);
  if (!t) return null;
  const m = TRIAGE_META[t];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${m.bg} ${m.text} ${m.ring}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  );
}

function ClassificationBadge({ value }: { value: string }) {
  const lower = value.toLowerCase();
  const cls = lower.includes("major")
    ? "border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-700/50 dark:bg-rose-900/20 dark:text-rose-400"
    : lower.includes("minor")
      ? "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-400"
      : lower.includes("ofi") ||
          lower.includes("improvement") ||
          lower.includes("observation")
        ? "border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700/50 dark:bg-blue-900/20 dark:text-blue-300"
        : "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-400";
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[10.5px] font-bold tracking-wider ${cls}`}
    >
      {value}
    </span>
  );
}

function ValueDots({
  value,
  critical,
}: {
  value: number;
  critical?: number | null;
}) {
  if (value <= 0) return null;
  const max = Math.max(value, critical ?? 0, 5);
  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: max }).map((_, i) => {
        const filled = i < value;
        const isCritical = critical != null && i === critical - 1;
        return (
          <span
            key={i}
            className={`h-2.5 w-2.5 rounded-full border transition ${
              filled
                ? value <= (critical ?? 0)
                  ? "border-rose-400 bg-rose-400"
                  : value === (critical ?? 0)
                    ? "border-amber-400 bg-amber-400"
                    : "border-emerald-400 bg-emerald-400"
                : "border-gray-200 bg-transparent dark:border-gray-700"
            } ${isCritical ? "ring-1 ring-offset-1 ring-gray-400" : ""}`}
          />
        );
      })}
      <span className="ml-1 text-xs tabular-nums text-gray-400">
        {value}/{max}
      </span>
    </div>
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

/* ─── Lightbox (reused pattern from CARs modal) ─────────── */
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
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") prev();
      if (e.key === "ArrowRight") next();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose, prev, next]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
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
        <div className="flex shrink-0 items-center gap-3 border-b border-white/10 bg-gray-900 px-4 py-3">
          <span className="text-xl">{getFileIcon(doc.filename)}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-white">
              {doc.filename}
            </p>
            <p className="text-xs text-gray-400">{formatBytes(doc.size)}</p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {docs.length > 1 && (
              <>
                <button
                  onClick={prev}
                  disabled={idx === 0}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 hover:bg-white/10 hover:text-white disabled:opacity-30"
                >
                  <ChevronLeftIcon className="h-4 w-4" />
                </button>
                <span className="min-w-[36px] text-center text-xs tabular-nums text-gray-400">
                  {idx + 1}/{docs.length}
                </span>
                <button
                  onClick={next}
                  disabled={idx === docs.length - 1}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 hover:bg-white/10 hover:text-white disabled:opacity-30"
                >
                  <ChevronRightIcon className="h-4 w-4" />
                </button>
                <span className="mx-1 h-5 w-px bg-white/10" />
              </>
            )}
            <a
              href={doc.file_url}
              download={doc.filename}
              target="_blank"
              rel="noopener noreferrer"
              className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-300 hover:bg-white/10 hover:text-white"
            >
              <ArrowDownTrayIcon className="h-4 w-4" />
            </a>
            <button
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15 text-white ring-1 ring-white/20 hover:bg-white/25"
            >
              <XMarkIcon className="h-4 w-4" />
            </button>
          </div>
        </div>
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
              <a
                href={doc.file_url}
                download
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-[#064273] to-[#0a4f7f] px-4 py-2 text-sm font-semibold text-white"
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
  documents,
  onPreview,
}: {
  documents: DocumentItem[];
  onPreview: (d: DocumentItem) => void;
}) {
  if (!documents.length) return null;
  return (
    <div className="mt-3">
      <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#355f7f] dark:text-blue-200/85">
        Evidence ({documents.length})
      </p>
      <div className="flex flex-wrap gap-2">
        {documents.map((doc, i) => (
          <button
            key={`${doc.id}-${i}`}
            onClick={() => onPreview(doc)}
            title={doc.filename}
            className="group relative flex items-center gap-2.5 overflow-hidden rounded-xl border border-[#064273]/10 bg-white py-2 pl-3 pr-4 text-left shadow-sm transition hover:border-[#064273]/30 hover:shadow-md dark:border-[#064273]/35 dark:bg-slate-800 dark:hover:border-[#77b7de]/40"
          >
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
                <span className="text-base">{getFileIcon(doc.filename)}</span>
              )}
            </div>
            <div className="min-w-0">
              <p className="max-w-[140px] truncate text-xs font-semibold text-gray-700 dark:text-gray-200">
                {doc.filename}
              </p>
              <p className="text-[10px] text-gray-400">
                {formatBytes(doc.size)}
              </p>
            </div>
            <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-[#064273]/0 transition group-hover:bg-[#064273]/10">
              <MagnifyingGlassPlusIcon className="h-4 w-4 scale-0 text-[#064273] transition group-hover:scale-100 dark:text-blue-200" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ─── Answer Card ────────────────────────────────────────── */
function AnswerCard({ answer, index }: { answer: AnswerItem; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const triage = getTriage(answer);
  const triageMeta = triage ? TRIAGE_META[triage] : null;

  const hasDetail =
    answer.finding_text ||
    answer.process ||
    answer.standard_paragraph ||
    answer.classification;

  const handlePreview = useCallback(
    (doc: DocumentItem) => {
      const i = answer.documents.findIndex((d) => d.id === doc.id);
      if (i >= 0) setLightboxIndex(i);
    },
    [answer.documents],
  );

  // Label: use question description if linked, else process/paragraph or identifier
  const label =
    answer.question?.description ??
    (answer.process && answer.standard_paragraph
      ? `${answer.process} — ${answer.standard_paragraph}`
      : (answer.process ??
        answer.standard_paragraph ??
        answer.identifier ??
        `Answer #${answer.id}`));

  const isDirectEntry = !answer.question;
  const answerSummary = describeRecordedAnswer(answer);

  return (
    <>
      <div className="overflow-hidden rounded-xl border border-[#064273]/10 bg-white shadow-sm transition hover:shadow-md dark:border-[#064273]/35 dark:bg-slate-900">
        {/* Header */}
        <div className="flex items-start gap-3 px-5 py-4">
          {/* Left accent */}
          <div
            className={`mt-0.5 w-1 self-stretch rounded-full ${triageMeta?.accent ?? "bg-gray-200 dark:bg-gray-700"}`}
          />

          <div className="flex min-w-0 flex-1 flex-col gap-2">
            {/* Top row */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs font-bold text-[#064273]/60 dark:text-blue-300/60">
                #{index + 1}
              </span>
              {answer.question?.question_code && (
                <span className="font-mono text-xs font-semibold text-[#064273] dark:text-blue-200">
                  {answer.question.question_code}
                </span>
              )}
              {answer.question?.chapter && (
                <span className="rounded bg-[#064273]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#064273] dark:bg-[#064273]/30 dark:text-blue-200">
                  {answer.question.chapter}
                </span>
              )}
              {answer.question?.is_asterisk && (
                <StarIcon
                  className="h-3.5 w-3.5 text-amber-400"
                  title="Critical question"
                />
              )}
              {isDirectEntry && (
                <span className="rounded bg-purple-50 px-1.5 py-0.5 text-[10px] font-semibold text-purple-600 dark:bg-purple-900/20 dark:text-purple-300">
                  Direct entry
                </span>
              )}
              {answer.classification && (
                <ClassificationBadge value={answer.classification} />
              )}
              {answer.silent_box && (
                <span
                  className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                  title="Silent Box: tracked internally, excluded from the printed Audit Report"
                >
                  SB
                </span>
              )}
              <div className="ml-auto flex items-center gap-2">
                <TriagePill answer={answer} />
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <TextBlock
                label={isDirectEntry ? "Related Entry" : "Related Question"}
                value={label}
              />
              <TextBlock label="Recorded Answer" value={answerSummary} />
            </div>

            {/* Value dots (for numeric-scored answers) */}
            {answer.value > 0 && answer.question?.critical_value != null && (
              <ValueDots
                value={answer.value}
                critical={answer.question.critical_value}
              />
            )}

            {/* Finding text preview */}
            {answer.finding_text && (
              <TextBlock label="Finding" value={answer.finding_text} />
            )}
          </div>
        </div>

        {/* Expand toggle */}
        {(hasDetail || answer.documents.length > 0) && (
          <>
            <button
              onClick={() => setExpanded((v) => !v)}
              className="flex w-full items-center justify-between border-t border-[#064273]/10 px-5 py-2.5 text-left transition hover:bg-[#064273]/[0.06] dark:border-[#064273]/35 dark:hover:bg-[#064273]/15"
            >
              <span className="flex items-center gap-2 text-xs font-semibold text-[#064273] dark:text-blue-200">
                {answer.documents.length > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <PaperClipIcon className="h-3.5 w-3.5" />
                    {answer.documents.length} file
                    {answer.documents.length !== 1 ? "s" : ""}
                  </span>
                )}
                {hasDetail && (
                  <span className="text-[#355f7f] dark:text-blue-200/85">
                    {answer.documents.length > 0 ? "· " : ""}Details
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
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      {answer.process && (
                        <TextBlock label="Process" value={answer.process} />
                      )}
                      {answer.standard_paragraph && (
                        <TextBlock
                          label="Standard paragraph"
                          value={answer.standard_paragraph}
                        />
                      )}
                      {answer.question?.element && (
                        <TextBlock
                          label="Element"
                          value={answer.question.element}
                        />
                      )}
                      {answer.question?.weight != null && (
                        <TextBlock
                          label="Weight"
                          value={String(answer.question.weight)}
                        />
                      )}
                    </div>
                    <DocumentStrip
                      documents={answer.documents}
                      onPreview={handlePreview}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </>
        )}
      </div>

      <AnimatePresence>
        {lightboxIndex !== null && (
          <DocumentLightbox
            docs={answer.documents}
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
function SummaryBar({ data }: { data: AnswersResponse }) {
  const auditStyle = inferAuditStyle(data.items);
  return (
    <div className="flex flex-wrap gap-2 rounded-xl border border-[#064273]/10 bg-[#edf5fb] px-4 py-3 dark:border-[#064273]/35 dark:bg-[#064273]/14">
      <span className="mr-1 text-xs font-bold text-[#355f7f] dark:text-blue-200/85">
        Summary:
      </span>
      <span className="inline-flex items-center rounded-full bg-white/70 px-2.5 py-1 text-xs font-semibold text-[#064273] dark:bg-white/10 dark:text-blue-200">
        {auditStyle}
      </span>
      {data.total_pass > 0 && (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${TRIAGE_META.pass.bg} ${TRIAGE_META.pass.text} ${TRIAGE_META.pass.ring}`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${TRIAGE_META.pass.dot}`}
          />
          {data.total_pass} Pass
        </span>
      )}
      {data.total_improve > 0 && (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${TRIAGE_META.improve.bg} ${TRIAGE_META.improve.text} ${TRIAGE_META.improve.ring}`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${TRIAGE_META.improve.dot}`}
          />
          {data.total_improve} Improve
        </span>
      )}
      {data.total_fail > 0 && (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${TRIAGE_META.fail.bg} ${TRIAGE_META.fail.text} ${TRIAGE_META.fail.ring}`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${TRIAGE_META.fail.dot}`}
          />
          {data.total_fail} Fail
        </span>
      )}
      <span className="ml-auto text-xs text-[#355f7f] dark:text-blue-200/85">
        {data.total_answers} answer{data.total_answers !== 1 ? "s" : ""}
      </span>
    </div>
  );
}

/* ─── Filter bar ─────────────────────────────────────────── */
type Filter = "all" | "pass" | "improve" | "fail";

function FilterBar({
  active,
  onChange,
  counts,
}: {
  active: Filter;
  onChange: (f: Filter) => void;
  counts: Record<Filter, number>;
}) {
  const filters: { key: Filter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "fail", label: "Fail" },
    { key: "improve", label: "Improve" },
    { key: "pass", label: "Pass" },
  ];
  return (
    <div className="flex gap-1.5">
      {filters.map((f) => (
        <button
          key={f.key}
          onClick={() => onChange(f.key)}
          className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
            active === f.key
              ? "bg-[#064273] text-white"
              : "bg-[#064273]/10 text-[#064273] hover:bg-[#064273]/15 dark:bg-[#064273]/30 dark:text-blue-200 dark:hover:bg-[#064273]/40"
          }`}
        >
          {f.label}
          {counts[f.key] > 0 && f.key !== "all" && (
            <span className="ml-1.5 opacity-70">({counts[f.key]})</span>
          )}
        </button>
      ))}
    </div>
  );
}

/* ─── Main Modal ─────────────────────────────────────────── */
export default function AuditAnswersModal({
  auditId,
  auditNumber,
  onClose,
}: AuditAnswersModalProps) {
  const [data, setData] = useState<AnswersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    axiosInstance
      .get(`/audits/${auditId}/answers`)
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch(() => {
        if (!cancelled) setError("Failed to load audit answers.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [auditId]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (filter === "all") return data.items;
    if (filter === "pass") return data.items.filter((a) => a.pass_);
    if (filter === "improve") return data.items.filter((a) => a.improve);
    if (filter === "fail") return data.items.filter((a) => a.fail);
    return data.items;
  }, [data, filter]);

  const counts = useMemo<Record<Filter, number>>(
    () => ({
      all: data?.total_answers ?? 0,
      pass: data?.total_pass ?? 0,
      improve: data?.total_improve ?? 0,
      fail: data?.total_fail ?? 0,
    }),
    [data],
  );

  const totalDocs =
    data?.items.reduce((s, a) => s + a.documents.length, 0) ?? 0;
  const showEmpty = !loading && !error && (data?.items.length ?? 0) === 0;

  return (
    <AnimatePresence>
      <motion.div
        key="answers-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100000] bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />

      <motion.div
        key="answers-panel"
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 24, scale: 0.97 }}
        transition={{ duration: 0.22, ease: "easeOut" }}
        onClick={(e) => e.stopPropagation()}
        className="fixed z-[100001] mx-auto flex w-full flex-col overflow-hidden rounded-2xl border border-[#064273]/20 bg-white shadow-2xl dark:border-[#064273]/40 dark:bg-slate-950
          bottom-0 left-0 right-0 top-[10vh] rounded-b-none
          sm:bottom-auto sm:left-1/2 sm:right-auto sm:top-1/2 sm:w-[90vw] sm:max-w-6xl sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl"
        style={{ maxHeight: "85vh" }}
      >
        {/* Header */}
        <div className="flex items-center gap-4 bg-gradient-to-r from-[#064273] via-[#0a4f7f] to-[#0f628f] px-6 py-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-blue-100/85">
              Audit Responses
            </p>
            <h2 className="text-base font-bold text-white">{auditNumber}</h2>
          </div>
          {!loading && data && (
            <div className="ml-2 flex items-center gap-2">
              <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold text-white">
                {data.total_answers} answer{data.total_answers !== 1 ? "s" : ""}
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

        {/* Filter bar */}
        {!loading && !error && (data?.items.length ?? 0) > 0 && (
          <div className="border-b border-[#064273]/10 bg-white px-5 py-2.5 dark:border-[#064273]/35 dark:bg-slate-950">
            <FilterBar active={filter} onChange={setFilter} counts={counts} />
          </div>
        )}

        {/* Body */}
        <div
          className={`flex-1 overflow-y-auto px-5 py-4 ${showEmpty || error ? "flex items-center justify-center" : ""}`}
        >
          {loading ? (
            <div className="space-y-3">
              {[...Array(4)].map((_, i) => (
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
                className="rounded-lg bg-gradient-to-r from-[#064273] to-[#0a4f7f] px-4 py-2 text-sm font-semibold text-white"
              >
                Retry
              </button>
            </div>
          ) : showEmpty ? (
            <div className="flex max-w-sm flex-col items-center gap-3 text-center">
              <CheckCircleIcon className="h-10 w-10 text-emerald-400" />
              <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">
                No answers recorded for this audit
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {data && <SummaryBar data={data} />}
              {filtered.length === 0 ? (
                <p className="py-8 text-center text-sm text-gray-400">
                  No answers match this filter.
                </p>
              ) : (
                filtered.map((answer, i) => (
                  <AnswerCard
                    key={`${answer.id}-${i}`}
                    answer={answer}
                    index={i}
                  />
                ))
              )}
            </div>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
