export type MessageType = "signal" | "transcript" | "text" | "update" | "input";

export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'failed';

export type ErrorType = 'network' | 'server' | 'timeout' | 'unknown';

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
  is_user: boolean;
  is_final: boolean;
  msg_id?: string;
  session_id?: string;
  metadata: Record<string, unknown>;
}

export class VoiceAssistantClient {
  private socket: WebSocket | null = null;
  private url: string;
  private audioContext: AudioContext | null = null;
  private analyserNode: AnalyserNode | null = null;
  private nextStartTime: number = 0;
  private onSpeakingChange?: (isSpeaking: boolean) => void;
  private speakingTimer: ReturnType<typeof setTimeout> | null = null;

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
  private onOpenCallback?: () => void;
  private connectionTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
  private lastError: { type: ErrorType; message: string } | null = null;

  constructor(sessionId: string, baseUrl: string = "localhost:8000") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.url = `${protocol}//${baseUrl}/ws/${sessionId}`;
  }

  connect(
    onMessage: (msg: WebsocketMessage) => void,
    onSpeakingChange?: (isSpeaking: boolean) => void,
    onOpen?: () => void,
    onConnectionStateChange?: (state: ConnectionState, metadata?: ConnectionMetadata) => void
  ) {
    this.onMessageCallback = onMessage;
    this.onSpeakingChange = onSpeakingChange;
    this.onOpenCallback = onOpen;
    this.onConnectionStateChange = onConnectionStateChange;
    this.shouldReconnect = true;

    this.attemptConnect();
  }

  private attemptConnect() {
    if (this.socket?.readyState === WebSocket.OPEN || this.socket?.readyState === WebSocket.CONNECTING) {
      return; // Already connected or connecting
    }

    this.updateConnectionState('connecting');
    this.socket = new WebSocket(this.url);
    this.socket.binaryType = "arraybuffer";

    // Set connection timeout
    this.startConnectionTimeout();

    this.socket.onopen = () => {
      console.log("WebSocket connected");
      this.clearConnectionTimeout();
      this.reconnectAttempts = 0; // Reset counter on successful connection
      this.lastError = null; // Clear last error
      this.updateConnectionState('connected');
      this.onOpenCallback?.();
    };

    this.socket.onmessage = (event) => {
      if (typeof event.data === "string") {
        const msg: WebsocketMessage = JSON.parse(event.data);
        this.onMessageCallback?.(msg);
      } else {
        // Handle binary audio chunk
        this.playAudioChunk(event.data);
      }
    };

    this.socket.onclose = (event) => {
      console.log("WebSocket disconnected", event.code, event.reason);
      this.clearConnectionTimeout();

      // Detect error type from close code
      const errorInfo = this.detectErrorType(event);
      this.lastError = errorInfo;

      // Only reconnect if it wasn't an intentional disconnect
      if (this.shouldReconnect && this.connectionState !== 'failed') {
        this.scheduleReconnect(errorInfo);
      }
    };

    this.socket.onerror = (error) => {
      console.error("WebSocket error:", error);
      this.clearConnectionTimeout();

      // Network error
      const errorInfo = { type: 'network' as ErrorType, message: 'Network connection failed' };
      this.lastError = errorInfo;

      // Trigger reconnection on error
      if (this.shouldReconnect && this.connectionState !== 'failed') {
        this.scheduleReconnect(errorInfo);
      }
    };
  }

  getAnalyserNode(): AnalyserNode | null {
    return this.analyserNode;
  }

  private ensureAudioContext() {
    if (!this.audioContext) {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.audioContext = new AudioCtx({ sampleRate: 24000 });
      this.nextStartTime = this.audioContext.currentTime;

      this.analyserNode = this.audioContext.createAnalyser();
      this.analyserNode.fftSize = 1024;
      this.analyserNode.smoothingTimeConstant = 0.7;
      this.analyserNode.minDecibels = -70;
      this.analyserNode.maxDecibels = -20;
      this.analyserNode.connect(this.audioContext.destination);
    }
  }

  private async playAudioChunk(data: ArrayBuffer) {
    this.ensureAudioContext();

    try {
      // Data is Int16 PCM, need to convert to Float32 for Web Audio
      const int16Array = new Int16Array(data);
      const float32Array = new Float32Array(int16Array.length);
      for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
      }

      const buffer = this.audioContext!.createBuffer(1, float32Array.length, 24000);
      buffer.getChannelData(0).set(float32Array);

      const source = this.audioContext!.createBufferSource();
      source.buffer = buffer;
      source.connect(this.analyserNode!);

      const startTime = Math.max(this.nextStartTime, this.audioContext!.currentTime);
      source.start(startTime);
      this.nextStartTime = startTime + buffer.duration;

      // Update speaking state
      if (this.onSpeakingChange) {
        this.onSpeakingChange(true);
        if (this.speakingTimer) clearTimeout(this.speakingTimer);

        // Set a timer to set speaking to false after the scheduled audio ends
        const delayMs = (this.nextStartTime - this.audioContext!.currentTime) * 1000;
        this.speakingTimer = setTimeout(() => {
          this.onSpeakingChange?.(false);
          this.speakingTimer = null;
        }, delayMs);
      }
    } catch (e) {
      console.error("Error playing audio chunk:", e);
    }
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

  stopSpeaking() {
    // Send interrupt signal to backend to stop TTS/LLM
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: 'signal', content: 'interrupt', metadata: {} }));
    }

    // Clear local audio playback by closing and nulling the AudioContext
    // Scheduled BufferSource nodes can't be cancelled individually,
    // so closing the context is the cleanest way to silence everything.
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
      this.analyserNode = null;
      this.nextStartTime = 0;
    }

    // Reset speaking state
    if (this.speakingTimer) {
      clearTimeout(this.speakingTimer);
      this.speakingTimer = null;
    }
    this.onSpeakingChange?.(false);
  }

  private startConnectionTimeout() {
    this.clearConnectionTimeout();
    this.connectionTimeoutTimer = setTimeout(() => {
      console.warn(`Connection timeout after ${this.connectionTimeout}ms`);

      // Close the socket if still connecting
      if (this.socket?.readyState === WebSocket.CONNECTING) {
        this.socket.close();
      }

      const errorInfo = { type: 'timeout' as ErrorType, message: 'Connection timeout' };
      this.lastError = errorInfo;

      // Trigger reconnection
      if (this.shouldReconnect && this.connectionState !== 'failed') {
        this.scheduleReconnect(errorInfo);
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
        errorType: error?.type || 'unknown'
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
      errorType: error?.type || 'unknown'
    });

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.attemptConnect();
    }, delay);
  }

  reconnect() {
    // Public API for manual reconnect - resets counter
    console.log("Manual reconnect triggered");
    this.reconnectAttempts = 0;
    this.shouldReconnect = true;
    this.lastError = null; // Clear last error on manual reconnect

    // Clear any existing timers
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.clearConnectionTimeout();

    // Close existing socket if any
    if (this.socket) {
      this.socket.onclose = null; // Prevent triggering auto-reconnect
      this.socket.onerror = null;
      this.socket.close();
      this.socket = null;
    }

    this.attemptConnect();
  }

  getConnectionState(): ConnectionState {
    return this.connectionState;
  }

  getConnectionMetadata(): ConnectionMetadata {
    if (this.connectionState === 'reconnecting' || this.connectionState === 'failed') {
      const error = this.lastError;
      return {
        attempt: this.reconnectAttempts,
        maxAttempts: this.maxReconnectAttempts,
        nextRetryIn: this.reconnectTimer ? this.calculateBackoffDelay(this.reconnectAttempts - 1) : undefined,
        error: error ? this.getErrorMessage(error) : undefined,
        errorType: error?.type || 'unknown'
      };
    }
    return {};
  }

  disconnect() {
    this.shouldReconnect = false; // Prevent auto-reconnect

    // Clear all timers
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.clearConnectionTimeout();

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
    this.audioContext?.close();
  }
}
