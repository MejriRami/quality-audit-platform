import { useState, ChangeEvent, useEffect, useMemo } from "react";
import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";
import ComponentCard from "../../components/common/ComponentCard";
import Select from "../../components/form/Select";
import { Modal } from "../../components/ui/modal";

import { Calendar as BigCalendar, dateFnsLocalizer } from "react-big-calendar";
import {
  format,
  parse,
  startOfWeek,
  getDay,
  addMonths,
  addWeeks,
  addDays,
  parseISO,
} from "date-fns";
import { enUS } from "date-fns/locale";
import "react-big-calendar/lib/css/react-big-calendar.css";
import Enum from "../../components/enum/Enum";
import { useDispatch, useSelector } from "react-redux";
import { getAuditsByAuditor } from "../../redux/audit/audit";
import PaginationCalendarCard from "../../components/ui/pagination/PaginationCalendarCard";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type DateFilterMode = "all" | "from_today" | "custom";
type CalendarViewMode = "month" | "week" | "day";

type CalendarEvent = {
  id: number;
  title: string;
  start: Date;
  end: Date;
  auditNumber: string;
  auditor: string;
  auditee: string;
  plant: string;
  sector?: string;
  status?: string;
  auditType?: string; // e.g. "IATF", "ISO", "VDA"
  frameworkCode?: string; // e.g. "IATF16949"
  frameworkLabel?: string; // e.g. "IATF 16949:2016"
  totalScore?: number | null;
  reportUrl?: string | null;
};

// ─────────────────────────────────────────────────────────────────────────────
// Localizer
// ─────────────────────────────────────────────────────────────────────────────

const locales = { "en-US": enUS };
const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek: (d: Date) => startOfWeek(d, { weekStartsOn: 1 }),
  getDay,
  locales,
});

// ─────────────────────────────────────────────────────────────────────────────
// Status colors
// ─────────────────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, { bg: string }> = {
  planned: { bg: "#1d4ed8" },
  rescheduled: { bg: "#d97706" },
  // in_progress: { bg: "#7c3aed" },
  completed: { bg: "#059669" },
  waiting_for_corrective_actions: { bg: "#7c3aed" },
  cancelled: { bg: "#dc2626" },
};
const statusBg = (s = "planned") =>
  (STATUS_COLORS[s] ?? STATUS_COLORS.planned).bg;

// ─────────────────────────────────────────────────────────────────────────────
// Small chip helper
// ─────────────────────────────────────────────────────────────────────────────

function Chip({
  label,
  color = "#f1f5f9",
  textColor = "#475569",
}: {
  label: string;
  color?: string;
  textColor?: string;
}) {
  if (!label) return null;
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 9,
        fontWeight: 700,
        fontFamily: "'IBM Plex Sans', sans-serif",
        letterSpacing: "0.05em",
        textTransform: "uppercase",
        background: color,
        color: textColor,
        borderRadius: 4,
        padding: "2px 7px",
      }}
    >
      {label}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Calendar event tile  ← THE KEY CHANGE
// Shows: audit number / auditor / type + framework
// ─────────────────────────────────────────────────────────────────────────────

