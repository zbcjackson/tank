export type MessageType = "signal" | "transcript" | "text" | "update" | "input";

export interface WebsocketMessage {
  type: MessageType;
  content: string;
  is_final: boolean;
  session_id?: string;
  metadata: Record<string, any>;
}

export class VoiceAssistantClient {
  private socket: WebSocket | null = null;
  private url: string;
  private audioContext: AudioContext | null = null;
  private nextStartTime: number = 0;

  constructor(sessionId: string, baseUrl: string = "localhost:8000") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.url = `${protocol}//${baseUrl}/ws/${sessionId}`;
  }

  connect(onMessage: (msg: WebsocketMessage) => void, onOpen?: () => void) {
    this.socket = new WebSocket(this.url);
    this.socket.binaryType = "arraybuffer";

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

  private async playAudioChunk(data: ArrayBuffer) {
    if (!this.audioContext) {
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: 24000,
      });
      this.nextStartTime = this.audioContext.currentTime;
    }

    try {
      // Data is Int16 PCM, need to convert to Float32 for Web Audio
      const int16Array = new Int16Array(data);
      const float32Array = new Float32Array(int16Array.length);
      for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
      }

      const buffer = this.audioContext.createBuffer(1, float32Array.length, 24000);
      buffer.getChannelData(0).set(float32Array);

      const source = this.audioContext.createBufferSource();
      source.buffer = buffer;
      source.connect(this.audioContext.destination);

      const startTime = Math.max(this.nextStartTime, this.audioContext.currentTime);
      source.start(startTime);
      this.nextStartTime = startTime + buffer.duration;
    } catch (e) {
      console.error("Error playing audio chunk:", e);
    }
  }

  sendAudio(data: Int16Array) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(data.buffer);
    }
  }

  sendMessage(type: MessageType, content: string, metadata: Record<string, any> = {}) {
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
    this.socket?.close();
    this.audioContext?.close();
  }
}
