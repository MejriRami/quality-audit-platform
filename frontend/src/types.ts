 
// -------------------- Users & Participants --------------------
export interface User {
  id: number;
  first_name: string;
  last_name:string;
  email: string;
}

export interface Participant {
  user: User;
  local_role: "auditor" | "auditee";
}
export type CorrectiveActionStatus =
  | "Pending"
  | "Submitted"
  | "Accepted"
  | "Rejected";

// -------------------- Questionnaire --------------------
export interface Questionnaire {
  id?: number;
  name: string;
  type: string;
}

// -------------------- Document --------------------
export interface Document {
  id: number;
  filename?: string;
  file_url: string;
  mimetype?: string;
  size?: number;
  uploaded_at?: string;
}

// -------------------- Question Response --------------------
export interface QuestionResponse {
  id: number;
  description: string;
  chapter?: string;
  criticality: string; // "Critical" | "High" | "Medium" | "Low" | "N/A"
  value?: number;
  response?: string;
}

// -------------------- Finding --------------------
export interface Finding {
  question_id: number;
  finding_type: string; // "Non-Conformity" | "Opportunity for Improvement" | "Conformity" | "Not Evaluated"
  finding_text?: string;
  corrective_action?: string;
  corrective_action_status?: string; // "pending" | "in_progress" | "submitted" | "accepted" | "rejected" | "completed"
  corrective_action_type?: string; // "Escalated" | "Overdue" | "Pending Review" | "In Progress" | "Awaiting Approval" | "Approved" | "Rejected" | "Completed" | "Standard"
}


// -------------------- Audit --------------------
export interface Audit {
  id: number;
  audit_number: string;
  status: string;
  planned_start_date: string;
  planned_end_date: string;
  actual_start_date?: string;
  actual_end_date?: string;
  plant?: string;
  sector?: string;
  total_score?: number; // Changed from finalScore
  weak_points?: string;
  strong_points?: string;
  event_created: boolean;
  finalScore?: number;
  // Relationships
  auditor?: User;
  questionnaire?: Questionnaire;
  auditees: string[]; // Array of email strings
  
  // Audit content
  questions_and_responses: QuestionResponse[];
  findings: Finding[];
}


export interface DocumentItem {
  id: number;
  filename: string;
  file_url: string;
  size: number;
  uploaded_at?: string | null;
  document_type?: "finding_evidence" | "car_solution";
}


// -------------------- Corrective Actions Table --------------------
export interface CorrectiveAction {
  id: number;
  auditId: number;
  plant?: string | null;
  plant_name?: string | null;
 
  /** e.g. "CAR-2024-001" */
  identifier?: string | null;
  audit_reference?: string | null;

  /** "corrective" (root-cause fix) or "immediate" (containment action) --
   *  a finding with immediate action required splits into two linked rows. */
  action_type?: string | null;
  linked_action_id?: number | null;

  auditAnswerId?: number | null;
 
  /** FAIL | IMPROVE | PASS */
  finding_type?: string | null;
  /** Question description used as the action label */
  corrective_action?: string | null;
  /** Full finding text from AuditAnswer */
  finding_text?: string | null;
 
  /** AuditAnswer.process */
  process?: string | null;
  /** AuditAnswer.standard_paragraph */
  standard_paragraph?: string | null;
  /** AuditAnswer.classification */
  classification?: string | null;
  /** Question.chapter */
  chapter?: string | null;
 
  auditee: string;
  pilotUser?: string | null;
 
  reason_why?: string | null;
  root_cause?: string | null;
  implemented_solution?: string | null;
 
  due_date?: string | null;
  submitted_at?: string | null;
  created_at?: string | null;
 
  status: CorrectiveActionStatus | string;
  escalated: boolean;
 
  /** Only present when status === "Rejected" */
  review_comment?: string | null;
 
  documents: DocumentItem[];
  documents_count?: number;
  reassigned_from_email?: string | null;
  cc_emails?: string[];
}

export interface CorrectiveActionReviewHistoryItem {
  id: number;
  decision: string;
  comment?: string | null;
  reviewed_at?: string | null;
  auditor?: string | null;
}

export interface CorrectiveActionActivityItem {
  id: string;
  event_type: string;
  event_label: string;
  at?: string | null;
  actor?: string | null;
  details?: string | null;
  severity?: string | null;
}

export interface CorrectiveActionDetail {
  id: number;
  auditId: number;
  audit_reference?: string | null;
  action_type?: string | null;
  linked_action_id?: number | null;
  auditAnswerId?: number | null;
  finding_type?: string | null;
  corrective_action?: string | null;
  auditee: string;
  pilotUser?: string | null;
  reason_why?: string | null;
  due_date?: string | null;
  status: CorrectiveActionStatus | string;
  escalated: boolean;
  root_cause?: string | null;
  implemented_solution?: string | null;
  submitted_at?: string | null;
  created_at?: string | null;
  documents: DocumentItem[];
  review_history: CorrectiveActionReviewHistoryItem[];
  activity_timeline: CorrectiveActionActivityItem[];
  reassigned_from_email?: string | null;
  cc_emails?: string[];
}
 
export interface CorrectiveActionListResponse {
  items: CorrectiveAction[];
  total: number;
  limit: number;
  offset: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ScheduleHistoryEntry {
  id: number;
  old_start: string;
  old_end: string;
  new_start: string;
  new_end: string;
  reason?: string;
  changed_at: string;
  changed_by: { id: number; name: string };
}


export interface Entity {
  id: number;
  type: string;       // maps from EntityType enum
  code: string;
  label: string;
  parent_id: number | null;
  parent?: {
    id: number;
    label: string;
    code: string;
  } | null;
}

export interface Framework {
  id: number;
  label: string;
  code: string;
}


export interface Auditor {
  email: string;
  id?: number;
}



export interface Question {
  id: number;
  description: string;
  chapter: string;
  weight: number;
  critical_value?: number;
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


export interface NotificationItem {  
  id: number;
  type: string;
  title: string;
  message: string;
  link?: string;
  read: boolean;
  created_at: string;
  metadata?: {
    car_id?: number;
    audit_id?: number;
    audit_number?: string;
    submitted_by?: string;
    submitted_at?: string;
    plant?: string;
    sector?: string;
    request_id?: number;
    questionnaire_id?: number;
    status?: "pending" | "approved" | "rejected" | "all" | string;
    tab?: string;
    entity_type?: string;
    action_type?: string;
  };
}

export interface NotificationListResponse {
  notifications: NotificationItem[];
  unread_count: number;
}

export type NotificationEventType = 
  | 'connected' 
  | 'notification' 
  | 'error' 
  | 'keepalive';

export interface SSEEvent {
  event: NotificationEventType;
  data: unknown;
  id?: number;
  timestamp: string;
}
