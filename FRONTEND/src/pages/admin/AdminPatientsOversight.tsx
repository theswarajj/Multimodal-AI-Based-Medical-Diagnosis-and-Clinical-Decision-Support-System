import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AdminLayout } from '../../components/layout/AdminLayout';
import { StatusChip } from '../../components/ui/StatusChip';
import { Button } from '../../components/ui/Button';
import { apiClient } from '../../api/client';
import {
  Eye,
  ShieldAlert,
  Search,
  Lock,
  FileSpreadsheet,
  AlertTriangle,
  Clock,
  X,
} from 'lucide-react';

export const AdminPatientsOversight: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedPatientId, setSelectedPatientId] = useState<number | null>(null);
  const [showReasonModal, setShowReasonModal] = useState(false);
  const [accessReason, setAccessReason] = useState('');
  const [clinicalRecord, setClinicalRecord] = useState<any | null>(null);

  const { data: patients = [], isLoading } = useQuery({
    queryKey: ['admin-patients', searchTerm],
    queryFn: () => apiClient<any[]>(`/api/admin/patients?search=${encodeURIComponent(searchTerm)}`),
  });

  const openRecordMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      apiClient<any>(`/api/admin/patients/${id}/open-record`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),
    onSuccess: (data) => {
      setClinicalRecord(data);
      setShowReasonModal(false);
      toast.info('Access to full clinical data logged in tamper-evident audit record.');
    },
    onError: (err: any) => toast.error(err.message || 'Access denied'),
  });

  const handleRequestAccess = (id: number) => {
    setSelectedPatientId(id);
    setAccessReason('');
    setShowReasonModal(true);
  };

  return (
    <AdminLayout
      title="Patient Records Oversight"
      subtitle="Default view is restricted to non-identifying metadata. Full clinical access requires an auditable justification."
    >
      {/* Notice Banner */}
      <div className="p-3.5 bg-snow rounded-[8px] border border-hairline flex items-center justify-between gap-3 mb-6 text-xs text-graphite-muted">
        <div className="flex items-center gap-2.5">
          <ShieldAlert className="w-4 h-4 text-cardinal shrink-0" />
          <span>
            <b>Privacy Isolation:</b> Administrators cannot create patients, alter clinical data, or run diagnoses.
          </span>
        </div>
        <span className="font-mono text-[11px] text-graphite-subtle">Audit Guard v2.0</span>
      </div>

      {/* Metadata Table */}
      <div className="bg-porcelain border border-hairline rounded-[12px] overflow-hidden shadow-panel">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-snow text-graphite-muted uppercase text-[10px] tracking-wider border-b border-hairline">
              <tr>
                <th className="px-4 py-3">Patient Code</th>
                <th className="px-4 py-3">Age / Sex</th>
                <th className="px-4 py-3">Owning Physician</th>
                <th className="px-4 py-3">Modalities</th>
                <th className="px-4 py-3">Triage Level</th>
                <th className="px-4 py-3">Cases</th>
                <th className="px-4 py-3">Registered</th>
                <th className="px-4 py-3 text-right">Audit Access</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {patients.map((pat: any) => (
                <tr key={pat.id} className="hover:bg-snow/60 transition-colors">
                  <td className="px-4 py-3 font-mono font-bold text-graphite">
                    {pat.patient_code}
                  </td>
                  <td className="px-4 py-3 text-graphite tabular-nums">
                    {pat.age} yrs / {pat.sex}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-graphite">{pat.doctor_name}</div>
                    <div className="text-[11px] font-mono text-graphite-muted">{pat.doctor_reg}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      {pat.modalities?.length > 0 ? (
                        pat.modalities.map((m: string) => (
                          <span
                            key={m}
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-snow border border-hairline text-graphite"
                          >
                            {m}
                          </span>
                        ))
                      ) : (
                        <span className="text-graphite-subtle text-[11px]">None</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip status={pat.triage_level} size="sm" />
                  </td>
                  <td className="px-4 py-3 tabular-nums font-semibold text-graphite">
                    {pat.case_count}
                  </td>
                  <td className="px-4 py-3 text-graphite-muted">
                    {new Date(pat.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleRequestAccess(pat.id)}
                    >
                      <Eye className="w-3.5 h-3.5 mr-1 text-cardinal" />
                      Open record
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Require Reason Modal */}
      {showReasonModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-porcelain rounded-[12px] border border-hairline p-6 shadow-floating">
            <div className="flex items-start gap-3 mb-3">
              <div className="w-9 h-9 rounded-full bg-blush flex items-center justify-center text-cardinal shrink-0">
                <Lock className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-graphite">Clinical Access Justification</h3>
                <p className="text-xs text-graphite-muted mt-0.5">
                  Opening patient medical details is restricted. Please select an auditable reason.
                </p>
              </div>
            </div>

            <div className="space-y-2 mb-3">
              {[
                'Clinical Safety Audit (urgent flag investigation)',
                'Regulatory Board Compliance Verification',
                'Patient Data Subject Access Request (SAR)',
                'Adverse Event Review',
              ].map((r, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setAccessReason(r)}
                  className={`w-full text-left text-xs p-2.5 rounded-[6px] border transition-colors ${
                    accessReason === r
                      ? 'bg-blush border-cardinal text-cardinal font-medium'
                      : 'bg-snow border-hairline text-graphite hover:bg-hairline/60'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>

            <textarea
              className="w-full h-16 p-2 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal focus:outline-none"
              placeholder="Or enter custom justification..."
              value={accessReason}
              onChange={(e) => setAccessReason(e.target.value)}
            />

            <div className="flex items-center justify-end gap-2 mt-4 pt-3 border-t border-hairline">
              <Button variant="ghost" size="sm" onClick={() => setShowReasonModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  openRecordMutation.mutate({
                    id: selectedPatientId!,
                    reason: accessReason,
                  })
                }
                isLoading={openRecordMutation.isPending}
                disabled={!accessReason.trim()}
              >
                Confirm & Log Access
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Clinical Record Viewer Modal */}
      {clinicalRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-2xl bg-porcelain rounded-[12px] border border-hairline p-6 shadow-floating max-h-[85vh] overflow-y-auto">
            <div className="flex items-start justify-between pb-3 border-b border-hairline mb-4">
              <div>
                <span className="text-[10px] font-bold text-cardinal tracking-wider uppercase block">
                  Audited Clinical Content
                </span>
                <h3 className="text-lg font-bold font-heading text-graphite">
                  {clinicalRecord.patient.name} ({clinicalRecord.patient.patient_code})
                </h3>
                <span className="text-xs text-graphite-muted">
                  Doctor: {clinicalRecord.patient.doctor_name}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setClinicalRecord(null)}
                className="p-1 rounded text-graphite-muted hover:text-cardinal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 bg-blush/60 rounded-[6px] border border-red-200 text-xs text-cardinal mb-4 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 shrink-0" />
              <span>{clinicalRecord.access_notice}</span>
            </div>

            {/* Cases Content */}
            <div className="space-y-4 text-xs">
              {clinicalRecord.patient.cases?.map((c: any, i: number) => (
                <div key={i} className="p-4 bg-snow rounded-[8px] border border-hairline space-y-2">
                  <div className="flex items-center justify-between pb-2 border-b border-hairline">
                    <span className="font-mono font-bold text-graphite">{c.case_code}</span>
                    <StatusChip status={c.triage_level} size="sm" />
                  </div>
                  <div>
                    <span className="text-graphite-muted block">Chief Complaint:</span>
                    <span className="text-graphite">{c.chief_complaint || 'None recorded'}</span>
                  </div>
                  <div>
                    <span className="text-graphite-muted block">Active Medications:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {c.medicines?.length > 0 ? (
                        c.medicines.map((m: any, idx: number) => (
                          <span
                            key={idx}
                            className="px-2 py-0.5 rounded bg-porcelain border border-hairline text-graphite"
                          >
                            {m.drug} ({m.dose})
                          </span>
                        ))
                      ) : (
                        <span className="text-graphite-muted">None</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end pt-4 mt-6 border-t border-hairline">
              <Button variant="ghost" size="sm" onClick={() => setClinicalRecord(null)}>
                Close record
              </Button>
            </div>
          </div>
        </div>
      )}
    </AdminLayout>
  );
};
