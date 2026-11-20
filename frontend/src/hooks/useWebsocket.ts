// useWebSocket.ts
// ----------------
// Production-hardened WebSocket hook for real-time notifications.
//
// Key fixes vs. original:
// - onMessage is stored in a ref so the hook never captures a stale closure,
//   even if the parent re-renders with a new callback.
// - connect() itself is stable (useCallback with empty deps) so the
//   useEffect cleanup/setup runs only once.
// - Browser Notification API is guarded with typeof checks for SSR / embedded
//   environments.
// - reconnectAttempts is reset correctly on a clean auth-close.

import { useCallback, useEffect, useRef, useState } from "react";

export interface WebSocketMessage {
  id: number;
  type: string;
  title: string;
  message: string;
  link?: string;
  metadata?: Record<string, unknown>;
  read: boolean;
  created_at: string;
}

type ServerControlMessage = {
  type: "connection" | "pong";
  message?: string;
  user_id?: number;
};

const MAX_RECONNECT_ATTEMPTS = 10;
// Browsers only allow app code to close with 1000 or 3000-4999 (RFC 6455);
// 1008 is reserved for the server, so we use our own sentinel for a
// client-initiated "no token" close and still recognize a server-sent 1008.
const NO_TOKEN_CLOSE_CODE = 4001;

function buildWsUrl(): string {
  const raw = (import.meta.env.VITE_API_URL as string) || "http://localhost:8000";
  const base = raw.replace(/\/+$/, "");
  const withPath = base.endsWith("/notifications") ? base : `${base}/notifications`;
  return withPath.replace(/^https/, "wss").replace(/^http/, "ws") + "/ws";
}

export function useWebSocket(
  onMessage: (message: WebSocketMessage) => void,
): { isConnected: boolean } {
  const [isConnected, setIsConnected] = useState(false);

  // Store the latest callback in a ref — never stale, never triggers reconnect.
  const onMessageRef = useRef(onMessage);
  useEffect(() => {
    onMessageRef.current = onMessage;
  });

  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const heartbeatInterval = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const reconnectAttempts = useRef(0);

  const clearTimers = useCallback(() => {
    if (reconnectTimeout.current !== undefined) {
      clearTimeout(reconnectTimeout.current);
      reconnectTimeout.current = undefined;
    }
    if (heartbeatInterval.current !== undefined) {
      clearInterval(heartbeatInterval.current);
      heartbeatInterval.current = undefined;
    }
  }, []);

  const connect = useCallback(() => {
    // Don't open a second socket if one is already live.
    if (
      ws.current &&
      (ws.current.readyState === WebSocket.OPEN ||
        ws.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    const url = buildWsUrl();
    console.debug("[ws] connecting →", url);
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => {
      const token = localStorage.getItem("token");
      if (!token) {
        console.warn("[ws] no token — closing");
        socket.close(NO_TOKEN_CLOSE_CODE, "No token");
        return;
      }
      socket.send(JSON.stringify({ type: "auth", token }));
      reconnectAttempts.current = 0;

      heartbeatInterval.current = setInterval(() => {
        if (ws.current?.readyState === WebSocket.OPEN) {
          ws.current.send("ping");
        }
      }, 30_000);
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as WebSocketMessage | ServerControlMessage;

        if (data.type === "connection") {
          setIsConnected(true);
          return;
        }
        if (data.type === "pong") return;

        onMessageRef.current(data as WebSocketMessage);

        // Safe browser notification (guard for SSR / iframe contexts)
        if (
          typeof window !== "undefined" &&
          "Notification" in window &&
          window.Notification.permission === "granted"
        ) {
          const n = data as WebSocketMessage;
          new window.Notification(n.title, {
            body: n.message,
            icon: "/notification-icon.png",
          });
        }
      } catch (e) {
        console.error("[ws] parse error:", e);
      }
    };

    socket.onerror = () => {
      // onerror always precedes onclose; close() triggers the reconnect logic.
      socket.close();
    };

    socket.onclose = (event: CloseEvent) => {
      console.debug("[ws] closed — code:", event.code, "reason:", event.reason);
      setIsConnected(false);
      clearTimers();

      // 1008 = server-reported auth failure; our own sentinel = no token
      // client-side. Either way, don't retry with a bad/missing token.
      if (event.code === 1008 || event.code === NO_TOKEN_CLOSE_CODE) {
        console.warn("[ws] auth failure — not reconnecting");
        return;
      }

      if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = Math.min(1_000 * 2 ** reconnectAttempts.current, 30_000);
        reconnectAttempts.current += 1;
        console.debug(`[ws] reconnect in ${delay}ms (attempt ${reconnectAttempts.current})`);
        reconnectTimeout.current = setTimeout(connect, delay);
      } else {
        console.error("[ws] max reconnect attempts reached");
      }
    };
  }, [clearTimers]); // stable — no external deps that change

  useEffect(() => {
    // Request browser notification permission once on mount.
    if (
      typeof window !== "undefined" &&
      "Notification" in window &&
      window.Notification.permission === "default"
    ) {
      window.Notification.requestPermission().catch(() => {
        /* permission denied — silently ignore */
      });
    }

    connect();

    return () => {
      clearTimers();
      ws.current?.close();
    };
  }, [connect, clearTimers]);

  return { isConnected };
}