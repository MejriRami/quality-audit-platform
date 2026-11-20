import axiosInstance from "./axiosInstance";

export interface AuditorChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

export async function fetchAuditorChatHistory(): Promise<AuditorChatMessage[]> {
  const res = await axiosInstance.get<AuditorChatMessage[]>(
    "/auditor-chatbot/history",
  );
  return res.data;
}

export async function sendAuditorChatMessage(
  message: string,
): Promise<{ reply: string }> {
  const res = await axiosInstance.post<{ reply: string }>(
    "/auditor-chatbot/message",
    { message },
  );
  return res.data;
}

export async function clearAuditorChatHistory(): Promise<void> {
  await axiosInstance.delete("/auditor-chatbot/history");
}
