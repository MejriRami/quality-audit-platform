import axiosInstance from "./axiosInstance";

export type CertificationStatus =
  | "pending_review"
  | "validated"
  | "rejected"
  | "expired";

export type AuditGroup =
  | "certification_review"
  | "certification_audits_2025"
  | "validated_certification_after_review"
  | "internal_audit"
  | "customer_cross_site_audit"
  | "external_audit";

export type CertificationDocumentType =
  | "certificate"
  | "report"
  | "report.json for IATF CARA"
  | "other";

export type Certification = {
  id: number;
  monday_item_id: string | null;
  monday_group: AuditGroup | null;
  certification_number: string | null;
  name: string;
  certification_type: string | null;
  document_type: CertificationDocumentType | null;
  // Shown as "Certificate Scope" when document_type is "certificate".
  scope: string | null;
  plant: string | null;
  quality_manager_name: string | null;
  quality_manager_email: string | null;
  external_certification_body: string | null;
  audit_date: string | null;
  date_of_last_audit: string | null;
  next_expected_audit: string | null;
  certification_expiration_date: string | null;
  status: CertificationStatus;
  rejected_reason: string | null;
  automation_status: string | null;
  quality_manager_decision: string | null;
  created_at: string | null;
  updated_at: string | null;
  nonconformity_count: number;
  document_count: number;
};

export type CertificationInput = Omit<
  Certification,
  | "id"
  | "monday_item_id"
  | "created_at"
  | "updated_at"
  | "nonconformity_count"
  | "document_count"
>;

export type CertificationDocument = {
  id: number;
  document_type: string | null;
  filename: string | null;
  uploaded_at: string | null;
  download_url: string;
};

export type CertificationMeta = {
  statuses: CertificationStatus[];
  document_types: CertificationDocumentType[];
  monday_groups: AuditGroup[];
  plants: string[];
  certification_types: string[];
};

export type CertificationFilters = {
  search?: string;
  status?: string;
  plant?: string;
  monday_group?: string;
};

const BASE = "/external-certifications";

// ── Public portal session (no app login, emailed code) ─────────────────────

export type PortalSession = {
  session_token: string;
  session_expires_at: string;
  email: string;
  can_edit: boolean;
};

const PORTAL_SESSION_KEY = "certificationPortalSession";
let portalSessionToken: string | null = null;

export function loadPortalSession(): PortalSession | null {
  try {
    const raw = localStorage.getItem(PORTAL_SESSION_KEY);
    const session = raw ? (JSON.parse(raw) as PortalSession) : null;
    if (session && new Date(session.session_expires_at) > new Date()) return session;
  } catch {
    // storage unavailable or corrupt: sign in again
  }
  clearPortalSession();
  return null;
}

export function savePortalSession(session: PortalSession) {
  try {
    localStorage.setItem(PORTAL_SESSION_KEY, JSON.stringify(session));
  } catch {
    // session still works for this page load
  }
}

export function clearPortalSession() {
  portalSessionToken = null;
  try {
    localStorage.removeItem(PORTAL_SESSION_KEY);
  } catch {
    // nothing to clear
  }
}

// Set by the portal page: every call below then authenticates with the
// portal session instead of the app login.
export function setPortalSessionToken(token: string | null) {
  portalSessionToken = token;
}

const auth = (headers: Record<string, string> = {}) => ({
  headers: portalSessionToken
    ? { ...headers, "X-Certification-Session": portalSessionToken }
    : headers,
});

export async function requestPortalCode(email: string) {
  const { data } = await axiosInstance.post<{ email: string }>(`${BASE}/portal/request-code`, { email });
  return data;
}

export async function verifyPortalCode(email: string, code: string) {
  const { data } = await axiosInstance.post<PortalSession>(`${BASE}/portal/verify-code`, { email, code });
  return data;
}

export async function fetchCertificationMe() {
  const { data } = await axiosInstance.get<{ email: string; can_edit: boolean }>(`${BASE}/me`, auth());
  return data;
}

// ── Certifications ─────────────────────────────────────────────────────────

export async function fetchCertificationMeta() {
  const { data } = await axiosInstance.get<CertificationMeta>(`${BASE}/meta`, auth());
  return data;
}

export async function fetchCertifications(filters: CertificationFilters) {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v),
  );
  const { data } = await axiosInstance.get<Certification[]>(BASE, { params, ...auth() });
  return data;
}

export async function createCertification(input: CertificationInput) {
  const { data } = await axiosInstance.post<Certification>(BASE, input, auth());
  return data;
}

export async function updateCertification(id: number, input: CertificationInput) {
  const { data } = await axiosInstance.put<Certification>(`${BASE}/${id}`, input, auth());
  return data;
}

export async function deleteCertification(id: number) {
  await axiosInstance.delete(`${BASE}/${id}`, auth());
}

export async function fetchCertificationDocuments(certId: number) {
  const { data } = await axiosInstance.get<CertificationDocument[]>(
    `${BASE}/${certId}/documents`,
    auth(),
  );
  return data;
}

export async function uploadCertificationDocument(
  certId: number,
  file: File,
  documentType: string,
) {
  const form = new FormData();
  form.append("file", file);
  if (documentType) form.append("document_type", documentType);
  const { data } = await axiosInstance.post<CertificationDocument>(
    `${BASE}/${certId}/documents`,
    form,
    auth({ "Content-Type": "multipart/form-data" }),
  );
  return data;
}

export async function deleteCertificationDocument(certId: number, docId: number) {
  await axiosInstance.delete(`${BASE}/${certId}/documents/${docId}`, auth());
}

export function apiErrorMessage(err: unknown, fallback: string) {
  const detail = (err as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

export function labelize(value: string) {
  return value
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
