import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ClipboardList,
  Filter,
  Layers,
  Plus,
  RotateCcw,
  ShieldAlert,
} from "lucide-react";

import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";
import TableAudits from "../../components/tables/BasicTables/TableAudits";
import PlanAudit from "../Audit/PlanAudit";

import { useAppDispatch, useAppSelector } from "../../redux/hooks";
import {
  fetchAudits,
  setAuditFilters as setAuditFiltersAction,
  clearAuditFilters as clearAuditFiltersAction,
} from "../../redux/audit/audit-slice";
import { AuditFilters } from "../../redux/audit/audit-slice-types";
import {
  selectAuditsLoading,
  selectAuditsError,
  selectAuditFilters,
  selectFilteredAudits,
  selectUniqueQuestionnaires,
  selectUniqueAuditors,
  selectUniqueAuditees,
} from "../../redux/audit/audit-selectors";
import CorrectiveActionsPage from "../../components/corrective-actions/CorrectiveActionsPage";

export default function BasicTables() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [activeTab, setActiveTab] = useState<"audits" | "corrective_actions">(
    "audits",
  );
  const [isAuditModalOpen, setIsAuditModalOpen] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  const auditsLoading = useAppSelector(selectAuditsLoading);
  const auditsError = useAppSelector(selectAuditsError);

  const auditFilters =
    useAppSelector(selectAuditFilters) ??
    ({
      search: "",
      status: "",
      plant: "",
      questionnaire: "",
      auditor: "",
      auditee: "",
      dateFrom: "",
      dateTo: "",
    } as AuditFilters);

  const filteredAudits = useAppSelector(selectFilteredAudits) ?? [];
  const uniqueQuestionnaires = useAppSelector(selectUniqueQuestionnaires) ?? [];
  const uniqueAuditors = useAppSelector(selectUniqueAuditors) ?? [];
  const uniqueAuditees = useAppSelector(selectUniqueAuditees) ?? [];
  const authRoles = useAppSelector((state) => state.auth.role || []);
  const normalizedRoles = authRoles.map((role: string) =>
    String(role).trim().toLowerCase(),
  );
  const isAuditor = normalizedRoles.includes("auditor");
  const auditorActionTooltip = "You are not auditor";

  useEffect(() => {
    dispatch(fetchAudits());
  }, [dispatch]);

  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab === "corrective_actions") {
      setActiveTab("corrective_actions");
      return;
    }
    setActiveTab("audits");
  }, [searchParams]);

  const handleTabChange = (tab: "audits" | "corrective_actions") => {
    setActiveTab(tab);
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    if (tab === "audits") {
      next.delete("car_id");
      next.delete("audit_id");
    }
    setSearchParams(next, { replace: true });
  };

  const handleSearchChange = (value: string) =>
    dispatch(setAuditFiltersAction({ search: value }));

  const handleFilterChange = (key: keyof AuditFilters, value: string) =>
    dispatch(setAuditFiltersAction({ [key]: value } as Partial<AuditFilters>));

  const handleResetFilters = () => dispatch(clearAuditFiltersAction());

  return (
    <>
      <PageMeta
        title="Audits & Corrective Actions"
        description="Manage audit plans, track status, and review corrective actions"
      />

      <div className="space-y-5">
        <PageBreadcrumb
          kicker="Operations"
          pageTitle="Audits & Corrective Actions"
          description="Manage audit plans, track status, and review corrective actions"
          actions={
            activeTab === "audits" ? (
              <button
                onClick={() => setIsAuditModalOpen(true)}
                disabled={!isAuditor}
                title={!isAuditor ? auditorActionTooltip : undefined}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-300/50 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
              >
                <Plus className="h-4 w-4" />
                Plan audit
              </button>
            ) : null
          }
        />

        {/* Main card */}
        <div className="rounded-2xl border border-slate-200/70 bg-white shadow-sm dark:border-slate-800/70 dark:bg-slate-950/60">
          {/* Tabs */}
          <div className="p-2">
            <div className="inline-flex rounded-xl border border-slate-200/70 bg-slate-50 p-1 dark:border-slate-800/70 dark:bg-slate-900/70">
              {(["audits", "corrective_actions"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => handleTabChange(tab)}
                  className={`inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition ${
                    activeTab === tab
                      ? "bg-slate-900 text-white shadow-sm dark:bg-white dark:text-slate-900"
                      : "text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
                  }`}
                >
                  {tab === "audits" ? (
                    <ClipboardList className="h-4 w-4" />
                  ) : (
                    <ShieldAlert className="h-4 w-4" />
                  )}
                  {tab === "audits" ? "Audits" : "Corrective actions"}
                </button>
              ))}

              <button
                onClick={() => navigate("/audits/consolidation")}
                disabled={!isAuditor}
                title={!isAuditor ? auditorActionTooltip : undefined}
                className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50 dark:text-slate-300 dark:hover:text-white"
              >
                <Layers className="h-4 w-4" />
                Audit consolidation
              </button>
            </div>
          </div>

          <div className="border-t border-slate-200/70 p-5 dark:border-slate-800/70">
            {/* Audits tab */}
            {activeTab === "audits" && (
              <>
                {/* Toolbar */}
                <div className="mb-4 flex flex-wrap gap-2 rounded-xl border border-slate-200/70 bg-slate-50 p-3 dark:border-slate-800/70 dark:bg-slate-900/50">
                  <input
                    type="text"
                    placeholder="Search by ID, auditor, plant..."
                    value={auditFilters.search ?? ""}
                    onChange={(e) => handleSearchChange(e.target.value)}
                    className="flex-1 min-w-[200px] rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200/70 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-100"
                  />

                  <button
                    onClick={() => setShowFilters((s) => !s)}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition ${
                      showFilters
                        ? "border-slate-300 bg-white text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300"
                    }`}
                  >
                    <Filter className="h-4 w-4" />
                    Filters
                  </button>

                  <button
                    onClick={handleResetFilters}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300"
                  >
                    <RotateCcw className="h-4 w-4" />
                    Reset
                  </button>
                </div>

                {/* Filter panel */}
                {showFilters && (
                  <div className="mb-4 grid grid-cols-2 gap-3 rounded-xl border border-slate-200/70 bg-white p-4 shadow-sm sm:grid-cols-3 lg:grid-cols-6 dark:border-slate-800/70 dark:bg-slate-900/60">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
                        Status
                      </label>
                      <select
                        className="w-full rounded-lg border border-slate-200 bg-white p-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
                        value={auditFilters.status ?? ""}
                        onChange={(e) =>
                          handleFilterChange("status", e.target.value)
                        }
                      >
                        <option value="">All</option>
                        <option value="planned_or_rescheduled">
                          Planned / Rescheduled
                        </option>
                        <option value="waiting_for_corrective_actions">
                          Ongoing (Waiting for CAR)
                        </option>
                        <option value="completed">Completed</option>
                        <option value="cancelled">Cancelled</option>
                      </select>
                    </div>

                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                        Plant
                      </label>
                      <select
                        className="w-full rounded-lg border border-slate-200 bg-white p-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
                        value={auditFilters.plant ?? ""}
                        onChange={(e) =>
                          handleFilterChange("plant", e.target.value)
                        }
                      >
                        <option value="">All</option>
                        {[
                          "anhui",
                          "chennai",
                          "loire",
                          "daegu",
                          "frankfort",
                          "galeana",
                          "kunshan",
                          "monterrey",
                          "medina",
                          "poitiers",
                          "rayones",
                          "carthage",
                          "atlas",
                          "tianjin",
                        ].map((p, idx) => (
                          <option
                            key={`plant-${p || "empty"}-${idx}`}
                            value={p}
                          >
                            {p.charAt(0).toUpperCase() + p.slice(1)}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
                        Questionnaire
                      </label>
                      <select
                        className="w-full rounded-lg border border-slate-200 bg-white p-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
                        value={auditFilters.questionnaire ?? ""}
                        onChange={(e) =>
                          handleFilterChange("questionnaire", e.target.value)
                        }
                      >
                        <option value="">All</option>
                        {uniqueQuestionnaires.map((q, idx) => (
                          <option
                            key={`questionnaire-${q || "empty"}-${idx}`}
                            value={q}
                          >
                            {q}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
                        Auditor
                      </label>
                      <select
                        className="w-full rounded-lg border border-slate-200 bg-white p-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
                        value={auditFilters.auditor ?? ""}
                        onChange={(e) =>
                          handleFilterChange("auditor", e.target.value)
                        }
                      >
                        <option value="">All</option>
                        {uniqueAuditors.map((email, idx) => (
                          <option
                            key={`auditor-${email || "empty"}-${idx}`}
                            value={email}
                          >
                            {email}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
                        Auditee
                      </label>
                      <select
                        className="w-full rounded-lg border border-slate-200 bg-white p-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
                        value={auditFilters.auditee ?? ""}
                        onChange={(e) =>
                          handleFilterChange("auditee", e.target.value)
                        }
                      >
                        <option value="">All</option>
                        {uniqueAuditees.map((email, idx) => (
                          <option
                            key={`auditee-${email || "empty"}-${idx}`}
                            value={email}
                          >
                            {email}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
                        Date range
                      </label>
                      <div className="flex items-center gap-1">
                        <input
                          type="date"
                          className="w-full rounded-lg border border-slate-200 bg-white p-2 text-xs text-slate-700 focus:border-slate-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
                          value={auditFilters.dateFrom ?? ""}
                          onChange={(e) =>
                            handleFilterChange("dateFrom", e.target.value)
                          }
                        />
                        <span className="text-xs text-slate-400">-</span>
                        <input
                          type="date"
                          className="w-full rounded-lg border border-slate-200 bg-white p-2 text-xs text-slate-700 focus:border-slate-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
                          value={auditFilters.dateTo ?? ""}
                          onChange={(e) =>
                            handleFilterChange("dateTo", e.target.value)
                          }
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* Error */}
                {auditsError && (
                  <div className="mb-4 flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300">
                    <svg
                      className="h-4 w-4 shrink-0"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                      viewBox="0 0 24 24"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <path strokeLinecap="round" d="M12 8v4m0 4h.01" />
                    </svg>
                    Failed to load audits: {auditsError}
                  </div>
                )}

                {/* Content */}
                {auditsLoading ? (
                  <div className="flex items-center justify-center py-12 text-sm text-slate-400">
                    <span className="animate-pulse">Loading audits...</span>
                  </div>
                ) : filteredAudits.length === 0 ? (
                  <div className="py-12 text-center text-sm text-slate-400">
                    No audits match your filters.
                  </div>
                ) : (
                  <TableAudits
                    audits={filteredAudits}
                    statusFilter={auditFilters.status ?? ""}
                  />
                )}
              </>
            )}

            {/* Corrective actions tab */}
            {activeTab === "corrective_actions" && <CorrectiveActionsPage />}
          </div>
        </div>
      </div>

      <PlanAudit
        isAuditModalOpen={isAuditModalOpen}
        closeAuditModalOpen={() => setIsAuditModalOpen(false)}
      />
    </>
  );
}
