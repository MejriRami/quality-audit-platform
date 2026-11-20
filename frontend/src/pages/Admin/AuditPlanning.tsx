import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import {
  AlertTriangle,
  CalendarRange,
  CheckCircle2,
  ClipboardList,
  Database,
  ListOrdered,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react";
import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";
import {
  Auditor,
  Escalation,
  HistoryEntry,
  ItemPatch,
  PlanItem,
  PlanMeta,
  PlanRun,
  PlanRunSummary,
  PriorityGuide,
  QualityMetric,
  SupportProcess,
  apiError,
  planningApi,
} from "../../services/auditPlanningApi";

const card =
  "rounded-2xl border border-slate-200/70 bg-white p-5 shadow-sm dark:border-slate-800/70 dark:bg-slate-900/60";
const input =
  "h-9 w-full rounded-lg border border-slate-200 bg-white px-2.5 text-sm text-slate-800 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100";
const btn =
  "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50";
const btnPrimary = `${btn} bg-gradient-to-r from-[#F68C1F] to-[#EF7807] text-white hover:opacity-90`;
const btnGhost = `${btn} border border-slate-200 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800`;
const th =
  "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400";
const td = "px-3 py-2 align-top text-sm text-slate-700 dark:text-slate-200";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const STATUS_LABEL: Record<string, string> = {
  scheduled: "Scheduled",
  over_capacity: "Over capacity",
  suppressed_recent: "Line audited < 3 months",
  removed: "Removed",
  completed: "Completed",
};
const STATUS_ORDER = [
  "scheduled",
  "completed",
  "over_capacity",
  "suppressed_recent",
  "removed",
];

const today = () => new Date().toISOString().slice(0, 10);
const thisMonth = () => today().slice(0, 7);
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function Badge({
  tone,
  children,
  title,
}: {
  tone: "green" | "amber" | "red" | "slate" | "blue";
  children: React.ReactNode;
  title?: string;
}) {
  const tones = {
    green:
      "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
    amber: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
    red: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300",
    slate:
      "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
    blue: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300",
  };
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export default function AuditPlanning() {
  const [tab, setTab] = useState<"plan" | "guide" | "inputs">("plan");
  const [meta, setMeta] = useState<PlanMeta | null>(null);
  const [auditors, setAuditors] = useState<Auditor[]>([]);
  const [processes, setProcesses] = useState<SupportProcess[]>([]);

  const loadProcesses = useCallback(async () => {
    setProcesses(await planningApi.supportProcesses());
  }, []);

  useEffect(() => {
    Promise.all([planningApi.meta(), planningApi.auditors(), loadProcesses()])
      .then(([m, a]) => {
        setMeta(m);
        setAuditors(a);
      })
      .catch((err) => toast.error(apiError(err, "Failed to load planning data")));
  }, [loadProcesses]);

  return (
    <div className="space-y-6">
      <PageMeta
        title="Audit Planning"
        description="Monthly audit plan generated from the P1-P11 priority checks."
      />
      <PageBreadcrumb
        kicker="Planning"
        pageTitle="Monthly Audit Planning"
        description="Review the draft plan generated from the P1-P11 checks, adjust it, then approve it."
        actions={
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900">
            {(
              [
                ["plan", "Plan review", ClipboardList],
                ["guide", "Priority guide", ListOrdered],
                ["inputs", "Manual inputs", Database],
              ] as const
            ).map(([key, label, Icon]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`${btn} py-1.5 ${
                  tab === key
                    ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                    : "text-slate-600 dark:text-slate-300"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>
        }
      />
      {!meta ? (
        <div className={card}>Loading…</div>
      ) : tab === "plan" ? (
        <PlanReview meta={meta} auditors={auditors} processes={processes} />
      ) : tab === "guide" ? (
        <PriorityGuideView priorities={meta.priorities} />
      ) : (
        <ManualInputs
          meta={meta}
          processes={processes}
          reloadProcesses={loadProcesses}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Plan review
// ─────────────────────────────────────────────────────────────

function PlanReview({
  meta,
  auditors,
  processes,
}: {
  meta: PlanMeta;
  auditors: Auditor[];
  processes: SupportProcess[];
}) {
  const [month, setMonth] = useState(thisMonth());
  const [runs, setRuns] = useState<PlanRunSummary[]>([]);
  const [run, setRun] = useState<PlanRun | null>(null);
  const [busy, setBusy] = useState(false);

  const monthRuns = useMemo(
    () => runs.filter((r) => r.plan_month.startsWith(month)),
    [runs, month],
  );

  const openRun = useCallback(async (id: number) => {
    try {
      setRun(await planningApi.run(id));
    } catch (err) {
      toast.error(apiError(err, "Failed to load plan"));
    }
  }, []);

  const loadRuns = useCallback(async () => {
    const all = await planningApi.runs();
    setRuns(all);
    return all;
  }, []);

  useEffect(() => {
    loadRuns()
      .then((all) => {
        const current =
          all.find((r) => r.plan_month.startsWith(month) && r.status !== "superseded") ??
          all.find((r) => r.plan_month.startsWith(month));
        if (current) void openRun(current.id);
        else setRun(null);
      })
      .catch((err) => toast.error(apiError(err, "Failed to load plans")));
  }, [month, loadRuns, openRun]);

  const generate = async () => {
    setBusy(true);
    try {
      const created = await planningApi.generate(`${month}-01`);
      setRun(created);
      await loadRuns();
      toast.success(`Draft generated: ${created.items.length} items`);
    } catch (err) {
      toast.error(apiError(err, "Failed to generate plan"));
    } finally {
      setBusy(false);
    }
  };

  const approve = async () => {
    if (!run) return;
    setBusy(true);
    try {
      await planningApi.approve(run.id);
      await openRun(run.id);
      await loadRuns();
      toast.success("Plan approved");
    } catch (err) {
      toast.error(apiError(err, "Failed to approve plan"), { duration: 8000 });
    } finally {
      setBusy(false);
    }
  };

  const replaceItem = (item: PlanItem) =>
    setRun((r) =>
      r ? { ...r, items: r.items.map((i) => (i.id === item.id ? item : i)) } : r,
    );

  const grouped = useMemo(() => {
    const out: Record<string, PlanItem[]> = {};
    for (const item of run?.items ?? []) (out[item.status] ||= []).push(item);
    for (const list of Object.values(out))
      list.sort(
        (a, b) =>
          (a.scheduled_date ?? "9").localeCompare(b.scheduled_date ?? "9") ||
          b.complaint_volume - a.complaint_volume ||
          a.priority - b.priority,
      );
    return out;
  }, [run]);

  const processName = (id: number | null) =>
    processes.find((p) => p.id === id)?.name ?? null;
  const weekdayOf = (plant: string) => {
    const group = Object.values(meta.schedule).find((g) =>
      g.plants.includes(plant),
    );
    return group ? WEEKDAYS[group.weekday] : "";
  };
  const editable = run && run.status !== "superseded";

  return (
    <div className="space-y-6">
      <section className={`${card} flex flex-wrap items-end gap-4`}>
        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700 dark:text-slate-200">
            Plan month
          </span>
          <input
            type="month"
            className={input}
            value={month}
            onChange={(e) => e.target.value && setMonth(e.target.value)}
          />
        </label>
        {monthRuns.length > 0 && (
          <label className="text-sm">
            <span className="mb-1 block font-medium text-slate-700 dark:text-slate-200">
              Run
            </span>
            <select
              className={input}
              value={run?.id ?? ""}
              onChange={(e) => void openRun(Number(e.target.value))}
            >
              {monthRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  #{r.id} · {r.status} · {new Date(r.generated_at).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="ml-auto flex gap-2">
          <button
            className={btnGhost}
            onClick={generate}
            disabled={busy || run?.status === "approved"}
            title={
              run?.status === "approved"
                ? "This month is already approved"
                : "Evaluate P1-P11 against live data and create a new draft"
            }
          >
            <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />
            {run ? "Regenerate draft" : "Generate draft"}
          </button>
          {run?.status === "draft" && (
            <button className={btnPrimary} onClick={approve} disabled={busy}>
              <CheckCircle2 className="h-4 w-4" />
              Approve plan
            </button>
          )}
        </div>
      </section>

      {!run ? (
        <div className={`${card} text-sm text-slate-600 dark:text-slate-300`}>
          No plan for this month yet. Generate a draft to evaluate the P1–P11
          checks against live data.
        </div>
      ) : (
        <>
          <section className={card}>
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                tone={
                  run.status === "approved"
                    ? "green"
                    : run.status === "draft"
                      ? "blue"
                      : "slate"
                }
              >
                {cap(run.status)}
              </Badge>
              <span className="text-sm text-slate-500 dark:text-slate-400">
                Data as of {run.as_of} · {run.items.length} items
              </span>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {Array.from({ length: 11 }, (_, i) => `P${i + 1}`).map((code) => {
                const s = run.check_status[code];
                const tone =
                  s?.status === "evaluated"
                    ? "green"
                    : s?.status === "partial"
                      ? "amber"
                      : "red";
                return (
                  <Badge key={code} tone={tone} title={s?.reason ?? s?.status}>
                    {code}
                    {s?.status !== "evaluated" && " ⚠"}
                  </Badge>
                );
              })}
            </div>
            {run.warnings.length > 0 && (
              <ul className="mt-4 space-y-1 rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-200">
                {run.warnings.map((w) => (
                  <li key={w} className="flex gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    {w}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {STATUS_ORDER.filter((s) => grouped[s]?.length).map((status) => (
            <section key={status} className={card}>
              <h2 className="mb-3 text-base font-semibold text-slate-900 dark:text-white">
                {STATUS_LABEL[status]}{" "}
                <span className="font-normal text-slate-500">
                  ({grouped[status].length})
                </span>
              </h2>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100 dark:divide-slate-800">
                  <thead>
                    <tr>
                      <th className={th}>Date</th>
                      <th className={th}>Plant / scope</th>
                      <th className={th}>Why</th>
                      <th className={th}>Auditee</th>
                      <th className={th}>Auditor</th>
                      <th className={th}>Status</th>
                      <th className={th} />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {grouped[status].map((item) => (
                      <ItemRow
                        key={item.id}
                        item={item}
                        runStatus={run.status}
                        editable={!!editable}
                        auditors={auditors}
                        statuses={meta.editable_statuses}
                        processName={processName(item.support_process_id)}
                        weekday={weekdayOf(item.plant)}
                        onSaved={replaceItem}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </>
      )}
    </div>
  );
}

function ItemRow({
  item,
  runStatus,
  editable,
  auditors,
  statuses,
  processName,
  weekday,
  onSaved,
}: {
  item: PlanItem;
  runStatus: string;
  editable: boolean;
  auditors: Auditor[];
  statuses: string[];
  processName: string | null;
  weekday: string;
  onSaved: (item: PlanItem) => void;
}) {
  const initial = useMemo(
    () => ({
      status: item.status,
      scheduled_date: item.scheduled_date ?? "",
      auditor_user_id: item.auditor_user_id ?? 0,
      auditee_name: item.auditee_name ?? "",
      auditee_email: item.auditee_email ?? "",
      override_note: item.override_note ?? "",
    }),
    [item],
  );
  const [draft, setDraft] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  useEffect(() => setDraft(initial), [initial]);

  const locked = !editable || item.status === "completed";
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);

  const save = async () => {
    const patch: ItemPatch = {};
    if (draft.status !== initial.status) patch.status = draft.status;
    if (draft.scheduled_date !== initial.scheduled_date)
      patch.scheduled_date = draft.scheduled_date || null;
    if (draft.auditor_user_id !== initial.auditor_user_id)
      patch.auditor_user_id = draft.auditor_user_id || null;
    if (
      draft.auditee_name !== initial.auditee_name ||
      draft.auditee_email !== initial.auditee_email
    ) {
      patch.auditee_name = draft.auditee_name || null;
      patch.auditee_email = draft.auditee_email || null;
    }
    if (draft.override_note !== initial.override_note)
      patch.override_note = draft.override_note || null;
    setSaving(true);
    try {
      onSaved(await planningApi.patchItem(item.id, patch));
      toast.success("Saved");
    } catch (err) {
      toast.error(apiError(err, "Failed to save"), { duration: 7000 });
    } finally {
      setSaving(false);
    }
  };

  const complete = async () => {
    const on = window.prompt("Date the audit was done (YYYY-MM-DD)", today());
    if (!on) return;
    try {
      onSaved(await planningApi.completeItem(item.id, on));
      toast.success("Marked as completed");
    } catch (err) {
      toast.error(apiError(err, "Failed to complete"));
    }
  };

  const scope =
    item.project_code ??
    processName ??
    item.product_line ??
    "Plant level";

  return (
    <tr>
      <td className={td}>
        {locked ? (
          item.completed_on ?? item.scheduled_date ?? "—"
        ) : (
          <input
            type="date"
            className={`${input} w-36`}
            value={draft.scheduled_date}
            onChange={(e) =>
              setDraft({ ...draft, scheduled_date: e.target.value })
            }
          />
        )}
        <div className="mt-1 text-xs text-slate-400">{weekday} slot</div>
      </td>
      <td className={td}>
        <div className="font-medium capitalize">{item.plant}</div>
        <div className="text-xs text-slate-500">{scope}</div>
      </td>
      <td className={`${td} max-w-xs`}>
        <div className="flex flex-wrap gap-1">
          {item.trigger_codes.map((c) => (
            <Badge key={c} tone="blue">
              {c}
            </Badge>
          ))}
          {item.complaint_volume > 0 && (
            <Badge tone="slate" title="Complaints in the last 12 months">
              {item.complaint_volume} compl.
            </Badge>
          )}
        </div>
        <div className="mt-1 text-xs">{item.checklist}</div>
        {item.status_reason && (
          <div className="mt-1 text-xs text-amber-600">{item.status_reason}</div>
        )}
        <button
          className="mt-1 text-xs text-[#EF7807] hover:underline"
          onClick={() => setShowEvidence((v) => !v)}
        >
          {showEvidence ? "Hide evidence" : "Evidence"}
        </button>
        {showEvidence && (
          <ul className="mt-1 space-y-0.5 text-xs text-slate-500">
            {item.evidence.map((e, i) => (
              <li key={i}>
                {Object.entries(e)
                  .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`)
                  .join(" · ")}
              </li>
            ))}
          </ul>
        )}
      </td>
      <td className={`${td} min-w-[14rem]`}>
        <div className="mb-1 flex items-center gap-1.5 text-xs text-slate-500">
          {item.auditee_role}
          <Badge
            tone={
              item.auditee_status === "manual_required"
                ? "red"
                : item.auditee_status === "overridden"
                  ? "amber"
                  : "green"
            }
            title={item.auditee_note ?? undefined}
          >
            {item.auditee_status === "manual_required"
              ? "Assign manually"
              : item.auditee_status}
          </Badge>
        </div>
        {locked ? (
          <div>
            {item.auditee_name ?? "—"}
            <div className="text-xs text-slate-500">{item.auditee_email}</div>
          </div>
        ) : (
          <div className="space-y-1">
            <input
              className={input}
              placeholder="Name"
              value={draft.auditee_name}
              onChange={(e) =>
                setDraft({ ...draft, auditee_name: e.target.value })
              }
            />
            <input
              className={input}
              placeholder="Email"
              type="email"
              value={draft.auditee_email}
              onChange={(e) =>
                setDraft({ ...draft, auditee_email: e.target.value })
              }
            />
          </div>
        )}
      </td>
      <td className={td}>
        {locked ? (
          (() => {
            const a = auditors.find((x) => x.id === item.auditor_user_id);
            return a ? `${a.first_name} ${a.last_name}` : "—";
          })()
        ) : (
          <select
            className={`${input} min-w-[10rem]`}
            value={draft.auditor_user_id}
            onChange={(e) =>
              setDraft({ ...draft, auditor_user_id: Number(e.target.value) })
            }
          >
            <option value={0}>Unassigned</option>
            {auditors.map((a) => (
              <option key={a.id} value={a.id}>
                {a.first_name} {a.last_name}
              </option>
            ))}
          </select>
        )}
      </td>
      <td className={td}>
        {locked ? (
          STATUS_LABEL[item.status] ?? item.status
        ) : (
          <div className="space-y-1">
            <select
              className={`${input} min-w-[9rem]`}
              value={draft.status}
              onChange={(e) => setDraft({ ...draft, status: e.target.value })}
            >
              {statuses.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s] ?? s}
                </option>
              ))}
            </select>
            <input
              className={input}
              placeholder="Override note"
              value={draft.override_note}
              onChange={(e) =>
                setDraft({ ...draft, override_note: e.target.value })
              }
            />
          </div>
        )}
      </td>
      <td className={`${td} whitespace-nowrap`}>
        {!locked && dirty && (
          <button className={btnPrimary} onClick={save} disabled={saving}>
            <Save className="h-4 w-4" />
            Save
          </button>
        )}
        {!dirty &&
          runStatus === "approved" &&
          item.status === "scheduled" && (
            <button className={btnGhost} onClick={complete}>
              <CheckCircle2 className="h-4 w-4" />
              Done
            </button>
          )}
      </td>
    </tr>
  );
}

