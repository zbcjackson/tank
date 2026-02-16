import { motion } from 'framer-motion';
import { Cpu, Wrench } from 'lucide-react';
import { WeatherCard } from './WeatherCard';
import type { WeatherData } from './WeatherCard';

export type StepType = 'thinking' | 'tool' | 'text' | 'weather';

export interface Step {
  id: string;
  type: StepType;
  content: any;
}

interface MessageStepProps {
  step: Step;
  role: 'user' | 'assistant';
}

export const MessageStep = ({ step, role }: MessageStepProps) => {
  if (step.type === 'text') {
    return (
      <div className={`px-5 py-3 rounded-2xl text-[15px] leading-relaxed shadow-sm ${role === 'user' ? 'bg-primary text-white rounded-tr-none' : 'bg-white dark:bg-zinc-900 border dark:border-zinc-800 rounded-tl-none'}`}>
        {step.content}
      </div>
    );
  }

  if (step.type === 'thinking') {
    return (
      <div className="flex items-center gap-2.5 text-xs text-slate-400 font-bold bg-slate-100 dark:bg-zinc-900/50 px-3 py-1.5 rounded-full mb-1">
        <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 2, ease: "linear" }}>
            <Cpu size={14} className="text-primary" />
        </motion.div>
        <span className="uppercase tracking-wider">Brain Thinking:</span>
        <span className="font-medium italic">{step.content}</span>
      </div>
    );
  }

  if (step.type === 'tool') {
    return (
      <div className="flex flex-col gap-2 my-1">
        <div className="flex items-center gap-3 text-xs font-mono bg-zinc-900 text-zinc-300 p-3 rounded-xl border border-zinc-700 shadow-lg">
          <div className="p-1.5 bg-zinc-800 rounded-lg text-green-400">
              <Wrench size={14} />
          </div>
          <div className="flex flex-col">
              <span className="text-[10px] text-zinc-500 font-bold uppercase">Executing Tool</span>
              <span>{step.content.name}({JSON.stringify(step.content.args)})</span>
          </div>
        </div>
        {step.content.result && (
          <div className="text-[10px] font-mono bg-zinc-100 dark:bg-zinc-800 p-2 rounded-lg border dark:border-zinc-700 text-zinc-500 max-h-32 overflow-y-auto">
             <span className="font-bold uppercase mr-2 text-zinc-400">Result:</span>
             {typeof step.content.result === 'string' ? step.content.result : JSON.stringify(step.content.result)}
          </div>
        )}
      </div>
    );
  }

  if (step.type === 'weather') {
    return <WeatherCard data={step.content as WeatherData} />;
  }

  return null;
};
