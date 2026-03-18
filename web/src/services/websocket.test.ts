import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { VoiceAssistantClient } from './websocket';
import type { ConnectionState, ConnectionMetadata, WebsocketMessage } from './websocket';

// --- Mock WebSocket ---

type WSHandler = ((event: unknown) => void) | null;

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  binaryType = '';
  onopen: WSHandler = null;
  onclose: WSHandler = null;
  onmessage: WSHandler = null;
  onerror: WSHandler = null;

  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED;
    setTimeout(() => this.onclose?.({ code: 1000, reason: '' }), 0);
  });

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({});
  }

  simulateMessage(data: string) {
    this.onmessage?.({ data });
  }

  simulateClose(code = 1006, reason = '') {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason });
  }

  simulateError() {
    this.onerror?.({});
  }
}

const wsInstances: MockWebSocket[] = [];

function latestWs(): MockWebSocket {
  return wsInstances[wsInstances.length - 1];
}

vi.stubGlobal(
  'WebSocket',
  class extends MockWebSocket {
    constructor() {
      super();
      wsInstances.push(this);
    }
  },
);

vi.stubGlobal('AudioContext', vi.fn());

// --- Tests ---

describe('VoiceAssistantClient', () => {
  let client: VoiceAssistantClient;
  let stateChanges: Array<{ state: ConnectionState; metadata?: ConnectionMetadata }>;
  let messages: WebsocketMessage[];

  beforeEach(() => {
    vi.useFakeTimers();
    wsInstances.length = 0;
    stateChanges = [];
    messages = [];

    client = new VoiceAssistantClient('test-session', 'localhost:8000');
    client.connect(
      (msg) => messages.push(msg),
      () => {}, // onBinaryMessage — not tested here
      undefined,
      (state, metadata) => stateChanges.push({ state, metadata }),
    );
  });

  afterEach(() => {
    client.disconnect();
    vi.useRealTimers();
  });

  describe('connection state machine', () => {
    it('transitions idle → connecting on connect()', () => {
      expect(stateChanges[0].state).toBe('connecting');
    });

    it('transitions connecting → connected on open', () => {
      latestWs().simulateOpen();
      expect(stateChanges.at(-1)!.state).toBe('connected');
    });

    it('transitions connected → reconnecting on close', () => {
      latestWs().simulateOpen();
      latestWs().simulateClose(1006);
      expect(stateChanges.at(-1)!.state).toBe('reconnecting');
    });

    it('transitions to failed after max attempts', () => {
      latestWs().simulateOpen();

      for (let i = 0; i < 10; i++) {
        latestWs().simulateClose(1006);
        vi.advanceTimersByTime(30_000);
      }

      const failed = stateChanges.find((s) => s.state === 'failed');
      expect(failed).toBeDefined();
      expect(failed!.metadata?.attempt).toBe(10);
    });
  });

  describe('exponential backoff', () => {
    it('first retry delay is ~1s', () => {
      latestWs().simulateOpen();
      latestWs().simulateClose(1006);

      const reconnecting = stateChanges.find((s) => s.state === 'reconnecting');
      expect(reconnecting!.metadata!.nextRetryIn).toBe(1000);
    });

    it('second retry delay is ~1.5s', () => {
      latestWs().simulateOpen();
      latestWs().simulateClose(1006);
      vi.advanceTimersByTime(1000);
      latestWs().simulateClose(1006);

      const attempts = stateChanges.filter((s) => s.state === 'reconnecting');
      expect(attempts[1].metadata!.nextRetryIn).toBe(1500);
    });

    it('delay is capped at 30s', () => {
      latestWs().simulateOpen();

      for (let i = 0; i < 9; i++) {
        latestWs().simulateClose(1006);
        vi.advanceTimersByTime(30_000);
      }

      const attempts = stateChanges.filter((s) => s.state === 'reconnecting');
      const lastDelay = attempts.at(-1)!.metadata!.nextRetryIn!;
      expect(lastDelay).toBeLessThanOrEqual(30_000);
    });
  });

  describe('manual reconnect', () => {
    it('resets attempt counter', () => {
      latestWs().simulateOpen();
      latestWs().simulateClose(1006);
      vi.advanceTimersByTime(1000);
      latestWs().simulateClose(1006);

      client.reconnect();
      latestWs().simulateOpen();
      latestWs().simulateClose(1006);

      const lastReconnecting = stateChanges.filter((s) => s.state === 'reconnecting').at(-1)!;
      expect(lastReconnecting.metadata!.attempt).toBe(1);
    });
  });

  describe('heartbeat', () => {
    it('sends ping after 30s interval', () => {
      latestWs().simulateOpen();
      latestWs().send.mockClear();

      vi.advanceTimersByTime(30_000);

      expect(latestWs().send).toHaveBeenCalledTimes(1);
      const sent = JSON.parse(latestWs().send.mock.calls[0][0]);
      expect(sent.type).toBe('signal');
      expect(sent.content).toBe('ping');
      expect(sent.metadata.timestamp).toBeTypeOf('number');
    });

    it('does not send ping immediately on connect', () => {
      latestWs().simulateOpen();
      latestWs().send.mockClear();

      vi.advanceTimersByTime(1000);
      expect(latestWs().send).not.toHaveBeenCalled();
    });

    it('clears timeout on pong', () => {
      latestWs().simulateOpen();
      vi.advanceTimersByTime(30_000);

      const pingMsg = JSON.parse(latestWs().send.mock.calls[0][0]);

      latestWs().simulateMessage(
        JSON.stringify({
          type: 'signal',
          content: 'pong',
          is_user: false,
          is_final: false,
          metadata: { timestamp: pingMsg.metadata.timestamp },
        }),
      );

      vi.advanceTimersByTime(5000);
      expect(stateChanges.at(-1)!.state).toBe('connected');
    });

    it('triggers reconnect on heartbeat timeout', () => {
      latestWs().simulateOpen();
      vi.advanceTimersByTime(30_000);

      vi.advanceTimersByTime(5000);
      latestWs().simulateClose(1005);

      expect(stateChanges.at(-1)!.state).toBe('reconnecting');
    });
  });

  describe('error type detection', () => {
    it('detects network error on code 1006', () => {
      latestWs().simulateOpen();
      latestWs().simulateClose(1006);

      const meta = stateChanges.find((s) => s.state === 'reconnecting')!.metadata!;
      expect(meta.errorType).toBe('network');
    });

    it('detects server error on code 1011', () => {
      latestWs().simulateOpen();
      latestWs().simulateClose(1011);

      const meta = stateChanges.find((s) => s.state === 'reconnecting')!.metadata!;
      expect(meta.errorType).toBe('server');
    });

    it('uses onerror info over close code', () => {
      latestWs().simulateOpen();
      latestWs().simulateError();
      latestWs().simulateClose(1000);

      const meta = stateChanges.find((s) => s.state === 'reconnecting')!.metadata!;
      expect(meta.errorType).toBe('network');
    });
  });

  describe('message forwarding', () => {
    it('forwards non-pong messages to callback', () => {
      latestWs().simulateOpen();
      latestWs().simulateMessage(
        JSON.stringify({
          type: 'text',
          content: 'hello',
          is_user: false,
          is_final: true,
          metadata: {},
        }),
      );

      expect(messages).toHaveLength(1);
      expect(messages[0].content).toBe('hello');
    });

    it('does not forward pong to callback', () => {
      latestWs().simulateOpen();
      latestWs().simulateMessage(
        JSON.stringify({
          type: 'signal',
          content: 'pong',
          is_user: false,
          is_final: false,
          metadata: { timestamp: 123 },
        }),
      );

      expect(messages).toHaveLength(0);
    });
  });

  describe('disconnect', () => {
    it('prevents auto-reconnect after disconnect()', () => {
      latestWs().simulateOpen();
      client.disconnect();

      const hasReconnecting = stateChanges.some((s) => s.state === 'reconnecting');
      expect(hasReconnecting).toBe(false);
    });

    it('stops heartbeat on disconnect', () => {
      latestWs().simulateOpen();
      client.disconnect();
      latestWs().send.mockClear();

      vi.advanceTimersByTime(30_000);
      expect(latestWs().send).not.toHaveBeenCalled();
    });
  });

  describe('connection timeout', () => {
    it('closes socket after 10s if still connecting', () => {
      vi.advanceTimersByTime(10_000);
      expect(latestWs().close).toHaveBeenCalled();
    });
  });
});
