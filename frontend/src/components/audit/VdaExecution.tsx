import { Fragment, useMemo } from "react";
import { AlertTriangle, Upload, X } from "lucide-react";

type AuditValue = "" | -1 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10;

interface UploadedDoc {
  filename: string;
  mimetype: string;
  size: number;
  file_url: string;
}

export interface AuditItem {
  row: number;
  uiId: string;
  questionId: number;
  parentQuestionId?: number | null;
  requirementId?: number | null;
  isRequirement?: boolean;
  process?: string | null;
  question: string;
  requirementCode?: string;
  critical: number;
  weight: number;
  value: AuditValue;
  findings: string;
  carReason: string;
  evidence: File[];
  uploadedDocs: UploadedDoc[];
  requestCAR: boolean;
  silentBox: boolean;
  immediateActionRequired: boolean;
  errors: {
    value?: string;
    findings?: string;
    carReason?: string;
  };
}

export interface ValueOption {
  value: AuditValue;
  label: string;
  color: string;
}

export type VdaQuestionMeta = {
  id?: number;
  question_id?: number | string;
  element: "P2" | "P3" | "P4" | "P5" | "P6" | "P7" | string;
  question_code: string;
  question_text_en: string;
  requirements?: Array<{
    id?: number;
    question_id?: number;
    requirement_code?: string;
    description?: string;
    sort_order?: number;
    value?: number | null;
  }>;
  requirement_id?: number | null;
  requirement_code?: string;
  requirement_sort_order?: number;
  is_requirement?: boolean;
  parent_question_id?: number | null;
  is_asterisk?: boolean;
  critical_value?: number;
  weight?: number;
  process?: string | null;
};

type Props = {
  items: AuditItem[];
  valueOptions: ValueOption[];
  questionnaireName: string;
  vdaQuestions: VdaQuestionMeta[];
  selectedIds: Set<string>;
  enabledSections: Set<string>;
  onToggleSection: (sectionKey: string) => void;
  onToggleSelect: (uiId: string) => void;
  onSelectAllInSection: (sectionKey: string, checked: boolean) => void;
  onUpdateField: <K extends keyof AuditItem>(
    rowId: string | number,
    field: K,
    value: AuditItem[K],
  ) => void;
  onToggleImmediateAction: (rowId: string | number) => void;
  previews: Map<string, string>;
  onAddEvidence: (uiId: string, files: FileList | null) => void;
  onRemoveLocalEvidence: (uiId: string, idx: number) => void;
  onRemoveUploadedEvidence: (uiId: string, idx: number) => void;
  sideModeByBase: Record<string, SideMode>;
  onSetSideMode: (baseCode: string, mode: SideMode) => void;
};

type SideMode = "product" | "process_support" | "both";

const SECTION_ORDER = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"] as const;

function sortByCode(a: VdaQuestionMeta, b: VdaQuestionMeta) {
  return (a.question_code || "").localeCompare(b.question_code || "", undefined, {
    numeric: true,
  });
}

