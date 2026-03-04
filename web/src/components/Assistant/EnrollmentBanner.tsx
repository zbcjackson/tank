import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { UserPlus, X, Mic, Check, Loader2 } from 'lucide-react';

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
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="mx-6 mt-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl px-4 py-3 flex items-center gap-3"
        >
          <UserPlus size={18} className="text-amber-600 dark:text-amber-400 shrink-0" />
          <p className="text-sm text-amber-700 dark:text-amber-300 flex-1">
            未识别的说话者。
            <button
              onClick={() => setShowModal(true)}
              className="ml-1 underline font-semibold hover:text-amber-900 dark:hover:text-amber-100 transition-colors"
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

  // Resume main audio capture when modal unmounts
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
      // Pause main audio capture so enrollment audio doesn't go to Brain
      pauseAudioCapture();

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1 },
      });
      streamRef.current = stream;

      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      // Reuse the same AudioWorklet processor as the main app
      await audioContext.audioWorklet.addModule('/audio-processor.js');

      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      const workletNode = new AudioWorkletNode(audioContext, 'audio-capture-processor');
      workletNodeRef.current = workletNode;

      // Disable VAD — collect all audio frames for enrollment
      workletNode.port.postMessage({
        type: 'vad-config',
        threshold: 0, // treat everything as speech so all frames are emitted
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

        // Merge Int16 chunks into a single blob
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="bg-white dark:bg-zinc-900 rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b dark:border-zinc-800">
          <h3 className="text-lg font-bold dark:text-white">录制声纹</h3>
          <button
            onClick={handleClose}
            className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors"
          >
            <X size={20} className="text-slate-500" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {state === 'idle' && (
            <>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                点击录制按钮，朗读任意内容 5 秒钟。系统将记录您的声纹特征。
              </p>
              <button
                onClick={startRecording}
                className="w-full flex items-center justify-center gap-2 bg-primary text-white py-3 rounded-xl font-semibold hover:bg-primary/90 transition-colors"
              >
                <Mic size={20} />
                开始录制
              </button>
            </>
          )}

          {state === 'recording' && (
            <div className="text-center space-y-4">
              <div className="w-20 h-20 mx-auto bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center animate-pulse">
                <Mic size={32} className="text-red-500" />
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                正在录制... 请朗读任意内容
              </p>
              <p className="text-3xl font-bold text-red-500">{countdown}s</p>
            </div>
          )}

          {state === 'recorded' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
                <Check size={20} />
                <span className="text-sm font-medium">录制完成</span>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  您的名字
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="输入您的名字..."
                  className="w-full bg-slate-50 dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-primary dark:text-white"
                  autoFocus
                />
              </div>
              <button
                onClick={submitEnrollment}
                disabled={!name.trim()}
                className="w-full flex items-center justify-center gap-2 bg-primary text-white py-3 rounded-xl font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                保存声纹
              </button>
            </div>
          )}

          {state === 'submitting' && (
            <div className="text-center space-y-3">
              <Loader2 size={32} className="mx-auto text-primary animate-spin" />
              <p className="text-sm text-slate-600 dark:text-slate-400">正在保存...</p>
            </div>
          )}

          {state === 'done' && (
            <div className="text-center space-y-3">
              <div className="w-16 h-16 mx-auto bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center">
                <Check size={32} className="text-green-500" />
              </div>
              <p className="text-sm font-medium text-green-600 dark:text-green-400">
                声纹注册成功
              </p>
            </div>
          )}

          {state === 'error' && (
            <div className="space-y-4">
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
              <button
                onClick={() => {
                  setState('idle');
                  setError('');
                  setAudioBlob(null);
                }}
                className="w-full bg-slate-100 dark:bg-zinc-800 py-3 rounded-xl font-semibold text-sm hover:bg-slate-200 dark:hover:bg-zinc-700 transition-colors dark:text-white"
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
