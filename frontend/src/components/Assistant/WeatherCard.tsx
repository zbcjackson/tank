import { motion } from 'framer-motion';
import { Sun, CloudRain, Wind } from 'lucide-react';

export interface WeatherData {
  city: string;
  temp: string;
  condition: string;
  wind: string;
}

interface WeatherCardProps {
  data: WeatherData;
}

export const WeatherCard = ({ data }: WeatherCardProps) => (
  <motion.div 
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    className="bg-gradient-to-br from-blue-500 to-blue-600 text-white p-5 rounded-3xl shadow-xl border border-white/20 my-3 w-full max-w-sm"
  >
    <div className="flex justify-between items-start">
      <div>
        <h3 className="text-xl font-bold">{data.city}</h3>
        <p className="text-5xl font-black mt-3">{data.temp}</p>
      </div>
      <div className="bg-white/20 p-3 rounded-2xl backdrop-blur-md">
        <Sun size={42} className="text-yellow-300" />
      </div>
    </div>
    <div className="flex gap-5 mt-6 text-sm font-medium opacity-90">
      <div className="flex items-center gap-2 bg-white/10 px-3 py-1.5 rounded-full"><CloudRain size={16}/> {data.condition}</div>
      <div className="flex items-center gap-2 bg-white/10 px-3 py-1.5 rounded-full"><Wind size={16}/> {data.wind}</div>
    </div>
  </motion.div>
);