function getQuestionNumericId(q: VdaQuestionMeta): number | null {
  const raw = q.id ?? q.question_id;
  if (raw === undefined || raw === null || raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function isRemarkLine(q: VdaQuestionMeta): boolean {
  const code = String(q.question_code ?? "").toLowerCase();
  const text = String(q.question_text_en ?? "").toLowerCase().trim();
  return (
    text.startsWith("remark") ||
    text.startsWith("remarks") ||
    text.includes("remarks to be fulfilled") ||
    code.includes("remark")
  );
}

function hasVisibleErrors(errors?: AuditItem["errors"]): boolean {
  if (!errors) return false;
  return Boolean(errors.value || errors.findings || errors.carReason);
}

function getSubElementLabel(q: VdaQuestionMeta): string | null {
  const raw = String(q.process ?? "").trim();
  if (!raw) return null;
  const low = raw.toLowerCase();
  if (low.includes("product")) return "Product";
  if (low.includes("support") || low.includes("process")) return "Process / Support";
  return raw;
}

function getSubElementSortKey(q: VdaQuestionMeta): string {
  const label = getSubElementLabel(q);
  if (label === "Product") return "1_product";
  if (label === "Process / Support") return "2_process_support";
  return "3_unspecified";
}

function baseCode(q: VdaQuestionMeta): string {
  const code = String(q.question_code ?? "").trim().toUpperCase().replace(/\*$/, "");
  const parts = code.split(".");
  return parts.length >= 2 ? `${parts[0]}.${parts[1]}` : code;
}

function getDisplayQuestionCode(q: VdaQuestionMeta, index: number): string {
  const code = String(q.question_code ?? "").trim();
  if (code) return code;
  return `Q-${index + 1}`;
}

function rowSide(q: VdaQuestionMeta): "" | "product" | "process_support" {
  const raw = String(q.process ?? "").toLowerCase();
  if (raw.includes("product")) return "product";
  if (raw.includes("process") || raw.includes("support")) return "process_support";
  return "";
}

function isRequirementRow(q: VdaQuestionMeta): boolean {
  return Boolean((q as any).is_requirement);
}

function getAvailableModes(rows: VdaQuestionMeta[]): SideMode[] {
  const hasProduct = rows.some((r) => rowSide(r) === "product");
  const hasProcess = rows.some((r) => rowSide(r) === "process_support");
  if (hasProduct && hasProcess) return ["both", "product", "process_support"];
  if (hasProduct) return ["product"];
  if (hasProcess) return ["process_support"];
  return ["both"];
}

type QuestionGroup = {
  key: string;
  base: VdaQuestionMeta;
  rows: VdaQuestionMeta[];
};

export default function VdaExecution({
  items,
  valueOptions,
  questionnaireName,
  vdaQuestions,
  selectedIds,
  enabledSections,
  onToggleSection,
  onSelectAllInSection,
  onToggleSelect,
  onUpdateField,
  onToggleImmediateAction,
  previews,
  onAddEvidence,
  onRemoveLocalEvidence,
  onRemoveUploadedEvidence,
  sideModeByBase,
  onSetSideMode,
}: Props) {
  const questionnaireLabel = String(questionnaireName ?? "").trim();
  const sectionOrder = useMemo(() => {
    const detected = Array.from(
      new Set(
        (vdaQuestions ?? [])
          .map((q) => String(q?.element ?? "").trim().toUpperCase())
          .filter(Boolean),
      ),
    );
    const ordered = SECTION_ORDER.filter((sec) => detected.includes(sec));
    const extra = detected
      .filter((sec) => !SECTION_ORDER.includes(sec as (typeof SECTION_ORDER)[number]))
      .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    return [...ordered, ...extra];
  }, [vdaQuestions]);

  const metaByElement = useMemo(() => {
    const map = new Map<string, VdaQuestionMeta[]>();
    for (const sec of sectionOrder) map.set(sec, []);

    for (const q of vdaQuestions ?? []) {
      const normalizedElement = String(q?.element ?? "").trim().toUpperCase();
      const targetSection = normalizedElement || sectionOrder[0] || "";
      if (!targetSection) continue;
      if (!map.has(targetSection)) map.set(targetSection, []);
      map.get(targetSection)!.push(q);
    }

    for (const [sec, arr] of map.entries()) {
      arr.sort((a, b) => {
        if (sec === "P3" || sec === "P4") {
          const byCode = sortByCode(a, b);
          if (byCode !== 0) return byCode;
          const bySub = getSubElementSortKey(a).localeCompare(getSubElementSortKey(b));
          if (bySub !== 0) return bySub;
        }
        return sortByCode(a, b);
      });
    }

    return map;
  }, [sectionOrder, vdaQuestions]);

  const itemByQuestionKey = useMemo(() => {
    const map = new Map<string, AuditItem>();
    for (const it of items) {
      map.set(`${it.questionId}::${String(it.process ?? "")}`, it);
    }
    return map;
  }, [items]);

  const buildQuestionGroups = (sec: string, sectionQuestions: VdaQuestionMeta[]): QuestionGroup[] => {
    if (sec !== "P3" && sec !== "P4") {
      return sectionQuestions.map((q) => ({
        key: String(q.id ?? q.question_id ?? q.question_code),
        base: q,
        rows: [q],
      }));
    }

    const groups = new Map<string, QuestionGroup>();
    for (const q of sectionQuestions) {
      const key = baseCode(q);
      const existing = groups.get(key);
      if (existing) {
        existing.rows.push(q);
      } else {
        groups.set(key, { key, base: q, rows: [q] });
      }
    }

    return Array.from(groups.values());
  };

  const getCounts = (sec: string) => {
    const sectionQuestions = (metaByElement.get(sec) ?? []).filter((q) => !isRemarkLine(q));
    const groups = buildQuestionGroups(sec, sectionQuestions);
    let selected = 0;
    let answered = 0;

    for (const group of groups) {
      const mode: SideMode = sideModeByBase[group.key] ?? "both";
      const linkedItems = group.rows
        .filter((q) => {
          const side = rowSide(q);
          if (!side) return true;
          return mode === "both" || mode === side;
        })
        .map((q) => {
          const qid = getQuestionNumericId(q);
          if (qid == null) return undefined;
          return itemByQuestionKey.get(`${qid}::${String(q.process ?? "")}`);
        })
        .filter((item): item is AuditItem => Boolean(item));

      const groupSelected = linkedItems.some((item) => selectedIds.has(item.uiId));
      const groupAnswered = linkedItems.some(
        (item) => selectedIds.has(item.uiId) && item.value !== "" && item.value !== -1,
      );

      if (groupSelected) selected++;
      if (groupAnswered) answered++;
    }

    return { total: groups.length, selected, answered };
  };

  const visibleSections = sectionOrder.filter((s) => enabledSections.has(s));

  return (
    <div
      className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden"
      data-questionnaire-name={questionnaireLabel || undefined}
    >
      <div className="px-6 py-4 border-b border-slate-200 bg-slate-50">
        <p className="text-sm text-slate-700">
          Enable one or more sections (P1-P7). Under each enabled section you can read the question, its related questions, and the VDA scoring fields.
        </p>
        <p className="mt-2 text-xs text-amber-700">
          Asterisk (*) questions are highlighted as special VDA questions. They are optional; if the auditor answers them, values 0 or 4 still apply the VDA downgrade rules.
          CARs for values 0 or 4 are created from the findings text.
        </p>
      </div>

      <div className="p-4 md:p-6 space-y-6">
        <div>
            <p className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-3">
            Sections
            </p>

          <div className="space-y-2">
            {sectionOrder.map((sec) => {
              const { total, selected, answered } = getCounts(sec);
              const enabled = enabledSections.has(sec);

              return (
                <label
                  key={sec}
                  className={[
                    "flex items-center justify-between gap-3 px-3 py-2 rounded-lg border cursor-pointer transition-colors",
                    enabled
                      ? "bg-indigo-50 border-indigo-200"
                      : "bg-white border-slate-200 hover:bg-slate-50",
                  ].join(" ")}
                >
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={() => onToggleSection(sec)}
                      className="w-4 h-4"
                    />
                    <span className="font-semibold text-slate-800">{sec}</span>
                  </div>

                  <span className="text-xs font-medium text-slate-600">
                    {answered}/{selected || total} answered
                  </span>
                </label>
              );
            })}
          </div>
        </div>

        {visibleSections.map((sec) => {
          const sectionQuestions = metaByElement.get(sec) ?? [];
          const actionableQuestions = sectionQuestions.filter((q) => !isRemarkLine(q));
          const groups = buildQuestionGroups(sec, sectionQuestions);
          const { total, selected, answered } = getCounts(sec);
          const allSelected = total > 0 && selected === total;
          let displayIndex = 0;

          return (
            <div key={sec} className="border border-slate-200 rounded-xl overflow-hidden">
              <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between gap-4">
                <div>
                  <h3 className="text-base font-semibold text-slate-800">{sec}</h3>
                  <p className="text-sm text-slate-500">
                    Selected {selected}/{total} • Answered {answered}/{selected || total}
                  </p>
                </div>

                <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={(e) => onSelectAllInSection(sec, e.target.checked)}
                    disabled={actionableQuestions.length === 0}
                    className="w-4 h-4"
                  />
                  Select all
                </label>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-white border-b border-slate-200">
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-700 uppercase tracking-wider w-16">Use</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-700 uppercase tracking-wider w-36">Code</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-700 uppercase tracking-wider min-w-[420px]">Question & requirements</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-700 uppercase tracking-wider w-52">Value</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-700 uppercase tracking-wider w-64">Findings</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-700 uppercase tracking-wider w-56">Evidence / Attachments</th>
                      {/* REMOVED: CAR column hidden — CAR is auto-managed by parent
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-700 uppercase tracking-wider w-72">CAR</th>
                      */}
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-slate-100">
                    {groups.map((group) => {
                      const q = group.base;

                      if (isRemarkLine(q)) {
                        return (
                          <Fragment key={group.key}>
                            <tr className="bg-amber-50/50">
                              <td className="px-4 py-3" />
                              <td className="px-4 py-3 align-top">
                                <span className="text-xs font-semibold text-amber-700">Remark</span>
                              </td>
                              <td className="px-4 py-3 align-top">
                                <p className="text-sm text-amber-800">{q.question_text_en}</p>
                              </td>
                              <td className="px-4 py-3" />
                              <td className="px-4 py-3" />
                              <td className="px-4 py-3" />
                              <td className="px-4 py-3" />
                              {/* REMOVED: CAR column hidden — CAR is auto-managed by parent
                              <td className="px-4 py-3" />
                              <td className="px-4 py-3" />
                              */}
                            </tr>
                          </Fragment>
                        );
                      }

                      const availableModes = getAvailableModes(group.rows);
                      const savedMode = sideModeByBase[group.key];
                      const mode: SideMode = savedMode && availableModes.includes(savedMode)
                        ? savedMode
                        : availableModes[0];
                      const visibleRows = group.rows.filter((row) => {
                        const side = rowSide(row);
                        if (!side) return true;
                        if (mode === "both") return true;
                        return mode === side;
                      });

                      return (
                        <Fragment key={group.key}>
                          {(sec === "P3" || sec === "P4") && group.rows.some((row) => rowSide(row) !== "") && (
                            <tr className="bg-sky-50 border-y border-sky-100">
                              <td colSpan={7} className="px-4 py-2">
                                <div className="flex items-center justify-between gap-4">
                                  <div className="text-sm font-semibold text-sky-900">
                                    {group.key}
                                  </div>
                                  <div className="flex items-center gap-3 text-xs">
                                    <span className="font-semibold text-sky-800">Evaluate:</span>
                                    {availableModes.length === 1 ? (
                                      <span className="px-2.5 py-1 rounded border bg-slate-100 text-slate-700 border-slate-200">
                                        {availableModes[0] === "product"
                                          ? "Product only"
                                          : availableModes[0] === "process_support"
                                            ? "Process only"
                                            : "Both"}
                                      </span>
                                    ) : (
                                      availableModes.map((m) => (
                                        <button
                                          key={m}
                                          type="button"
                                          className={`px-2.5 py-1 rounded border ${
                                            mode === m
                                              ? "bg-sky-600 text-white border-sky-600"
                                              : "bg-white text-sky-700 border-sky-200"
                                          }`}
                                        onClick={() => onSetSideMode(group.key, m)}
                                      >
                                          {m === "product" ? "Product" : m === "process_support" ? "Process" : "Both"}
                                        </button>
                                      ))
                                    )}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}

                          {visibleRows.map((row, rowIdx) => {
                            const displayNumber = ++displayIndex;
                            const qid = getQuestionNumericId(row);
                            const qKey = `${qid}::${String(row.process ?? "")}`;
                            const linkedItem = qid != null ? itemByQuestionKey.get(qKey) : undefined;
                            const isLoaded = !!linkedItem;
                            const selectedRow = isLoaded && selectedIds.has(linkedItem.uiId);
                            // REMOVED: carMandatory no longer needed — parent auto-checks CAR for 0/4/6/8
                            // const carMandatory = isLoaded && selectedRow && linkedItem.value === 8;
                            const sideLabel = getSubElementLabel(row);
                            const requirementRow = isRequirementRow(row);
                            const requirementCode = String((row as any).requirement_code ?? "").trim();

                            return (
                              <tr
                                key={`${group.key}-${sideLabel ?? rowIdx}`}
                                id={isLoaded ? `audit-item-${linkedItem.uiId}` : undefined}
                                className={[
                                  isLoaded ? "hover:bg-slate-50/60" : "bg-slate-50",
                                  selectedRow && row.is_asterisk ? "bg-red-50/30" : "",
                                  requirementRow ? "bg-emerald-50/50" : "",
                                  isLoaded && selectedRow && hasVisibleErrors(linkedItem.errors)
                                    ? "bg-red-50/40"
                                    : "",
                                ].join(" ")}
                              >
                                <td className="px-4 py-4 align-top">
                                  <input
                                    type="checkbox"
                                    checked={!!selectedRow}
                                    disabled={!isLoaded}
                                    onChange={() => isLoaded && onToggleSelect(linkedItem.uiId)}
                                    className="w-5 h-5"
                                  />
                                </td>

                                <td className="px-4 py-4 align-top">
                                    <span className="text-sm font-semibold text-slate-700">
                                    {getDisplayQuestionCode(row, displayNumber - 1)}
                                    </span>
                                  {requirementRow && (
                                    <div className="mt-2 inline-flex rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                                      Requirement
                                    </div>
                                  )}
                                  {!!row.is_asterisk && (
                                    <span className="ml-2 inline-flex items-center px-2 py-0.5 text-xs font-bold rounded bg-red-50 text-red-700 border border-red-200" title="Special VDA asterisk question">
                                      *
                                    </span>
                                  )}
                                  {sideLabel && (
                                    <div className="mt-2 inline-flex rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-800">
                                      {sideLabel}
                                    </div>
                                  )}
                                </td>

                                <td className="px-4 py-4 align-top">
                                  {requirementRow ? (
                                    <div>
                                      <p className="text-sm text-emerald-900 font-medium">
                                        {requirementCode ? `${requirementCode}: ` : ""}
                                        {q.question_text_en}
                                      </p>
                                      <p className="text-xs text-emerald-700 mt-1">
                                        Scored independently from the parent question. A score of 0/4/6/8 raises its own CAR.
                                      </p>
                                    </div>
                                  ) : rowIdx === 0 ? (
                                    <p className="text-sm text-slate-800">{q.question_text_en}</p>
                                  ) : (
                                    <p className="text-sm text-slate-500 italic">Same question, separate side assessment.</p>
                                  )}

                                  {!requirementRow && rowIdx === 0 && !!q.requirements?.length && (
                                    <p className="mt-3 text-xs text-slate-500 italic">
                                      Related requirement questions are shown below as separate scored rows.
                                    </p>
                                  )}

                                  {!isLoaded && (
                                    <p className="text-xs text-amber-700 mt-1">
                                      This question was returned by the API but is not present in <code>items</code>.
                                    </p>
                                  )}

                                  {isLoaded && !selectedRow && (
                                    <p className="text-xs text-slate-500 italic mt-1">Not selected - will not be evaluated</p>
                                  )}

                                  {/* REMOVED: carMandatory warning no longer needed — parent auto-checks CAR for 0/4/6/8
                                  {isLoaded && selectedRow && carMandatory && !linkedItem.requestCAR && (
                                    <div className="flex items-center gap-2 mt-2 text-xs text-amber-700 font-medium">
                                      <AlertTriangle size={14} />
                                      Value 8 requires a CAR before submitting.
                                    </div>
                                  )}
                                  */}

                                  {isLoaded && selectedRow && hasVisibleErrors(linkedItem.errors) && (
                                    <div className="flex items-center gap-2 mt-2 text-xs text-red-600 font-medium">
                                      <AlertTriangle size={14} />
                                      Please complete required fields
                                    </div>
                                  )}
                                </td>

                                <td className="px-4 py-4 align-top">
                                  <select
                                    value={isLoaded ? linkedItem.value : ""}
                                    disabled={!isLoaded || !selectedRow}
                                    onChange={(e) => {
                                      if (!isLoaded) return;
                                      const val = e.target.value === "" ? "" : (Number(e.target.value) as AuditValue);
                                      onUpdateField(linkedItem.uiId, "value", val);
                                    }}
                                    className={`w-full p-2.5 text-sm border rounded-lg ${
                                      !isLoaded || !selectedRow
                                        ? "bg-slate-50 border-slate-200 text-slate-400"
                                        : linkedItem.errors?.value
                                          ? "bg-red-50 border-red-400 ring-1 ring-red-200"
                                          : "bg-white border-slate-300"
                                    }`}
                                  >
                                    <option value="">Select value...</option>
                                    {valueOptions.map((opt) => (
                                      <option key={String(opt.value)} value={opt.value}>{opt.label}</option>
                                    ))}
                                  </select>

                                  {isLoaded && selectedRow && linkedItem.errors?.value && (
                                    <p className="text-xs text-red-600 mt-1 font-medium">{linkedItem.errors.value}</p>
                                  )}
                                </td>

                                <td className="px-4 py-4 align-top">
                                  {isLoaded && selectedRow && (
                                    <label className="flex items-center gap-2 mb-2 text-xs font-medium text-slate-700">
                                      <input
                                        type="checkbox"
                                        checked={Boolean(linkedItem.immediateActionRequired)}
                                        onChange={() => onToggleImmediateAction(linkedItem.uiId)}
                                        className="w-4 h-4"
                                      />
                                      Immediate action required (24h submit / 48h close)
                                    </label>
                                  )}
                                  {isLoaded && selectedRow && (
                                    <label className="flex items-center gap-2 mb-2 text-xs font-medium text-slate-700">
                                      <input
                                        type="checkbox"
                                        checked={Boolean(linkedItem.silentBox)}
                                        onChange={(e) =>
                                          onUpdateField(linkedItem.uiId, "silentBox", e.target.checked)
                                        }
                                        className="w-4 h-4"
                                      />
                                      Silent Box (SB) — exclude from printed report
                                    </label>
                                  )}
                                  <textarea
                                    value={isLoaded ? (selectedRow ? linkedItem.findings : "Disabled") : ""}
                                    disabled={!isLoaded || !selectedRow}
                                    onChange={(e) => {
                                      if (!isLoaded) return;
                                      onUpdateField(linkedItem.uiId, "findings", e.target.value);
                                    }}
                                    rows={3}
                                    className={`w-full p-2.5 text-sm border rounded-lg resize-none ${
                                      !isLoaded || !selectedRow
                                        ? "bg-slate-50 border-slate-200 text-slate-400"
                                        : linkedItem.errors?.findings
                                          ? "bg-red-50 border-red-400 ring-1 ring-red-200"
                                          : "bg-white border-slate-300"
                                    }`}
                                    placeholder="Optional..."
                                  />
                                  {isLoaded && selectedRow && linkedItem.errors?.findings && (
                                    <p className="text-xs text-red-600 mt-1 font-medium">{linkedItem.errors.findings}</p>
                                  )}
                                </td>

                                <td className="px-4 py-4 align-top">
                                  <div className="space-y-2">
                                    <label className={`inline-flex items-center gap-2 px-3 py-2 text-xs font-medium border rounded-lg transition-colors ${
                                      !isLoaded || !selectedRow
                                        ? "bg-slate-50 border-slate-200 text-slate-400 cursor-not-allowed"
                                        : linkedItem.errors?.findings?.includes("Evidence")
                                          ? "bg-red-50 hover:bg-red-100 border-red-400 ring-1 ring-red-200 cursor-pointer"
                                          : "bg-slate-50 hover:bg-slate-100 border-slate-200 cursor-pointer"
                                    }`}>
                                      <Upload size={14} />
                                      <span>Upload Images</span>
                                      <input
                                        type="file"
                                        accept="image/*"
                                        multiple
                                        className="hidden"
                                        disabled={!isLoaded || !selectedRow}
                                        onChange={(e) => {
                                          if (!isLoaded || !selectedRow) return;
                                          onAddEvidence(linkedItem.uiId, e.target.files);
                                          e.currentTarget.value = "";
                                        }}
                                      />
                                    </label>

                                    {isLoaded && (linkedItem.evidence.length > 0 || linkedItem.uploadedDocs.length > 0) && (
                                      <div className="flex flex-wrap gap-2">
                                        {linkedItem.evidence.map((file, idx) => {
                                          const key = `${linkedItem.questionId}-${file.name}-${file.size}-${file.lastModified}-${idx}`;
                                          const src = previews.get(key);
                                          return (
                                            <div key={key} className="relative group rounded-lg overflow-hidden border border-slate-200 shadow-sm">
                                              {src ? (
                                                <img src={src} alt={file.name} className="h-14 w-14 object-cover" />
                                              ) : (
                                                <div className="h-14 w-14 bg-slate-100" />
                                              )}
                                              <button
                                                type="button"
                                                className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                                                onClick={() => onRemoveLocalEvidence(linkedItem.uiId, idx)}
                                              >
                                                <X size={14} className="text-white" />
                                              </button>
                                            </div>
                                          );
                                        })}
                                        {linkedItem.uploadedDocs.map((doc, idx) => (
                                          <div key={`${linkedItem.uiId}-uploaded-${idx}-${doc.file_url}`} className="relative group rounded-lg overflow-hidden border border-slate-200 shadow-sm">
                                            <img src={doc.file_url} alt={doc.filename} className="h-14 w-14 object-cover" />
                                            <button
                                              type="button"
                                              className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                                              onClick={() => onRemoveUploadedEvidence(linkedItem.uiId, idx)}
                                            >
                                              <X size={14} className="text-white" />
                                            </button>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                </td>

                                {/* REMOVED: CAR column hidden — CAR is auto-managed by parent
                                <td className="px-4 py-4 align-top">
                                  <div className="space-y-3">
                                    <label className="flex items-center gap-2">
                                      <input
                                        type="checkbox"
                                        disabled={!canRequestCAR}
                                        checked={isLoaded ? !!linkedItem.requestCAR : false}
                                        onChange={() => isLoaded && onToggleCAR(linkedItem.uiId)}
                                        className="w-4 h-4"
                                      />
                                      <span className={`text-sm font-medium ${canRequestCAR ? "text-slate-800" : "text-slate-400"}`}>
                                        Request CAR
                                      </span>
                                    </label>

                                    <textarea
                                      value={isLoaded ? (selectedRow ? (linkedItem.requestCAR ? linkedItem.carReason : "") : "Disabled") : ""}
                                      disabled={!isLoaded || !selectedRow || !linkedItem.requestCAR}
                                      onChange={(e) => {
                                        if (!isLoaded) return;
                                        onUpdateField(linkedItem.uiId, "carReason", e.target.value);
                                      }}
                                      rows={3}
                                      className={`w-full p-2.5 text-sm border rounded-lg resize-none ${isLoaded && selectedRow && linkedItem.requestCAR ? "bg-white border-slate-300" : "bg-slate-50 border-slate-200 text-slate-400"}`}
                                      placeholder="CAR reason"
                                    />

                                    {isLoaded && selectedRow && linkedItem.errors?.carReason && (
                                      <p className="text-xs text-red-600 font-medium">{linkedItem.errors.carReason}</p>
                                    )}
                                  </div>
                                </td>
                                */}

                              </tr>
                            );
                          })}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="px-4 py-3 text-xs text-slate-500 bg-white">
                Tip: Unselected rows are excluded from VDA scoring. Optional / N.E. rows are not counted in the score formula.
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

