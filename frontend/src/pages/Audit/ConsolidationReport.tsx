import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layers, ArrowLeft, FileDown, X } from "lucide-react";
import { toast } from "react-hot-toast";
import type { AxiosError } from "axios";

import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";
import axiosInstance from "../../services/axiosInstance";
import { useAppDispatch, useAppSelector } from "../../redux/hooks";
import { fetchAudits } from "../../redux/audit/audit-slice";
import type { Audit } from "../../redux/audit/audit-types";

const TOAST_STYLE_BASE = { borderRadius: "12px", padding: "14px" };
const TOAST_DARK = { ...TOAST_STYLE_BASE, background: "#0b2c44", color: "#fff" };
const TOAST_SUCCESS = { ...TOAST_STYLE_BASE, background: "#059669", color: "#fff" };
const TOAST_ERROR = { ...TOAST_STYLE_BASE, background: "#dc2626", color: "#fff" };

function formatDate(value?: string | null) {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

const CONSOLIDATABLE_STATUSES = new Set<string>([
  "completed",
  "waiting_for_corrective_actions",
]);

function statusPill(status?: string) {
  switch ((status || "").toLowerCase()) {
    case "completed":
      return "bg-emerald-100 text-emerald-900 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-800";
    case "cancelled":
      return "bg-rose-100 text-rose-900 border-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:border-rose-800";
    case "waiting_for_corrective_actions":
      return "bg-sky-100 text-sky-900 border-sky-200 dark:bg-sky-900/30 dark:text-sky-300 dark:border-sky-800";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700";
  }
}

export default function ConsolidationReport() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const audits = useAppSelector((state) => state.audit.items);
  const auditsLoading = useAppSelector((state) => state.audit.loading);

  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    dispatch(fetchAudits());
  }, [dispatch]);

  // Only audits that have actually been carried out (completed, or ongoing
  // while their CARs are still open) with a real questionnaire link carry a
  // meaningful set of findings to consolidate — legacy audits backfilled from
  // the monday.com migration have no questionnaire (shown as "N/A") and can't
  // be grouped by theme, so they're excluded here.
  const eligibleAudits = useMemo(
    () =>
      audits.filter(
        (audit) =>
          CONSOLIDATABLE_STATUSES.has(audit.status ?? "") && audit.questionnaire?.name,
      ),
    [audits],
  );

  const filteredAudits = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return eligibleAudits;
    return eligibleAudits.filter((audit) =>
      [audit.audit_number, audit.plant, audit.questionnaire?.name]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(term)),
    );
  }, [eligibleAudits, search]);

  // Once the first audit is picked, only audits sharing its plant and
  // questionnaire may be added — a consolidated report only makes sense
  // for e.g. "several IATF audits for Plant X", not an arbitrary mix.
  const selectedAudits = useMemo(
    () => audits.filter((audit) => selectedIds.has(audit.id)),
    [audits, selectedIds],
  );
  const lockPlant = selectedAudits[0]?.plant ?? null;
  const lockQuestionnaireId = selectedAudits[0]?.questionnaire?.id ?? null;
  const lockQuestionnaireName = selectedAudits[0]?.questionnaire?.name ?? null;

  function matchesLock(audit: Audit) {
    if (!lockPlant) return true;
    return (
      audit.plant === lockPlant &&
      (audit.questionnaire?.id ?? null) === lockQuestionnaireId
    );
  }

  function toggleAudit(audit: Audit) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(audit.id)) {
        next.delete(audit.id);
        return next;
      }
      if (!matchesLock(audit)) {
        toast.error(
          `Only ${lockQuestionnaireName ?? "the same questionnaire"} audits from ${lockPlant} can be added to this selection.`,
          { style: TOAST_ERROR },
        );
        return prev;
      }
      next.add(audit.id);
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  function toggleSelectAllVisible() {
    setSelectedIds((prev) => {
      const selectableVisible = filteredAudits.filter(
        (audit) => matchesLock(audit) || prev.has(audit.id),
      );
      const visibleIds = selectableVisible.map((a) => a.id);
      const allSelected =
        visibleIds.length > 0 && visibleIds.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) {
        visibleIds.forEach((id) => next.delete(id));
      } else {
        visibleIds.forEach((id) => next.add(id));
      }
      return next;
    });
  }

  async function generateConsolidatedReport() {
    if (selectedIds.size < 2 || generating) return;
    setGenerating(true);
    const loadingToast = toast.loading("Generating consolidated report…", {
      style: TOAST_DARK,
    });
    try {
      const response = await axiosInstance.post(
        "/reports/consolidate-theme-report",
        { audit_ids: Array.from(selectedIds) },
        { responseType: "blob" },
      );
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      const timestamp = new Date().toISOString().slice(0, 10);
      link.setAttribute("download", `consolidated_audit_report_${timestamp}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Consolidated report downloaded.", {
        id: loadingToast,
        style: TOAST_SUCCESS,
      });
    } catch (error) {
      const axiosError = error as AxiosError<{ detail?: string }>;
      const detail =
        typeof axiosError?.response?.data === "object"
          ? (axiosError.response?.data as { detail?: string })?.detail
          : undefined;
      toast.error(detail || "Failed to generate the consolidated report.", {
        id: loadingToast,
        style: TOAST_ERROR,
      });
    } finally {
      setGenerating(false);
    }
  }

  const selectableVisible = filteredAudits.filter(
    (audit) => matchesLock(audit) || selectedIds.has(audit.id),
  );
  const allVisibleSelected =
    selectableVisible.length > 0 &&
    selectableVisible.every((audit) => selectedIds.has(audit.id));

  return (
    <>
      <PageMeta
        title="Audit Consolidation"
        description="Select several audits of the same plant and questionnaire and merge them into one consolidated report grouped by theme"
      />

      <div className="space-y-5">
        <PageBreadcrumb
          kicker="Operations"
          pageTitle="Audit Consolidation"
          description="Select two or more completed or ongoing audits from the same plant and questionnaire (e.g. several IATF audits for one plant) to merge their full results into a single report, organized by theme."
          actions={
            <button
              onClick={() => navigate("/audits")}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to audits
            </button>
          }
        />

        <div className="rounded-2xl border border-slate-200/70 bg-white shadow-sm dark:border-slate-800/70 dark:bg-slate-950/60">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/70 p-5 dark:border-slate-800/70">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
                <Layers className="h-4 w-4" />
                {selectedIds.size} audit{selectedIds.size === 1 ? "" : "s"} selected
              </div>
              {lockPlant && (
                <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300">
                  {lockQuestionnaireName} · {lockPlant}
                  <button
                    onClick={clearSelection}
                    aria-label="Clear selection"
                    className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-100"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
              )}
            </div>
            <button
              onClick={generateConsolidatedReport}
              disabled={selectedIds.size < 2 || generating}
              title={
                selectedIds.size < 2
                  ? "Select at least two audits to consolidate"
                  : undefined
              }
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-300/50 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
            >
              <FileDown className="h-4 w-4" />
              {generating ? "Generating…" : "Generate consolidated report"}
            </button>
          </div>

          <div className="p-5">
            <input
              type="text"
              placeholder="Search by audit number, plant, or questionnaire..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="mb-4 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200/70 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-100"
            />

            {auditsLoading ? (
              <div className="flex items-center justify-center py-12 text-sm text-slate-400">
                <span className="animate-pulse">Loading audits...</span>
              </div>
            ) : filteredAudits.length === 0 ? (
              <div className="py-12 text-center text-sm text-slate-400">
                No completed or ongoing audits match your search.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-200/70 dark:border-slate-800/70">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500 dark:bg-slate-900/70 dark:text-slate-400">
                    <tr>
                      <th className="w-10 px-4 py-3">
                        <input
                          type="checkbox"
                          checked={allVisibleSelected}
                          onChange={toggleSelectAllVisible}
                          className="h-4 w-4 rounded border-slate-300 accent-slate-900 dark:accent-white"
                        />
                      </th>
                      <th className="px-4 py-3">Audit number</th>
                      <th className="px-4 py-3">Plant</th>
                      <th className="px-4 py-3">Questionnaire</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Planned start</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {filteredAudits.map((audit) => {
                      const selected = selectedIds.has(audit.id);
                      const selectable = matchesLock(audit) || selected;
                      return (
                        <tr
                          key={audit.id}
                          onClick={() => selectable && toggleAudit(audit)}
                          title={
                            !selectable
                              ? `Only ${lockQuestionnaireName ?? "matching"} audits from ${lockPlant} can be added right now`
                              : undefined
                          }
                          className={`transition ${
                            selected
                              ? "bg-slate-50 dark:bg-slate-900/60"
                              : selectable
                                ? "cursor-pointer hover:bg-slate-50/60 dark:hover:bg-slate-900/40"
                                : "cursor-not-allowed opacity-40"
                          }`}
                        >
                          <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                            <input
                              type="checkbox"
                              checked={selected}
                              disabled={!selectable}
                              onChange={() => selectable && toggleAudit(audit)}
                              className="h-4 w-4 rounded border-slate-300 accent-slate-900 disabled:cursor-not-allowed dark:accent-white"
                            />
                          </td>
                          <td className="px-4 py-3 font-medium text-slate-900 dark:text-white">
                            {audit.audit_number}
                          </td>
                          <td className="px-4 py-3 text-slate-600 dark:text-slate-300">
                            {audit.plant || "N/A"}
                          </td>
                          <td className="px-4 py-3 text-slate-600 dark:text-slate-300">
                            {audit.questionnaire?.name || "N/A"}
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statusPill(audit.status)}`}
                            >
                              {(audit.status || "unknown").replace(/_/g, " ")}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-slate-600 dark:text-slate-300">
                            {formatDate(audit.planned_start_date)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
