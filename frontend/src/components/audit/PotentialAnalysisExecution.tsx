import { AlertTriangle, Upload, X } from "lucide-react";

export type PaValue = "" | -1 | 0 | 4 | 10;

export type PaQuestionMeta = {
  id: number;
  question_code: string;
  question_text_en: string;
  critical_value: number;
};

export type PaAnswerState = {
  value: PaValue;
  findings: string;
  evidence: File[];
};

type Props = {
  questions: PaQuestionMeta[];
  answers: Map<number, PaAnswerState>;
  onChange: (questionId: number, patch: Partial<PaAnswerState>) => void;
  onAddEvidence: (questionId: number, files: FileList | null) => void;
  onRemoveEvidence: (questionId: number, idx: number) => void;
};

const PA_VALUE_OPTIONS: Array<{ value: PaValue; label: string; badge: string }> = [
  { value: -1, label: "n.e.", badge: "bg-gray-100 text-gray-700 border-gray-300" },
  { value: 0, label: "Red", badge: "bg-red-50 text-red-700 border-red-300" },
  { value: 4, label: "Yellow", badge: "bg-amber-50 text-amber-700 border-amber-300" },
  { value: 10, label: "Green", badge: "bg-emerald-50 text-emerald-700 border-emerald-300" },
];

function needsDetails(value: PaValue): boolean {
  return value === 0 || value === 4;
}

export default function PotentialAnalysisExecution({
  questions,
  answers,
  onChange,
  onAddEvidence,
  onRemoveEvidence,
}: Props) {
  const red = questions.filter((q) => answers.get(q.id)?.value === 0).length;
  const yellow = questions.filter((q) => answers.get(q.id)?.value === 4).length;
  const green = questions.filter((q) => answers.get(q.id)?.value === 10).length;
  const ne = questions.filter((q) => answers.get(q.id)?.value === -1).length;

  let classification: "R" | "Y" | "G" | null = null;
  if (red > 0 || yellow > 12) classification = "R";
  else if (yellow <= 6) classification = "G";
  else classification = "Y";

  const classificationLabel =
    classification === "R"
      ? "Red - Barred supplier"
      : classification === "G"
        ? "Green - Approved supplier"
        : "Yellow - Conditionally approved supplier";

  const classificationClass =
    classification === "R"
      ? "bg-red-50 text-red-700 border-red-300"
      : classification === "G"
        ? "bg-emerald-50 text-emerald-700 border-emerald-300"
        : "bg-amber-50 text-amber-700 border-amber-300";

  return (
    <div className="rounded-2xl border border-indigo-200 bg-indigo-50/30 dark:bg-indigo-950/10 dark:border-indigo-900 p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-gray-900 dark:text-white">
            Potential Analysis (P1)
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {questions.length} question{questions.length === 1 ? "" : "s"} &middot; Red / Yellow /
            Green / n.e.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="px-2 py-1 rounded-md border bg-white text-gray-700">Red: {red}</span>
          <span className="px-2 py-1 rounded-md border bg-white text-gray-700">
            Yellow: {yellow}
          </span>
          <span className="px-2 py-1 rounded-md border bg-white text-gray-700">
            Green: {green}
          </span>
          <span className="px-2 py-1 rounded-md border bg-white text-gray-700">n.e.: {ne}</span>
          <span className={`px-2 py-1 rounded-md border font-medium ${classificationClass}`}>
            {classificationLabel}
          </span>
        </div>
      </div>

      {ne > 3 && (
        <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Potential Analysis allows at most 3 "n.e." answers ({ne} selected).
        </div>
      )}

      <div className="space-y-3">
        {questions.map((q) => {
          const answer = answers.get(q.id) ?? { value: "" as PaValue, findings: "", evidence: [] };
          const requiresDetails = needsDetails(answer.value);
          const missingFindings = requiresDetails && !answer.findings.trim();
          const missingEvidence = requiresDetails && answer.evidence.length === 0;

          return (
            <div
              key={q.id}
              className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 space-y-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <span className="text-xs font-mono text-gray-500">{q.question_code}</span>
                  <p className="text-sm text-gray-800 dark:text-gray-200">
                    {q.question_text_en}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                {PA_VALUE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => onChange(q.id, { value: opt.value })}
                    className={`px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors ${
                      answer.value === opt.value
                        ? opt.badge
                        : "bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              {requiresDetails && (
                <div className="space-y-2">
                  <textarea
                    value={answer.findings}
                    onChange={(e) => onChange(q.id, { findings: e.target.value })}
                    placeholder="Findings (required for Red/Yellow)"
                    className={`w-full text-sm rounded-md border px-3 py-2 dark:bg-gray-950 ${
                      missingFindings ? "border-red-400" : "border-gray-300 dark:border-gray-700"
                    }`}
                    rows={2}
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <label
                      className={`inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border cursor-pointer ${
                        missingEvidence
                          ? "border-red-400 text-red-600"
                          : "border-gray-300 text-gray-600 dark:border-gray-700"
                      }`}
                    >
                      <Upload className="h-3.5 w-3.5" />
                      Upload evidence
                      <input
                        type="file"
                        multiple
                        className="hidden"
                        onChange={(e) => {
                          onAddEvidence(q.id, e.target.files);
                          e.target.value = "";
                        }}
                      />
                    </label>
                    {answer.evidence.map((file, idx) => (
                      <span
                        key={`${file.name}-${idx}`}
                        className="inline-flex items-center gap-1 text-xs bg-gray-100 dark:bg-gray-800 rounded-md px-2 py-1"
                      >
                        {file.name}
                        <button
                          type="button"
                          onClick={() => onRemoveEvidence(q.id, idx)}
                          className="text-gray-400 hover:text-red-600"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                  {(missingFindings || missingEvidence) && (
                    <p className="text-xs text-red-600">
                      Findings and evidence are required for Red/Yellow answers.
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
