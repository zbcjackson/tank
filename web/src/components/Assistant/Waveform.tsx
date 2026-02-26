import { useRef, useEffect, useState } from 'react';
import { motion } from 'framer-motion';

const BAR_COUNT = 96;
const IDLE_HEIGHTS = new Array(BAR_COUNT).fill(2);

interface WaveformProps {
  active: boolean;
  variant?: 'primary' | 'white';
  getAnalyserNode?: () => AnalyserNode | null;
}

export const Waveform = ({ active, variant = 'primary', getAnalyserNode }: WaveformProps) => {
  const [liveHeights, setLiveHeights] = useState<number[]>(IDLE_HEIGHTS);
  const rafRef = useRef<number>(0);
  const dataArrayRef = useRef<Uint8Array | null>(null);
  const getAnalyserRef = useRef(getAnalyserNode);
  useEffect(() => { getAnalyserRef.current = getAnalyserNode; }, [getAnalyserNode]);

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
        const normalized = max / 255;
        const boosted = Math.pow(normalized, 0.85);
        heights[i] = 2 + boosted * 98;
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
  const colorClass = variant === 'white' ? 'bg-white' : 'bg-primary';

  return (
    <div className="flex items-center justify-center gap-[2px] h-24">
      {barHeights.map((height, i) => (
        <motion.div
          key={i}
          className={`w-1 rounded-full ${colorClass}`}
          animate={{
            height: active ? height : 2,
            opacity: active ? Math.max(0.3, height / 100) : 0.2,
          }}
          transition={{ duration: 0.06, ease: 'linear' }}
        />
      ))}
    </div>
  );
};
