export type MessageType = 'signal' | 'transcript' | 'text' | 'update' | 'input';

export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'failed';

export type ErrorType = 'network' | 'server' | 'timeout' | 'unknown';

export interface Capabilities {
  asr: boolean;
  tts: boolean;
  speaker_id: boolean;
}

export interface ConnectionMetadata {
  attempt?: number;
  maxAttempts?: number;
  nextRetryIn?: number; // milliseconds
  error?: string;
  errorType?: ErrorType;
}

export interface WebsocketMessage {
  type: MessageType;
  content: string;
  speaker?: string;
  is_user: boolean;
  is_final: boolean;
  msg_id?: string;
  session_id?: string;
  metadata: Record<string, unknown>;
}

export class VoiceAssistantClient {
  private socket: WebSocket | null = null;
  private url: string;

  // Reconnection state
  private connectionState: ConnectionState = 'idle';
  private reconnectAttempts: number = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly maxReconnectAttempts: number = 10;
  private readonly baseReconnectDelay: number = 1000; // 1s
  private readonly maxReconnectDelay: number = 30000; // 30s
  private readonly reconnectMultiplier: number = 1.5;
  private readonly connectionTimeout: number = 10000; // 10s
  private shouldReconnect: boolean = true;
  private onConnectionStateChange?: (state: ConnectionState, metadata?: ConnectionMetadata) => void;
  private onMessageCallback?: (msg: WebsocketMessage) => void;
  private onBinaryMessageCallback?: (data: ArrayBuffer) => void;
  private onOpenCallback?: () => void;
  private connectionTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
  private lastError: { type: ErrorType; message: string } | null = null;

