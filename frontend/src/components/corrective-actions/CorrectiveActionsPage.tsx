import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import TableCorrectiveActions from "../tables/BasicTables/TableCorrectiveActions";
import AuditorHolidayWidget from "./AuditorHolidayWidget";
import {
  CorrectiveAction,
  CorrectiveActionListResponse,
  CorrectiveActionStatus,
} from "../../types";
import {
  escalateCorrectiveAction,
  extendCorrectiveActionDueDate,
  reassignCorrectiveActionAuditee,
  fetchCorrectiveActions,
  reviewCorrectiveAction,
} from "../../services/correctiveActionsApi";
import { useDebouncedValue } from "../../redux/hooks";
import {
  MagnifyingGlassIcon,
  FunnelIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  ExclamationCircleIcon,
} from "@heroicons/react/24/outline";

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
const SERVER_BATCH_SIZE = 100;

type DateFilterField = "due_date" | "created_at" | "submitted_at";

type ClientFilters = {
  plant: string;
  auditee: string;
  pilotUser: string;
  findingType: string;
  escalated: "" | "yes" | "no";
  dateField: DateFilterField;
  dateFrom: string;
  dateTo: string;
};

const DEFAULT_CLIENT_FILTERS: ClientFilters = {
  plant: "",
  auditee: "",
  pilotUser: "",
  findingType: "",
  escalated: "",
  dateField: "due_date",
  dateFrom: "",
  dateTo: "",
};

const STATUS_CONFIG: Record<
  CorrectiveActionStatus | "all",
  {
    label: string;
    color: string;
    activeColor: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  all: {
    label: "All",
    color:
      "text-slate-600 ring-slate-200 bg-white hover:bg-slate-50 dark:text-slate-300 dark:ring-slate-600/40 dark:bg-white/5",
    activeColor:
      "bg-[#0f2333] text-white ring-[#0f2333] dark:bg-[#0f2333] dark:text-white",
    icon: FunnelIcon,
  },
  Pending: {
    label: "Pending",
    color:
      "text-amber-700 ring-amber-200 bg-white hover:bg-amber-50 dark:text-amber-300 dark:ring-amber-700/40 dark:bg-white/5",
    activeColor: "bg-[#d48a1b] text-white ring-[#d48a1b]",
    icon: ClockIcon,
  },
  Submitted: {
    label: "Submitted",
    color:
      "text-[#0f2333] ring-[#0f2333]/20 bg-white hover:bg-[#0f2333]/10 dark:text-[#b9ddf5] dark:ring-[#0f2333] dark:bg-white/5",
    activeColor: "bg-[#0f2333] text-white ring-[#0f2333]",
    icon: ExclamationCircleIcon,
  },
  Accepted: {
    label: "Accepted",
    color:
      "text-emerald-700 ring-emerald-200 bg-white hover:bg-emerald-50 dark:text-emerald-400 dark:ring-emerald-800 dark:bg-white/5",
    activeColor: "bg-emerald-600 text-white ring-emerald-600",
    icon: CheckCircleIcon,
  },
  Rejected: {
    label: "Rejected",
    color:
      "text-rose-700 ring-rose-200 bg-white hover:bg-rose-50 dark:text-rose-400 dark:ring-rose-800 dark:bg-white/5",
    activeColor: "bg-rose-600 text-white ring-rose-600",
    icon: XCircleIcon,
  },
};

