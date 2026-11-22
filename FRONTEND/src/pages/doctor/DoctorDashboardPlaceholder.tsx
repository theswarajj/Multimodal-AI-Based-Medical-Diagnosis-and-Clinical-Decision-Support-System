import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import { Activity, LogOut, CheckCircle, Shield, User, ArrowRight } from 'lucide-react';

export const DoctorDashboardPlaceholder: React.FC = () => {
  const { user, logout } = useAuth();
  const doc = user?.doctor;

  return (
    <div className="min-h-screen bg-snow flex flex-col">
      {/* Top Bar */}
      <header className="bg-porcelain border-b border-hairline px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-[6px] bg-cardinal flex items-center justify-center text-porcelain">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <span className="font-heading font-bold text-base text-graphite tracking-tight">
              ClinicalLens
            </span>
            <span className="text-xs text-graphite-muted ml-2">Doctor Workspace</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right hidden sm:block">
            <div className="text-xs font-semibold text-graphite">{doc?.full_name || 'Dr. Aris Thorne'}</div>
            <div className="text-[11px] text-graphite-muted">{doc?.specialty || 'Clinician'} • {doc?.reg_number}</div>
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
                <StatusChip status="APPROVED" label="Account Approved & Active" />
                <span className="text-xs text-graphite-muted">• Medical License Verified</span>
              </div>
              <h1 className="text-2xl font-bold font-heading text-graphite tracking-tight">
                Welcome, {doc?.full_name || 'Doctor'}
              </h1>
              <p className="text-sm text-graphite-muted mt-1">
                Hospital Affiliation: <span className="font-medium text-graphite">{doc?.hospital_clinic}</span>
              </p>
            </div>
            <div className="w-12 h-12 rounded-full bg-emerald-50 text-[#1F7A5C] flex items-center justify-center border border-emerald-200">
              <CheckCircle className="w-6 h-6" />
            </div>
          </div>

          <div className="p-4 bg-snow rounded-[8px] border border-hairline mt-6">
            <h3 className="text-sm font-semibold text-graphite mb-2 flex items-center gap-2">
              <Shield className="w-4 h-4 text-cardinal" />
              <span>Phase 1 Verification Complete</span>
            </h3>
            <p className="text-xs text-graphite-muted leading-relaxed max-w-[75ch]">
              Design system, tokens (Porcelain, Snow, Hairline, Graphite, Cardinal, Blush), typography (Bricolage Grotesque & Public Sans), multi-step registration wizard, doctor credentials verification, and security safeguards are operational.
            </p>
            <div className="mt-3 flex items-center gap-2 text-xs font-medium text-cardinal">
              <span>Ready to proceed to Phase 2 (Admin Portal) and Phase 3 (Doctor Workspace & Modalities)</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
