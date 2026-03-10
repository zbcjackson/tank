import { motion } from 'framer-motion';
import { Sun, Cloud, Wind } from 'lucide-react';

export interface WeatherData {
  city: string;
  temp: string;
  condition: string;
  wind: string;
}

const CARD_BG_STYLE = {
  background: 'linear-gradient(135deg, rgba(212,160,84,0.08) 0%, rgba(212,160,84,0.02) 100%)',
};
const ICON_BG_STYLE = { background: 'rgba(212,160,84,0.08)' };
const CARD_INITIAL = { opacity: 0, y: 6 };
const CARD_ANIMATE = { opacity: 1, y: 0 };
const CARD_TRANSITION = { duration: 0.3 };

interface WeatherCardProps {
  data: WeatherData;
}

export const WeatherCard = ({ data }: WeatherCardProps) => (
  <motion.div
    initial={CARD_INITIAL}
    animate={CARD_ANIMATE}
    transition={CARD_TRANSITION}
    className="w-full max-w-sm my-2 rounded-2xl border border-border-subtle overflow-hidden"
    style={CARD_BG_STYLE}
  >
    <div className="p-5">
      <div className="flex justify-between items-start">
        <div>
          <p className="text-[11px] font-mono tracking-widest text-text-muted uppercase mb-1">
            Weather
          </p>
          <h3 className="text-lg font-semibold text-text-primary">{data.city}</h3>
          <p className="text-3xl font-semibold text-amber-400 mt-2">{data.temp}</p>
        </div>
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center"
          style={ICON_BG_STYLE}
        >
          <Sun size={24} className="text-amber-400/70" />
        </div>
      </div>

      <div className="flex gap-3 mt-5">
        <div className="flex items-center gap-1.5 text-[12px] text-text-secondary px-2.5 py-1.5 rounded-lg bg-white/3 border border-border-subtle">
          <Cloud size={13} className="text-text-muted" />
          {data.condition}
        </div>
        <div className="flex items-center gap-1.5 text-[12px] text-text-secondary px-2.5 py-1.5 rounded-lg bg-white/3 border border-border-subtle">
          <Wind size={13} className="text-text-muted" />
          {data.wind}
        </div>
      </div>
    </div>
  </motion.div>
);
