import { useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { RootState } from "../../redux/store";
import {
  hasAuditorRole,
  hasQualityManagerRole,
  hasSystemAdminRole,
} from "../../utils/roleAccess";
import {
  clearAuditorChatHistory,
  fetchAuditorChatHistory,
  sendAuditorChatMessage,
  type AuditorChatMessage,
} from "../../services/auditorChatbotApi";

const MAX_MESSAGE_LENGTH = 4000;

const SUGGESTIONS = [
  "Which of my CARs are late?",
  "What audits do I have coming up?",
  "Which findings keep repeating on my audits?",
  "How do I write a good VDA 6.3 finding?",
];

const markdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="mb-2 last:mb-0">{children}</p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="mb-2 list-disc space-y-1 pl-4 last:mb-0">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="mb-2 list-decimal space-y-1 pl-4 last:mb-0">{children}</ol>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="mb-2 overflow-x-auto">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="border border-slate-200 px-2 py-1 text-left font-semibold dark:border-slate-700">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="border border-slate-200 px-2 py-1 dark:border-slate-700">
      {children}
    </td>
  ),
};

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  return typeof detail === "string"
    ? detail
    : "The assistant is unavailable right now, please try again.";
}

// Floating audit assistant for auditors, quality managers and admins:
// audit know-how plus questions about the user's own audits and CARs.
export default function AuditorAssistant() {
  const roles = useSelector((state: RootState) => state.auth.role || []);
  const allowed =
    hasAuditorRole(roles) ||
    hasQualityManagerRole(roles) ||
    hasSystemAdminRole(roles);

  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [messages, setMessages] = useState<AuditorChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open || loaded) return;
    fetchAuditorChatHistory()
      .then(setMessages)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoaded(true));
  }, [open, loaded]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, sending, open]);

  if (!allowed) return null;

  async function send(text: string) {
    const message = text.trim();
    if (!message || sending) return;
    setError(null);
    setInput("");
    setMessages((m) => [...m, { role: "user", content: message }]);
    setSending(true);
    try {
      const { reply } = await sendAuditorChatMessage(message);
      setMessages((m) => [...m, { role: "assistant", content: reply }]);
    } catch (e) {
      setMessages((m) => m.slice(0, -1));
      setInput(message);
      setError(errorMessage(e));
    } finally {
      setSending(false);
    }
  }

  async function clear() {
    if (!window.confirm("Clear the whole conversation?")) return;
    try {
      await clearAuditorChatHistory();
      setMessages([]);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <>
      {open && (
        <div className="fixed inset-x-3 bottom-20 z-[99999] flex h-[70vh] max-h-[640px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 shadow-2xl sm:inset-x-auto sm:right-6 sm:w-[420px] dark:border-slate-800 dark:bg-slate-950">
          <div className="flex items-center justify-between gap-2 bg-blue-900 px-4 py-3 text-white">
            <div>
              <p className="text-sm font-semibold">Audit assistant</p>
              <p className="text-xs text-blue-100">
                Audit know-how and your audits, findings and CARs
              </p>
            </div>
            <div className="flex items-center gap-1">
              {messages.length > 0 && (
                <button
                  type="button"
                  onClick={clear}
                  className="rounded-md px-2 py-1 text-xs text-blue-100 hover:bg-blue-800"
                >
                  Clear
                </button>
              )}
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close assistant"
                className="rounded-md px-2 py-1 text-lg leading-none hover:bg-blue-800"
              >
                ×
              </button>
            </div>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {loaded && messages.length === 0 && !sending && (
              <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
                <p>
                  Ask about audit methods (VDA 6.3, IATF 16949, ISO 9001/14001)
                  or about your own audits, findings and corrective actions.
                </p>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => send(s)}
                      className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-700 hover:border-blue-300 hover:text-blue-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg, index) => (
              <div
                key={index}
                className={`flex ${msg.role === "user" ? "justify-end" : ""}`}
              >
                <div
                  className={`rounded-2xl px-4 py-2.5 text-sm shadow-sm ${
                    msg.role === "user"
                      ? "max-w-[80%] whitespace-pre-wrap rounded-br-sm bg-blue-800 text-white"
                      : "max-w-[95%] rounded-bl-sm border border-slate-200 bg-white text-slate-800 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100"
                  }`}
                >
                  {msg.role === "assistant" ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={markdownComponents}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  ) : (
                    msg.content
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex w-fit items-center gap-1 rounded-2xl rounded-bl-sm bg-white px-4 py-3 shadow-sm dark:bg-slate-900">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
              </div>
            )}
            <div ref={endRef} />
          </div>

          {error && (
            <p className="border-t border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              {error}
            </p>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex items-end gap-2 border-t border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              maxLength={MAX_MESSAGE_LENGTH}
              rows={2}
              placeholder="Ask the assistant…"
              className="flex-1 resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              className="rounded-lg bg-blue-800 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-900 disabled:opacity-50"
            >
              Send
            </button>
          </form>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close audit assistant" : "Open audit assistant"}
        className="fixed bottom-5 right-5 z-[99999] flex h-12 items-center gap-2 rounded-full bg-blue-800 px-4 text-sm font-semibold text-white shadow-lg hover:bg-blue-900 sm:right-6"
      >
        <span aria-hidden="true">✦</span>
        {open ? "Close" : "Assistant"}
      </button>
    </>
  );
}