export default function CorrectiveActionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryCarIdRaw = searchParams.get("car_id");
  const queryAuditIdRaw = searchParams.get("audit_id");
  const querySearch = searchParams.get("search") || "";
  const targetCarIdFromQuery =
    queryCarIdRaw && Number.isFinite(Number(queryCarIdRaw))
      ? Number(queryCarIdRaw)
      : null;

  const [allItems, setAllItems] = useState<CorrectiveAction[]>([]);
  const [limit, setLimit] = useState(20);
  const [pageIndex, setPageIndex] = useState(0);
  const [searchInput, setSearchInput] = useState(querySearch);
  const debouncedSearch = useDebouncedValue(searchInput, 400);

  const [status, setStatus] = useState<CorrectiveActionStatus | "">("");
  const [showFilters, setShowFilters] = useState(false);
  const [clientFilters, setClientFilters] =
    useState<ClientFilters>(DEFAULT_CLIENT_FILTERS);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);
  const [pendingTargetCarId, setPendingTargetCarId] = useState<number | null>(
    null,
  );

  useEffect(() => {
    if (!targetCarIdFromQuery) {
      setPendingTargetCarId(null);
      return;
    }
    setPendingTargetCarId(targetCarIdFromQuery);
    setStatus("");
    setPageIndex(0);
  }, [targetCarIdFromQuery]);

  useEffect(() => {
    setSearchInput(querySearch);
  }, [querySearch]);

  const handleTargetCarOpened = useCallback(
    (openedCarId: number) => {
      if (!pendingTargetCarId || openedCarId !== pendingTargetCarId) return;
      setPendingTargetCarId(null);
      const next = new URLSearchParams(searchParams);
      next.delete("car_id");
      setSearchParams(next, { replace: true });
    },
    [pendingTargetCarId, searchParams, setSearchParams],
  );

  const normalizedItems = useMemo(
    () =>
      allItems.map((item) => ({
        ...item,
        plantLabel: item.plant_name?.trim() || item.plant?.trim() || "",
        auditeeLabel: item.auditee?.trim() || "",
        pilotLabel: item.pilotUser?.trim() || "",
        findingLabel: item.finding_type?.trim() || "",
      })),
    [allItems],
  );

  const filterOptions = useMemo(() => {
    const toSortedUnique = (values: string[]) =>
      [...new Set(values.filter(Boolean))].sort((a, b) =>
        a.localeCompare(b, undefined, { sensitivity: "base" }),
      );

    return {
      plants: toSortedUnique(normalizedItems.map((item) => item.plantLabel)),
      auditees: toSortedUnique(
        normalizedItems.map((item) => item.auditeeLabel),
      ),
      pilotUsers: toSortedUnique(normalizedItems.map((item) => item.pilotLabel)),
      findingTypes: toSortedUnique(
        normalizedItems.map((item) => item.findingLabel),
      ),
    };
  }, [normalizedItems]);

  const filteredItems = useMemo(() => {
    const normalize = (value?: string | null) => value?.trim().toLowerCase() || "";
    const rawFromDate = clientFilters.dateFrom
      ? new Date(`${clientFilters.dateFrom}T00:00:00`)
      : null;
    const rawToDate = clientFilters.dateTo
      ? new Date(`${clientFilters.dateTo}T23:59:59.999`)
      : null;
    const fromDate =
      rawFromDate && rawToDate && rawFromDate > rawToDate ? rawToDate : rawFromDate;
    const toDate =
      rawFromDate && rawToDate && rawFromDate > rawToDate ? rawFromDate : rawToDate;

    return normalizedItems.filter((item) => {
      if (
        clientFilters.plant &&
        normalize(item.plantLabel) !== normalize(clientFilters.plant)
      ) {
        return false;
      }

      if (
        clientFilters.auditee &&
        normalize(item.auditeeLabel) !== normalize(clientFilters.auditee)
      ) {
        return false;
      }

      if (
        clientFilters.pilotUser &&
        normalize(item.pilotLabel) !== normalize(clientFilters.pilotUser)
      ) {
        return false;
      }

      if (
        clientFilters.findingType &&
        normalize(item.findingLabel) !== normalize(clientFilters.findingType)
      ) {
        return false;
      }

      if (
        clientFilters.escalated &&
        (clientFilters.escalated === "yes") !== item.escalated
      ) {
        return false;
      }

      if (fromDate || toDate) {
        const rawDate = item[clientFilters.dateField];
        if (!rawDate) return false;
        const itemDate = new Date(rawDate);
        if (Number.isNaN(itemDate.getTime())) return false;
        if (fromDate && itemDate < fromDate) return false;
        if (toDate && itemDate > toDate) return false;
      }

      return true;
    });
  }, [clientFilters, normalizedItems]);

  // The table below groups corrective actions by audit. Slicing the flat,
  // ungrouped list by raw item count (as this used to) can cut an audit's
  // CARs in half across two pages - whichever CARs land after the cut
  // silently disappear from view, since the audit's group header and row
  // count are drawn only from whichever items made it onto the current
  // page. Paginating over whole audit groups instead guarantees every CAR
  // for an audit shows up together, on one page.
  const pages = useMemo(() => {
    const auditOrder: number[] = [];
    const byAudit = new Map<number, CorrectiveAction[]>();
    for (const item of filteredItems) {
      if (!byAudit.has(item.auditId)) {
        byAudit.set(item.auditId, []);
        auditOrder.push(item.auditId);
      }
      byAudit.get(item.auditId)!.push(item);
    }

    const result: CorrectiveAction[][] = [];
    let current: CorrectiveAction[] = [];
    for (const auditId of auditOrder) {
      const group = byAudit.get(auditId)!;
      if (current.length > 0 && current.length + group.length > limit) {
        result.push(current);
        current = [];
      }
      current.push(...group);
    }
    if (current.length > 0) result.push(current);
    return result.length > 0 ? result : [[]];
  }, [filteredItems, limit]);

  const total = filteredItems.length;
  const totalPages = pages.length;
  // Clamp defensively: filters/status changes or an accept/reject action
  // can shrink `pages` out from under an already-selected page index.
  const currentPageIndex = Math.min(pageIndex, totalPages - 1);
  const currentPage = currentPageIndex + 1;
  const items = pages[currentPageIndex] ?? [];
  const pageStartOffset = useMemo(
    () =>
      pages
        .slice(0, currentPageIndex)
        .reduce((sum, page) => sum + page.length, 0),
    [pages, currentPageIndex],
  );
  const hasPrev = currentPageIndex > 0;
  const hasNext = currentPageIndex < totalPages - 1;

  const loadData = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      else setRefreshing(true);
      setError(null);
      try {
        let nextOffset = 0;
        let aggregatedItems: CorrectiveAction[] = [];
        let hasNextPage = true;

        while (hasNextPage) {
          const data: CorrectiveActionListResponse =
            await fetchCorrectiveActions({
            search: debouncedSearch,
            status,
            audit_id:
              queryAuditIdRaw && Number.isFinite(Number(queryAuditIdRaw))
                ? Number(queryAuditIdRaw)
                : undefined,
            car_id: pendingTargetCarId ?? undefined,
            include_documents: false,
            limit: SERVER_BATCH_SIZE,
            offset: nextOffset,
          });

          aggregatedItems = [...aggregatedItems, ...data.items];
          hasNextPage = data.has_next;
          nextOffset += data.limit;
        }

        setAllItems(aggregatedItems);
      } catch (err) {
        console.error(err);
        setError("Failed to load corrective actions. Please try again.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [
      debouncedSearch,
      status,
      queryAuditIdRaw,
      pendingTargetCarId,
    ],
  );

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    setPageIndex(0);
  }, [clientFilters, debouncedSearch, status, pendingTargetCarId, queryAuditIdRaw]);

  useEffect(() => {
    if (!actionFeedback) return;
    const t = setTimeout(() => setActionFeedback(null), 4000);
    return () => clearTimeout(t);
  }, [actionFeedback]);

  const handleAccept = useCallback(
    async (id: number) => {
      await reviewCorrectiveAction(id, { decision: "ACCEPT" });
      setActionFeedback({
        type: "success",
        message: `CAR #${id} accepted successfully.`,
      });
      await loadData(true);
    },
    [loadData],
  );

  const handleReject = useCallback(
    async (id: number, reason: string) => {
      await reviewCorrectiveAction(id, { decision: "REJECT", comment: reason });
      setActionFeedback({
        type: "error",
        message: `CAR #${id} has been rejected.`,
      });
      await loadData(true);
    },
    [loadData],
  );

  const handleExtendDueDate = useCallback(
    async (id: number, newDueDate: string, comment?: string) => {
      await extendCorrectiveActionDueDate(id, {
        new_due_date: newDueDate,
        comment,
      });
      setActionFeedback({
        type: "success",
        message: `CAR #${id} due date updated successfully.`,
      });
      await loadData(true);
    },
    [loadData],
  );

  const handleEscalate = useCallback(
    async (id: number, emails: string[], comment?: string) => {
      await escalateCorrectiveAction(id, { emails, comment });
      setActionFeedback({
        type: "success",
        message: `CAR #${id} escalated successfully.`,
      });
      await loadData(true);
    },
    [loadData],
  );

  const handleReassignAuditee = useCallback(
    async (id: number, newAuditeeEmail: string, reason?: string) => {
      await reassignCorrectiveActionAuditee(id, {
        new_auditee_email: newAuditeeEmail,
        reason,
      });
      setActionFeedback({
        type: "success",
        message: `CAR #${id} reassigned to ${newAuditeeEmail}.`,
      });
      await loadData(true);
    },
    [loadData],
  );

  const handleSearchChange = (v: string) => {
    if (searchParams.get("audit_id")) {
      const next = new URLSearchParams(searchParams);
      next.delete("audit_id");
      setSearchParams(next, { replace: true });
    }
    setSearchInput(v);
    setPageIndex(0);
  };
  const handleStatusChange = (v: CorrectiveActionStatus | "") => {
    if (searchParams.get("audit_id")) {
      const next = new URLSearchParams(searchParams);
      next.delete("audit_id");
      setSearchParams(next, { replace: true });
    }
    setStatus(v);
    setPageIndex(0);
  };
  const handlePageSizeChange = (v: number) => {
    setLimit(v);
    setPageIndex(0);
  };
  const handleClientFilterChange = <K extends keyof ClientFilters>(
    key: K,
    value: ClientFilters[K],
  ) => {
    setClientFilters((prev) => ({ ...prev, [key]: value }));
  };
  const hasActiveClientFilters = Object.entries(clientFilters).some(
    ([key, value]) => key !== "dateField" && value !== "",
  );
  const hasAnyActiveFilters =
    !!searchInput ||
    !!status ||
    hasActiveClientFilters ||
    !!queryAuditIdRaw ||
    !!pendingTargetCarId;
  const clearAllFilters = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("audit_id");
    next.delete("car_id");
    next.delete("search");
    setSearchParams(next, { replace: true });
    setPendingTargetCarId(null);
    setSearchInput("");
    setStatus("");
    setClientFilters(DEFAULT_CLIENT_FILTERS);
    setPageIndex(0);
  };
  const goPrev = () => {
    if (hasPrev) setPageIndex((p) => Math.max(0, p - 1));
  };
  const goNext = () => {
    if (hasNext) setPageIndex((p) => p + 1);
  };

  return (
    <div className="space-y-4 [font-family:'Manrope',sans-serif]">
      <AuditorHolidayWidget />

      {/* Toolbar row */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Status pills */}
        <div className="flex flex-wrap gap-1.5">
          {(["", "Pending", "Submitted", "Accepted", "Rejected"] as const).map(
            (s) => {
              const key = s === "" ? "all" : s;
              const cfg = STATUS_CONFIG[key as keyof typeof STATUS_CONFIG];
              const Icon = cfg.icon;
              const isActive = status === s;
              return (
                <button
                  key={key}
                  onClick={() =>
                    handleStatusChange(s as CorrectiveActionStatus | "")
                  }
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition ${isActive ? cfg.activeColor : cfg.color}`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {cfg.label}
                </button>
              );
            },
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setShowFilters((prev) => !prev)}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
              showFilters || hasActiveClientFilters
                ? "border-[#0f2333] bg-[#0f2333] text-white dark:border-[#0f2333] dark:bg-[#0f2333]"
                : "border-[#c8d8e4] bg-white text-[#40596b] hover:bg-[#edf3f8] dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#c0deef]"
            }`}
          >
            <FunnelIcon className="h-3.5 w-3.5" />
            Filters
          </button>

          <button
            onClick={clearAllFilters}
            disabled={!hasAnyActiveFilters}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#c8d8e4] bg-white px-3 py-1.5 text-xs font-semibold text-[#40596b] transition hover:bg-[#edf3f8] disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#c0deef]"
          >
            Clear filters
          </button>

          {/* Refresh */}
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#c8d8e4] bg-white px-3 py-1.5 text-xs font-semibold text-[#40596b] transition hover:bg-[#edf3f8] disabled:opacity-50 dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#c0deef]"
          >
            <ArrowPathIcon
              className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
            />
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Search + page size */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            value={searchInput}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search CAR, audit, plant, auditee, question..."
            className="w-full rounded-lg border border-[#c8d8e4] bg-white py-2 pl-9 pr-3 text-sm outline-none placeholder:text-[#8ba2b3] focus:border-[#0f2333] focus:ring-2 focus:ring-[#89aec8]/40 dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#e1edf5]"
          />
        </div>

        <select
          value={limit}
          onChange={(e) => handlePageSizeChange(Number(e.target.value))}
          className="rounded-lg border border-[#c8d8e4] bg-white px-3 py-2 text-sm text-[#476174] outline-none focus:border-[#0f2333] dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#e1edf5]"
        >
          {PAGE_SIZE_OPTIONS.map((size) => (
            <option key={size} value={size}>
              {size} / page
            </option>
          ))}
        </select>

        <p className="shrink-0 text-xs text-gray-400 dark:text-gray-500">
          {loading
            ? "Loading..."
            : `${total.toLocaleString()} result${total !== 1 ? "s" : ""}${status ? ` · ${STATUS_CONFIG[status as CorrectiveActionStatus]?.label}` : ""}`}
        </p>
      </div>

      {showFilters && (
        <div className="grid grid-cols-1 gap-3 rounded-2xl border border-[#d5e0e8] bg-[#f8fbfd] p-4 md:grid-cols-2 xl:grid-cols-4 dark:border-[#1a4a6a] dark:bg-[#0e3048]/40">
          <div>
            <label className="mb-1 block text-xs font-semibold text-[#5f7889] dark:text-[#a9cee5]">
              Plant
            </label>
            <select
              value={clientFilters.plant}
              onChange={(e) => handleClientFilterChange("plant", e.target.value)}
              className="w-full rounded-lg border border-[#c8d8e4] bg-white px-3 py-2 text-sm text-[#476174] outline-none focus:border-[#0f2333] dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#e1edf5]"
            >
              <option value="">All plants</option>
              {filterOptions.plants.map((plant) => (
                <option key={plant} value={plant}>
                  {plant}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-[#5f7889] dark:text-[#a9cee5]">
              Auditee
            </label>
            <select
              value={clientFilters.auditee}
              onChange={(e) =>
                handleClientFilterChange("auditee", e.target.value)
              }
              className="w-full rounded-lg border border-[#c8d8e4] bg-white px-3 py-2 text-sm text-[#476174] outline-none focus:border-[#0f2333] dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#e1edf5]"
            >
              <option value="">All auditees</option>
              {filterOptions.auditees.map((auditee) => (
                <option key={auditee} value={auditee}>
                  {auditee}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-[#5f7889] dark:text-[#a9cee5]">
              Pilot
            </label>
            <select
              value={clientFilters.pilotUser}
              onChange={(e) =>
                handleClientFilterChange("pilotUser", e.target.value)
              }
              className="w-full rounded-lg border border-[#c8d8e4] bg-white px-3 py-2 text-sm text-[#476174] outline-none focus:border-[#0f2333] dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#e1edf5]"
            >
              <option value="">All pilots</option>
              {filterOptions.pilotUsers.map((pilot) => (
                <option key={pilot} value={pilot}>
                  {pilot}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-[#5f7889] dark:text-[#a9cee5]">
              Finding type
            </label>
            <select
              value={clientFilters.findingType}
              onChange={(e) =>
                handleClientFilterChange("findingType", e.target.value)
              }
              className="w-full rounded-lg border border-[#c8d8e4] bg-white px-3 py-2 text-sm text-[#476174] outline-none focus:border-[#0f2333] dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#e1edf5]"
            >
              <option value="">All finding types</option>
              {filterOptions.findingTypes.map((findingType) => (
                <option key={findingType} value={findingType}>
                  {findingType}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-[#5f7889] dark:text-[#a9cee5]">
              Escalated
            </label>
            <select
              value={clientFilters.escalated}
              onChange={(e) =>
                handleClientFilterChange(
                  "escalated",
                  e.target.value as ClientFilters["escalated"],
                )
              }
              className="w-full rounded-lg border border-[#c8d8e4] bg-white px-3 py-2 text-sm text-[#476174] outline-none focus:border-[#0f2333] dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#e1edf5]"
            >
              <option value="">All escalation states</option>
              <option value="yes">Escalated only</option>
              <option value="no">Not escalated</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-[#5f7889] dark:text-[#a9cee5]">
              Date field
            </label>
            <select
              value={clientFilters.dateField}
              onChange={(e) =>
                handleClientFilterChange(
                  "dateField",
                  e.target.value as DateFilterField,
                )
              }
              className="w-full rounded-lg border border-[#c8d8e4] bg-white px-3 py-2 text-sm text-[#476174] outline-none focus:border-[#0f2333] dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#e1edf5]"
            >
              <option value="due_date">Due date</option>
              <option value="created_at">Created date</option>
              <option value="submitted_at">Submitted date</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-[#5f7889] dark:text-[#a9cee5]">
              From
            </label>
            <input
              type="date"
              value={clientFilters.dateFrom}
              onChange={(e) =>
                handleClientFilterChange("dateFrom", e.target.value)
              }
              className="w-full rounded-lg border border-[#c8d8e4] bg-white px-3 py-2 text-sm text-[#476174] outline-none focus:border-[#0f2333] dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#e1edf5]"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-[#5f7889] dark:text-[#a9cee5]">
              To
            </label>
            <input
              type="date"
              value={clientFilters.dateTo}
              onChange={(e) =>
                handleClientFilterChange("dateTo", e.target.value)
              }
              className="w-full rounded-lg border border-[#c8d8e4] bg-white px-3 py-2 text-sm text-[#476174] outline-none focus:border-[#0f2333] dark:border-[#23516f] dark:bg-[#0e3048]/70 dark:text-[#e1edf5]"
            />
          </div>

          <div className="md:col-span-2 xl:col-span-4 flex justify-end">
            <button
              onClick={clearAllFilters}
              disabled={!hasAnyActiveFilters}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#d9b06f] bg-[#fff6ea] px-3 py-2 text-xs font-semibold text-[#905000] transition hover:bg-[#ffedd2] disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#87531a] dark:bg-[#593812]/45 dark:text-[#ffd79f]"
            >
              Clear all filters
            </button>
          </div>
        </div>
      )}

      {/* Feedback toast */}
      {actionFeedback && (
        <div
          className={`flex items-center gap-2.5 rounded-xl px-4 py-3 text-sm font-medium ${
            actionFeedback.type === "success"
              ? "border border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300"
              : "border border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-900/30 dark:text-rose-300"
          }`}
        >
          {actionFeedback.type === "success" ? (
            <CheckCircleIcon className="h-4 w-4 shrink-0 text-emerald-600" />
          ) : (
            <XCircleIcon className="h-4 w-4 shrink-0 text-rose-600" />
          )}
          {actionFeedback.message}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2.5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-400">
          <ExclamationCircleIcon className="h-4 w-4 shrink-0" />
          {error}
          <button
            onClick={() => loadData()}
            className="ml-auto text-xs font-semibold underline underline-offset-2 hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Skeleton */}
      {loading && (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-12 animate-pulse rounded-xl bg-gray-100 dark:bg-white/5"
            />
          ))}
        </div>
      )}

      {/* Content */}
      {!loading && !error && (
        <>
          <TableCorrectiveActions
            correctiveActions={items}
            onAccept={handleAccept}
            onReject={handleReject}
            onExtendDueDate={handleExtendDueDate}
            onEscalate={handleEscalate}
            onReassignAuditee={handleReassignAuditee}
            targetCarId={pendingTargetCarId}
            onTargetCarOpened={handleTargetCarOpened}
            onRefresh={() => loadData(true)}
            exportSourceActions={filteredItems}
          />

          {/* Empty state */}
          {total === 0 && (
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-[#c8d8e4] bg-white py-14 text-center dark:border-[#23516f] dark:bg-[#0e3048]/30">
              <FunnelIcon className="mb-3 h-8 w-8 text-gray-300 dark:text-gray-600" />
              <p className="text-sm font-medium text-gray-600 dark:text-gray-300">
                No corrective actions found
              </p>
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                {hasAnyActiveFilters
                  ? "Try adjusting your filters or search term."
                  : "No corrective actions have been created yet."}
              </p>
              {hasAnyActiveFilters && (
                <button
                  onClick={clearAllFilters}
                  className="mt-4 rounded-lg border border-[#d9b06f] bg-[#fff6ea] px-3 py-1.5 text-xs font-semibold text-[#905000] transition hover:bg-[#ffedd2] dark:border-[#87531a] dark:bg-[#593812]/45 dark:text-[#ffd79f]"
                >
                  Clear filters
                </button>
              )}
            </div>
          )}

          {/* Pagination */}
          {total > 0 && (
            <div className="flex flex-col items-start gap-3 rounded-xl border border-[#d7b98a] bg-gradient-to-r from-[#fff9ef] to-[#fff4e2] px-4 py-3 sm:flex-row sm:items-center sm:justify-between dark:border-[#744a1a] dark:from-[#4a2f10]/50 dark:to-[#5a3a12]/45">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Showing{" "}
                <span className="font-semibold text-gray-700 dark:text-gray-300">
                  {pageStartOffset + 1}-{pageStartOffset + items.length}
                </span>{" "}
                of{" "}
                <span className="font-semibold text-gray-700 dark:text-gray-300">
                  {total.toLocaleString()}
                </span>
              </p>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={goPrev}
                  disabled={!hasPrev}
                  className="rounded-lg border border-[#dd9b3a] bg-gradient-to-r from-[#f9d28a] to-[#f4b14f] px-3 py-1.5 text-xs font-semibold text-[#7b4300] transition hover:from-[#f8c977] hover:to-[#eca03c] disabled:cursor-not-allowed disabled:opacity-40 dark:border-[#8f571c] dark:from-[#6b4316] dark:to-[#7a4d19] dark:text-[#ffd89e]"
                >
                  Previous
                </button>
                <span className="min-w-[60px] text-center text-xs text-gray-400 dark:text-gray-500">
                  {currentPage} / {totalPages}
                </span>
                <button
                  onClick={goNext}
                  disabled={!hasNext}
                  className="rounded-lg border border-[#dd9b3a] bg-gradient-to-r from-[#f9d28a] to-[#f4b14f] px-3 py-1.5 text-xs font-semibold text-[#7b4300] transition hover:from-[#f8c977] hover:to-[#eca03c] disabled:cursor-not-allowed disabled:opacity-40 dark:border-[#8f571c] dark:from-[#6b4316] dark:to-[#7a4d19] dark:text-[#ffd89e]"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
