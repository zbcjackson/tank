import { motion } from 'framer-motion';

interface WaveformProps {
  active: boolean;
  variant?: 'primary' | 'white';
}

export const Waveform = ({ active, variant = 'primary' }: WaveformProps) => {
  return (
    <div className="flex items-center justify-center gap-1.5 h-24">
      {[...Array(24)].map((_, i) => (
        <motion.div
          key={i}
          className={`w-2 rounded-full ${variant === 'white' ? 'bg-white' : 'bg-primary'}`}
          animate={{
            height: active ? [20, Math.random() * 80 + 20, 20] : 10,
            opacity: active ? 1 : 0.4
          }}
          transition={{
            repeat: Infinity,
            duration: 0.5 + Math.random() * 0.5,
            ease: "easeInOut"
          }}
        />
      ))}
    </div>
  );
};
