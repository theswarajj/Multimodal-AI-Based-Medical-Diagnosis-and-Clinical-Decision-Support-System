import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { DoctorLayout } from '../../components/layout/DoctorLayout';
import { StatusChip } from '../../components/ui/StatusChip';
import { Button } from '../../components/ui/Button';
import { apiClient } from '../../api/client';
import {
  Search,
  LayoutGrid,
  List as ListIcon,
  UserPlus,
  ArrowRight,
  Activity,
} from 'lucide-react';

export const PatientList: React.FC = () => {
  const [searchParams] = useSearchParams();
  const initialSearch = searchParams.get('search') || '';
  const initialTriage = searchParams.get('triage') || 'ALL';

  const [searchTerm, setSearchTerm] = useState(initialSearch);
  const [triageFilter, setTriageFilter] = useState(initialTriage);
  const [viewMode, setViewMode] = useState<'table' | 'cards'>('table');

  const { data: patients = [], isLoading } = useQuery({
    queryKey: ['doctor-patients', searchTerm, triageFilter],
    queryFn: () =>
      apiClient<any[]>(
        `/api/doctor/patients?search=${encodeURIComponent(searchTerm)}&triage=${triageFilter}`
      ),
  });

  return (
    <DoctorLayout
      title="Patients Registry"
      subtitle="Search patient records, filter by triage flags, and access clinical diagnostic workspaces."
      actions={
        <Link to="/doctor/new-patient">
          <Button variant="primary" size="sm">
            <UserPlus className="w-3.5 h-3.5 mr-1" />
            New patient
          </Button>
        </Link>
      }
    >
      {/* Controls Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 mb-5">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="relative w-full sm:w-72">
            <Search className="w-4 h-4 text-graphite-muted absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search by patient name or MRN code..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:outline-none focus:border-cardinal"
            />
          </div>

          <div className="flex items-center gap-1 text-xs">
            {['ALL', 'URGENT', 'PRIORITY', 'ROUTINE'].map((lvl) => (
              <button
                key={lvl}
                onClick={() => setTriageFilter(lvl)}
                className={`px-2.5 py-1.5 rounded-[6px] text-xs font-medium transition-colors ${
                  triageFilter === lvl
                    ? 'bg-cardinal text-porcelain'
                    : 'bg-porcelain text-graphite-muted hover:text-graphite border border-hairline'
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>
        </div>

        {/* View Switcher */}
        <div className="flex items-center gap-1 border border-hairline rounded-[6px] p-0.5 bg-porcelain">
          <button
            type="button"
            onClick={() => setViewMode('table')}
            className={`p-1.5 rounded-[4px] text-xs transition-colors ${
              viewMode === 'table' ? 'bg-snow text-cardinal' : 'text-graphite-muted'
            }`}
            title="Table view"
          >
            <ListIcon className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setViewMode('cards')}
            className={`p-1.5 rounded-[4px] text-xs transition-colors ${
              viewMode === 'cards' ? 'bg-snow text-cardinal' : 'text-graphite-muted'
            }`}
            title="Cards view"
          >
            <LayoutGrid className="w-4 h-4" />
          </button>
        </div>
      </div>

      {patients.length === 0 ? (
        <div className="bg-porcelain border border-hairline rounded-[12px] p-12 text-center text-xs text-graphite-muted">
          <p className="mb-3">No patient profiles match the filter criteria.</p>
          <Link to="/doctor/new-patient">
            <Button variant="outline" size="sm">
              Create new patient profile
            </Button>
          </Link>
        </div>
      ) : viewMode === 'table' ? (
        /* Table View */
        <div className="bg-porcelain border border-hairline rounded-[12px] overflow-hidden shadow-panel">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-snow text-graphite-muted uppercase text-[10px] tracking-wider border-b border-hairline">
                <tr>
                  <th className="px-4 py-3">Patient Code</th>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Age / Sex</th>
                  <th className="px-4 py-3">Blood Group</th>
                  <th className="px-4 py-3">Triage</th>
                  <th className="px-4 py-3">Modalities</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3 text-right">Workspace</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {patients.map((pat: any) => (
                  <tr key={pat.id} className="hover:bg-snow/60 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-graphite">
                      {pat.patient_code}
                    </td>
                    <td className="px-4 py-3 font-semibold text-graphite">{pat.name}</td>
                    <td className="px-4 py-3 text-graphite-muted tabular-nums">
                      {pat.age} yrs • {pat.sex}
                    </td>
                    <td className="px-4 py-3 font-medium text-graphite">
                      {pat.blood_group || '-'}
                    </td>
                    <td className="px-4 py-3">
                      <StatusChip status={pat.triage_level} size="sm" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        {pat.modalities?.map((m: string) => (
                          <span
                            key={m}
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-snow border border-hairline text-graphite"
                          >
                            {m}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-graphite-muted">
                      {new Date(pat.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {pat.latest_case_id ? (
                        <Link to={`/doctor/cases/${pat.latest_case_id}`}>
                          <Button variant="outline" size="sm">
                            Open workspace
                          </Button>
                        </Link>
                      ) : (
                        <Link to={`/doctor/patients/${pat.id}`}>
                          <Button variant="outline" size="sm">
                            View details
                          </Button>
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* Compact Card Grid View */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {patients.map((pat: any) => (
            <div
              key={pat.id}
              className="bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel hover:border-graphite-subtle transition-colors flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <span className="font-mono text-xs font-bold text-graphite block">
                      {pat.patient_code}
                    </span>
                    <h3 className="text-base font-bold font-heading text-graphite mt-0.5">
                      {pat.name}
                    </h3>
                  </div>
                  <StatusChip status={pat.triage_level} size="sm" />
                </div>
                <div className="text-xs text-graphite-muted space-y-1 mb-4">
                  <div>Age / Sex: {pat.age} yrs • {pat.sex}</div>
                  <div>Blood Group: {pat.blood_group || 'N/A'}</div>
                </div>
              </div>

              <div className="pt-3 border-t border-hairline flex items-center justify-between">
                <span className="text-[11px] text-graphite-subtle">
                  {new Date(pat.created_at).toLocaleDateString()}
                </span>
                {pat.latest_case_id ? (
                  <Link to={`/doctor/cases/${pat.latest_case_id}`}>
                    <Button variant="primary" size="sm">
                      Open case
                      <ArrowRight className="w-3.5 h-3.5 ml-1" />
                    </Button>
                  </Link>
                ) : (
                  <Link to={`/doctor/patients/${pat.id}`}>
                    <Button variant="outline" size="sm">
                      Details
                    </Button>
                  </Link>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </DoctorLayout>
  );
};
