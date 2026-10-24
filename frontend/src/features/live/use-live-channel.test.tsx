import { StrictMode } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setTokenSource } from "../../api/client";
import { renderWithProviders } from "../../test/render";
import { useLiveChannel } from "./use-live-channel";

type TestMessage = { type: string; channel?: string };

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readonly url: string;
  readonly protocols: string | string[];
  readyState = FakeWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  sent: string[] = [];

  constructor(url: string, protocols: string | string[]) {
    this.url = url;
    this.protocols = protocols;
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  message(message: TestMessage) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  send(message: string) {
    this.sent.push(message);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code: 1000 });
  }
}

function setDocumentHidden(hidden: boolean) {
  Object.defineProperty(document, "hidden", {
    configurable: true,
    get: () => hidden,
  });
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useLiveChannel", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    setTokenSource(async () => "fake-token");
  });

  afterEach(() => {
    setTokenSource(null);
    vi.unstubAllGlobals();
    vi.useRealTimers();
    setDocumentHidden(false);
  });

  it("authenticates the first frame, resyncs once, and ignores pings", async () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useLiveChannel({ channel: "/ws/vendor", onMessage }),
    );
    await flush();
    const socket = FakeWebSocket.instances[0];
    expect(new URL(socket.url).pathname).toBe("/ws/vendor");
    expect(socket.url).not.toContain("fake-token");
    expect(socket.protocols).toBe("spn.v1");

    act(() => socket.open());
    expect(JSON.parse(socket.sent[0])).toEqual({
      type: "authenticate",
      token: "fake-token",
    });
    act(() => {
      socket.message({ type: "subscribed", channel: "/ws/vendor" });
      vi.advanceTimersByTime(50);
    });
    expect(result.current).toBe("live");
    expect(onMessage).toHaveBeenCalledTimes(1);

    act(() => {
      socket.message({ type: "resync" });
      vi.advanceTimersByTime(50);
      socket.message({ type: "order.transition" });
      vi.advanceTimersByTime(50);
      socket.message({ type: "ping" });
      vi.advanceTimersByTime(50);
    });
    expect(onMessage).toHaveBeenCalledTimes(3);
  });

  it("backs off exponentially and resets only after a ready subscription", async () => {
    const { result } = renderHook(() =>
      useLiveChannel({ channel: "/ws/vendor", onMessage: vi.fn() }),
    );
    await flush();
    const first = FakeWebSocket.instances[0];
    act(() => first.close());
    expect(result.current).toBe("polling");
    act(() => vi.advanceTimersByTime(999));
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    await flush();
    expect(FakeWebSocket.instances).toHaveLength(2);

    const second = FakeWebSocket.instances[1];
    act(() => second.close());
    act(() => vi.advanceTimersByTime(1999));
    expect(FakeWebSocket.instances).toHaveLength(2);
    act(() => vi.advanceTimersByTime(1));
    await flush();
    expect(FakeWebSocket.instances).toHaveLength(3);

    const third = FakeWebSocket.instances[2];
    act(() => third.close());
    act(() => vi.advanceTimersByTime(3999));
    expect(FakeWebSocket.instances).toHaveLength(3);
    act(() => vi.advanceTimersByTime(1));
    await flush();
    expect(FakeWebSocket.instances).toHaveLength(4);

    const fourth = FakeWebSocket.instances[3];
    act(() => fourth.open());
    act(() => {
      fourth.message({ type: "subscribed", channel: "/ws/vendor" });
      vi.advanceTimersByTime(50);
    });
    expect(result.current).toBe("live");
    act(() => fourth.close());
    act(() => vi.advanceTimersByTime(999));
    expect(FakeWebSocket.instances).toHaveLength(4);
    act(() => vi.advanceTimersByTime(1));
    await flush();
    expect(FakeWebSocket.instances).toHaveLength(5);
  });

  it("closes on hide and resyncs once on visibility restoration", async () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useLiveChannel({ channel: "/ws/vendor", onMessage }),
    );
    await flush();
    const first = FakeWebSocket.instances[0];
    act(() => first.open());
    act(() => {
      first.message({ type: "subscribed", channel: "/ws/vendor" });
      vi.advanceTimersByTime(50);
    });
    expect(result.current).toBe("live");

    setDocumentHidden(true);
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(first.readyState).toBe(FakeWebSocket.CLOSED);
    expect(result.current).toBe("polling");
    act(() => vi.advanceTimersByTime(15_000));
    expect(FakeWebSocket.instances).toHaveLength(1);

    setDocumentHidden(false);
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    await flush();
    expect(FakeWebSocket.instances).toHaveLength(2);
    const second = FakeWebSocket.instances[1];
    act(() => second.open());
    act(() => {
      second.message({ type: "subscribed", channel: "/ws/vendor" });
      vi.advanceTimersByTime(50);
    });
    expect(result.current).toBe("live");
    expect(onMessage).toHaveBeenCalledTimes(2);
  });

  it("does not connect when disabled and cleans up StrictMode generations", async () => {
    const disabled = renderHook(() =>
      useLiveChannel({
        channel: "/ws/vendor",
        onMessage: vi.fn(),
        enabled: false,
      }),
    );
    await flush();
    expect(disabled.result.current).toBe("polling");
    expect(FakeWebSocket.instances).toHaveLength(0);

    function Live() {
      useLiveChannel({ channel: "/ws/vendor", onMessage: vi.fn() });
      return null;
    }
    const view = renderWithProviders(
      <StrictMode>
        <Live />
      </StrictMode>,
    );
    await flush();
    expect(FakeWebSocket.instances).toHaveLength(1);
    view.unmount();
    expect(FakeWebSocket.instances[0].readyState).toBe(FakeWebSocket.CLOSED);
  });
});