  // Heartbeat state
  private readonly heartbeatInterval: number = 30000; // 30s
  private readonly heartbeatTimeout: number = 5000; // 5s
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private heartbeatTimeoutTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(sessionId: string, baseUrl: string = 'localhost:8000') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.url = `${protocol}//${baseUrl}/ws/${sessionId}`;
  }

  connect(
    onMessage: (msg: WebsocketMessage) => void,
    onBinaryMessage: (data: ArrayBuffer) => void,
    onOpen?: () => void,
    onConnectionStateChange?: (state: ConnectionState, metadata?: ConnectionMetadata) => void,
  ) {
    this.onMessageCallback = onMessage;
    this.onBinaryMessageCallback = onBinaryMessage;
    this.onOpenCallback = onOpen;
    this.onConnectionStateChange = onConnectionStateChange;
    this.shouldReconnect = true;

    this.attemptConnect();
  }

  private attemptConnect() {
    if (
      this.socket?.readyState === WebSocket.OPEN ||
      this.socket?.readyState === WebSocket.CONNECTING
    ) {
      return; // Already connected or connecting
    }

    this.updateConnectionState('connecting');
    const socket = new WebSocket(this.url);
    socket.binaryType = 'arraybuffer';
    this.socket = socket;

    // Set connection timeout
    this.startConnectionTimeout();

    socket.onopen = () => {
      if (this.socket !== socket) return; // Stale socket
      console.log('WebSocket connected');
      this.clearConnectionTimeout();
      this.reconnectAttempts = 0;
      this.lastError = null;
      this.updateConnectionState('connected');
      this.startHeartbeat();
      this.onOpenCallback?.();
    };

    socket.onmessage = (event) => {
      if (this.socket !== socket) return; // Stale socket
      if (typeof event.data === 'string') {
        const msg: WebsocketMessage = JSON.parse(event.data);

        // Handle pong response
        if (msg.type === 'signal' && msg.content === 'pong') {
          this.handlePong(msg);
          return;
        }

        this.onMessageCallback?.(msg);
      } else {
        this.onBinaryMessageCallback?.(event.data);
      }
    };

    socket.onclose = (event) => {
      if (this.socket !== socket) return; // Stale socket — ignore
      console.log('WebSocket disconnected', event.code, event.reason);
      this.clearConnectionTimeout();
      this.stopHeartbeat();

      // Use error from onerror if already set (more specific), otherwise detect from close code
      const errorInfo = this.lastError || this.detectErrorType(event);
      this.lastError = errorInfo;

      if (this.shouldReconnect && this.connectionState !== 'failed') {
        this.scheduleReconnect(errorInfo);
      }
    };

    socket.onerror = () => {
      if (this.socket !== socket) return; // Stale socket
      console.error('WebSocket error');
      // Only record the error — onclose always fires after onerror,
      // so reconnection is handled exclusively in onclose to avoid double-scheduling.
      this.lastError = { type: 'network' as ErrorType, message: 'Network connection failed' };
    };
  }

  sendAudio(data: Int16Array) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(data.buffer);
    }
  }

  sendMessage(type: MessageType, content: string, metadata: Record<string, unknown> = {}) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      const msg: Partial<WebsocketMessage> = {
        type,
        content,
        metadata,
      };
      this.socket.send(JSON.stringify(msg));
    }
  }

  sendInterrupt() {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: 'signal', content: 'interrupt', metadata: {} }));
    }
  }

  private startConnectionTimeout() {
    this.clearConnectionTimeout();
    this.connectionTimeoutTimer = setTimeout(() => {
      console.warn(`Connection timeout after ${this.connectionTimeout}ms`);
      this.lastError = { type: 'timeout' as ErrorType, message: 'Connection timeout' };

      // Close the socket — onclose will handle reconnection
      if (this.socket?.readyState === WebSocket.CONNECTING) {
        this.socket.close();
      }
    }, this.connectionTimeout);
  }

  private clearConnectionTimeout() {
    if (this.connectionTimeoutTimer) {
      clearTimeout(this.connectionTimeoutTimer);
      this.connectionTimeoutTimer = null;
    }
  }

  private detectErrorType(event: CloseEvent): { type: ErrorType; message: string } {
    // WebSocket close codes: https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent/code
    const code = event.code;
    const reason = event.reason || '';

    // Normal closure
    if (code === 1000) {
      return { type: 'unknown', message: 'Connection closed normally' };
    }

    // Server errors (1001-1015)
    if (code >= 1001 && code <= 1015) {
      if (code === 1001) return { type: 'server', message: 'Server is shutting down' };
      if (code === 1002) return { type: 'server', message: 'Protocol error' };
      if (code === 1003) return { type: 'server', message: 'Unsupported data type' };
      if (code === 1006) return { type: 'network', message: 'Connection lost abnormally' };
      if (code === 1007) return { type: 'server', message: 'Invalid message data' };
      if (code === 1008) return { type: 'server', message: 'Policy violation' };
      if (code === 1009) return { type: 'server', message: 'Message too large' };
      if (code === 1011) return { type: 'server', message: 'Server error' };
      if (code === 1012) return { type: 'server', message: 'Service restart' };
      if (code === 1013) return { type: 'server', message: 'Service overload' };
      if (code === 1014) return { type: 'server', message: 'Bad gateway' };
      if (code === 1015) return { type: 'network', message: 'TLS handshake failed' };
    }

    // Custom application codes (4000-4999)
    if (code >= 4000 && code <= 4999) {
      return { type: 'server', message: reason || 'Application error' };
    }

    // Network/unknown errors
    return { type: 'network', message: reason || 'Connection failed' };
  }

  private getErrorMessage(errorInfo: { type: ErrorType; message: string }): string {
    switch (errorInfo.type) {
      case 'network':
        return '网络连接失败，请检查网络设置';
      case 'server':
        return `服务器错误: ${errorInfo.message}`;
      case 'timeout':
        return '连接超时，请稍后重试';
      default:
        return errorInfo.message || '连接失败';
    }
  }

  private startHeartbeat() {
    this.stopHeartbeat();

    // First ping after one full interval — no immediate ping to avoid
    // racing with the backend's ready signal or slow startup.
    this.heartbeatTimer = setInterval(() => {
      this.sendPing();
    }, this.heartbeatInterval);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }

    if (this.heartbeatTimeoutTimer) {
      clearTimeout(this.heartbeatTimeoutTimer);
      this.heartbeatTimeoutTimer = null;
    }
  }

  private sendPing() {
    if (this.socket?.readyState !== WebSocket.OPEN) {
      return;
    }

    const timestamp = Date.now();
    this.sendMessage('signal', 'ping', { timestamp });

    // Set timeout for pong response
    this.heartbeatTimeoutTimer = setTimeout(() => {
      console.warn(`Heartbeat timeout: no pong within ${this.heartbeatTimeout}ms`);

      // Close the socket to trigger reconnection
      if (this.socket) {
        this.lastError = { type: 'timeout', message: 'Heartbeat timeout' };
        this.socket.close();
      }
    }, this.heartbeatTimeout);
  }

  private handlePong(msg: WebsocketMessage) {
    const pingTimestamp = msg.metadata?.timestamp as number;
    const roundTripTime = Date.now() - pingTimestamp;
    console.log(`Pong RTT: ${roundTripTime}ms`);

    if (this.heartbeatTimeoutTimer) {
      clearTimeout(this.heartbeatTimeoutTimer);
      this.heartbeatTimeoutTimer = null;
    }
  }

  private updateConnectionState(state: ConnectionState, metadata?: ConnectionMetadata) {
    this.connectionState = state;
    this.onConnectionStateChange?.(state, metadata);
  }

  private calculateBackoffDelay(attempt: number): number {
    const delay = this.baseReconnectDelay * Math.pow(this.reconnectMultiplier, attempt);
    return Math.min(delay, this.maxReconnectDelay);
  }

  private scheduleReconnect(errorInfo?: { type: ErrorType; message: string }) {
    // Clear any existing timer
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    // Check if we've exceeded max attempts
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      const error = errorInfo || this.lastError;
      this.updateConnectionState('failed', {
        attempt: this.reconnectAttempts,
        maxAttempts: this.maxReconnectAttempts,
        error: error ? this.getErrorMessage(error) : '达到最大重连次数',
        errorType: error?.type || 'unknown',
      });
      return;
    }

    const delay = this.calculateBackoffDelay(this.reconnectAttempts);
    this.reconnectAttempts++;

    const error = errorInfo || this.lastError;
    this.updateConnectionState('reconnecting', {
      attempt: this.reconnectAttempts,
      maxAttempts: this.maxReconnectAttempts,
      nextRetryIn: delay,
      error: error ? this.getErrorMessage(error) : undefined,
      errorType: error?.type || 'unknown',
    });

    console.log(
      `Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`,
    );

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.attemptConnect();
    }, delay);
  }

  reconnect() {
    // Public API for manual reconnect - resets counter
    console.log('Manual reconnect triggered');
    this.reconnectAttempts = 0;
    this.shouldReconnect = true;
    this.lastError = null; // Clear last error on manual reconnect

    // Clear all timers
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.clearConnectionTimeout();
    this.stopHeartbeat();

    // Close existing socket if any
    if (this.socket) {
      this.socket.onclose = null; // Prevent triggering auto-reconnect
      this.socket.onerror = null;
      this.socket.close();
      this.socket = null;
    }

    this.attemptConnect();
  }

  disconnect() {
    this.shouldReconnect = false; // Prevent auto-reconnect

    // Clear all timers
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.clearConnectionTimeout();
    this.stopHeartbeat();

    if (this.socket) {
      const socket = this.socket;
      this.socket = null;

      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'signal', content: 'disconnect', metadata: {} }));
        socket.close();
      } else if (socket.readyState === WebSocket.CONNECTING) {
        // Let the handshake finish, then close cleanly
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;
        socket.onopen = () => socket.close();
      }
    }
  }
}
