import { useRef, useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';

const BAR_COUNT = 96;

interface WaveformProps {
  active: boolean;
  variant?: 'primary' | 'white';
  getAnalyserNode?: () => AnalyserNode | null;
}

export const Waveform = ({ active, variant = 'primary', getAnalyserNode }: WaveformProps) => {
  const [barHeights, setBarHeights] = useState<number[]>(() => new Array(BAR_COUNT).fill(2));
  const rafRef = useRef<number>(0);
  const dataArrayRef = useRef<Uint8Array | null>(null);

  const animate = useCallback(() => {
    const analyser = getAnalyserNode?.();
    if (!analyser) {
      rafRef.current = requestAnimationFrame(animate);
      return;
    }

    if (!dataArrayRef.current || dataArrayRef.current.length !== analyser.frequencyBinCount) {
      dataArrayRef.current = new Uint8Array(analyser.frequencyBinCount);
    }

    analyser.getByteFrequencyData(dataArrayRef.current);

    const data = dataArrayRef.current;
    const binCount = data.length; // 512 bins (fftSize=1024), covering 0-12kHz
    const step = Math.max(1, Math.floor(binCount / BAR_COUNT));

    const heights = new Array(BAR_COUNT);
    for (let i = 0; i < BAR_COUNT; i++) {
      const startBin = i * step;
      let max = 0;
      for (let j = startBin; j < startBin + step && j < binCount; j++) {
        if (data[j] > max) max = data[j];
      }
      // Power curve to widen dynamic range
      const normalized = max / 255;
      const boosted = Math.pow(normalized, 0.85);
      // Min height 2px so silent bars are barely visible, max 100px
      heights[i] = 2 + boosted * 98;
    }

    setBarHeights(heights);
    rafRef.current = requestAnimationFrame(animate);
  }, [getAnalyserNode]);

  useEffect(() => {
    if (active && getAnalyserNode) {
      rafRef.current = requestAnimationFrame(animate);
      return () => cancelAnimationFrame(rafRef.current);
    }
    setBarHeights(new Array(BAR_COUNT).fill(2));
  }, [active, getAnalyserNode, animate]);

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
