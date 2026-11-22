import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import { ShieldCheck, LogOut, CheckCircle, ArrowRight, ShieldAlert, Users, Activity } from 'lucide-react';

export const AdminDashboardPlaceholder: React.FC = () => {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-snow flex flex-col">
      {/* Top Bar */}
      <header className="bg-porcelain border-b border-hairline px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-[6px] bg-cardinal flex items-center justify-center text-porcelain">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <span className="font-heading font-bold text-base text-graphite tracking-tight flex items-center gap-1.5">
              ClinicalLens
              <span className="text-[10px] font-semibold bg-gray-100 text-graphite-muted px-1.5 py-0.5 rounded-full border border-hairline uppercase tracking-wider">
                Admin
              </span>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right hidden sm:block">
            <div className="text-xs font-semibold text-graphite">Administrator Session</div>
            <div className="text-[11px] text-[#1F7A5C] font-medium flex items-center gap-1 justify-end">
              <ShieldCheck className="w-3 h-3" />
              <span>TOTP 2FA Verified</span>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={logout}>
            <LogOut className="w-3.5 h-3.5 mr-1.5" />
            Sign out
          </Button>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-5xl w-full mx-auto p-6 md:p-8">
        <div className="bg-porcelain border border-hairline rounded-[12px] p-8 shadow-panel mb-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <StatusChip status="APPROVED" label="Admin Session Active" />
                <span className="text-xs text-graphite-muted">• Full Audit Integrity</span>
              </div>
              <h1 className="text-2xl font-bold font-heading text-graphite tracking-tight">
                Clinical Administrator Overview
              </h1>
              <p className="text-sm text-graphite-muted mt-1">
                Account: <span className="font-medium text-graphite">{user?.email}</span>
              </p>
            </div>
            <div className="w-12 h-12 rounded-full bg-emerald-50 text-[#1F7A5C] flex items-center justify-center border border-emerald-200">
              <CheckCircle className="w-6 h-6" />
            </div>
          </div>

          <div className="p-4 bg-snow rounded-[8px] border border-hairline mt-6">
            <h3 className="text-sm font-semibold text-graphite mb-2 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-cardinal" />
              <span>Phase 1 Verification Complete</span>
            </h3>
            <p className="text-xs text-graphite-muted leading-relaxed max-w-[75ch]">
              Admin login with TOTP two-factor authentication, Argon2id security, tamper-evident SHA-256 audit log chaining, and doctor review status flows are active and verified.
            </p>
            <div className="mt-3 flex items-center gap-2 text-xs font-medium text-cardinal">
              <span>Ready for Phase 2: Full Admin Portal (doctor management, approvals, activity monitor, security center)</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
