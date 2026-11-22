import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { AdminLayout } from '../../components/layout/AdminLayout';
import { StatusChip } from '../../components/ui/StatusChip';
import { apiClient } from '../../api/client';
import {
  Users,
  UserCheck,
  Activity,
  AlertTriangle,
  HardDrive,
  Cpu,
  ShieldCheck,
  FileSpreadsheet,
  Clock,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

export const AdminOverview: React.FC = () => {
  const { data, isLoading } = useQuery({
    queryKey: ['admin-overview'],
    queryFn: () => apiClient<any>('/api/admin/overview'),
    refetchInterval: 10000,
  });

  const counts = data?.counts || {};
  const health = data?.system_health || {};
  const charts = data?.charts || {};

  const MODALITY_COLORS = ['#25272D', '#1F7A5C', '#C8102E'];

  return (
    <AdminLayout
      title="System Overview"
      subtitle="Operational monitoring, pending doctor credentialing, and system health status."
    >
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <div className="bg-porcelain p-4 rounded-[12px] border border-hairline shadow-subtle">
          <div className="flex items-center justify-between text-graphite-muted text-xs mb-1.5">
            <span>Pending Review</span>
            <UserCheck className="w-4 h-4 text-blue-600" />
          </div>
          <div className="text-2xl font-bold font-heading text-graphite">
            {counts.pending_applications ?? '-'}
          </div>
        </div>

        <div className="bg-porcelain p-4 rounded-[12px] border border-hairline shadow-subtle">
          <div className="flex items-center justify-between text-graphite-muted text-xs mb-1.5">
            <span>Active Doctors</span>
            <Users className="w-4 h-4 text-[#1F7A5C]" />
          </div>
          <div className="text-2xl font-bold font-heading text-graphite">
            {counts.active_doctors ?? '-'}
          </div>
        </div>

        <div className="bg-porcelain p-4 rounded-[12px] border border-hairline shadow-subtle">
          <div className="flex items-center justify-between text-graphite-muted text-xs mb-1.5">
            <span>Total Patients</span>
            <FileSpreadsheet className="w-4 h-4 text-graphite" />
          </div>
          <div className="text-2xl font-bold font-heading text-graphite">
            {counts.total_patients ?? '-'}
          </div>
        </div>

        <div className="bg-porcelain p-4 rounded-[12px] border border-hairline shadow-subtle">
          <div className="flex items-center justify-between text-graphite-muted text-xs mb-1.5">
            <span>Analyses Today</span>
            <Activity className="w-4 h-4 text-graphite" />
          </div>
          <div className="text-2xl font-bold font-heading text-graphite">
            {counts.analyses_today ?? '-'}
          </div>
        </div>

        <div className="bg-porcelain p-4 rounded-[12px] border border-hairline shadow-subtle">
          <div className="flex items-center justify-between text-graphite-muted text-xs mb-1.5">
            <span>Urgent Cases</span>
            <AlertTriangle className="w-4 h-4 text-cardinal" />
          </div>
          <div className="text-2xl font-bold font-heading text-cardinal">
            {counts.urgent_cases ?? '-'}
          </div>
        </div>

        <div className="bg-porcelain p-4 rounded-[12px] border border-hairline shadow-subtle">
          <div className="flex items-center justify-between text-graphite-muted text-xs mb-1.5">
            <span>Security Events</span>
            <ShieldCheck className="w-4 h-4 text-[#B7791F]" />
          </div>
          <div className="text-2xl font-bold font-heading text-graphite">
            {counts.recent_security_events ?? '0'}
          </div>
        </div>
      </div>

      {/* System Health Status Panel */}
      <div className="bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel mb-6">
        <h3 className="text-sm font-semibold text-graphite mb-3 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-cardinal" />
          <span>Local Hardware & Model Service Health</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
          <div className="p-3 bg-snow rounded-[8px] border border-hairline">
            <span className="text-graphite-muted block mb-1">MedGemma LLM Service</span>
            <div className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  health.ollama_running ? 'bg-[#1F7A5C]' : 'bg-amber-500'
                }`}
              />
              <span className="font-semibold text-graphite">
                {health.ollama_status || 'Checking...'}
              </span>
            </div>
            <span className="text-[11px] text-graphite-muted mt-1 block">
              Model: {health.ollama_model || 'medgemma-text'}
            </span>
          </div>

          <div className="p-3 bg-snow rounded-[8px] border border-hairline">
            <span className="text-graphite-muted block mb-1">GPU Compute & VRAM</span>
            <span className="font-semibold text-graphite block truncate">
              {health.gpu_status || 'Ready'}
            </span>
            <span className="text-[11px] text-[#1F7A5C] mt-1 block font-medium">
              Single-worker queue protection active
            </span>
          </div>

          <div className="p-3 bg-snow rounded-[8px] border border-hairline">
            <span className="text-graphite-muted block mb-1">Queue Backlog</span>
            <div className="flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-cardinal" />
              <span className="font-semibold text-graphite tabular-nums">
                {health.analysis_queue_length || 0} jobs waiting
              </span>
            </div>
            <span className="text-[11px] text-graphite-muted mt-1 block">
              FIFO serial execution mode
            </span>
          </div>

          <div className="p-3 bg-snow rounded-[8px] border border-hairline">
            <span className="text-graphite-muted block mb-1">Local Storage Free</span>
            <div className="flex items-center gap-2">
              <HardDrive className="w-3.5 h-3.5 text-graphite" />
              <span className="font-semibold text-graphite tabular-nums">
                {health.disk_free_gb || 0} GB free / {health.disk_total_gb || 0} GB
              </span>
            </div>
            <span className="text-[11px] text-graphite-muted mt-1 block">
              Zero cloud transmission
            </span>
          </div>
        </div>
      </div>

      {/* Charts: Cases per day and Modality Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-graphite">Cases Processed (7 Days)</h3>
            <span className="text-xs text-graphite-muted">Daily volume</span>
          </div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={charts.cases_per_day || []}>
                <XAxis dataKey="day" stroke="#8C9199" fontSize={11} tickLine={false} />
                <YAxis stroke="#8C9199" fontSize={11} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#FFFFFF',
                    border: '1px solid #E6E6E9',
                    borderRadius: '6px',
                    fontSize: '12px',
                  }}
                />
                <Bar dataKey="cases" fill="#25272D" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel">
          <h3 className="text-sm font-semibold text-graphite mb-2">Modality Distribution</h3>
          <p className="text-xs text-graphite-muted mb-4">Diagnostic volume by imaging neural net</p>
          <div className="h-48 w-full flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={charts.modality_breakdown || []}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={45}
                  outerRadius={70}
                  paddingAngle={4}
                >
                  {(charts.modality_breakdown || []).map((_: any, index: number) => (
                    <Cell key={`cell-${index}`} fill={MODALITY_COLORS[index % MODALITY_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#FFFFFF',
                    border: '1px solid #E6E6E9',
                    borderRadius: '6px',
                    fontSize: '11px',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="space-y-1.5 mt-2 text-xs">
            {(charts.modality_breakdown || []).map((item: any, idx: number) => (
              <div key={idx} className="flex items-center justify-between text-graphite">
                <div className="flex items-center gap-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: MODALITY_COLORS[idx % MODALITY_COLORS.length] }}
                  />
                  <span>{item.name}</span>
                </div>
                <span className="font-semibold tabular-nums">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AdminLayout>
  );
};
