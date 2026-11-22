import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AdminLayout } from '../../components/layout/AdminLayout';
import { StatusChip } from '../../components/ui/StatusChip';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { apiClient } from '../../api/client';
import {
  Search,
  SlidersHorizontal,
  KeyRound,
  Ban,
  CheckCircle2,
  Lock,
  UserCheck,
  Shield,
  Clock,
  Sparkles,
  MessageSquare,
} from 'lucide-react';

export const AdminDoctors: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDoctor, setSelectedDoctor] = useState<any | null>(null);

  // Permissions Drawer
  const [showPermissions, setShowPermissions] = useState(false);
  const [allowedModels, setAllowedModels] = useState<string[]>([]);
  const [dailyLimit, setDailyLimit] = useState<number>(50);
  const [aiSummary, setAiSummary] = useState(true);
  const [pdfExport, setPdfExport] = useState(true);

  // Suspend/Reactivate Modal
  const [showActionModal, setShowActionModal] = useState(false);
  const [actionType, setActionType] = useState<'suspend' | 'reactivate'>('suspend');
  const [actionReason, setActionReason] = useState('');

  const { data: doctors = [], isLoading } = useQuery({
    queryKey: ['admin-doctors', searchTerm],
    queryFn: () => apiClient<any[]>(`/api/admin/doctors?search=${encodeURIComponent(searchTerm)}`),
  });

  const updatePermissionsMutation = useMutation({
    mutationFn: (id: number) =>
      apiClient(`/api/admin/doctors/${id}/permissions`, {
        method: 'POST',
        body: JSON.stringify({
          allowed_models: allowedModels,
          daily_case_limit: dailyLimit,
          ai_summary_enabled: aiSummary,
          pdf_export_enabled: pdfExport,
        }),
      }),
    onSuccess: () => {
      toast.success('Doctor permissions updated');
      queryClient.invalidateQueries({ queryKey: ['admin-doctors'] });
      setShowPermissions(false);
    },
    onError: (err: any) => toast.error(err.message || 'Update failed'),
  });

  const toggleStatusMutation = useMutation({
    mutationFn: ({ id, type, reason }: { id: number; type: string; reason: string }) =>
      apiClient(`/api/admin/doctors/${id}/${type}`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),
    onSuccess: (_, vars) => {
      toast.success(`Doctor ${vars.type === 'suspend' ? 'suspended' : 'reactivated'}`);
      queryClient.invalidateQueries({ queryKey: ['admin-doctors'] });
      setShowActionModal(false);
    },
    onError: (err: any) => toast.error(err.message || 'Action failed'),
  });

  const issueTempPwdMutation = useMutation({
    mutationFn: (id: number) =>
      apiClient<{ temporary_password: string }>(`/api/admin/doctors/${id}/issue-temp-password`, {
        method: 'POST',
      }),
    onSuccess: (data) => {
      toast.success(`Temporary password generated: ${data.temporary_password}`, {
        duration: 10000,
      });
    },
    onError: (err: any) => toast.error(err.message || 'Failed to issue temporary password'),
  });

  const openPermissions = (doc: any) => {
    setSelectedDoctor(doc);
    setAllowedModels(doc.allowed_models || ['SKIN', 'XRAY', 'MRI']);
    setDailyLimit(doc.daily_case_limit || 50);
    setAiSummary(doc.ai_summary_enabled ?? true);
    setPdfExport(doc.pdf_export_enabled ?? true);
    setShowPermissions(true);
  };

  const handleModelToggle = (model: string) => {
    setAllowedModels((prev) =>
      prev.includes(model) ? prev.filter((m) => m !== model) : [...prev, model]
    );
  };

  return (
    <AdminLayout
      title="Doctors Management"
      subtitle="Supervise active practitioners, manage diagnostic model privileges, and enforce security policies."
    >
      {/* Search & Stats Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 mb-4">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 text-graphite-muted absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Search doctor name, reg # or hospital..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:outline-none focus:border-cardinal"
          />
        </div>
        <div className="text-xs text-graphite-muted">
          Showing <span className="font-semibold text-graphite">{doctors.length}</span> practitioner profiles
        </div>
      </div>

      {/* Doctors Table */}
      <div className="bg-porcelain border border-hairline rounded-[12px] overflow-hidden shadow-panel">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-snow text-graphite-muted uppercase text-[10px] tracking-wider border-b border-hairline">
              <tr>
                <th className="px-4 py-3">Practitioner</th>
                <th className="px-4 py-3">Council Reg #</th>
                <th className="px-4 py-3">Specialty & Affiliation</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Allowed Models</th>
                <th className="px-4 py-3">Patients</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {doctors.map((doc: any) => (
                <tr key={doc.id} className="hover:bg-snow/60 transition-colors">
                  <td className="px-4 py-3">
                    <div className="font-semibold text-graphite">{doc.full_name}</div>
                    <div className="text-[11px] text-graphite-muted">{doc.email}</div>
                  </td>
                  <td className="px-4 py-3 font-mono text-graphite font-medium">
                    {doc.reg_number}
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-graphite font-medium">{doc.specialty}</div>
                    <div className="text-[11px] text-graphite-muted truncate max-w-[200px]">
                      {doc.hospital_clinic}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip status={doc.status} size="sm" />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      {doc.allowed_models?.map((m: string) => (
                        <span
                          key={m}
                          className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-snow border border-hairline text-graphite"
                        >
                          {m}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3 tabular-nums font-semibold text-graphite">
                    {doc.patient_count}
                  </td>
                  <td className="px-4 py-3 text-right space-x-1.5">
                    <button
                      type="button"
                      onClick={() => navigate(`/admin/messaging?doctorId=${doc.id}`)}
                      className="p-1 rounded text-graphite-muted hover:text-cardinal hover:bg-blush"
                      title={`Message Dr. ${doc.full_name} separately`}
                    >
                      <MessageSquare className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => openPermissions(doc)}
                      className="p-1 rounded text-graphite-muted hover:text-cardinal hover:bg-snow"
                      title="Adjust model & case permissions"
                    >
                      <SlidersHorizontal className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => issueTempPwdMutation.mutate(doc.id)}
                      className="p-1 rounded text-graphite-muted hover:text-[#B7791F] hover:bg-snow"
                      title="Issue one-time temporary password"
                    >
                      <KeyRound className="w-4 h-4" />
                    </button>
                    {doc.status === 'APPROVED' ? (
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedDoctor(doc);
                          setActionType('suspend');
                          setActionReason('');
                          setShowActionModal(true);
                        }}
                        className="p-1 rounded text-graphite-muted hover:text-cardinal hover:bg-snow"
                        title="Suspend account"
                      >
                        <Ban className="w-4 h-4" />
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedDoctor(doc);
                          setActionType('reactivate');
                          setActionReason('');
                          setShowActionModal(true);
                        }}
                        className="p-1 rounded text-graphite-muted hover:text-[#1F7A5C] hover:bg-snow"
                        title="Reactivate account"
                      >
                        <CheckCircle2 className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Permissions Modal */}
      {showPermissions && selectedDoctor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-porcelain rounded-[12px] border border-hairline p-6 shadow-floating">
            <h3 className="text-base font-semibold text-graphite mb-1">
              Practitioner Permissions
            </h3>
            <p className="text-xs text-graphite-muted mb-4">
              Configure diagnostic neural network access and daily processing quotas for{' '}
              <span className="font-semibold text-graphite">{selectedDoctor.full_name}</span>.
            </p>

            <div className="space-y-4">
              <div>
                <label className="text-xs font-medium text-graphite mb-1.5 block">
                  Allowed Modality Models
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {['SKIN', 'XRAY', 'MRI'].map((mod) => {
                    const active = allowedModels.includes(mod);
                    return (
                      <button
                        key={mod}
                        type="button"
                        onClick={() => handleModelToggle(mod)}
                        className={`p-2 rounded-[6px] text-xs font-semibold border transition-colors ${
                          active
                            ? 'bg-blush border-cardinal text-cardinal'
                            : 'bg-snow border-hairline text-graphite-muted'
                        }`}
                      >
                        {mod}
                      </button>
                    );
                  })}
                </div>
              </div>

              <Input
                label="Daily analysis case limit"
                type="number"
                value={dailyLimit}
                onChange={(e) => setDailyLimit(Number(e.target.value))}
              />

              <div className="space-y-2 pt-2 border-t border-hairline text-xs">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={aiSummary}
                    onChange={(e) => setAiSummary(e.target.checked)}
                    className="rounded text-cardinal focus:ring-cardinal"
                  />
                  <span>Enable MedGemma AI diagnostic narrative summary</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pdfExport}
                    onChange={(e) => setPdfExport(e.target.checked)}
                    className="rounded text-cardinal focus:ring-cardinal"
                  />
                  <span>Enable certified ReportLab PDF export & letterhead generation</span>
                </label>
              </div>
            </div>

            <div className="flex items-center justify-between gap-2 mt-6 pt-3 border-t border-hairline">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  const docId = selectedDoctor.id;
                  setShowPermissions(false);
                  navigate(`/admin/messaging?doctorId=${docId}`);
                }}
              >
                <MessageSquare className="w-3.5 h-3.5 mr-1 text-cardinal" />
                Message Doctor
              </Button>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="sm" onClick={() => setShowPermissions(false)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => updatePermissionsMutation.mutate(selectedDoctor.id)}
                  isLoading={updatePermissionsMutation.isPending}
                >
                  Save permissions
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Action Modal (Suspend / Reactivate) */}
      {showActionModal && selectedDoctor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-porcelain rounded-[12px] border border-hairline p-6 shadow-floating">
            <h3 className="text-base font-semibold text-graphite mb-1 capitalize">
              {actionType} Doctor Account
            </h3>
            <p className="text-xs text-graphite-muted mb-4">
              Enter the administrative reason for {actionType}ing{' '}
              <span className="font-semibold text-graphite">{selectedDoctor.full_name}</span>. This will be recorded in the tamper-evident audit log.
            </p>

            <textarea
              className="w-full h-24 p-2.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal focus:outline-none"
              placeholder={`Enter reason for ${actionType}...`}
              value={actionReason}
              onChange={(e) => setActionReason(e.target.value)}
            />

            <div className="flex items-center justify-end gap-2 mt-4 pt-3 border-t border-hairline">
              <Button variant="ghost" size="sm" onClick={() => setShowActionModal(false)}>
                Cancel
              </Button>
              <Button
                variant={actionType === 'suspend' ? 'danger' : 'primary'}
                size="sm"
                onClick={() =>
                  toggleStatusMutation.mutate({
                    id: selectedDoctor.id,
                    type: actionType,
                    reason: actionReason,
                  })
                }
                isLoading={toggleStatusMutation.isPending}
                disabled={!actionReason.trim()}
              >
                Confirm {actionType}
              </Button>
            </div>
          </div>
        </div>
      )}
    </AdminLayout>
  );
};
