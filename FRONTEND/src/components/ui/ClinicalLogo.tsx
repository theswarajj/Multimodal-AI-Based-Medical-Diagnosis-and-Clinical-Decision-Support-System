import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export interface ClinicalLogoProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  mode?: 'idle' | 'loop' | 'repeat-2';
  showText?: boolean;
  onCycleComplete?: () => void;
  className?: string;
  subtitle?: string;
}

const sizeConfig = {
  sm: { icon: 32, box: 40, stroke: 1.5, text: 'text-sm', sub: 'text-[9px]' },
  md: { icon: 48, box: 56, stroke: 2, text: 'text-base', sub: 'text-[10px]' },
  lg: { icon: 72, box: 84, stroke: 2.25, text: 'text-xl', sub: 'text-xs' },
  xl: { icon: 104, box: 120, stroke: 2.5, text: 'text-2xl', sub: 'text-sm' },
};

export const ClinicalLogo: React.FC<ClinicalLogoProps> = ({
  size = 'md',
  mode = 'idle',
  showText = false,
  onCycleComplete,
  className = '',
  subtitle,
}) => {
  const { icon, stroke, text, sub } = sizeConfig[size];
  const [cycle, setCycle] = useState(0);

  // Handle exactly 2 repetitions when in 'repeat-2' mode
  useEffect(() => {
    if (mode !== 'repeat-2') return;

    const timer = setInterval(() => {
      setCycle((prev) => {
        const next = prev + 1;
        if (next >= 2) {
          clearInterval(timer);
          if (onCycleComplete) {
            setTimeout(onCycleComplete, 600);
          }
        }
        return next;
      });
    }, 1500);

    return () => clearInterval(timer);
  }, [mode, onCycleComplete]);

  // Center coordinates for a 100x100 viewBox
  // ECG Line Path across the circular lens
  const ecgPath = "M 10 50 L 32 50 L 37 44 L 41 56 L 46 22 L 53 74 L 59 36 L 64 54 L 68 50 L 90 50";

  return (
    <div className={`inline-flex items-center gap-3 select-none ${className}`}>
      {/* Precision Lens & ECG Symbol */}
      <div className="relative flex items-center justify-center shrink-0">
        {/* Ambient Halo Pulse (active in loop or repeat-2 mode) */}
        {(mode === 'loop' || mode === 'repeat-2') && (
          <motion.div
            className="absolute rounded-full bg-cardinal/10 -inset-3 pointer-events-none"
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{
              scale: [0.9, 1.25, 0.9],
              opacity: [0.15, 0.45, 0.15],
            }}
            transition={{
              duration: 2.4,
              repeat: Infinity,
              ease: [0.4, 0, 0.2, 1],
            }}
          />
        )}

        <svg
          width={icon}
          height={icon}
          viewBox="0 0 100 100"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="relative z-10"
        >
          {/* Outer Optical Lens Reticle Ring */}
          <motion.circle
            cx="50"
            cy="50"
            r="42"
            stroke="#E6E6E9"
            strokeWidth={stroke}
            initial={{ scale: 0.95, opacity: 0.8 }}
            animate={
              mode === 'loop' || mode === 'repeat-2'
                ? {
                    scale: [0.98, 1.02, 0.98],
                    borderColor: ['#E6E6E9', '#FCEBED', '#E6E6E9'],
                  }
                : {}
            }
            transition={{
              duration: 3,
              repeat: Infinity,
              ease: 'easeInOut',
            }}
          />

          {/* Precision Crosshair Ticks (0°, 90°, 180°, 270°) */}
          <line x1="50" y1="2" x2="50" y2="8" stroke="#C8102E" strokeWidth={stroke} strokeLinecap="round" />
          <line x1="50" y1="92" x2="50" y2="98" stroke="#C8102E" strokeWidth={stroke} strokeLinecap="round" />
          <line x1="2" y1="50" x2="8" y2="50" stroke="#C8102E" strokeWidth={stroke} strokeLinecap="round" />
          <line x1="92" y1="50" x2="98" y2="50" stroke="#C8102E" strokeWidth={stroke} strokeLinecap="round" />

          {/* Mid Focal Circle */}
          <circle
            cx="50"
            cy="50"
            r="32"
            stroke="#25272D"
            strokeOpacity="0.12"
            strokeWidth={stroke * 0.75}
            strokeDasharray="3 3"
          />

          {/* Inner Tinted Aperture Core */}
          <circle cx="50" cy="50" r="26" fill="#FCEBED" fillOpacity="0.45" />

          {/* Secondary Target Crosshair (faint graphite) */}
          <line x1="50" y1="20" x2="50" y2="28" stroke="#25272D" strokeOpacity="0.3" strokeWidth="1" />
          <line x1="50" y1="72" x2="50" y2="80" stroke="#25272D" strokeOpacity="0.3" strokeWidth="1" />
          <line x1="20" y1="50" x2="28" y2="50" stroke="#25272D" strokeOpacity="0.3" strokeWidth="1" />
          <line x1="72" y1="50" x2="80" y2="50" stroke="#25272D" strokeOpacity="0.3" strokeWidth="1" />

          {/* Signature ECG Pulse Line */}
          {mode === 'idle' ? (
            <path
              d={ecgPath}
              stroke="#C8102E"
              strokeWidth={stroke * 1.25}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : (
            <motion.path
              key={mode === 'repeat-2' ? cycle : 'loop'}
              d={ecgPath}
              stroke="#C8102E"
              strokeWidth={stroke * 1.3}
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={{ pathLength: 0, opacity: 0.2 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{
                duration: 1.4,
                repeat: mode === 'loop' ? Infinity : 0,
                repeatDelay: 0.4,
                ease: [0.25, 0.1, 0.25, 1],
              }}
            />
          )}

          {/* Focal Centerpoint Core */}
          <circle cx="50" cy="50" r="2" fill="#C8102E" />
        </svg>
      </div>

      {/* Optional Wordmark */}
      {showText && (
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5 leading-none">
            <span className={`font-heading font-bold text-graphite tracking-tight ${text}`}>
              ClinicalLens
            </span>
            <span className="w-1.5 h-1.5 rounded-full bg-cardinal inline-block" />
          </div>
          {subtitle && (
            <span className={`font-body text-graphite-muted mt-1 leading-tight tracking-normal ${sub}`}>
              {subtitle}
            </span>
          )}
        </div>
      )}
    </div>
  );
};
