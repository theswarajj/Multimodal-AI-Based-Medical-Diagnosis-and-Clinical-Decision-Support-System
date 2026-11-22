import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AdminLayout } from '../../components/layout/AdminLayout';
import { Button } from '../../components/ui/Button';
import { apiClient } from '../../api/client';
import {
  ShieldCheck,
  ShieldAlert,
  Download,
  CheckCircle2,
  AlertTriangle,
  Lock,
  RefreshCw,
  HardDrive,
} from 'lucide-react';

export const AdminSecurityCenter: React.FC = () => {
  const [chainResult, setChainResult] = useState<any | null>(null);

  const verifyChainMutation = useMutation({
    mutationFn: () => apiClient<any>('/api/admin/security/verify-chain'),
    onSuccess: (data) => {
      setChainResult(data);
      if (data.is_intact) {
        toast.success(data.message);
      } else {
        toast.error(data.message);
      }
    },
  });

  const handleDownloadCsv = () => {
    window.location.href = '/api/admin/security/export-csv';
    toast.info('Downloading audit log CSV export...');
  };

  return (
    <AdminLayout
      title="Security & Audit Center"
      subtitle="Cryptographic verification of audit trails, tamper-evident hash chaining, and security safeguards."
      actions={
        <Button variant="outline" size="sm" onClick={handleDownloadCsv}>
          <Download className="w-3.5 h-3.5 mr-1" />
          Export Audit Log (CSV)
        </Button>
      }
    >
      {/* Hash Chaining Card */}
      <div className="bg-porcelain border border-hairline rounded-[12px] p-6 shadow-panel mb-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-hairline">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <ShieldCheck className="w-5 h-5 text-cardinal" />
              <h3 className="text-base font-semibold text-graphite">
                Cryptographic Hash-Chain Verification
              </h3>
            </div>
            <p className="text-xs text-graphite-muted max-w-[70ch] leading-relaxed">
              Every system event is irreversibly bound to the preceding entry using SHA-256 cryptographic hashing. Any post-hoc record alteration or insertion immediately breaks the chain.
            </p>
          </div>
          <Button
            variant="primary"
            size="sm"
            onClick={() => verifyChainMutation.mutate()}
            isLoading={verifyChainMutation.isPending}
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1" />
            Verify audit integrity
          </Button>
        </div>

        {chainResult && (
          <div
            className={`mt-4 p-4 rounded-[8px] border text-xs flex items-center justify-between ${
              chainResult.is_intact
                ? 'bg-emerald-50 border-emerald-200 text-[#1F7A5C]'
                : 'bg-blush border-red-200 text-cardinal'
            }`}
          >
            <div className="flex items-center gap-2.5">
              {chainResult.is_intact ? (
                <CheckCircle2 className="w-5 h-5 shrink-0" />
              ) : (
                <AlertTriangle className="w-5 h-5 shrink-0" />
              )}
              <span className="font-semibold">{chainResult.message}</span>
            </div>
            <span className="font-mono text-[11px] font-medium">Algorithm: SHA-256 Chaining</span>
          </div>
        )}
      </div>

      {/* Security Policies Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel">
          <div className="flex items-center gap-2.5 mb-2 font-semibold text-sm text-graphite">
            <Lock className="w-4 h-4 text-cardinal" />
            <span>Lockout Protection</span>
          </div>
          <p className="text-xs text-graphite-muted leading-relaxed mb-3">
            Accounts automatically lock for 30 minutes upon reaching 5 consecutive failed login attempts.
          </p>
          <div className="p-2.5 bg-snow rounded-[6px] border border-hairline text-xs font-medium text-graphite flex justify-between">
            <span>Threshold:</span>
            <span className="font-semibold">5 attempts</span>
          </div>
        </div>

        <div className="bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel">
          <div className="flex items-center gap-2.5 mb-2 font-semibold text-sm text-graphite">
            <ShieldCheck className="w-4 h-4 text-[#1F7A5C]" />
            <span>Session Idle Guard</span>
          </div>
          <p className="text-xs text-graphite-muted leading-relaxed mb-3">
            Clinician sessions automatically lock after 15 minutes of inactivity with a 2-minute modal countdown.
          </p>
          <div className="p-2.5 bg-snow rounded-[6px] border border-hairline text-xs font-medium text-graphite flex justify-between">
            <span>Timeout:</span>
            <span className="font-semibold">15 minutes</span>
          </div>
        </div>

        <div className="bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel">
          <div className="flex items-center gap-2.5 mb-2 font-semibold text-sm text-graphite">
            <HardDrive className="w-4 h-4 text-graphite" />
            <span>Local Data Boundary</span>
          </div>
          <p className="text-xs text-graphite-muted leading-relaxed mb-3">
            Strict local isolation: no patient imaging, vitals, or clinical narration is routed to third-party endpoints.
          </p>
          <div className="p-2.5 bg-snow rounded-[6px] border border-hairline text-xs font-medium text-[#1F7A5C] flex justify-between">
            <span>External Network:</span>
            <span className="font-semibold">Blocked</span>
          </div>
        </div>
      </div>
    </AdminLayout>
  );
};
