import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AdminLayout } from '../../components/layout/AdminLayout';
import { apiClient } from '../../api/client';
import {
  ScrollText,
  Filter,
  CheckCircle,
  AlertCircle,
  Clock,
  User,
  Shield,
  FileText,
  Activity,
} from 'lucide-react';

export const AdminActivityMonitor: React.FC = () => {
  const [filterAction, setFilterAction] = useState('ALL');

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['admin-activity', filterAction],
    queryFn: () => apiClient<any[]>(`/api/admin/activity?action_filter=${filterAction}&limit=100`),
    refetchInterval: 5000,
  });

  const getBadgeStyle = (action: string) => {
    if (action.includes('LOGIN') || action.includes('LOGOUT')) {
      return 'bg-blue-50 text-blue-700 border-blue-200';
    }
    if (action.includes('CREATED') || action.includes('APPROVED')) {
      return 'bg-emerald-50 text-[#1F7A5C] border-emerald-200';
    }
    if (action.includes('LOCKED') || action.includes('SUSPENDED') || action.includes('REJECTED') || action.includes('ACCESSED')) {
      return 'bg-blush text-cardinal border-red-200';
    }
    return 'bg-snow text-graphite border-hairline';
  };

  return (
    <AdminLayout
      title="Activity Monitor"
      subtitle="Real-time operational event stream tracking clinician logins, file ingestions, AI analyses, and administrative decisions."
    >
      {/* Filter Row */}
      <div className="flex items-center gap-2 mb-4 pb-2 border-b border-hairline overflow-x-auto text-xs">
        {['ALL', 'LOGIN', 'PATIENT', 'APPROVED', 'ACCESSED', 'LOCKED'].map((f) => (
          <button
            key={f}
            onClick={() => setFilterAction(f)}
            className={`px-3 py-1.5 rounded-[6px] font-medium transition-colors ${
              filterAction === f
                ? 'bg-cardinal text-porcelain'
                : 'bg-porcelain text-graphite-muted hover:text-graphite border border-hairline'
            }`}
          >
            {f === 'ALL' ? 'All events' : f.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Feed Table */}
      <div className="bg-porcelain border border-hairline rounded-[12px] overflow-hidden shadow-panel">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-snow text-graphite-muted uppercase text-[10px] tracking-wider border-b border-hairline">
              <tr>
                <th className="px-4 py-3">Seq #</th>
                <th className="px-4 py-3">Timestamp (UTC)</th>
                <th className="px-4 py-3">Event Action</th>
                <th className="px-4 py-3">Role & Actor</th>
                <th className="px-4 py-3">Target Details</th>
                <th className="px-4 py-3">SHA-256 Hash</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {logs.map((e: any) => (
                <tr key={e.id} className="hover:bg-snow/60 transition-colors">
                  <td className="px-4 py-3 font-mono text-graphite-subtle tabular-nums font-semibold">
                    #{e.sequence_num}
                  </td>
                  <td className="px-4 py-3 text-graphite tabular-nums">
                    {new Date(e.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex px-2 py-0.5 rounded text-[11px] font-semibold border ${getBadgeStyle(
                        e.action
                      )}`}
                    >
                      {e.action}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-semibold text-graphite capitalize">
                      {e.actor_role || 'System'}
                    </span>
                    {e.actor_id && (
                      <span className="text-graphite-muted text-[11px] block">
                        ID: {e.actor_id}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-graphite font-mono text-[11px]">
                      {e.target_type && `${e.target_type} #${e.target_id || ''}`}
                    </div>
                    {e.details && Object.keys(e.details).length > 0 && (
                      <div className="text-graphite-muted text-[11px] truncate max-w-[280px]">
                        {JSON.stringify(e.details)}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-graphite-subtle">
                    {e.current_hash}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AdminLayout>
  );
};
