import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ClinicalLogo } from './ClinicalLogo';
import { ShieldCheck, Sparkles, CheckCircle2 } from 'lucide-react';

interface LoginIntroOverlayProps {
  name: string;
  role: 'doctor' | 'admin';
  onComplete: () => void;
}

export const LoginIntroOverlay: React.FC<LoginIntroOverlayProps> = ({
  name,
  role,
  onComplete,
}) => {
  // Format the greeting text cleanly
  const greetingText =
    role === 'doctor'
      ? name.toLowerCase().startsWith('dr')
        ? `Hello, ${name}`
        : `Hello, Dr. ${name}`
      : `Hello, Administrator ${name.replace(/administrator/i, '').trim() || ''}`.trim();

  // Typewriter state
  const [displayedText, setDisplayedText] = useState('');
  const [isTypingComplete, setIsTypingComplete] = useState(false);
  const [currentCycle, setCurrentCycle] = useState(1);

  // Typewriter writing animation
  useEffect(() => {
    let index = 0;
    const speed = 45; // ms per character for a deliberate, premium clinical feel
    const timer = setInterval(() => {
      index++;
      setDisplayedText(greetingText.slice(0, index));
      if (index >= greetingText.length) {
        clearInterval(timer);
        setIsTypingComplete(true);
      }
    }, speed);

    return () => clearInterval(timer);
  }, [greetingText]);

  // Track the 2 logo cycles
  useEffect(() => {
    if (!isTypingComplete) return;

    // Cycle 1 lasts 1.4s, then cycle 2 starts
    const cycleTimer = setTimeout(() => {
      setCurrentCycle(2);
    }, 1500);

    return () => clearTimeout(cycleTimer);
  }, [isTypingComplete]);

  const handleLogoCyclesDone = () => {
    // Smooth transition to portal
    setTimeout(() => {
      onComplete();
    }, 450);
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0, scale: 1.02, filter: 'blur(4px)' }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="fixed inset-0 z-[999] flex flex-col items-center justify-between p-8 bg-snow select-none cursor-default overflow-hidden"
      >
        {/* Subtle Ambient Radial Glows */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blush/60 rounded-full blur-3xl pointer-events-none -z-10" />
        <div className="absolute -top-32 right-1/4 w-[400px] h-[400px] bg-red-100/30 rounded-full blur-3xl pointer-events-none -z-10" />

        {/* Top Header Bar */}
        <div className="w-full max-w-4xl flex items-center justify-between text-xs text-graphite-muted">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cardinal animate-ping" />
            <span className="font-mono uppercase tracking-wider text-[11px] text-graphite font-semibold">
              ClinicalLens Secure Session
            </span>
          </div>

          <button
            onClick={onComplete}
            className="text-[11px] text-graphite-muted hover:text-cardinal transition-colors font-medium hover:underline px-2 py-1"
          >
            Skip intro
          </button>
        </div>

        {/* Centerpiece: Cinematic Greeting & 2-Cycle Repeating Animated Logo */}
        <div className="w-full max-w-2xl flex flex-col items-center text-center my-auto space-y-8">
          {/* Animated Writing Greeting */}
          <div className="space-y-3 min-h-[90px] flex flex-col items-center justify-center">
            <h1 className="text-3xl sm:text-4xl md:text-5xl font-heading font-bold text-graphite tracking-tight leading-tight">
              <span>{displayedText}</span>
              <motion.span
                animate={{ opacity: [1, 0, 1] }}
                transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
                className="inline-block w-[3px] h-8 sm:h-10 md:h-12 bg-cardinal ml-1.5 align-middle rounded-full"
              />
            </h1>

            {/* Sub-greeting appears once typing begins */}
            <motion.p
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: isTypingComplete ? 1 : 0.4, y: 0 }}
              transition={{ duration: 0.5 }}
              className="text-xs sm:text-sm text-graphite-muted max-w-[55ch] font-body"
            >
              {role === 'doctor'
                ? 'Clinical decision-support workspace authenticated • Local multimodal models ready'
                : 'Administrative authority verified • Cryptographic tamper-evident center active'}
            </motion.p>
          </div>

          {/* Logo Animation Repeating Slowly 2 Times */}
          <motion.div
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.3, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            className="flex flex-col items-center space-y-6 pt-2"
          >
            {/* The Signature ClinicalLens Reticle & ECG Pulse */}
            <div className="p-4 rounded-full bg-porcelain border border-hairline shadow-panel relative">
              <ClinicalLogo
                size="xl"
                mode="repeat-2"
                onCycleComplete={handleLogoCyclesDone}
              />
            </div>

            {/* Repetition Cycle Indicator (Cycle 1 of 2 -> Cycle 2 of 2 -> Launch) */}
            <div className="flex flex-col items-center space-y-2">
              <div className="flex items-center gap-3">
                <span
                  className={`text-[11px] font-mono tracking-wider transition-colors duration-300 font-semibold ${
                    currentCycle === 1 ? 'text-cardinal' : 'text-graphite-muted'
                  }`}
                >
                  Neural Sync 1/2
                </span>
                <span className="w-1 h-1 rounded-full bg-hairline" />
                <span
                  className={`text-[11px] font-mono tracking-wider transition-colors duration-300 font-semibold ${
                    currentCycle === 2 ? 'text-cardinal' : 'text-graphite-muted'
                  }`}
                >
                  Model Calibration 2/2
                </span>
              </div>

              {/* Refined dual-stage progress track */}
              <div className="w-36 h-1 bg-hairline rounded-full overflow-hidden flex">
                <motion.div
                  className="h-full bg-cardinal"
                  initial={{ width: '0%' }}
                  animate={{ width: currentCycle === 1 ? '50%' : '100%' }}
                  transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
                />
              </div>
            </div>
          </motion.div>
        </div>

        {/* Bottom Calm Assurance */}
        <div className="w-full max-w-4xl flex items-center justify-center gap-6 text-[11px] text-graphite-muted border-t border-hairline/60 pt-4">
          <span className="inline-flex items-center gap-1.5 text-teal-800">
            <ShieldCheck className="w-3.5 h-3.5 text-[#1F7A5C]" />
            Zero External Cloud Egress
          </span>
          <span className="hidden sm:inline text-hairline">•</span>
          <span className="hidden sm:inline font-mono">
            4 GB VRAM Queue Active
          </span>
          <span className="hidden sm:inline text-hairline">•</span>
          <span className="hidden sm:inline">
            Local SQLite & ReportLab
          </span>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};
