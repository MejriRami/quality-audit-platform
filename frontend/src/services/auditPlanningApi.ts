import axiosInstance from "./axiosInstance";

export type CheckStatus = {
  status: "evaluated" | "not_evaluated" | "partial";
  reason?: string;
};

export type PlanItem = {
  id: number;
  plant: string;
  product_line: string | null;
  project_code: string | null;
  support_process_id: number | null;
  trigger_codes: string[];
  checklist: string;
  evidence: Record<string, unknown>[];
  complaint_volume: number;
  priority: number;
  status: string;
  status_reason: string | null;
  scheduled_date: string | null;
  auditor_user_id: number | null;
  auditee_role: string;
  auditee_name: string | null;
  auditee_email: string | null;
  auditee_status: "resolved" | "manual_required" | "overridden";
  auditee_note: string | null;
  overridden: boolean;
  override_note: string | null;
  completed_on: string | null;
};

export type PlanRunSummary = {
  id: number;
  plan_month: string;
  status: "draft" | "approved" | "superseded";
  as_of: string;
  generated_at: string;
  approved_at: string | null;
};

export type PlanRun = PlanRunSummary & {
  check_status: Record<string, CheckStatus>;
  warnings: string[];
  items: PlanItem[];
};

export type PriorityGuide = {
  code: string;
  question: string;
  rule: string;
  format: "open" | "checklist";
  audit_type: string;
  questionnaire: string;
  scope: string;
  auditee_role: string;
};

export type PlanMeta = {
  plants: string[];
  schedule: Record<string, { weekday: number; plants: string[] }>;
  history_kinds: string[];
  editable_statuses: string[];
  priorities: PriorityGuide[];
};

export type Auditor = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
};

export type ItemPatch = Partial<{
  status: string;
  scheduled_date: string | null;
  auditor_user_id: number | null;
  auditee_name: string | null;
  auditee_email: string | null;
  override_note: string | null;
}>;

export type Escalation = {
  id?: number;
  plant: string;
  product_line: string | null;
  customer: string | null;
  level: "CSI" | "CSII";
  opened_on: string;
  closed_on: string | null;
  reference: string | null;
  note: string | null;
};

export type QualityMetric = {
  id?: number;
  plant: string;
  month: string;
  metric: "nqc" | "scrap";
  value: number;
  target: number;
  unit: string | null;
  note: string | null;
};

export type HistoryEntry = {
  id?: number;
  plant: string;
  product_line: string | null;
  kind: string;
  support_process_id: number | null;
  audited_on: string;
  note: string | null;
  source?: string;
  plan_item_id?: number | null;
};

export type SupportProcess = {
  id?: number;
  name: string;
  is_active: boolean;
  sort_order: number;
};

const base = "/audit-planning";

export const planningApi = {
  meta: async () => (await axiosInstance.get<PlanMeta>(`${base}/meta`)).data,
  runs: async () =>
    (await axiosInstance.get<PlanRunSummary[]>(`${base}/runs`)).data,
  run: async (id: number) =>
    (await axiosInstance.get<PlanRun>(`${base}/runs/${id}`)).data,
  generate: async (plan_month: string) =>
    (await axiosInstance.post<PlanRun>(`${base}/runs`, { plan_month })).data,
  approve: async (id: number) =>
    (await axiosInstance.post<PlanRunSummary>(`${base}/runs/${id}/approve`))
      .data,
  patchItem: async (id: number, patch: ItemPatch) =>
    (await axiosInstance.patch<PlanItem>(`${base}/items/${id}`, patch)).data,
  completeItem: async (id: number, completed_on: string) =>
    (
      await axiosInstance.post<PlanItem>(`${base}/items/${id}/complete`, {
        completed_on,
      })
    ).data,
  auditors: async () =>
    (await axiosInstance.get<Auditor[]>(`${base}/auditors`)).data,

  escalations: async () =>
    (await axiosInstance.get<Escalation[]>(`${base}/escalations`)).data,
  saveEscalation: async (row: Escalation) =>
    row.id
      ? (await axiosInstance.put<Escalation>(`${base}/escalations/${row.id}`, row)).data
      : (await axiosInstance.post<Escalation>(`${base}/escalations`, row)).data,
  deleteEscalation: (id: number) =>
    axiosInstance.delete(`${base}/escalations/${id}`),

  metrics: async () =>
    (await axiosInstance.get<QualityMetric[]>(`${base}/metrics`)).data,
  saveMetric: async (row: QualityMetric) =>
    (await axiosInstance.post<QualityMetric>(`${base}/metrics`, row)).data,
  deleteMetric: (id: number) => axiosInstance.delete(`${base}/metrics/${id}`),

  history: async () =>
    (await axiosInstance.get<HistoryEntry[]>(`${base}/history`)).data,
  addHistory: async (row: HistoryEntry) =>
    (await axiosInstance.post<HistoryEntry>(`${base}/history`, row)).data,
  deleteHistory: (id: number) => axiosInstance.delete(`${base}/history/${id}`),

  supportProcesses: async () =>
    (await axiosInstance.get<SupportProcess[]>(`${base}/support-processes`))
      .data,
  saveSupportProcess: async (row: SupportProcess) =>
    row.id
      ? (await axiosInstance.put<SupportProcess>(`${base}/support-processes/${row.id}`, row)).data
      : (await axiosInstance.post<SupportProcess>(`${base}/support-processes`, row)).data,
};

export const apiError = (err: unknown, fallback: string) => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return fallback;
};