// ─────────────────────────────────────────────────────────────
// Priority guide
// ─────────────────────────────────────────────────────────────

function PriorityGuideView({ priorities }: { priorities: PriorityGuide[] }) {
  return (
    <div className="space-y-6">
      <section className={`${card} grid gap-4 md:grid-cols-2`}>
        <div>
          <div className="flex items-center gap-2">
            <Badge tone="amber">Open audit</Badge>
            <span className="text-sm font-semibold text-slate-900 dark:text-white">
              No fixed questions
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            The auditor types each question and the answer on the spot, and
            marks it Conformity, Observation or Nonconformity. A CAR can be
            requested for an Observation or a Nonconformity. The scope below
            says what to look at.
          </p>
        </div>
        <div>
          <div className="flex items-center gap-2">
            <Badge tone="blue">Checklist</Badge>
            <span className="text-sm font-semibold text-slate-900 dark:text-white">
              Fixed questionnaire
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            The audit is filled in with the questionnaire named below. All 11
            checks run every month; when several fire on the same plant and
            product line with the same audit type (P2 + P3, P4 + P5), they
            become one audit.
          </p>
        </div>
      </section>

      <section className={card}>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100 dark:divide-slate-800">
            <thead>
              <tr>
                <th className={th}>#</th>
                <th className={th}>Check</th>
                <th className={th}>Audit type</th>
                <th className={th}>What to audit</th>
                <th className={th}>Auditee</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {priorities.map((p) => (
                <tr key={p.code}>
                  <td className={`${td} font-semibold`}>{p.code}</td>
                  <td className={`${td} max-w-sm`}>
                    <div className="font-medium text-slate-900 dark:text-white">
                      {p.question}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">{p.rule}</div>
                  </td>
                  <td className={td}>
                    <Badge tone={p.format === "open" ? "amber" : "blue"}>
                      {p.format === "open" ? "Open audit" : "Checklist"}
                    </Badge>
                    <div className="mt-1 text-xs text-slate-500">
                      {p.questionnaire}
                    </div>
                  </td>
                  <td className={`${td} max-w-sm`}>{p.scope}</td>
                  <td className={td}>{p.auditee_role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Manual inputs
// ─────────────────────────────────────────────────────────────

function ManualInputs({
  meta,
  processes,
  reloadProcesses,
}: {
  meta: PlanMeta;
  processes: SupportProcess[];
  reloadProcesses: () => Promise<void>;
}) {
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [metrics, setMetrics] = useState<QualityMetric[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  const reload = useCallback(async () => {
    try {
      const [e, m, h] = await Promise.all([
        planningApi.escalations(),
        planningApi.metrics(),
        planningApi.history(),
      ]);
      setEscalations(e);
      setMetrics(m);
      setHistory(h);
    } catch (err) {
      toast.error(apiError(err, "Failed to load manual inputs"));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast.success(ok);
      await reload();
    } catch (err) {
      toast.error(apiError(err, "Save failed"));
    }
  };

  const plantSelect = (value: string, onChange: (v: string) => void) => (
    <select
      className={input}
      value={value}
      required
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">Plant…</option>
      {meta.plants.map((p) => (
        <option key={p} value={p}>
          {cap(p)}
        </option>
      ))}
    </select>
  );

  // ── forms ──
  const [esc, setEsc] = useState({
    plant: "",
    product_line: "",
    customer: "",
    level: "CSI" as "CSI" | "CSII",
    opened_on: today(),
    reference: "",
  });
  const [met, setMet] = useState({
    plant: "",
    month: thisMonth(),
    metric: "scrap" as "scrap" | "nqc",
    value: "",
    target: "",
    unit: "",
  });
  const [hist, setHist] = useState({
    plant: "",
    product_line: "",
    kind: "plant_manager",
    support_process_id: 0,
    audited_on: today(),
    note: "",
  });
  const [newProcess, setNewProcess] = useState("");

  return (
    <div className="grid gap-6 2xl:grid-cols-2">
      {/* CSI / CSII */}
      <section className={card}>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">
          Customer escalations (P2 CSII · P3 CSI)
        </h2>
        <p className="mb-3 text-sm text-slate-500">
          Open escalations trigger an audit. Set a closed date when the
          customer releases it.
        </p>
        <form
          className="grid grid-cols-2 gap-2 md:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault();
            void run(
              () =>
                planningApi.saveEscalation({
                  ...esc,
                  product_line: esc.product_line || null,
                  customer: esc.customer || null,
                  reference: esc.reference || null,
                  closed_on: null,
                  note: null,
                }),
              "Escalation added",
            );
          }}
        >
          {plantSelect(esc.plant, (plant) => setEsc({ ...esc, plant }))}
          <input className={input} placeholder="Product line" value={esc.product_line} onChange={(e) => setEsc({ ...esc, product_line: e.target.value })} />
          <input className={input} placeholder="Customer" value={esc.customer} onChange={(e) => setEsc({ ...esc, customer: e.target.value })} />
          <select className={input} value={esc.level} onChange={(e) => setEsc({ ...esc, level: e.target.value as "CSI" | "CSII" })}>
            <option>CSI</option>
            <option>CSII</option>
          </select>
          <input className={input} type="date" value={esc.opened_on} onChange={(e) => setEsc({ ...esc, opened_on: e.target.value })} />
          <button className={btnPrimary}>Add</button>
        </form>
        <table className="mt-4 min-w-full text-sm">
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {escalations.map((r) => (
              <tr key={r.id}>
                <td className={td}>
                  <Badge tone={r.closed_on ? "slate" : "red"}>{r.level}</Badge>
                </td>
                <td className={`${td} capitalize`}>{r.plant}</td>
                <td className={td}>{r.product_line ?? "—"}</td>
                <td className={td}>{r.customer ?? "—"}</td>
                <td className={td}>
                  {r.opened_on}
                  {r.closed_on ? ` → ${r.closed_on}` : " · open"}
                </td>
                <td className={`${td} text-right`}>
                  {!r.closed_on && (
                    <button
                      className="text-xs text-[#EF7807] hover:underline"
                      onClick={() =>
                        void run(
                          () => planningApi.saveEscalation({ ...r, closed_on: today() }),
                          "Escalation closed",
                        )
                      }
                    >
                      Close today
                    </button>
                  )}
                  <button
                    className="ml-3 text-slate-400 hover:text-rose-600"
                    title="Delete"
                    onClick={() => void run(() => planningApi.deleteEscalation(r.id!), "Deleted")}
                  >
                    <Trash2 className="inline h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* NQC / scrap */}
      <section className={card}>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">
          NQC / scrap per month (P11)
        </h2>
        <p className="mb-3 text-sm text-slate-500">
          Over target last month triggers an audit. PPM is read automatically
          from the KPI system; saving the same plant/month/metric again
          replaces the value.
        </p>
        <form
          className="grid grid-cols-2 gap-2 md:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault();
            void run(
              () =>
                planningApi.saveMetric({
                  plant: met.plant,
                  month: `${met.month}-01`,
                  metric: met.metric,
                  value: Number(met.value),
                  target: Number(met.target),
                  unit: met.unit || null,
                  note: null,
                }),
              "Metric saved",
            );
          }}
        >
          {plantSelect(met.plant, (plant) => setMet({ ...met, plant }))}
          <input className={input} type="month" value={met.month} onChange={(e) => setMet({ ...met, month: e.target.value })} />
          <select className={input} value={met.metric} onChange={(e) => setMet({ ...met, metric: e.target.value as "scrap" | "nqc" })}>
            <option value="scrap">Scrap</option>
            <option value="nqc">NQC</option>
          </select>
          <input className={input} type="number" step="any" required placeholder="Value" value={met.value} onChange={(e) => setMet({ ...met, value: e.target.value })} />
          <input className={input} type="number" step="any" required placeholder="Target" value={met.target} onChange={(e) => setMet({ ...met, target: e.target.value })} />
          <button className={btnPrimary}>Save</button>
        </form>
        <table className="mt-4 min-w-full text-sm">
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {metrics.map((r) => (
              <tr key={r.id}>
                <td className={td}>{r.month.slice(0, 7)}</td>
                <td className={`${td} capitalize`}>{r.plant}</td>
                <td className={`${td} uppercase`}>{r.metric}</td>
                <td className={td}>
                  <span className={Number(r.value) > Number(r.target) ? "font-semibold text-rose-600" : ""}>
                    {Number(r.value)}
                  </span>{" "}
                  / {Number(r.target)}
                </td>
                <td className={`${td} text-right`}>
                  <button className="text-slate-400 hover:text-rose-600" title="Delete" onClick={() => void run(() => planningApi.deleteMetric(r.id!), "Deleted")}>
                    <Trash2 className="inline h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* History */}
      <section className={card}>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">
          Audit history
        </h2>
        <p className="mb-3 text-sm text-slate-500">
          Feeds the "audited in the last N months" checks (P7, P8, P9 and the
          3-month line rule). Completing a plan item adds a row automatically;
          add older audits here.
        </p>
        <form
          className="grid grid-cols-2 gap-2 md:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault();
            void run(
              () =>
                planningApi.addHistory({
                  plant: hist.plant,
                  product_line: hist.product_line || null,
                  kind: hist.kind,
                  support_process_id:
                    hist.kind === "support_process" ? hist.support_process_id || null : null,
                  audited_on: hist.audited_on,
                  note: hist.note || null,
                }),
              "History added",
            );
          }}
        >
          {plantSelect(hist.plant, (plant) => setHist({ ...hist, plant }))}
          <select className={input} value={hist.kind} onChange={(e) => setHist({ ...hist, kind: e.target.value })}>
            {meta.history_kinds.map((k) => (
              <option key={k} value={k}>
                {cap(k.replace(/_/g, " "))}
              </option>
            ))}
          </select>
          {hist.kind === "line" ? (
            <input className={input} required placeholder="Product line" value={hist.product_line} onChange={(e) => setHist({ ...hist, product_line: e.target.value })} />
          ) : hist.kind === "support_process" ? (
            <select className={input} required value={hist.support_process_id} onChange={(e) => setHist({ ...hist, support_process_id: Number(e.target.value) })}>
              <option value={0}>Process…</option>
              {processes.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          ) : (
            <span />
          )}
          <input className={input} type="date" value={hist.audited_on} onChange={(e) => setHist({ ...hist, audited_on: e.target.value })} />
          <input className={input} placeholder="Note" value={hist.note} onChange={(e) => setHist({ ...hist, note: e.target.value })} />
          <button className={btnPrimary}>Add</button>
        </form>
        <table className="mt-4 min-w-full text-sm">
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {history.map((r) => (
              <tr key={r.id}>
                <td className={td}>{r.audited_on}</td>
                <td className={`${td} capitalize`}>{r.plant}</td>
                <td className={td}>
                  {cap(r.kind.replace(/_/g, " "))}
                  <div className="text-xs text-slate-500">
                    {r.product_line ??
                      processes.find((p) => p.id === r.support_process_id)?.name ??
                      ""}
                  </div>
                </td>
                <td className={td}>
                  <Badge tone={r.source === "plan" ? "blue" : "slate"}>{r.source}</Badge>
                </td>
                <td className={`${td} text-right`}>
                  {r.source === "manual" && (
                    <button className="text-slate-400 hover:text-rose-600" title="Delete" onClick={() => void run(() => planningApi.deleteHistory(r.id!), "Deleted")}>
                      <Trash2 className="inline h-4 w-4" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Support processes */}
      <section className={card}>
        <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900 dark:text-white">
          <CalendarRange className="h-4 w-4" />
          Support processes (P8)
        </h2>
        <p className="mb-3 text-sm text-slate-500">
          When an external IATF audit is due within 4 months, each active
          process not audited internally in the last 4 months gets an audit.
        </p>
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {processes.map((p) => (
            <li key={p.id} className="flex items-center justify-between py-2 text-sm">
              <span className={p.is_active ? "" : "text-slate-400 line-through"}>{p.name}</span>
              <button
                className="text-xs text-[#EF7807] hover:underline"
                onClick={() =>
                  void run(
                    async () => {
                      await planningApi.saveSupportProcess({ ...p, is_active: !p.is_active });
                      await reloadProcesses();
                    },
                    p.is_active ? "Deactivated" : "Activated",
                  )
                }
              >
                {p.is_active ? "Deactivate" : "Activate"}
              </button>
            </li>
          ))}
        </ul>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await planningApi.saveSupportProcess({
                name: newProcess,
                is_active: true,
                sort_order: processes.length + 1,
              });
              setNewProcess("");
              await reloadProcesses();
            }, "Process added");
          }}
        >
          <input className={input} required placeholder="New process name" value={newProcess} onChange={(e) => setNewProcess(e.target.value)} />
          <button className={btnPrimary}>Add</button>
        </form>
      </section>
    </div>
  );
}
