import { useEffect, useRef, useState } from "react";

import { currentToken } from "../../api/client";

export type ConnectionState = "connecting" | "live" | "polling";

export const RECONNECT_BASE_MS = 1000;
export const RECONNECT_MAX_MS = 15_000;
const SYNC_COALESCE_MS = 50;

type LiveChannelOptions = {
  channel: string | null;
  onMessage: () => void;
  enabled?: boolean;
};

type Message = {
  type?: string;
  channel?: string;
};

export function reconnectDelay(attempt: number): number {
  return Math.min(
    RECONNECT_BASE_MS * 2 ** Math.min(attempt, 4),
    RECONNECT_MAX_MS,
  );
}

/** Open one authenticated socket, with bounded lifetime and visible-only work. */
export function useLiveChannel({
  channel,
  onMessage,
  enabled = true,
}: LiveChannelOptions): ConnectionState {
  const [state, setState] = useState<ConnectionState>("connecting");
  const onMessageRef = useRef(onMessage);
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    if (!enabled || channel === null || typeof WebSocket === "undefined") {
      queueMicrotask(() => setState("polling"));
      return;
    }

    let stopped = false;
    let generation = 0;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let syncTimer: number | null = null;
    let attempts = 0;

    const scheduleSync = () => {
      if (syncTimer !== null) return;
      syncTimer = window.setTimeout(() => {
        syncTimer = null;
        if (!stopped) onMessageRef.current();
      }, SYNC_COALESCE_MS);
    };

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer !== null) return;
      const delay = reconnectDelay(attempts);
      attempts = Math.min(attempts + 1, 4);
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        void connect();
      }, delay);
    };

    const close = () => {
      stopped = true;
      generation += 1;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (syncTimer !== null) {
        window.clearTimeout(syncTimer);
        syncTimer = null;
      }
      if (socket !== null && socket.readyState < WebSocket.CLOSING) {
        socket.close();
      }
      socket = null;
      setState("polling");
    };

    const connect = async () => {
      const currentGeneration = ++generation;
      if (stopped) return;
      setState("connecting");
      try {
        const token = await currentToken();
        if (stopped || currentGeneration !== generation) return;
        if (token === null) {
          setState("polling");
          return;
        }
        const url = new URL(channel, window.location.origin);
        url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
        const next = new WebSocket(url, "spn.v1");
        socket = next;
        next.onopen = () => {
          if (currentGeneration !== generation || stopped) return;
          next.send(JSON.stringify({ type: "authenticate", token }));
        };
        next.onmessage = (event) => {
          if (currentGeneration !== generation || stopped) return;
          let message: Message;
          try {
            message = JSON.parse(String(event.data)) as Message;
          } catch {
            return;
          }
          if (message.type === "subscribed" && message.channel === channel) {
            attempts = 0;
            setState("live");
            scheduleSync();
          } else if (
            message.type === "order.transition" ||
            message.type === "resync"
          ) {
            scheduleSync();
          }
        };
        next.onerror = () => {
          if (currentGeneration === generation && !stopped) setState("polling");
        };
        next.onclose = () => {
          if (currentGeneration !== generation || stopped) return;
          setState("polling");
          scheduleReconnect();
        };
      } catch {
        if (currentGeneration === generation && !stopped) {
          setState("polling");
          scheduleReconnect();
        }
      }
    };

    const onVisibilityChange = () => {
      if (document.hidden) {
        close();
      } else {
        stopped = false;
        void connect();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    void connect();
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      close();
    };
  }, [channel, enabled]);

  return state;
}
