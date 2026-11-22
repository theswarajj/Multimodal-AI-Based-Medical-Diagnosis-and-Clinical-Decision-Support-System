import React from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { DoctorLayout } from '../../components/layout/DoctorLayout';
import { StatusChip } from '../../components/ui/StatusChip';
import { Button } from '../../components/ui/Button';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import {
  AlertTriangle,
  Clock,
  Activity,
  FileCheck2,
  Users,
  UserPlus,
  ArrowRight,
  Bell,
  CheckCircle2,
} from 'lucide-react';

export const DoctorDashboard: React.FC = () => {
  const { user } = useAuth();
  const doc = user?.doctor;

  const { data: dashData, isLoading } = useQuery({
    queryKey: ['doctor-dashboard'],
    queryFn: () => apiClient<any>('/api/doctor/dashboard'),
    refetchInterval: 10000,
  });

  const recentPatients = dashData?.recent_patients || [];

  return (
    <DoctorLayout
      title={`Good day, ${doc?.full_name || 'Doctor'}`}
      subtitle={`${doc?.specialty || 'General Practice'} • ${doc?.hospital_clinic || 'Clinical Workspace'}`}
      actions={
        <Link to="/doctor/new-patient">
          <Button variant="primary" size="sm">
            <UserPlus className="w-3.5 h-3.5 mr-1" />
            Create patient profile
          </Button>
        </Link>
      }
    >
      {/* Urgent Cases Alert Banner (Highest Priority) */}
      {(dashData?.urgent_cases_count || 0) > 0 && (
        <div className="mb-6 p-4 rounded-[12px] bg-blush border border-cardinal/30 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-cardinal text-porcelain flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-graphite">
                {dashData.urgent_cases_count} Urgent Case(s) Require Clinician Assessment
              </h4>
              <p className="text-xs text-graphite-muted mt-0.5">
                Rule-based safety triage triggered critical thresholds (hypoxaemia, critical labs, or high-risk imaging).
              </p>
            </div>
          </div>
          <Link to="/doctor/patients?triage=URGENT">
            <Button variant="danger" size="sm">
              Review urgent cases
            </Button>
          </Link>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="bg-porcelain p-4 rounded-[12px] border border-hairline shadow-subtle">
          <div className="flex items-center justify-between text-graphite-muted text-xs mb-1.5">
            <span>Awaiting Clinical Review</span>
            <Clock className="w-4 h-4 text-[#B7791F]" />
          </div>
          <div className="text-2xl font-bold font-heading text-graphite">
            {dashData?.cases_awaiting_review || 0}
          </div>
          <span className="text-[11px] text-graphite-muted mt-1 block">
            Analyses ready for doctor decision
          </span>
        </div>

        <div className="bg-porcelain p-4 rounded-[12px] border border-hairline shadow-subtle">
          <div className="flex items-center justify-between text-graphite-muted text-xs mb-1.5">
            <span>Analyses In Queue</span>
            <Activity className="w-4 h-4 text-cardinal" />
          </div>
          <div className="text-2xl font-bold font-heading text-graphite">
            {dashData?.analyses_in_progress || 0}
          </div>
          <span className="text-[11px] text-graphite-muted mt-1 block">
            Single-worker GPU execution queue
          </span>
        </div>

        <div className="bg-porcelain p-4 rounded-[12px] border border-hairline shadow-subtle">
          <div className="flex items-center justify-between text-graphite-muted text-xs mb-1.5">
            <span>Total Patient Records</span>
            <Users className="w-4 h-4 text-[#1F7A5C]" />
          </div>
          <div className="text-2xl font-bold font-heading text-graphite">
            {recentPatients.length}
          </div>
          <span className="text-[11px] text-graphite-muted mt-1 block">
            Assigned to your practitioner ID
          </span>
        </div>

        <div className="bg-porcelain p-4 rounded-[12px] border border-hairline shadow-subtle">
          <div className="flex items-center justify-between text-graphite-muted text-xs mb-1.5">
            <span>Admin Notices</span>
            <Bell className="w-4 h-4 text-graphite" />
          </div>
          <div className="text-2xl font-bold font-heading text-graphite">
            {dashData?.unread_admin_messages || 0}
          </div>
          <Link
            to="/doctor/messages"
            className="text-[11px] text-cardinal hover:underline mt-1 block font-medium"
          >
            Check inbox & instructions
          </Link>
        </div>
      </div>

      {/* Recent Patients Table */}
      <div className="bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-graphite">Recent Patient Cases</h3>
            <p className="text-xs text-graphite-muted">Patients registered or updated under your care</p>
          </div>
          <Link
            to="/doctor/patients"
            className="text-xs font-semibold text-cardinal hover:underline inline-flex items-center gap-1"
          >
            <span>View all patients</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {recentPatients.length === 0 ? (
          <div className="py-12 text-center text-xs text-graphite-muted">
            <p className="mb-2">No patients registered yet.</p>
            <Link to="/doctor/new-patient">
              <Button variant="outline" size="sm">
                Create first patient profile
              </Button>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-snow text-graphite-muted uppercase text-[10px] tracking-wider border-b border-hairline">
                <tr>
                  <th className="px-4 py-2.5">Patient Code</th>
                  <th className="px-4 py-2.5">Patient Name</th>
                  <th className="px-4 py-2.5">Age / Sex</th>
                  <th className="px-4 py-2.5">Triage State</th>
                  <th className="px-4 py-2.5">Latest Case</th>
                  <th className="px-4 py-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {recentPatients.map((p: any) => (
                  <tr key={p.id} className="hover:bg-snow/60 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-graphite">{p.patient_code}</td>
                    <td className="px-4 py-3 font-semibold text-graphite">{p.name}</td>
                    <td className="px-4 py-3 text-graphite-muted tabular-nums">
                      {p.age} yrs • {p.sex}
                    </td>
                    <td className="px-4 py-3">
                      <StatusChip status={p.triage_level} size="sm" />
                    </td>
                    <td className="px-4 py-3 font-mono text-graphite text-[11px]">
                      {p.last_case_code || '-'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {p.latest_case_id ? (
                        <Link to={`/doctor/cases/${p.latest_case_id}`}>
                          <Button variant="outline" size="sm">
                            Open workspace
                          </Button>
                        </Link>
                      ) : (
                        <Link to={`/doctor/patients/${p.id}`}>
                          <Button variant="outline" size="sm">
                            View profile
                          </Button>
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DoctorLayout>
  );
};
