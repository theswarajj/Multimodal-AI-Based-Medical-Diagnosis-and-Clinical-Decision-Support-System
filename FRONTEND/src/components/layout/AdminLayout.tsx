import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../ui/Button';
import { PulseLine } from '../ui/PulseLine';
import { ClinicalLogo } from '../ui/ClinicalLogo';
import {
  Activity,
  LayoutDashboard,
  UserCheck,
  Users,
  Eye,
  ScrollText,
  ShieldCheck,
  Send,
  LogOut,
  ChevronRight,
} from 'lucide-react';

interface AdminLayoutProps {
  children: React.ReactNode;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

const NAV_ITEMS = [
  { path: '/admin/overview', label: 'Overview', icon: LayoutDashboard },
  { path: '/admin/applications', label: 'Applications', icon: UserCheck },
  { path: '/admin/doctors', label: 'Doctors', icon: Users },
  { path: '/admin/patients', label: 'Patient oversight', icon: Eye },
  { path: '/admin/activity', label: 'Activity monitor', icon: ScrollText },
  { path: '/admin/security', label: 'Security center', icon: ShieldCheck },
  { path: '/admin/messaging', label: 'Messaging', icon: Send },
];

export const AdminLayout: React.FC<AdminLayoutProps> = ({
  children,
  title,
  subtitle,
  actions,
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    navigate('/admin/login');
  };

  return (
    <div className="min-h-screen bg-snow flex flex-col selection:bg-blush selection:text-cardinal">
      {/* Top Navbar */}
      <header className="bg-porcelain border-b border-hairline sticky top-0 z-30">
        <div className="px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/admin/overview" className="flex items-center gap-2 group">
              <ClinicalLogo size="sm" showText subtitle="Security & Audit" />
              <span className="text-[10px] font-semibold bg-gray-100 text-graphite-muted px-1.5 py-0.5 rounded-full border border-hairline uppercase tracking-wider ml-1">
                Admin
              </span>
            </Link>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right hidden sm:block">
              <div className="text-xs font-semibold text-graphite">Clinical Administrator</div>
              <div className="text-[11px] text-[#1F7A5C] font-medium flex items-center gap-1 justify-end">
                <ShieldCheck className="w-3 h-3" />
                <span>Local Session Active</span>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-xs">
              <LogOut className="w-3.5 h-3.5 mr-1.5" />
              Sign out
            </Button>
          </div>
        </div>
      </header>

      {/* Main Body with Sidebar */}
      <div className="flex-1 flex">
        {/* Left Nav Rail */}
        <aside className="w-60 bg-porcelain border-r border-hairline flex flex-col justify-between p-4 shrink-0 hidden md:flex">
          <nav className="space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname.startsWith(item.path);

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
            <span className="font-semibold text-graphite block mb-1">Privacy Guarantee</span>
            All data and model inference stay entirely within this machine. External cloud routing is disabled.
          </div>
        </aside>

        {/* Content Area */}
        <main className="flex-1 p-6 md:p-8 max-w-7xl w-full mx-auto">
          {/* Header Block */}
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
