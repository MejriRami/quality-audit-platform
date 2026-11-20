import axiosInstance from "./axiosInstance";
import {
  CorrectiveActionDetail,
  CorrectiveActionListResponse,
  CorrectiveActionStatus,
} from "../types";

export interface CorrectiveActionFilters {
  audit_id?: number;
  car_id?: number;
  status?: CorrectiveActionStatus | "";
  search?: string;
  include_documents?: boolean;
  limit: number;
  offset: number;
}

export async function fetchCorrectiveActions(
  filters: CorrectiveActionFilters,
): Promise<CorrectiveActionListResponse> {
  const response = await axiosInstance.get<CorrectiveActionListResponse>(
    "/car/admin/corrective-actions",
    {
      params: {
        audit_id: filters.audit_id || undefined,
        car_id: filters.car_id || undefined,
        status: filters.status || undefined,
        search: filters.search?.trim() || undefined,
        include_documents: filters.include_documents ?? undefined,
        limit: filters.limit,
        offset: filters.offset,
      },
    },
  );

  return response.data;
}

export async function reviewCorrectiveAction(
  id: number,
  payload: { decision: "ACCEPT" | "REJECT"; comment?: string },
): Promise<void> {
  await axiosInstance.post(`/car/admin/${id}/review`, payload);
}

export async function fetchCorrectiveActionDetails(
  id: number,
): Promise<CorrectiveActionDetail> {
  const response = await axiosInstance.get<CorrectiveActionDetail>(
    `/car/admin/${id}`,
  );

  return response.data;
}

export async function extendCorrectiveActionDueDate(
  id: number,
  payload: { new_due_date: string; comment?: string },
): Promise<void> {
  await axiosInstance.post(`/car/admin/${id}/extend-due-date`, payload);
}

export async function escalateCorrectiveAction(
  id: number,
  payload: { emails: string[]; comment?: string },
): Promise<void> {
  await axiosInstance.post(`/car/admin/${id}/escalate`, payload);
}

export async function reassignCorrectiveActionAuditee(
  id: number,
  payload: { new_auditee_email: string; reason?: string },
): Promise<void> {
  await axiosInstance.post(`/car/admin/${id}/reassign-auditee`, payload);
}

export interface AuditorHoliday {
  id: number;
  start_date: string;
  end_date: string;
  reason?: string | null;
}

export async function fetchAuditorHolidays(): Promise<AuditorHoliday[]> {
  const response = await axiosInstance.get<AuditorHoliday[]>(
    "/car/admin/auditor-holidays",
  );
  return response.data;
}

export async function createAuditorHoliday(payload: {
  start_date: string;
  end_date: string;
  reason?: string;
}): Promise<AuditorHoliday> {
  const response = await axiosInstance.post<AuditorHoliday>(
    "/car/admin/auditor-holidays",
    payload,
  );
  return response.data;
}

export async function deleteAuditorHoliday(id: number): Promise<void> {
  await axiosInstance.delete(`/car/admin/auditor-holidays/${id}`);
}