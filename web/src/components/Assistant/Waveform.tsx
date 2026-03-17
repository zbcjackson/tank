import { useRef, useEffect, useState } from 'react';
import { motion } from 'framer-motion';

const BAR_COUNT = 64;
const IDLE_HEIGHTS = new Array(BAR_COUNT).fill(1);
const BAR_TRANSITION = { duration: 0.06, ease: 'linear' as const };
const WAVEFORM_STYLE = { width: 200, height: 80 };

// Pre-compute per-bar static values (centerDist, envelope, active/idle opacities)
const BAR_CENTER_DISTS = new Array(BAR_COUNT);
const BAR_ENVELOPES = new Array(BAR_COUNT);
const BAR_ACTIVE_STYLES = new Array<React.CSSProperties>(BAR_COUNT);
const BAR_IDLE_STYLES = new Array<React.CSSProperties>(BAR_COUNT);
for (let i = 0; i < BAR_COUNT; i++) {
  const centerDist = Math.abs(i - BAR_COUNT / 2) / (BAR_COUNT / 2);
  BAR_CENTER_DISTS[i] = centerDist;
  BAR_ENVELOPES[i] = 1 - centerDist * centerDist * 0.6;
  const activeOpacity = Math.max(0.2, 1 - centerDist * 0.7);
  BAR_ACTIVE_STYLES[i] = { width: 2, background: `rgba(212, 160, 84, ${activeOpacity})` };
  BAR_IDLE_STYLES[i] = { width: 2, background: 'rgba(212, 160, 84, 0.1)' };
}

interface WaveformProps {
  active: boolean;
  getAnalyserNode?: () => AnalyserNode | null;
  rmsAmplitude?: number; // For Tauri mode: 0-1 amplitude from TTS chunks
}

export const Waveform = ({ active, getAnalyserNode, rmsAmplitude }: WaveformProps) => {
  const [liveHeights, setLiveHeights] = useState<number[]>(IDLE_HEIGHTS);
  const rafRef = useRef<number>(0);
  const dataArrayRef = useRef<Uint8Array | null>(null);
  const getAnalyserRef = useRef(getAnalyserNode);
  useEffect(() => {
    getAnalyserRef.current = getAnalyserNode;
  }, [getAnalyserNode]);

  // RMS-based waveform for Tauri mode (no AnalyserNode available)
  const rmsAmplitudeRef = useRef(rmsAmplitude);
  useEffect(() => {
    rmsAmplitudeRef.current = rmsAmplitude;
  }, [rmsAmplitude]);

  useEffect(() => {
    if (!active || getAnalyserNode || rmsAmplitude === undefined) return;

    let cancelled = false;

    const tick = () => {
      if (cancelled) return;

      const amp = Math.min(rmsAmplitudeRef.current ?? 0, 1);
      const heights = new Array(BAR_COUNT);
      for (let i = 0; i < BAR_COUNT; i++) {
        // Vary height per bar using envelope + slight pseudo-random jitter from position
        const jitter = 0.7 + 0.3 * Math.sin(i * 1.7 + amp * 20);
        heights[i] = 1 + amp * 60 * BAR_ENVELOPES[i] * jitter;
      }
      setLiveHeights(heights);
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
    };
  }, [active, getAnalyserNode, rmsAmplitude]);

  useEffect(() => {
    if (!active || !getAnalyserNode) return;

    let cancelled = false;

    const tick = () => {
      if (cancelled) return;

      const analyser = getAnalyserRef.current?.();
      if (!analyser) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      if (!dataArrayRef.current || dataArrayRef.current.length !== analyser.frequencyBinCount) {
        dataArrayRef.current = new Uint8Array(analyser.frequencyBinCount);
      }

      analyser.getByteFrequencyData(dataArrayRef.current);

      const data = dataArrayRef.current;
      const binCount = data.length;
      const step = Math.max(1, Math.floor(binCount / BAR_COUNT));

      const heights = new Array(BAR_COUNT);
      for (let i = 0; i < BAR_COUNT; i++) {
        const startBin = i * step;
        let max = 0;
        for (let j = startBin; j < startBin + step && j < binCount; j++) {
          if (data[j] > max) max = data[j];
        }
        const boosted = Math.pow(max / 255, 0.8) * BAR_ENVELOPES[i];
        heights[i] = 1 + boosted * 60;
      }

      setLiveHeights(heights);
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
    };
  }, [active, getAnalyserNode]);

  const barHeights = active ? liveHeights : IDLE_HEIGHTS;

  return (
    <div className="flex items-center justify-center gap-[1.5px]" style={WAVEFORM_STYLE}>
      {barHeights.map((height, i) => (
        <motion.div
          key={i}
          className="rounded-full"
          style={active ? BAR_ACTIVE_STYLES[i] : BAR_IDLE_STYLES[i]}
          animate={{ height: active ? height : 1 }}
          transition={BAR_TRANSITION}
        />
      ))}
    </div>
  );
};
