import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { UserPlus, X, Mic, Check, Loader2 } from 'lucide-react';

const RECORDING_PULSE_ANIMATE = { scale: [1, 1.2, 1] };
const RECORDING_PULSE_TRANSITION = { repeat: Infinity, duration: 1.5 };
const MODAL_INITIAL = { scale: 0.96, opacity: 0 };
const MODAL_ANIMATE = { scale: 1, opacity: 1 };
const MODAL_TRANSITION = { duration: 0.2 };
const BANNER_INITIAL = { opacity: 0, y: -10 };
const BANNER_ANIMATE = { opacity: 1, y: 0 };
const BANNER_EXIT = { opacity: 0, y: -10 };

interface EnrollmentBannerProps {
  speaker: string | undefined;
  onEnrollComplete: () => void;
  pauseAudioCapture: () => void;
  resumeAudioCapture: () => void;
}

export const EnrollmentBanner = ({
  speaker,
  onEnrollComplete,
  pauseAudioCapture,
  resumeAudioCapture,
}: EnrollmentBannerProps) => {
  const [showModal, setShowModal] = useState(false);

  if (speaker && speaker !== 'Unknown') return null;

  return (
    <>
      <AnimatePresence>
        <motion.div
          initial={BANNER_INITIAL}
          animate={BANNER_ANIMATE}
          exit={BANNER_EXIT}
          className="mx-6 mt-2 bg-amber-500/5 border border-amber-500/10 rounded-xl px-4 py-3 flex items-center gap-3"
        >
          <UserPlus size={16} className="text-amber-500/60 shrink-0" />
          <p className="text-[13px] text-text-secondary flex-1">
            未识别的说话者。
            <button
              onClick={() => setShowModal(true)}
              className="ml-1 underline underline-offset-2 font-medium text-amber-400 hover:text-amber-300 transition-colors"
            >
              录制声纹
            </button>
          </p>
        </motion.div>
      </AnimatePresence>

      {showModal && (
        <EnrollmentModal
          onClose={() => setShowModal(false)}
          onComplete={() => {
            setShowModal(false);
            onEnrollComplete();
          }}
          pauseAudioCapture={pauseAudioCapture}
          resumeAudioCapture={resumeAudioCapture}
        />
      )}
    </>
  );
};

interface EnrollmentModalProps {
  onClose: () => void;
  onComplete: () => void;
  pauseAudioCapture: () => void;
  resumeAudioCapture: () => void;
}

type RecordingState = 'idle' | 'recording' | 'recorded' | 'submitting' | 'done' | 'error';

