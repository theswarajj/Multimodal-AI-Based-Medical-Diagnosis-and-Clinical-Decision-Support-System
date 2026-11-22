import React from 'react';
import { motion } from 'framer-motion';
import { ClinicalLogo } from './ClinicalLogo';
import { Cpu, ShieldCheck, Activity, Layers, Sparkles } from 'lucide-react';

export interface AIEngineLoadingSceneProps {
  stage?: string;
  progress?: number;
  queuePosition?: number;
  streamedText?: string;
  isModal?: boolean;
  onCancel?: () => void;
  className?: string;
}

export const AIEngineLoadingScene: React.FC<AIEngineLoadingSceneProps> = ({
  stage = 'Neural Network Inference in Progress',
  progress = 45,
  queuePosition = 0,
  streamedText = '',
  isModal = false,
  onCancel,
  className = '',
}) => {
  const content = (
    <div className="w-full flex flex-col items-center text-center space-y-6">
      {/* Central Animated Looping Logo & Ambient Orbital Rings */}
      <div className="relative flex items-center justify-center p-6">
        {/* Soft Ambient Radial Blur */}
        <div className="absolute w-44 h-44 bg-cardinal/15 rounded-full blur-2xl pointer-events-none animate-pulse" />

        {/* Outer Rotating Optical Tick Ring */}
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 18, repeat: Infinity, ease: 'linear' }}
          className="absolute w-36 h-36 rounded-full border border-dashed border-cardinal/30 pointer-events-none"
        />

        {/* Mid Concentric Ring with slow counter-rotation */}
        <motion.div
          animate={{ rotate: -360 }}
          transition={{ duration: 24, repeat: Infinity, ease: 'linear' }}
          className="absolute w-28 h-28 rounded-full border border-hairline pointer-events-none"
        />

        {/* The Signature ClinicalLens Reticle & ECG Pulse in Continuous Loop */}
        <div className="relative z-10 bg-porcelain p-3.5 rounded-full border border-hairline shadow-panel">
          <ClinicalLogo size="lg" mode="loop" />
        </div>
      </div>

      {/* Primary Status & Heading */}
      <div className="space-y-1.5 max-w-lg">
        <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-blush border border-cardinal/20 text-cardinal text-[11px] font-semibold uppercase tracking-wider mb-1">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Multimodal AI Diagnostic Engine</span>
        </div>
        <h3 className="text-lg sm:text-xl font-heading font-bold text-graphite tracking-tight">
          {stage || 'Processing Clinical Scans'}
        </h3>
        <p className="text-xs text-graphite-muted max-w-md mx-auto leading-relaxed">
          Running localized CNN classifiers and MedGemma language synthesis through our hardware queue.
        </p>
      </div>

      {/* Progress Bar with Cardinal Pulse Thread */}
      <div className="w-full max-w-md space-y-2">
        <div className="flex items-center justify-between text-[11px] font-mono text-graphite-subtle">
          <span className="flex items-center gap-1.5 font-medium text-graphite">
            <Activity className="w-3.5 h-3.5 text-cardinal animate-spin" />
            <span>Execution Stage</span>
          </span>
          <span className="font-semibold text-cardinal">{Math.min(100, Math.max(0, Math.round(progress)))}%</span>
        </div>

        <div className="w-full h-2 bg-snow rounded-full overflow-hidden border border-hairline relative">
          <motion.div
            className="h-full bg-cardinal rounded-full"
            initial={{ width: '15%' }}
            animate={{ width: `${Math.min(100, Math.max(10, progress))}%` }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          />
          {/* Subtle scanning highlight across the progress bar */}
          <motion.div
            className="absolute top-0 bottom-0 w-12 bg-white/40 skew-x-12"
            animate={{ left: ['-10%', '110%'] }}
            transition={{ repeat: Infinity, duration: 1.8, ease: 'easeInOut' }}
          />
        </div>
      </div>

      {/* Hardware & Single-Worker Queue Telemetry */}
      <div className="flex flex-wrap items-center justify-center gap-2 pt-1 text-[11px]">
        {queuePosition > 0 && (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-porcelain border border-cardinal/40 text-cardinal font-mono font-semibold shadow-subtle">
            Queue Priority: #{queuePosition}
          </span>
        )}
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-snow border border-hairline text-graphite-muted font-mono">
          <Cpu className="w-3.5 h-3.5 text-graphite" />
          <span>Single-Worker GPU Queue (4 GB VRAM Safe)</span>
        </span>
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-50 border border-emerald-200/60 text-emerald-800 font-medium">
          <ShieldCheck className="w-3.5 h-3.5 text-[#1F7A5C]" />
          <span>100% Local Inference</span>
        </span>
      </div>

      {/* Live Token Streaming Output (if MedGemma text is arriving) */}
      {streamedText && (
        <div className="w-full max-w-lg mt-3 p-3.5 rounded-[8px] bg-snow border border-hairline text-left">
          <div className="flex items-center justify-between text-[10px] text-graphite-muted uppercase tracking-wider font-semibold mb-1.5">
            <span>MedGemma Live Stream</span>
            <span className="w-1.5 h-1.5 rounded-full bg-cardinal animate-ping" />
          </div>
          <p className="text-xs font-mono text-graphite line-clamp-3 leading-relaxed whitespace-pre-wrap">
            {streamedText}
          </p>
        </div>
      )}
    </div>
  );

  if (isModal) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-graphite/40 backdrop-blur-sm">
        <div className="bg-porcelain border border-hairline rounded-[16px] p-8 max-w-lg w-full shadow-modal relative">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className={`p-6 sm:p-8 bg-porcelain border border-hairline rounded-[12px] shadow-panel ${className}`}>
      {content}
    </div>
  );
};
