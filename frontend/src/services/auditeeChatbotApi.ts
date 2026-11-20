import axiosInstance from "./axiosInstance";

export interface ChatbotMessage {
  role: "user" | "assistant";
  content: string;
  car_id?: number | null;
  created_at?: string;
}

interface PortalIdentity {
  plant: string;
  email: string;
  access_mode: string;
  sessionToken: string;
}

export async function fetchChatHistory(
  identity: PortalIdentity,
): Promise<ChatbotMessage[]> {
  const res = await axiosInstance.get<ChatbotMessage[]>(
    "/car/portal/chatbot/history",
    {
      params: {
        plant: identity.plant,
        email: identity.email,
        access_mode: identity.access_mode,
      },
      headers: {
        "X-Portal-Session": identity.sessionToken,
      },
    },
  );
  return res.data;
}

export async function sendChatMessage(
  identity: PortalIdentity & { message: string; car_id?: number | null },
): Promise<{ reply: string }> {
  const res = await axiosInstance.post<{ reply: string }>(
    "/car/portal/chatbot/message",
    {
      plant: identity.plant,
      email: identity.email,
      access_mode: identity.access_mode,
      message: identity.message,
      car_id: identity.car_id ?? null,
    },
    {
      headers: {
        "X-Portal-Session": identity.sessionToken,
      },
    },
  );
  return res.data;
}

export interface ChatbotDraftEntry {
  text: string;
  verdict: "ready" | "weak";
  suggested_rewrite: string | null;
  note: string | null;
}

export interface ChatbotDraft {
  whys: ChatbotDraftEntry[];
  implemented_solution: ChatbotDraftEntry;
  overall_ready: boolean;
}

export async function generateDraft(
  identity: PortalIdentity & { car_id: number },
): Promise<ChatbotDraft> {
  const res = await axiosInstance.post<ChatbotDraft>(
    "/car/portal/chatbot/draft",
    {
      plant: identity.plant,
      email: identity.email,
      access_mode: identity.access_mode,
      car_id: identity.car_id,
    },
    {
      headers: {
        "X-Portal-Session": identity.sessionToken,
      },
    },
  );
  return res.data;
}

export interface ChatbotDocument {
  id: number;
  filename: string;
  size: number;
  truncated: boolean;
  created_at?: string;
}

// Allowed here mirrors the backend's CHATBOT_DOCUMENT_EXTENSIONS — text-based
// formats only (no images/PPT/legacy .doc; nothing here does OCR or vision).
export const CHATBOT_DOCUMENT_ACCEPT = ".pdf,.docx,.txt";
export const CHATBOT_DOCUMENT_MAX_SIZE = 5 * 1024 * 1024; // 5 MB, mirrors backend cap

export async function uploadChatDocument(
  identity: PortalIdentity & { car_id: number; file: File },
): Promise<ChatbotDocument> {
  const formData = new FormData();
  formData.append("plant", identity.plant);
  formData.append("email", identity.email);
  formData.append("access_mode", identity.access_mode);
  formData.append("car_id", String(identity.car_id));
  formData.append("file", identity.file);

  const res = await axiosInstance.post<ChatbotDocument>(
    "/car/portal/chatbot/document",
    formData,
    {
      headers: {
        "X-Portal-Session": identity.sessionToken,
        "Content-Type": "multipart/form-data",
      },
    },
  );
  return res.data;
}

export async function fetchChatDocuments(
  identity: PortalIdentity & { car_id: number },
): Promise<ChatbotDocument[]> {
  const res = await axiosInstance.get<ChatbotDocument[]>(
    "/car/portal/chatbot/documents",
    {
      params: {
        plant: identity.plant,
        email: identity.email,
        access_mode: identity.access_mode,
        car_id: identity.car_id,
      },
      headers: {
        "X-Portal-Session": identity.sessionToken,
      },
    },
  );
  return res.data;
}
