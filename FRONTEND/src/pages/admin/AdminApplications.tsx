import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AdminLayout } from '../../components/layout/AdminLayout';
import { StatusChip } from '../../components/ui/StatusChip';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { apiClient } from '../../api/client';
import {
  FileText,
  CheckCircle,
  XCircle,
  HelpCircle,
  ExternalLink,
  ShieldAlert,
  User,
  Clock,
  Building,
} from 'lucide-react';

export const AdminApplications: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedApp, setSelectedApp] = useState<any | null>(null);
  const [filter, setFilter] = useState<string>('ALL');

  // Modal actions
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showInfoModal, setShowInfoModal] = useState(false);
  const [infoMessage, setInfoMessage] = useState('');

  const { data: applications = [], isLoading } = useQuery({
    queryKey: ['admin-applications', filter],
    queryFn: () => apiClient<any[]>(`/api/admin/applications?status_filter=${filter}`),
  });

  const approveMutation = useMutation({
    mutationFn: (id: number) =>
      apiClient(`/api/admin/applications/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify({ allowed_models: ['SKIN', 'XRAY', 'MRI'], daily_case_limit: 50 }),
      }),
    onSuccess: () => {
      toast.success('Doctor application approved successfully');
      queryClient.invalidateQueries({ queryKey: ['admin-applications'] });
      setSelectedApp(null);
    },
    onError: (err: any) => toast.error(err.message || 'Approval failed'),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      apiClient(`/api/admin/applications/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),
    onSuccess: () => {
      toast.success('Doctor application rejected');
      queryClient.invalidateQueries({ queryKey: ['admin-applications'] });
      setShowRejectModal(false);
      setSelectedApp(null);
    },
    onError: (err: any) => toast.error(err.message || 'Action failed'),
  });

  const infoMutation = useMutation({
    mutationFn: ({ id, message }: { id: number; message: string }) =>
      apiClient(`/api/admin/applications/${id}/request-info`, {
        method: 'POST',
        body: JSON.stringify({ message }),
      }),
    onSuccess: () => {
      toast.success('Information request sent to doctor');
      queryClient.invalidateQueries({ queryKey: ['admin-applications'] });
      setShowInfoModal(false);
      setSelectedApp(null);
    },
    onError: (err: any) => toast.error(err.message || 'Action failed'),
  });

  return (
    <AdminLayout
      title="Doctor Applications Queue"
      subtitle="Verify medical licenses, council credentials, and attached documentation."
    >
      {/* Filter Tabs */}
      <div className="flex items-center gap-2 mb-4 pb-2 border-b border-hairline">
        {['ALL', 'PENDING', 'NEEDS_INFO', 'REJECTED'].map((st) => (
          <button
            key={st}
            onClick={() => {
              setFilter(st);
              setSelectedApp(null);
            }}
            className={`px-3 py-1.5 rounded-[6px] text-xs font-medium transition-colors ${
              filter === st
                ? 'bg-cardinal text-porcelain'
                : 'bg-porcelain text-graphite-muted hover:text-graphite border border-hairline'
            }`}
          >
            {st.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Split View */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left List of Applicants */}
        <div className="lg:col-span-5 bg-porcelain border border-hairline rounded-[12px] p-4 shadow-panel space-y-2.5">
          <h3 className="text-xs font-semibold text-graphite mb-2 uppercase tracking-wider">
            Applicants ({applications.length})
          </h3>

          {applications.length === 0 ? (
            <div className="p-8 text-center text-xs text-graphite-muted">
              No doctor applications found matching current filter.
            </div>
          ) : (
            applications.map((app) => {
              const isSelected = selectedApp?.id === app.id;
              return (
                <div
                  key={app.id}
                  onClick={() => setSelectedApp(app)}
                  className={`p-3.5 rounded-[8px] border transition-colors cursor-pointer ${
                    isSelected
                      ? 'border-cardinal bg-blush/40'
                      : 'border-hairline bg-snow/60 hover:bg-snow'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className="text-sm font-semibold text-graphite">{app.full_name}</span>
                    <StatusChip status={app.status} size="sm" />
                  </div>
                  <div className="text-xs text-graphite-muted">
                    {app.specialty} • {app.hospital_clinic}
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[11px] text-graphite-subtle">
                    <span className="font-mono">{app.reg_number}</span>
                    <span>{new Date(app.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Right Details & Document Review */}
        <div className="lg:col-span-7 bg-porcelain border border-hairline rounded-[12px] p-6 shadow-panel">
          {selectedApp ? (
            <div className="space-y-6">
              {/* Header */}
              <div className="flex items-start justify-between pb-4 border-b border-hairline">
                <div>
                  <h2 className="text-xl font-bold font-heading text-graphite">
                    {selectedApp.full_name}
                  </h2>
                  <p className="text-xs text-graphite-muted mt-0.5">
                    {selectedApp.qualification} • {selectedApp.specialty}
                  </p>
                </div>
                <StatusChip status={selectedApp.status} />
              </div>

              {/* Council & Affiliation Details */}
              <div className="grid grid-cols-2 gap-3 text-xs bg-snow p-4 rounded-[8px] border border-hairline">
                <div>
                  <span className="text-graphite-muted block">Medical Council Reg #:</span>
                  <span className="font-mono font-bold text-graphite">{selectedApp.reg_number}</span>
                </div>
                <div>
                  <span className="text-graphite-muted block">Issuing Council:</span>
                  <span className="text-graphite">{selectedApp.issuing_council}</span>
                </div>
                <div>
                  <span className="text-graphite-muted block">Year of Registration:</span>
                  <span className="text-graphite">{selectedApp.reg_year}</span>
                </div>
                <div>
                  <span className="text-graphite-muted block">Date of Birth:</span>
                  <span className="text-graphite">{selectedApp.dob}</span>
                </div>
                <div>
                  <span className="text-graphite-muted block">Institutional Affiliation:</span>
                  <span className="text-graphite">{selectedApp.hospital_clinic}</span>
                </div>
                <div>
                  <span className="text-graphite-muted block">Contact Email:</span>
                  <span className="text-graphite">{selectedApp.email}</span>
                </div>
              </div>

              {/* Uploaded Verification Proofs */}
              <div>
                <h4 className="text-xs font-semibold text-graphite mb-2 uppercase tracking-wider">
                  Attached Verification Proofs
                </h4>
                <div className="space-y-2">
                  {selectedApp.documents?.length > 0 ? (
                    selectedApp.documents.map((doc: any) => (
                      <div
                        key={doc.id}
                        className="p-3 bg-snow rounded-[6px] border border-hairline flex items-center justify-between text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <FileText className="w-4 h-4 text-cardinal" />
                          <div>
                            <span className="font-medium text-graphite block">{doc.filename}</span>
                            <span className="text-[10px] text-graphite-muted uppercase">
                              {doc.type}
                            </span>
                          </div>
                        </div>
                        <a
                          href={doc.path}
                          target="_blank"
                          rel="noreferrer"
                          className="text-cardinal hover:underline inline-flex items-center gap-1 font-medium"
                        >
                          <span>Open preview</span>
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-graphite-muted">No documents uploaded.</p>
                  )}
                </div>
              </div>

              {/* Reason / Notes banner if already processed */}
              {selectedApp.status_reason && (
                <div className="p-3 bg-amber-50 rounded-[6px] border border-amber-200/80 text-xs text-graphite">
                  <span className="font-semibold block mb-0.5">Status notes:</span>
                  {selectedApp.status_reason}
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-hairline">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowInfoModal(true)}
                  disabled={approveMutation.isPending}
                >
                  <HelpCircle className="w-3.5 h-3.5 mr-1 text-[#B7791F]" />
                  Request info
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowRejectModal(true)}
                  disabled={approveMutation.isPending}
                >
                  <XCircle className="w-3.5 h-3.5 mr-1 text-cardinal" />
                  Reject application
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => approveMutation.mutate(selectedApp.id)}
                  isLoading={approveMutation.isPending}
                >
                  <CheckCircle className="w-3.5 h-3.5 mr-1" />
                  Approve doctor
                </Button>
              </div>
            </div>
          ) : (
            <div className="py-20 text-center text-xs text-graphite-muted">
              Select an applicant from the left to view medical credentials and take action.
            </div>
          )}
        </div>
      </div>

      {/* Reject Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-porcelain rounded-[12px] border border-hairline p-6 shadow-floating">
            <h3 className="text-base font-semibold text-graphite mb-1">Reject Doctor Application</h3>
            <p className="text-xs text-graphite-muted mb-4">
              Specify the clinical or regulatory reason. This will be visible on the doctor's status page.
            </p>
            <div className="mb-3">
              <label className="text-xs font-medium text-graphite mb-1 block">Quick templates:</label>
              <div className="flex flex-wrap gap-1.5">
                {[
                  'Medical council registration could not be verified on state registry.',
                  'Attached registration certificate expired or illegible.',
                  'Specialty board certification mismatch.',
                ].map((tpl, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setRejectReason(tpl)}
                    className="text-[11px] p-1.5 rounded bg-snow hover:bg-hairline text-graphite text-left border border-hairline"
                  >
                    {tpl}
                  </button>
                ))}
              </div>
            </div>
            <textarea
              className="w-full h-24 p-2.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal focus:outline-none"
              placeholder="Enter rejection reason..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
            />
            <div className="flex items-center justify-end gap-2 mt-4 pt-3 border-t border-hairline">
              <Button variant="ghost" size="sm" onClick={() => setShowRejectModal(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() =>
                  rejectMutation.mutate({ id: selectedApp.id, reason: rejectReason })
                }
                isLoading={rejectMutation.isPending}
                disabled={!rejectReason.trim()}
              >
                Confirm rejection
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Request Info Modal */}
      {showInfoModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-porcelain rounded-[12px] border border-hairline p-6 shadow-floating">
            <h3 className="text-base font-semibold text-graphite mb-1">Request More Information</h3>
            <p className="text-xs text-graphite-muted mb-4">
              Send instructions to the doctor regarding missing credentials or clarification needed.
            </p>
            <textarea
              className="w-full h-24 p-2.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal focus:outline-none"
              placeholder="e.g. Please provide your renewed state medical council certificate for 2026..."
              value={infoMessage}
              onChange={(e) => setInfoMessage(e.target.value)}
            />
            <div className="flex items-center justify-end gap-2 mt-4 pt-3 border-t border-hairline">
              <Button variant="ghost" size="sm" onClick={() => setShowInfoModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  infoMutation.mutate({ id: selectedApp.id, message: infoMessage })
                }
                isLoading={infoMutation.isPending}
                disabled={!infoMessage.trim()}
              >
                Send request
              </Button>
            </div>
          </div>
        </div>
      )}
    </AdminLayout>
  );
};
