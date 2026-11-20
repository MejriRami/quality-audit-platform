
import { Audit, AuditAuditeeUpdateRequest, AuditByAuditor, AuditCancelRequest, AuditPlanCreate, AuditPlanningDetails, AuditPlanningDetailsUpdate, AuditPlanningSyncResponse, AuditRescheduleHistory, AuditRescheduleRequest, ExecuteAuditRequest, ExecuteAuditResponse, PickableAudit, UploadResponse } from "./audit-types";
import axiosInstance from "../../services/axiosInstance";
import type { AxiosError } from "axios";
import { getAuditorsByAuditorFailure, getAuditorsByAuditorRequest, getAuditorsByAuditorSuccess } from "./audit-slice";

const parseAxiosError = (error: unknown) => {
  const err = error as AxiosError<unknown>;
  return {
    status: err.response?.status,
    data: err.response?.data,
    message: err.message,
  };
};

// Create audit (plan)
export const apiPlanAudit = async (payload: AuditPlanCreate): Promise<Audit> => {
  const url ='/audits/plan';

  try {
    const response = await axiosInstance.post(url, payload, {
      params: payload.allow_unavailable_auditee
        ? { allow_unavailable_auditee: true }
        : undefined,
    });
    return response.data;
  } catch (error: unknown) {
    const parsed = parseAxiosError(error);
    console.error("Failed to plan audit:", parsed.data || parsed.message);
    throw error;
  }
};

// reschedule audit 
export const apiRescheduleAudit= async(  auditId: number,payload:AuditRescheduleRequest):Promise<Audit>=>{
  const url=`/audits/${auditId}/reschedule`
  try{
    const response= await axiosInstance.patch(url,payload, {
      params: payload.allow_unavailable_auditee
        ? { allow_unavailable_auditee: true }
        : undefined,
    });
    return response.data;
  }
  catch(error: unknown){
     const parsed = parseAxiosError(error);
     console.error("Failed to reschedule audit:", parsed.data || parsed.message);
    throw error;
  }
}

export const apiCancelAudit = async (
  auditId: number,
  payload: AuditCancelRequest,
): Promise<Audit> => {
  const url = `/audits/${auditId}/cancel`;
  try {
    const response = await axiosInstance.patch(url, payload);
    return response.data;
  } catch (error: unknown) {
    const parsed = parseAxiosError(error);
    console.error("Failed to cancel audit:", parsed.data || parsed.message);
    throw error;
  }
};

export const apiDeleteAudit = async (auditId: number): Promise<{ message: string; audit_id: number }> => {
  const url = `/audits/${auditId}`;
  const response = await axiosInstance.delete(url);
  return response.data;
};

export const apiUpdateAuditAuditees = async (
  auditId: number,
  payload: AuditAuditeeUpdateRequest,
): Promise<Audit> => {
  const url = `/audits/${auditId}/auditees`;
  try {
    const response = await axiosInstance.patch(url, payload);
    return response.data;
  } catch (error: unknown) {
    const parsed = parseAxiosError(error);
    console.error("Failed to update audit auditees:", parsed.data || parsed.message);
    throw error;
  }
};

export const apiGetAuditPlanningDetails = async (
  auditId: number,
): Promise<AuditPlanningDetails> => {
  const url = `/audits/${auditId}/planning-details`;
  const response = await axiosInstance.get(url);
  return response.data;
};

export const apiUpdateAuditPlanningDetails = async (
  auditId: number,
  payload: AuditPlanningDetailsUpdate,
): Promise<AuditPlanningDetails> => {
  const url = `/audits/${auditId}/planning-details`;
  const response = await axiosInstance.patch(url, payload);
  return response.data;
};

export const apiSendAuditPlanningCalendar = async (
  auditId: number,
): Promise<AuditPlanningSyncResponse> => {
  const url = `/audits/${auditId}/planning-details/send-calendar`;
  const response = await axiosInstance.post(url);
  return response.data;
};

// Fetch all audits
export const apiGetAudits = async (): Promise<Audit[]> => {
    const url='/audits/all';
  try {
    const res = await axiosInstance.get(url);
    if (res.status != 200) throw new Error("Failed to fetch audits");
    const data = await res.data?.audits;
    return data
    // return data.audits; 
  } catch (err) {
    console.error("Error fetching audits:", err);
    throw err;
  }
};

// Fetch audit reschedule history
export const apiGetAuditHistory = async (
  auditId: number
): Promise<AuditRescheduleHistory[]> => {
  const url=`/audits/${auditId}/history`
  try {
    const res = await axiosInstance.get(url);
    if (res.status!=200) throw new Error("Failed to fetch audit history");
    const data = await res?.data;

    return Array.isArray(data) ? data : data?.history ?? [];
  } catch (err) {
    console.error("Error fetching audit history:", err);
    return [];
  }
};

//get audits by auditor id
export const getAuditsByAuditor: AuditByAuditor = async (
  dispatch,
  auditor_id: number | string,
  target: string,
  page?: number,
  per_page?: number
  ) => {
  dispatch(getAuditorsByAuditorRequest());
  const isAllAuditors = auditor_id === "all" || Number(auditor_id) === 0;
  const resolvedAuditorId = isAllAuditors ? 0 : Number(auditor_id);
  let url=`/audits/auditor/${resolvedAuditorId}`

  if(page && per_page){
    url+=`?page=${page}&per_page=${per_page}`;
  }

  try {
    const response = await axiosInstance.get(url);
    dispatch(getAuditorsByAuditorSuccess({data: response.data, target}));
    return true;
  } catch (error: unknown) {
    const { data } = parseAxiosError(error);
    dispatch(getAuditorsByAuditorFailure(data));
  }

  return false;
};

// Get Audit questions by auditID
export const apiGetAuditQuestions = async (auditId: number) => {
  const res = await axiosInstance.get(`/audits/${auditId}/questions`);
  return res.data;
};

export const apiGetPickableAuditsByAuditor = async (
  auditorId: number
): Promise<PickableAudit[]> => {
  const res = await axiosInstance.get(`/audits/auditor/${auditorId}/pickable-audits`);
  return res.data;
};

export const apiExecuteAudit = async (
  auditId: number,
  payload: ExecuteAuditRequest
): Promise<ExecuteAuditResponse> => {
  const res = await axiosInstance.post(`/audits/${auditId}/execute`, payload);
  return res.data;
};


export async function apiUploadFile(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await axiosInstance.post("/files/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return res.data;
}
