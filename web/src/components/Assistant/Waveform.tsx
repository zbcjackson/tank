import { motion } from 'framer-motion';

const BARS = Array.from({ length: 24 }, () => ({
  height: Math.random() * 80 + 20,
  duration: 0.5 + Math.random() * 0.5,
}));

interface WaveformProps {
  active: boolean;
  variant?: 'primary' | 'white';
}

export const Waveform = ({ active, variant = 'primary' }: WaveformProps) => {
  return (
    <div className="flex items-center justify-center gap-1.5 h-24">
      {BARS.map((bar, i) => (
        <motion.div
          key={i}
          className={`w-2 rounded-full ${variant === 'white' ? 'bg-white' : 'bg-primary'}`}
          animate={{
            height: active ? [20, bar.height, 20] : 10,
            opacity: active ? 1 : 0.4
          }}
          transition={{
            repeat: Infinity,
            duration: bar.duration,
            ease: "easeInOut"
          }}
        />
      ))}
    </div>
  );
};