const EnrollmentModal = ({
  onClose,
  onComplete,
  pauseAudioCapture,
  resumeAudioCapture,
}: EnrollmentModalProps) => {
  const [state, setState] = useState<RecordingState>('idle');
  const [name, setName] = useState('');
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(5);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    return () => {
      resumeAudioCapture();
      cleanupRecording();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cleanupRecording = () => {
    workletNodeRef.current?.disconnect();
    sourceRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioContextRef.current?.close();
    workletNodeRef.current = null;
    sourceRef.current = null;
    streamRef.current = null;
    audioContextRef.current = null;
  };

  const startRecording = async () => {
    try {
      pauseAudioCapture();

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1 },
      });
      streamRef.current = stream;

      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      await audioContext.audioWorklet.addModule('/audio-processor.js');

      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      const workletNode = new AudioWorkletNode(audioContext, 'audio-capture-processor');
      workletNodeRef.current = workletNode;

      workletNode.port.postMessage({
        type: 'vad-config',
        threshold: 0,
        preRollSize: 0,
        hangoverMax: 999999,
      });

      const chunks: ArrayBuffer[] = [];
      workletNode.port.onmessage = (event: MessageEvent) => {
        if (event.data instanceof ArrayBuffer) {
          chunks.push(event.data);
        }
      };

      source.connect(workletNode);
      workletNode.connect(audioContext.destination);

      setState('recording');
      setCountdown(5);

      let remaining = 5;
      const countdownInterval = setInterval(() => {
        remaining--;
        setCountdown(remaining);
        if (remaining <= 0) clearInterval(countdownInterval);
      }, 1000);

      setTimeout(() => {
        clearInterval(countdownInterval);
        cleanupRecording();

        const totalLength = chunks.reduce((acc, c) => acc + c.byteLength, 0);
        const merged = new Uint8Array(totalLength);
        let offset = 0;
        for (const chunk of chunks) {
          merged.set(new Uint8Array(chunk), offset);
          offset += chunk.byteLength;
        }

        setAudioBlob(new Blob([merged.buffer], { type: 'application/octet-stream' }));
        setState('recorded');
      }, 5000);
    } catch (err) {
      console.error('Failed to start recording:', err);
      setError('无法访问麦克风');
      setState('error');
      resumeAudioCapture();
    }
  };

  const submitEnrollment = async () => {
    if (!audioBlob || !name.trim()) return;

    setState('submitting');
    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'enrollment.pcm');

      const res = await fetch(`/api/speakers/enroll?name=${encodeURIComponent(name.trim())}`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: 'Enrollment failed' }));
        throw new Error(data.detail || 'Enrollment failed');
      }

      setState('done');
      setTimeout(onComplete, 1000);
    } catch (err) {
      console.error('Enrollment failed:', err);
      setError(err instanceof Error ? err.message : '注册失败');
      setState('error');
    }
  };

  const handleClose = () => {
    cleanupRecording();
    resumeAudioCapture();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <motion.div
        initial={MODAL_INITIAL}
        animate={MODAL_ANIMATE}
        transition={MODAL_TRANSITION}
        className="bg-surface-raised border border-border-subtle rounded-2xl shadow-2xl shadow-black/50 w-full max-w-md mx-4 overflow-hidden"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle">
          <h3 className="text-sm font-semibold text-text-primary">录制声纹</h3>
          <button
            onClick={handleClose}
            className="p-1 rounded-lg hover:bg-white/5 transition-colors"
          >
            <X size={18} className="text-text-muted" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {state === 'idle' && (
            <>
              <p className="text-sm text-text-secondary">
                点击录制按钮，朗读任意内容 5 秒钟。系统将记录您的声纹特征。
              </p>
              <button
                onClick={startRecording}
                className="w-full flex items-center justify-center gap-2 bg-amber-500/10 text-amber-400 border border-amber-500/20 py-3 rounded-xl font-medium hover:bg-amber-500/15 transition-colors"
              >
                <Mic size={18} />
                开始录制
              </button>
            </>
          )}

          {state === 'recording' && (
            <div className="text-center space-y-4">
              <div className="w-16 h-16 mx-auto rounded-full flex items-center justify-center bg-red-500/10 border border-red-500/20">
                <motion.div
                  animate={RECORDING_PULSE_ANIMATE}
                  transition={RECORDING_PULSE_TRANSITION}
                >
                  <Mic size={24} className="text-red-400" />
                </motion.div>
              </div>
              <p className="text-sm text-text-secondary">正在录制... 请朗读任意内容</p>
              <p className="text-2xl font-mono font-semibold text-red-400">{countdown}s</p>
            </div>
          )}

          {state === 'recorded' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-emerald-400">
                <Check size={18} />
                <span className="text-sm font-medium">录制完成</span>
              </div>
              <div>
                <label className="block text-xs font-mono tracking-wider text-text-muted uppercase mb-2">
                  您的名字
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="输入您的名字..."
                  className="w-full bg-surface border border-border-subtle rounded-xl px-4 py-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-amber-500/30 transition-colors"
                  autoFocus
                />
              </div>
              <button
                onClick={submitEnrollment}
                disabled={!name.trim()}
                className="w-full flex items-center justify-center gap-2 bg-amber-500/10 text-amber-400 border border-amber-500/20 py-3 rounded-xl font-medium hover:bg-amber-500/15 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                保存声纹
              </button>
            </div>
          )}

          {state === 'submitting' && (
            <div className="text-center space-y-3 py-4">
              <Loader2 size={24} className="mx-auto text-amber-400 animate-spin" />
              <p className="text-sm text-text-secondary">正在保存...</p>
            </div>
          )}

          {state === 'done' && (
            <div className="text-center space-y-3 py-4">
              <div className="w-14 h-14 mx-auto rounded-full flex items-center justify-center bg-emerald-500/10 border border-emerald-500/20">
                <Check size={24} className="text-emerald-400" />
              </div>
              <p className="text-sm font-medium text-emerald-400">声纹注册成功</p>
            </div>
          )}

          {state === 'error' && (
            <div className="space-y-4">
              <p className="text-sm text-red-400">{error}</p>
              <button
                onClick={() => {
                  setState('idle');
                  setError('');
                  setAudioBlob(null);
                }}
                className="w-full bg-white/5 border border-border-subtle py-3 rounded-xl font-medium text-sm text-text-secondary hover:bg-white/8 transition-colors"
              >
                重试
              </button>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
};
