import React from 'react';
import { motion } from 'framer-motion';

interface PulseLineProps {
  mode?: 'initial-draw' | 'loading' | 'static';
  className?: string;
}

/**
 * Signature element: "pulse line"
 * A thin Cardinal ECG-style line that draws itself once on the login screen,
 * and becomes the slim progress bar under the top navigation while loading.
 */
export const PulseLine: React.FC<PulseLineProps> = ({ mode = 'initial-draw', className = '' }) => {
  if (mode === 'loading') {
    return (
      <div className={`relative w-full h-[2px] bg-hairline overflow-hidden ${className}`}>
        <motion.div
          className="absolute h-full bg-cardinal"
          initial={{ left: '-30%', width: '30%' }}
          animate={{ left: '100%', width: '40%' }}
          transition={{
            repeat: Infinity,
            duration: 1.4,
            ease: [0.4, 0, 0.2, 1],
          }}
        />
      </div>
    );
  }

  // ECG wave pattern path
  const ecgPath = "M0 16 L60 16 L70 16 L76 7 L82 25 L88 4 L94 28 L100 16 L110 16 L170 16";

  return (
    <div className={`w-full overflow-hidden flex items-center justify-center ${className}`}>
      <svg
        viewBox="0 0 170 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-48 h-8 stroke-cardinal"
        aria-hidden="true"
      >
        <motion.path
          d={ecgPath}
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{
            duration: 1.6,
            ease: [0.25, 0.1, 0.25, 1],
          }}
        />
      </svg>
    </div>
  );
};