function EventTile({ eventInfo }: { eventInfo: any }) {
  const ev: CalendarEvent = eventInfo.event.extendedProps?.__raw;
  if (!ev) return <div>{eventInfo.event.title}</div>;

  const bg = statusBg(ev.status);
  const auditorLine = [ev.auditor, ev.plant].filter(Boolean).join(" · ");

  // Build a compact meta string: "VDA · IATF 16949" or just one of them
  const meta = [ev.auditType, ev.frameworkCode].filter(Boolean).join(" · ");

  return (
    <div
      style={{
        background: bg,
        borderRadius: 4,
        padding: "3px 6px",
        overflow: "hidden",
        fontSize: 11,
        fontFamily: "'IBM Plex Sans', sans-serif",
        color: "#fff",
        lineHeight: 1.3,
        cursor: "pointer",
      }}
    >
      {/* Line 1: audit number */}
      <div
        style={{
          fontWeight: 700,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {ev.auditNumber}
      </div>
      {/* Line 2: auditor name */}
      {ev.auditor && ev.auditor !== "—" && (
        <div
          style={{
            opacity: 0.88,
            fontSize: 10,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {auditorLine}
        </div>
      )}
      {/* Line 3: type · framework (only if there is room / not clipped) */}
      {meta && (
        <div
          style={{
            opacity: 0.75,
            fontSize: 9.5,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {meta}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Status badge
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ status = "planned" }: { status?: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        background: statusBg(status),
        color: "#fff",
        borderRadius: 4,
        padding: "2px 8px",
        fontSize: 10,
        fontFamily: "'IBM Plex Sans', sans-serif",
        fontWeight: 600,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
      }}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// List card
// ─────────────────────────────────────────────────────────────────────────────

function AuditListItem({ e, onShow }: { e: any; onShow: () => void }) {
  const start = new Date(e.planned_start_date);
  const end = new Date(e.planned_end_date);
  const auditorName = e?.auditor
    ? [e.auditor, e.second_auditor]
        .filter(Boolean)
        .map((a: { first_name: string; last_name: string }) => `${a.first_name} ${a.last_name}`)
        .join(" & ")
    : "—";

  const fmt = (d: Date) =>
    d.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }) +
    " " +
    d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <li
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
        border: "1px solid #e2e8f0",
        borderRadius: 8,
        background: "#fff",
        padding: "14px 16px",
      }}
      className="dark:border-slate-700 dark:bg-slate-800"
    >
      {/* Status accent stripe */}
      <div
        style={{
          width: 3,
          minWidth: 3,
          borderRadius: 2,
          alignSelf: "stretch",
          background: statusBg(e.status),
          flexShrink: 0,
        }}
      />

      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Header row */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: 6,
            marginBottom: 6,
          }}
        >
          <span
            style={{
              fontFamily: "'IBM Plex Sans', sans-serif",
              fontWeight: 700,
              fontSize: 13,
              color: "#0f172a",
            }}
            className="dark:text-slate-100"
          >
            {e.audit_number}
          </span>
          <StatusBadge status={e.status} />
          {e.plant && (
            <Chip
              label={e.plant.toUpperCase()}
              color="#eff6ff"
              textColor="#1d4ed8"
            />
          )}
          {/* ── Audit type chip ── */}
          {e.audit_type && (
            <Chip label={e.audit_type} color="#f0fdf4" textColor="#15803d" />
          )}
          {/* ── Framework chip ── */}
          {e.framework_code && (
            <Chip
              label={e.framework_code}
              color="#faf5ff"
              textColor="#7c3aed"
            />
          )}
        </div>

        {/* Detail grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: "4px 20px",
          }}
        >
          <InfoRow label="Auditor" value={auditorName} />
          <InfoRow label="Auditee" value={e.auditees?.join(", ") || "—"} />
          <InfoRow label="Start" value={fmt(start)} />
          <InfoRow label="End" value={fmt(end)} />
          {e.sector && <InfoRow label="Sector" value={e.sector} />}
          {e.framework_label && (
            <InfoRow label="Framework" value={e.framework_label} />
          )}
        </div>
      </div>

      <button
        onClick={onShow}
        style={{
          flexShrink: 0,
          alignSelf: "flex-start",
          background: "#f8fafc",
          border: "1px solid #e2e8f0",
          borderRadius: 6,
          padding: "5px 10px",
          fontSize: 11,
          cursor: "pointer",
          fontFamily: "'IBM Plex Sans', sans-serif",
          color: "#475569",
          whiteSpace: "nowrap",
        }}
        className="dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300 hover:bg-slate-100"
      >
        View
      </button>
    </li>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 4,
        fontSize: 11,
        fontFamily: "'IBM Plex Sans', sans-serif",
      }}
    >
      <span style={{ color: "#94a3b8", minWidth: 58, flexShrink: 0 }}>
        {label}:
      </span>
      <span
        style={{
          color: "#334155",
          fontWeight: 500,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        className="dark:text-slate-300"
      >
        {value}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Modal detail row
// ─────────────────────────────────────────────────────────────────────────────

function ModalRow({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div>
      <div
        style={{
          fontSize: 9,
          color: "#94a3b8",
          letterSpacing: "0.07em",
          textTransform: "uppercase",
          marginBottom: 2,
          fontFamily: "'IBM Plex Sans', sans-serif",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 13,
          fontWeight: 500,
          color: "#1e293b",
          fontFamily: "'IBM Plex Sans', sans-serif",
        }}
        className="dark:text-slate-200"
      >
        {value}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Convert backend audit → CalendarEvent
// ─────────────────────────────────────────────────────────────────────────────

function convertToEvent(audit: any): CalendarEvent {
  const auditorName = audit?.auditor
    ? [audit.auditor, audit.second_auditor]
        .filter(Boolean)
        .map((a: { first_name: string; last_name: string }) => `${a.first_name} ${a.last_name}`)
        .join(" & ")
    : "—";
  return {
    id: audit.id,
    title: [
      audit.audit_number,
      audit.plant ?? "",
      auditorName,
      audit.audit_type ?? undefined,
    ]
      .filter((value) => value && value !== "â€”")
      .join(" · "),
    auditNumber: audit.audit_number,
    start: new Date(audit.planned_start_date),
    end: new Date(audit.planned_end_date),
    auditor: auditorName,
    auditee: audit.auditees?.join(", ") || "—",
    plant: audit.plant ?? "",
    sector: audit.sector ?? "",
    status: audit.status ?? "planned",
    auditType: audit.audit_type ?? undefined,
    frameworkCode: audit.framework_code ?? undefined,
    frameworkLabel: audit.framework_label ?? undefined,
    totalScore: audit.total_score ?? null,
    reportUrl: audit.report_url ?? null,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Legend
// ─────────────────────────────────────────────────────────────────────────────

const LEGEND = [
  { label: "Planned", color: STATUS_COLORS.planned.bg },
  { label: "Rescheduled", color: STATUS_COLORS.rescheduled.bg },
  // { label: "In progress", color: STATUS_COLORS.in_progress.bg },
  { label: "Completed", color: STATUS_COLORS.completed.bg },
  {
    label: "Waiting for corrective actions",
    color: STATUS_COLORS.waiting_for_corrective_actions.bg,
  },
  { label: "Cancelled", color: STATUS_COLORS.cancelled.bg },
];

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export default function AuditsCalendar() {
  const dispatch = useDispatch();
  const [selectedAuditor, setSelectedAuditor] = useState<string | number>(
    "all",
  );
  const [selectedPlant, setSelectedPlant] = useState<string>("all");
  const [selectedType, setSelectedType] = useState<string>("all");
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(
    null,
  );
  const { auditorOptions } = Enum();
  const auditorFilterOptions = useMemo(
    () => [{ value: "all", label: "All auditors" }, ...auditorOptions],
    [auditorOptions],
  );
  const [currentDate, setCurrentDate] = useState<Date>(new Date());
  const [calendarView, setCalendarView] = useState<CalendarViewMode>("week");
  const [dateFilterMode, setDateFilterMode] =
    useState<DateFilterMode>("all");
  const [customFrom, setCustomFrom] = useState<string>(
    format(new Date(), "yyyy-MM-dd"),
  );

  const { calendarItems, cardsItems } = useSelector(
    (state: any) => state.audit,
  );
  const plantFilterOptions = useMemo(() => {
    const items = [
      ...(calendarItems?.items ?? []),
      ...(cardsItems?.items ?? []),
    ] as any[];
    const plants = Array.from(
      new Set(
        items.map((item) => String(item?.plant ?? "").trim()).filter(Boolean),
      ),
    ).sort((a, b) => a.localeCompare(b));

    return [
      { value: "all", label: "All plants" },
      ...plants.map((plant) => ({ value: plant, label: plant })),
    ];
  }, [calendarItems, cardsItems]);
  const typeFilterOptions = useMemo(() => {
    const items = [
      ...(calendarItems?.items ?? []),
      ...(cardsItems?.items ?? []),
    ] as any[];
    const types = Array.from(
      new Set(
        items
          .map((item) => String(item?.audit_type ?? "").trim())
          .filter(Boolean),
      ),
    ).sort((a, b) => a.localeCompare(b));

    return [
      { value: "all", label: "All types" },
      ...types.map((type) => ({ value: type, label: type })),
    ];
  }, [calendarItems, cardsItems]);
  const [page, setPage] = useState(1);
  const PER_PAGE = 5;
  const minVisibleTime = new Date(1970, 0, 1, 7, 0, 0);
  const maxVisibleTime = new Date(1970, 0, 1, 18, 0, 0);
  const scrollToTime = new Date(1970, 0, 1, 7, 0, 0);

  // ── Seed auditor select ──────────────────────────────────────────────────
  // ── Fetch calendar (all, no pagination) ─────────────────────────────────
  useEffect(() => {
    if (!selectedAuditor) return;
    getAuditsByAuditor(dispatch, selectedAuditor, "calendar");
  }, [dispatch, selectedAuditor]);

  // ── Fetch cards (paginated) ──────────────────────────────────────────────
  useEffect(() => {
    if (!selectedAuditor) return;
    getAuditsByAuditor(dispatch, selectedAuditor, "cards", page, PER_PAGE);
  }, [dispatch, selectedAuditor, page]);

  useEffect(() => {
    setPage(1);
  }, [
    selectedAuditor,
    selectedPlant,
    selectedType,
    dateFilterMode,
    customFrom,
  ]);

  // ── Build calendar events with client-side date filter ──────────────────
  const calendarEvents = useMemo(() => {
    const raw: any[] = calendarItems?.items ?? [];

    const filtered = raw.filter((a: any) => {
      if (
        selectedPlant !== "all" &&
        String(a?.plant ?? "")
          .trim()
          .toLowerCase() !== selectedPlant.trim().toLowerCase()
      ) {
        return false;
      }
      if (
        selectedType !== "all" &&
        String(a?.audit_type ?? "")
          .trim()
          .toLowerCase() !== selectedType.trim().toLowerCase()
      ) {
        return false;
      }
      const start = new Date(a.planned_start_date);
      if (dateFilterMode === "from_today") {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return start >= today;
      }
      if (dateFilterMode === "custom" && customFrom) {
        return start >= parseISO(customFrom);
      }
      return true; // "all"
    });

    return filtered.map((a: any) => {
      const ev = convertToEvent(a);
      return { ...ev, extendedProps: { __raw: ev } };
    });
  }, [calendarItems, selectedPlant, selectedType, dateFilterMode, customFrom]);

  // ── Filtered card list ───────────────────────────────────────────────────
  const filteredCards = useMemo(() => {
    const all: any[] = cardsItems?.items ?? [];
    return all
      .filter((a: any) => {
        if (
          selectedPlant !== "all" &&
          String(a?.plant ?? "")
            .trim()
            .toLowerCase() !== selectedPlant.trim().toLowerCase()
        ) {
          return false;
        }
        if (
          selectedType !== "all" &&
          String(a?.audit_type ?? "")
            .trim()
            .toLowerCase() !== selectedType.trim().toLowerCase()
        ) {
          return false;
        }
        const start = new Date(a.planned_start_date);
        if (dateFilterMode === "from_today") {
          const today = new Date();
          today.setHours(0, 0, 0, 0);
          return start >= today;
        }
        if (dateFilterMode === "custom" && customFrom) {
          return start >= parseISO(customFrom);
        }
        return true;
      })
      .sort(
        (a: any, b: any) =>
          new Date(b.planned_start_date).getTime() -
          new Date(a.planned_start_date).getTime(),
      );
  }, [cardsItems, selectedPlant, selectedType, dateFilterMode, customFrom]);

  // ── Month picker ─────────────────────────────────────────────────────────
  const handleMonthChange = (e: ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    if (!v) return;
    const [y, m] = v.split("-").map(Number);
    if (!isNaN(y) && !isNaN(m)) setCurrentDate(new Date(y, m - 1, 1));
  };

  const handlePrev = () => {
    if (calendarView === "month") {
      setCurrentDate(addMonths(currentDate, -1));
      return;
    }
    if (calendarView === "week") {
      setCurrentDate(addWeeks(currentDate, -1));
      return;
    }
    setCurrentDate(addDays(currentDate, -1));
  };

  const handleNext = () => {
    if (calendarView === "month") {
      setCurrentDate(addMonths(currentDate, 1));
      return;
    }
    if (calendarView === "week") {
      setCurrentDate(addWeeks(currentDate, 1));
      return;
    }
    setCurrentDate(addDays(currentDate, 1));
  };

  return (
    <div className="space-y-5">
      <PageMeta
        title="Audits Calendar"
        description="Plan audits and track upcoming schedules by auditor."
      />
      <PageBreadcrumb
        kicker="Calendar"
        pageTitle="Audits Calendar"
        description="Plan audits and track upcoming schedules by auditor."
      />

      {/* ── Filters ────────────────────────────────────────────────────── */}
      <ComponentCard title="Filters">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-5 items-end">
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
              Auditor
            </p>
            <Select
              options={auditorFilterOptions}
              defaultValue={selectedAuditor}
              onChange={(v: string | number) => setSelectedAuditor(v)}
            />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
              Plant
            </p>
            <Select
              options={plantFilterOptions}
              defaultValue={selectedPlant}
              onChange={(v: string | number) => setSelectedPlant(String(v))}
            />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
              Audit type
            </p>
            <Select
              options={typeFilterOptions}
              defaultValue={selectedType}
              onChange={(v: string | number) => setSelectedType(String(v))}
            />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
              Show audits
            </p>
            <select
              value={dateFilterMode}
              onChange={(e) =>
                setDateFilterMode(e.target.value as DateFilterMode)
              }
              className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm
                text-slate-700 focus:border-slate-400 focus:outline-none
                dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
            >
              <option value="all">All dates</option>
              <option value="from_today">From today</option>
              <option value="custom">From custom date…</option>
            </select>
          </div>

          {dateFilterMode === "custom" && (
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
                Starting from
              </p>
              <input
                type="date"
                value={customFrom}
                onChange={(e) => setCustomFrom(e.target.value)}
                className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm
                  text-slate-700 focus:outline-none
                  dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
              />
            </div>
          )}

          <div className="space-y-2 flex items-end">
            <button
              onClick={() => {
                setSelectedAuditor("all");
                setSelectedPlant("all");
                setSelectedType("all");
                setDateFilterMode("all");
              }}
              className="inline-flex w-full items-center justify-center rounded-lg
                border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium
                text-slate-600 hover:bg-slate-100
                dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Reset
            </button>
          </div>
        </div>
      </ComponentCard>

      {/* ── Calendar ────────────────────────────────────────────────────── */}
      <ComponentCard title="Calendar — Audits">
        {/* Nav bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-2">
            {[
              {
                label: "← Prev",
                onClick: handlePrev,
              },
              { label: "Today", onClick: () => setCurrentDate(new Date()) },
              {
                label: "Next →",
                onClick: handleNext,
              },
            ].map((b) => (
              <button
                key={b.label}
                type="button"
                onClick={b.onClick}
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs
                  text-slate-600 hover:bg-slate-100
                  dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300"
              >
                {b.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            {(["month", "week", "day"] as CalendarViewMode[]).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setCalendarView(v)}
                className={`rounded-md border px-3 py-1.5 text-xs ${
                  calendarView === v
                    ? "border-slate-900 bg-slate-900 text-white dark:border-white dark:bg-white dark:text-slate-900"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300"
                }`}
              >
                {v[0].toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Jump to:
            </span>
            <input
              type="month"
              value={format(currentDate, "yyyy-MM")}
              onChange={handleMonthChange}
              className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs
                text-slate-700 focus:border-slate-400 focus:outline-none
                dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
            />
          </div>
        </div>

        <div className="h-[680px]">
          <BigCalendar
            localizer={localizer}
            events={calendarEvents}
            startAccessor="start"
            endAccessor="end"
            style={{ height: "100%" }}
            components={{
              month: {
                event: (props: any) => <EventTile eventInfo={props} />,
              },
            }}
            eventPropGetter={(event: any) => ({
              style: {
                backgroundColor: statusBg(event.status),
                border: "none",
                borderRadius: 6,
                color: "#ffffff",
                fontSize: "0.75rem",
                padding: "2px 4px",
              },
            })}
            popup
            popupOffset={{ x: 30, y: 20 }}
            views={["month", "week", "day"]}
            view={calendarView}
            drilldownView="day"
            date={currentDate}
            min={minVisibleTime}
            max={maxVisibleTime}
            step={30}
            timeslots={2}
            scrollToTime={scrollToTime}
            formats={{ timeGutterFormat: "HH:mm" }}
            onNavigate={(d) => setCurrentDate(d as Date)}
            onView={(v) => setCalendarView(v as CalendarViewMode)}
            onDrillDown={(d) => {
              setCurrentDate(d as Date);
              setCalendarView("day");
            }}
            onShowMore={(_, d) => {
              setCurrentDate(d as Date);
              setCalendarView("day");
            }}
            onSelectEvent={(event: any) => {
              const raw: CalendarEvent = event.extendedProps?.__raw ?? event;
              setSelectedEvent(raw);
            }}
          />
        </div>

        {/* Legend */}
        <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2">
          {LEGEND.map((l) => (
            <div key={l.label} className="flex items-center gap-2">
              <span
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: 3,
                  background: l.color,
                  display: "inline-block",
                }}
              />
              <span className="text-xs text-slate-500 dark:text-slate-300">
                {l.label}
              </span>
            </div>
          ))}
        </div>
      </ComponentCard>

      {/* ── Upcoming list ───────────────────────────────────────────────── */}
      {filteredCards.length > 0 && (
        <ComponentCard title="Audits">
          <ul className="space-y-3">
            {filteredCards.map((e: any) => (
              <AuditListItem
                key={e.id}
                e={e}
                onShow={() => {
                  const ev = convertToEvent(e);
                  setSelectedEvent(ev);
                  setCurrentDate(ev.start);
                }}
              />
            ))}
          </ul>
          <PaginationCalendarCard
            page={cardsItems?.page}
            totalPages={cardsItems?.total_pages}
            onPageChange={setPage}
          />
        </ComponentCard>
      )}

      {/* ── Event detail modal ──────────────────────────────────────────── */}
      <Modal
        isOpen={selectedEvent !== null}
        onClose={() => setSelectedEvent(null)}
        className="max-w-[560px] p-6 lg:p-8"
      >
        {selectedEvent && (
          <div className="space-y-5">
            {/* Modal header */}
            <div>
              <h3 className="text-lg font-bold text-[#064273] dark:text-[#e1f2ff] mb-2">
                {selectedEvent.auditNumber}
              </h3>
              <div className="flex flex-wrap gap-2">
                <StatusBadge status={selectedEvent.status} />
                {selectedEvent.plant && (
                  <Chip
                    label={selectedEvent.plant.toUpperCase()}
                    color="#eff6ff"
                    textColor="#1d4ed8"
                  />
                )}
                {/* ── Type chip in modal ── */}
                {selectedEvent.auditType && (
                  <Chip
                    label={selectedEvent.auditType}
                    color="#f0fdf4"
                    textColor="#15803d"
                  />
                )}
                {/* ── Framework chip in modal ── */}
                {selectedEvent.frameworkCode && (
                  <Chip
                    label={selectedEvent.frameworkCode}
                    color="#faf5ff"
                    textColor="#7c3aed"
                  />
                )}
              </div>
            </div>

            {/* Details grid */}
            <div
              style={{
                background: "#f8fafc",
                borderRadius: 8,
                border: "1px solid #e2e8f0",
                padding: "16px",
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "12px 20px",
              }}
              className="dark:bg-slate-800 dark:border-slate-700"
            >
              <ModalRow label="Auditor" value={selectedEvent.auditor} />
              <ModalRow label="Auditee" value={selectedEvent.auditee} />
              <ModalRow
                label="Start"
                value={
                  selectedEvent.start.toLocaleDateString("en-GB", {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                  }) +
                  " " +
                  selectedEvent.start.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                }
              />
              <ModalRow
                label="End"
                value={
                  selectedEvent.end.toLocaleDateString("en-GB", {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                  }) +
                  " " +
                  selectedEvent.end.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                }
              />
              {selectedEvent.sector && (
                <ModalRow label="Sector" value={selectedEvent.sector} />
              )}
              {selectedEvent.auditType && (
                <ModalRow label="Audit type" value={selectedEvent.auditType} />
              )}
              {selectedEvent.frameworkLabel && (
                <ModalRow
                  label="Framework"
                  value={selectedEvent.frameworkLabel}
                />
              )}
              {selectedEvent.totalScore != null && (
                <ModalRow
                  label="Score"
                  value={String(selectedEvent.totalScore)}
                />
              )}
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => setSelectedEvent(null)}
                className="rounded-lg border border-[#c0d8ea] bg-white px-4 py-2 text-sm
                  text-[#3f7090] hover:bg-[#edf7ff]
                  dark:border-[#0f6ea9] dark:bg-[#072f4a] dark:text-[#cfe9f9]"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
