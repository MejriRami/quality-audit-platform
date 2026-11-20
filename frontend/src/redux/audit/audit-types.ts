import { Dispatch } from "@reduxjs/toolkit";
import { Finding, QuestionResponse } from "../../types";

// redux/audit/audit-types.ts
export interface Audit {
  audit_number: string;
  event_created: boolean;
  id: number;
  questionnaire?: { id:number,name: string ,type?:string};
  plant?: string;
  sector?: string;
  status?: string;
  finalScore?: number;
  auditor?: {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
  };
  // Optional co-auditor; `auditor` stays the lead auditor.
  second_auditor?: {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
  } | null;
  auditees?: string[];
  // Additive alongside `auditees` — carries people_id per auditee so a
  // picker re-opened from an already-fetched audit knows who came from the
  // Northwind directory instead of showing everyone as manually typed. Falls
  // back to `auditees` when absent (older cached data, etc.).
  auditee_details?: AuditeeInput[];
  sessions?: { start_time: string; end_time: string }[];
  questions_and_responses?: QuestionResponse[];
  findings?: Finding[];
  planned_start_date?: string;
  planned_end_date?: string;
  actual_start_date?: string;
  actual_end_date?: string;
  total_score?: number; 
  weak_points?: string;
  strong_points?: string;

  report_exists: boolean;
  event_id?: string | null;
  supervisor_email?: string | null;
  hardware_email?: string | null;
  cancel_reason?: string | null;
}

export interface AuditeeInput {
  email: string;
  people_id?: number | null;
}

export interface AuditPlanCreate {
  auditee_emails: string[];
  // Optional, richer alternative to auditee_emails — when present and
  // non-empty, the backend prioritizes it (see audit_service.resolve_auditee_inputs).
  // auditee_emails is still sent too, kept in sync, so nothing breaks if a
  // consumer of this type only reads that field.
  auditees?: AuditeeInput[];
  auditor_id: number;
  second_auditor_id?: number | null;
  plant: string;
  sector: string;
  hardware_email?: string;
  questionnaire_id: number;
  audit_date: string;  // "YYYY-MM-DD"
  start_time: string;  // "HH:mm:ss"
  end_time: string;    // "HH:mm:ss"
  supervisor_email: string; // supervisor email
  allow_unavailable_auditee?: boolean;
}



export interface AuditPlanningDetails {
  audit_id: number;
  audit_number?: string | null;
  status: string;
  event_created: boolean;
  event_id?: string | null;
  calendar_sync_needed?: boolean | null;
  plant: string;
  sector?: string | null;
  supervisor_email?: string | null;
  hardware_email?: string | null;
  audit_date: string;
  start_time: string;
  end_time: string;
  auditee_emails: string[];
  auditee_details?: AuditeeInput[];
  auditor: {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
  };
  second_auditor?: {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
  } | null;
  questionnaire_id: number;
  questionnaire: {
    name: string;
    type?: string | null;
  };
}

export interface AuditPlanningDetailsUpdate {
  auditee_emails: string[];
  auditees?: AuditeeInput[];
  plant: string;
  sector?: string | null;
  supervisor_email?: string | null;
  hardware_email?: string | null;
  audit_date: string;
  start_time: string;
  end_time: string;
}

export interface AuditDeleteResponse {
  message: string;
  audit_id: number;
}

export interface AuditPlanningSyncResponse {
  ok: boolean;
  audit_id: number;
  event_action: string;
  event_created: boolean;
  event_id?: string | null;
}

export interface AuditRescheduleHistory {
  id: number;
  action_type: string;
  old_date: string | null;
  new_date: string | null;
  reason_code?: number | null;
  reason: string | null;
  changed_by?: string | null;
  created_at: string;
}

export type PlanAudit = (
  data: AuditPlanCreate,
  dispatch: Dispatch
) => Promise<boolean>;

export  interface AuditRescheduleRequest{
  new_start_date:string;
  new_end_date:string;
  reason:string;
  email:string;
  allow_unavailable_auditee?: boolean;
}

export interface AuditCancelRequest {
  reason_code: number;
  reason?: string;
  email: string;
}

export interface AuditAuditeeUpdateRequest {
  auditee_emails: string[];
  auditees?: AuditeeInput[];
  email: string;
  allow_unavailable_auditee?: boolean;
}
export type AuditByAuditor = (
  dispatch: Dispatch,
  auditor_id: number | string,
  target: string,
  page?: number,
  per_page?: number,
) => Promise<boolean>;

export interface AuditQuestion {
  id: number;
  description: string;
  critical_value: number;
  weight?: number | null;
}


export interface AuditeeMini {
  id: number;
  email?: string | null;
}

export interface PickableAudit {
  id: number;
  audit_number: string;
  planned_date: string;         
  planned_start_time: string;   
  planned_end_time: string;     
  status: string;
  auditees: AuditeeMini[];
  questionnaire_name?: string | null;
  plant?: string;
  framework_code?: string | null;
  framework_label?: string | null;
  audit_type_value?: string | null;
  score_calculation?: string | null;
}
export interface DocumentCreate {
  filename: string;
  mimetype: string;
  size: number;
  file_url: string;
}

export interface AuditAnswerCreate {
  requirements?: {
    question_requirement_id: number;
    value?: number | null;
    fulfilled?: boolean | null;
    finding_text?: string | null;
    evidence?: DocumentCreate[];
  }[];
  question_id: number;
  value: number; // -1 allowed
  finding_text?: string | null;
  documents: DocumentCreate[];
  car_reason?: string | null;
  request_car: boolean;
  silent_box?: boolean;
  critical_value:number;
  question_text?: string;
}

export interface ExecuteAuditRequest {
  answers: AuditAnswerCreate[];
  audit_date: string;          
  start_time: string;          
  end_time: string;             
  strong_points: string;       
  weak_points: string;         
}

export interface ExecuteAuditResponse {
  message: string;
  audit_id: number;
  status: string;
  answers_created: number;
  cars_created: number;
}


export type UploadResponse = {
  filename: string;
  mimetype: string;
  size: number;
  file_url: string;
};



