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
      <div className={`px-5 py-3 rounded-2xl text-[15px] leading-relaxed shadow-sm transition-all ${role === 'user' ? 'bg-primary text-white rounded-tr-none' : 'bg-white dark:bg-zinc-900 border dark:border-zinc-800 rounded-tl-none text-slate-800 dark:text-slate-200'}`}>
        {step.content}
      </div>
    );
  }

  if (step.type === 'thinking') {
    return (
      <div className="flex flex-col gap-1 w-full max-w-2xl">
        <div className="px-5 py-3 rounded-2xl bg-white/50 dark:bg-zinc-900/50 text-[13px] text-slate-500 italic border border-slate-200 dark:border-zinc-800 shadow-sm leading-relaxed rounded-tl-none">
          <div className="flex items-center gap-2 mb-1.5 opacity-60 not-italic">
            <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 4, ease: "linear" }}>
                <Cpu size={14} className="text-primary" />
            </motion.div>
            <span className="text-[10px] font-black uppercase tracking-widest">Internal Thought</span>
          </div>
          {step.content}
        </div>
      </div>
    );
  }

  if (step.type === 'tool') {
    return (
      <div className="flex flex-col gap-1.5 w-full max-w-2xl">
        <div className="flex flex-col gap-2 p-1 bg-white dark:bg-zinc-900 border dark:border-zinc-800 rounded-2xl shadow-sm rounded-tl-none overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b dark:border-zinc-800 bg-slate-50 dark:bg-zinc-800/50">
                <Wrench size={14} className="text-green-500" />
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Tool Execution</span>
            </div>
            <div className="p-3 pt-1 space-y-2">
                <div className="text-xs font-mono bg-zinc-950 text-zinc-300 p-3 rounded-xl border border-zinc-800 shadow-inner">
                    <span className="text-primary-foreground/50 mr-2">$</span>
                    <span className="text-blue-400">{step.content.name}</span>
                    <span className="text-zinc-500"> --args </span>
                    <span className="text-orange-300">{JSON.stringify(step.content.arguments)}</span>
                </div>
                {step.content.result && (
                  <div className="text-[11px] font-mono bg-zinc-50 dark:bg-black/40 p-3 rounded-xl border dark:border-zinc-800 text-zinc-500 max-h-48 overflow-y-auto">
                     <div className="flex justify-between mb-1 opacity-50">
                        <span className="font-bold uppercase text-[9px]">Output</span>
                        <span className="text-[9px]">Success</span>
                     </div>
                     {typeof step.content.result === 'string' ? step.content.result : JSON.stringify(step.content.result)}
                  </div>
                )}
            </div>
        </div>
      </div>
    );
  }

  if (step.type === 'weather') {
    return <WeatherCard data={step.content as WeatherData} />;
  }

  return null;
};
