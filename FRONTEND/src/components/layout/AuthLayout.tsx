import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { PulseLine } from '../ui/PulseLine';
import { ClinicalLogo } from '../ui/ClinicalLogo';
import { ShieldCheck, Activity } from 'lucide-react';

interface AuthLayoutProps {
  children: React.ReactNode;
  title: string;
  subtitle: string;
  isAdmin?: boolean;
}

export const AuthLayout: React.FC<AuthLayoutProps> = ({
  children,
  title,
  subtitle,
  isAdmin = false,
}) => {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-snow flex flex-col justify-between selection:bg-blush selection:text-cardinal">
      {/* Top calm header */}
      <header className="w-full border-b border-hairline bg-porcelain/80 backdrop-blur-sm px-6 py-4 flex items-center justify-between">
        <Link to="/login" className="flex items-center gap-2 group">
          <ClinicalLogo
            size="sm"
            showText
            subtitle={isAdmin ? 'Security Administration' : 'Multimodal Decision Support'}
          />
          {isAdmin && (
            <span className="text-[10px] font-semibold bg-gray-100 text-graphite-muted px-1.5 py-0.5 rounded-full border border-hairline uppercase tracking-wider ml-1">
              Admin
            </span>
          )}
        </Link>

        <div className="flex items-center gap-3 text-xs text-graphite-muted">
          <span className="inline-flex items-center gap-1.5 text-[#1F7A5C] bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200/60 font-medium">
            <ShieldCheck className="w-3.5 h-3.5" />
            100% Local Processing & Storage
          </span>
          <span className="hidden sm:inline text-hairline">|</span>
          <span className="hidden sm:inline">HIPAA / GDPR Aligned Data Isolation</span>
        </div>
      </header>

      {/* Main card area with orchestrated entrance */}
      <main className="flex-1 flex flex-col items-center justify-center p-4 sm:p-6 md:p-8">
        <div className="w-full max-w-md">
          {/* Brand Signature Pulse Line draws once */}
          <PulseLine mode="initial-draw" className="mb-4" />

          {/* Form container settles in */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
            className="bg-porcelain border border-hairline rounded-[12px] p-6 sm:p-8 shadow-panel relative"
          >
            <div className="mb-6">
              <h1 className="text-xl sm:text-2xl font-bold font-heading text-graphite tracking-tight">
                {title}
              </h1>
              <p className="text-xs sm:text-sm text-graphite-muted mt-1.5 max-w-[70ch] leading-relaxed">
                {subtitle}
              </p>
            </div>

            {children}
          </motion.div>

          {/* Footer Portal Switch */}
          <div className="mt-6 text-center text-xs text-graphite-muted flex items-center justify-center gap-4">
            {isAdmin ? (
              <Link
                to="/login"
                className="hover:text-cardinal transition-colors font-medium flex items-center gap-1"
              >
                Switch to Doctor portal
              </Link>
            ) : (
              <div className="flex items-center gap-3">
                <Link
                  to="/admin/login"
                  className="hover:text-cardinal transition-colors font-medium"
                >
                  Administrator portal
                </Link>
                <span className="text-hairline">•</span>
                <Link
                  to="/application-status"
                  className="hover:text-cardinal transition-colors font-medium"
                >
                  Check application status
                </Link>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Simple footer */}
      <footer className="w-full py-4 px-6 border-t border-hairline text-center text-xs text-graphite-subtle">
        <p>
          ClinicalLens Multimodal Diagnostic System • Confidential Clinical Decision-Support • No external cloud dependencies
        </p>
      </footer>
    </div>
  );
};
