import React, { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { AuthLayout } from '../../components/layout/AuthLayout';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import { apiClient } from '../../api/client';
import type { ApplicationStatusResponse } from '../../types/auth';
import {
  CheckCircle2,
  Clock,
  AlertCircle,
  HelpCircle,
  RefreshCw,
  Search,
  ShieldCheck,
} from 'lucide-react';

export const ApplicationStatus: React.FC = () => {
  const [searchParams] = useSearchParams();
  const initialReg = searchParams.get('reg') || '';
  const [regNumber, setRegNumber] = useState(initialReg);
  const [isLoading, setIsLoading] = useState(false);
  const [statusData, setStatusData] = useState<ApplicationStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async (reg: string) => {
    if (!reg.trim()) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient<ApplicationStatusResponse>(
        `/api/auth/application-status/${encodeURIComponent(reg.trim())}`
      );
      setStatusData(data);
    } catch (err: any) {
      setError(err.message || 'Registration number not found in registry');
      setStatusData(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (initialReg) {
      fetchStatus(initialReg);
    }
  }, [initialReg]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchStatus(regNumber);
  };

  // Helper to determine stage states
  const getTimelineStages = (status: string) => {
    const isApproved = status === 'APPROVED';
    const isRejected = status === 'REJECTED';
    const isNeedsInfo = status === 'NEEDS_INFO';
    const isPending = status === 'PENDING';

    return [
      {
        title: 'Application submitted',
        desc: 'Credentials and documents securely logged',
        state: 'complete',
      },
      {
        title: 'Registry cross-verification',
        desc: 'Verifying registration with state medical council',
        state: isPending ? 'current' : 'complete',
      },
      {
        title: 'Administrative credential review',
        desc: 'Institutional affiliation and scope permissions check',
        state: isPending ? 'upcoming' : isNeedsInfo ? 'warning' : 'complete',
      },
      {
        title: isApproved
          ? 'Application approved'
          : isRejected
          ? 'Application rejected'
          : isNeedsInfo
          ? 'More information requested'
          : 'Final activation',
        desc: isApproved
          ? 'Account activated for clinical diagnostics'
          : isRejected
          ? statusData?.status_reason || 'Verification criteria not met'
          : isNeedsInfo
          ? statusData?.status_reason || 'Please supply updated institutional credentials'
          : 'Pending administrative approval',
        state: isApproved
          ? 'complete'
          : isRejected
          ? 'rejected'
          : isNeedsInfo
          ? 'warning'
          : 'upcoming',
      },
    ];
  };

  return (
    <AuthLayout
      title="Application status"
      subtitle="Check the real-time credentialing and review status of your medical registration."
    >
      <form onSubmit={handleSearch} className="mb-6 flex gap-2">
        <div className="flex-1">
          <Input
            placeholder="Medical council reg number (e.g. MC-2021-49102)"
            value={regNumber}
            onChange={(e) => setRegNumber(e.target.value)}
          />
        </div>
        <Button type="submit" variant="primary" size="md" isLoading={isLoading}>
          <Search className="w-4 h-4 mr-1.5" />
          Check
        </Button>
      </form>

      {error && (
        <div className="p-3 bg-blush/60 border border-cardinal/20 rounded-[6px] text-xs text-cardinal flex items-center gap-2 mb-4">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {statusData && (
        <div className="space-y-5">
          {/* Status Header Block */}
          <div className="bg-snow rounded-[8px] p-4 border border-hairline flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-graphite">{statusData.full_name}</div>
              <div className="text-xs text-graphite-muted mt-0.5">
                {statusData.specialty} • {statusData.hospital_clinic}
              </div>
            </div>
            <StatusChip status={statusData.status} />
          </div>

          {/* Reason Callout if Rejected or Needs Info */}
          {(statusData.status === 'REJECTED' || statusData.status === 'NEEDS_INFO') && (
            <div
              className={`p-3.5 rounded-[6px] border text-xs leading-relaxed ${
                statusData.status === 'REJECTED'
                  ? 'bg-blush border-red-200 text-graphite'
                  : 'bg-amber-50 border-amber-200 text-graphite'
              }`}
            >
              <span className="font-semibold block mb-1">
                {statusData.status === 'REJECTED' ? 'Administrative decision notice:' : 'Action required:'}
              </span>
              {statusData.status_reason}
            </div>
          )}

          {/* Timeline */}
          <div>
            <div className="flex items-center justify-between text-xs text-graphite-muted mb-3 font-medium">
              <span>Review timeline</span>
              <button
                type="button"
                onClick={() => fetchStatus(regNumber)}
                className="text-cardinal hover:underline inline-flex items-center gap-1"
              >
                <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
                <span>Refresh</span>
              </button>
            </div>

            <ol className="relative border-l border-hairline ml-3 space-y-5">
              {getTimelineStages(statusData.status).map((stage, i) => (
                <li key={i} className="ml-5">
                  <span
                    className={`absolute -left-2.5 flex items-center justify-center w-5 h-5 rounded-full text-[10px] ${
                      stage.state === 'complete'
                        ? 'bg-emerald-50 text-[#1F7A5C] ring-4 ring-porcelain border border-emerald-300'
                        : stage.state === 'current'
                        ? 'bg-cardinal text-porcelain ring-4 ring-porcelain'
                        : stage.state === 'warning'
                        ? 'bg-amber-100 text-[#B7791F] ring-4 ring-porcelain border border-amber-300'
                        : stage.state === 'rejected'
                        ? 'bg-blush text-cardinal ring-4 ring-porcelain border border-red-300'
                        : 'bg-snow text-graphite-subtle ring-4 ring-porcelain border border-hairline'
                    }`}
                  >
                    {stage.state === 'complete' ? (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    ) : stage.state === 'warning' ? (
                      <AlertCircle className="w-3 h-3" />
                    ) : stage.state === 'rejected' ? (
                      <AlertCircle className="w-3 h-3" />
                    ) : (
                      i + 1
                    )}
                  </span>
                  <h4 className="text-xs font-semibold text-graphite">{stage.title}</h4>
                  <p className="text-[11px] text-graphite-muted mt-0.5 leading-normal">
                    {stage.desc}
                  </p>
                </li>
              ))}
            </ol>
          </div>

          {statusData.status === 'APPROVED' && (
            <div className="pt-2">
              <Link to="/login">
                <Button variant="primary" size="md" className="w-full">
                  Sign in to clinical portal
                </Button>
              </Link>
            </div>
          )}
        </div>
      )}

      <div className="pt-4 border-t border-hairline mt-6 text-center text-xs">
        <Link to="/login" className="text-graphite-muted hover:text-cardinal transition-colors font-medium">
          Return to doctor sign in
        </Link>
      </div>
    </AuthLayout>
  );
};
