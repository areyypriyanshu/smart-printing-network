import { useEffect, useRef, useState } from "react";

import { currentToken } from "../../api/client";

export type ConnectionState = "connecting" | "live" | "polling";

export const RECONNECT_BASE_MS = 1000;
export const RECONNECT_MAX_MS = 15_000;
/** The server pings an idle socket at least every 25 seconds. */
export const WATCHDOG_SILENCE_MS = 45_000;
export const WATCHDOG_CHECK_MS = 10_000;
const SYNC_COALESCE_MS = 50;

type LiveChannelOptions = {
  channel: string | null;
  onMessage: () => void;
  enabled?: boolean;
};

type Message = {
  type?: string;
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
    let watchdogTimer: number | null = null;
    let attempts = 0;
    let lastMessageAt = 0;

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

    // A socket that has gone quiet without closing (a half-open
    // connection, a network address translation that dropped it) would
    // otherwise stay "live" with polling switched off, and the page
    // would show a stale status. Drop it so a fresh one is opened.
    const forceReconnect = () => {
      if (stopped) return;
      generation += 1;
      const stale = socket;
      socket = null;
      if (stale !== null && stale.readyState < WebSocket.CLOSING) {
        stale.close();
      }
      setState("polling");
      scheduleReconnect();
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
        lastMessageAt = Date.now();
        next.onopen = () => {
          if (currentGeneration !== generation || stopped) return;
          lastMessageAt = Date.now();
          next.send(JSON.stringify({ type: "authenticate", token }));
        };
        next.onmessage = (event) => {
          if (currentGeneration !== generation || stopped) return;
          lastMessageAt = Date.now();
          let message: Message;
          try {
            message = JSON.parse(String(event.data)) as Message;
          } catch {
            return;
          }
          // The server confirms the subscription on this socket with the
          // channel it derived itself (`vendor:{shop_id}`), which the
          // client cannot predict because the shop id is decided on the
          // server. This socket is the subscription, and the generation
          // guard already discards a message from a socket that has been
          // replaced, so any `subscribed` here is this socket's.
          if (message.type === "subscribed") {
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

    watchdogTimer = window.setInterval(() => {
      if (stopped || socket === null) return;
      if (socket.readyState !== WebSocket.OPEN) return;
      if (Date.now() - lastMessageAt <= WATCHDOG_SILENCE_MS) return;
      forceReconnect();
    }, WATCHDOG_CHECK_MS);

    // A hidden tab does no live work: the socket is closed and polling
    // takes over, because the browser is not being looked at. Coming
    // back opens a fresh socket and resyncs once it is subscribed.
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
      if (watchdogTimer !== null) {
        window.clearInterval(watchdogTimer);
        watchdogTimer = null;
      }
      close();
    };
  }, [channel, enabled]);

  return state;
}
