export type MessageType = "signal" | "transcript" | "text" | "update" | "input";

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

  constructor(sessionId: string, baseUrl: string = "localhost:8000") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.url = `${protocol}//${baseUrl}/ws/${sessionId}`;
  }

  connect(onMessage: (msg: WebsocketMessage) => void, onSpeakingChange?: (isSpeaking: boolean) => void, onOpen?: () => void) {
    this.socket = new WebSocket(this.url);
    this.socket.binaryType = "arraybuffer";
    this.onSpeakingChange = onSpeakingChange;

    this.socket.onopen = () => {
      console.log("WebSocket connected");
      onOpen?.();
    };

    this.socket.onmessage = (event) => {
      if (typeof event.data === "string") {
        const msg: WebsocketMessage = JSON.parse(event.data);
        onMessage(msg);
      } else {
        // Handle binary audio chunk
        this.playAudioChunk(event.data);
      }
    };

    this.socket.onclose = () => {
      console.log("WebSocket disconnected");
    };

    this.socket.onerror = (error) => {
      console.error("WebSocket error:", error);
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

  disconnect() {
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
