import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../ui/Button';
import { PulseLine } from '../ui/PulseLine';
import { ClinicalLogo } from '../ui/ClinicalLogo';
import {
  Activity,
  LayoutDashboard,
  Users,
  UserPlus,
  Inbox,
  FileSpreadsheet,
  LogOut,
  Bell,
  Search,
} from 'lucide-react';

interface DoctorLayoutProps {
  children: React.ReactNode;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  isLoading?: boolean;
}

const NAV_ITEMS = [
  { path: '/doctor/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/doctor/patients', label: 'Patients', icon: Users },
  { path: '/doctor/new-patient', label: 'New patient', icon: UserPlus },
  { path: '/doctor/messages', label: 'Messages', icon: Inbox },
];

export const DoctorLayout: React.FC<DoctorLayoutProps> = ({
  children,
  title,
  subtitle,
  actions,
  isLoading = false,
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const doc = user?.doctor;
  const [globalSearch, setGlobalSearch] = useState('');

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (globalSearch.trim()) {
      navigate(`/doctor/patients?search=${encodeURIComponent(globalSearch.trim())}`);
    }
  };

  return (
    <div className="min-h-screen bg-snow flex flex-col selection:bg-blush selection:text-cardinal">
      {/* Top Navbar */}
      <header className="bg-porcelain border-b border-hairline sticky top-0 z-30">
        <div className="px-6 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/doctor/dashboard" className="flex items-center gap-2 group">
              <ClinicalLogo size="sm" showText subtitle="Physician Workspace" />
            </Link>

            {/* Global Quick Patient Search */}
            <form onSubmit={handleSearchSubmit} className="hidden sm:flex items-center">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-graphite-muted absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Search patient MRN or name..."
                  value={globalSearch}
                  onChange={(e) => setGlobalSearch(e.target.value)}
                  className="pl-8 pr-3 py-1.5 text-xs bg-snow text-graphite rounded-[6px] border border-hairline focus:outline-none focus:border-cardinal focus:bg-porcelain transition-colors w-64"
                />
              </div>
            </form>
          </div>

          <div className="flex items-center gap-4">
            <Link
              to="/doctor/messages"
              className="p-1.5 text-graphite-muted hover:text-cardinal hover:bg-snow rounded-[6px] transition-colors relative"
              title="Admin messages"
            >
              <Bell className="w-4 h-4" />
            </Link>

            <div className="text-right hidden sm:block">
              <div className="text-xs font-semibold text-graphite">
                {doc?.full_name || 'Dr. Aris Thorne'}
              </div>
              <div className="text-[11px] text-graphite-muted">
                {doc?.specialty || 'Clinician'} • {doc?.reg_number || 'MC-2015-88412'}
              </div>
            </div>

            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-xs">
              <LogOut className="w-3.5 h-3.5 mr-1" />
              Sign out
            </Button>
          </div>
        </div>

        {/* Pulse Line signature element: becomes progress bar while anything loads */}
        <PulseLine mode={isLoading ? 'loading' : 'static'} />
      </header>

      {/* Main Body */}
      <div className="flex-1 flex">
        {/* Slim Left Rail */}
        <aside className="w-56 bg-porcelain border-r border-hairline flex flex-col justify-between p-3 shrink-0 hidden md:flex">
          <nav className="space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path || location.pathname.startsWith(item.path + '/');

              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-[6px] text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-blush text-cardinal font-semibold border-l-2 border-cardinal rounded-l-none'
                      : 'text-graphite-muted hover:text-graphite hover:bg-snow'
                  }`}
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          <div className="p-3 bg-snow rounded-[8px] border border-hairline text-[11px] text-graphite-muted leading-relaxed">
            <div className="flex items-center gap-1.5 text-[#1F7A5C] font-semibold mb-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[#1F7A5C]" />
              <span>Offline Inference</span>
            </div>
            Local model pipeline: HAM10000, CheXpert, BraTS 2021 & MedGemma.
          </div>
        </aside>

        {/* Workspace Content */}
        <main className="flex-1 p-6 md:p-8 max-w-7xl w-full mx-auto">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6 pb-4 border-b border-hairline">
            <div>
              <h1 className="text-2xl font-bold font-heading text-graphite tracking-tight">
                {title}
              </h1>
              {subtitle && (
                <p className="text-xs sm:text-sm text-graphite-muted mt-1 max-w-[75ch] leading-relaxed">
                  {subtitle}
                </p>
              )}
            </div>
            {actions && <div className="flex items-center gap-2">{actions}</div>}
          </div>

          {children}
        </main>
      </div>
    </div>
  );
};
