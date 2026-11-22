import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';

import { AuthProvider, useAuth } from './context/AuthContext';

// Auth Pages
import { DoctorLogin } from './pages/auth/DoctorLogin';
import { AdminLogin } from './pages/auth/AdminLogin';
import { DoctorRegister } from './pages/auth/DoctorRegister';
import { ApplicationStatus } from './pages/auth/ApplicationStatus';
import { ChangeTempPassword } from './pages/auth/ChangeTempPassword';

// Admin Pages
import { AdminOverview } from './pages/admin/AdminOverview';
import { AdminApplications } from './pages/admin/AdminApplications';
import { AdminDoctors } from './pages/admin/AdminDoctors';
import { AdminPatientsOversight } from './pages/admin/AdminPatientsOversight';
import { AdminActivityMonitor } from './pages/admin/AdminActivityMonitor';
import { AdminSecurityCenter } from './pages/admin/AdminSecurityCenter';
import { AdminMessaging } from './pages/admin/AdminMessaging';

// Doctor Pages
import { DoctorDashboard } from './pages/doctor/DoctorDashboard';
import { PatientList } from './pages/doctor/PatientList';
import { PatientCreateStepper } from './pages/doctor/PatientCreateStepper';
import { PatientWorkspace } from './pages/doctor/PatientWorkspace';
import { DoctorMessages } from './pages/doctor/DoctorMessages';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const ProtectedDoctorRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen bg-snow flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-cardinal border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (!user || user.role !== 'doctor') {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

const ProtectedAdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen bg-snow flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-cardinal border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (!user || user.role !== 'admin') {
    return <Navigate to="/admin/login" replace />;
  }
  return <>{children}</>;
};

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            {/* Public Auth Routes */}
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="/login" element={<DoctorLogin />} />
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/register" element={<DoctorRegister />} />
            <Route path="/application-status" element={<ApplicationStatus />} />
            <Route path="/change-temp-password" element={<ChangeTempPassword />} />

            {/* Protected Doctor Routes */}
            <Route
              path="/doctor/dashboard"
              element={
                <ProtectedDoctorRoute>
                  <DoctorDashboard />
                </ProtectedDoctorRoute>
              }
            />
            <Route
              path="/doctor/patients"
              element={
                <ProtectedDoctorRoute>
                  <PatientList />
                </ProtectedDoctorRoute>
              }
            />
            <Route
              path="/doctor/new-patient"
              element={
                <ProtectedDoctorRoute>
                  <PatientCreateStepper />
                </ProtectedDoctorRoute>
              }
            />
            <Route
              path="/doctor/cases/:id"
              element={
                <ProtectedDoctorRoute>
                  <PatientWorkspace />
                </ProtectedDoctorRoute>
              }
            />
            <Route
              path="/doctor/messages"
              element={
                <ProtectedDoctorRoute>
                  <DoctorMessages />
                </ProtectedDoctorRoute>
              }
            />

            {/* Protected Admin Routes */}
            <Route
              path="/admin/overview"
              element={
                <ProtectedAdminRoute>
                  <AdminOverview />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="/admin/applications"
              element={
                <ProtectedAdminRoute>
                  <AdminApplications />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="/admin/doctors"
              element={
                <ProtectedAdminRoute>
                  <AdminDoctors />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="/admin/patients"
              element={
                <ProtectedAdminRoute>
                  <AdminPatientsOversight />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="/admin/activity"
              element={
                <ProtectedAdminRoute>
                  <AdminActivityMonitor />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="/admin/security"
              element={
                <ProtectedAdminRoute>
                  <AdminSecurityCenter />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="/admin/messaging"
              element={
                <ProtectedAdminRoute>
                  <AdminMessaging />
                </ProtectedAdminRoute>
              }
            />

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: '#FFFFFF',
              color: '#25272D',
              border: '1px solid #E6E6E9',
              borderRadius: '6px',
              fontSize: '13px',
              fontFamily: '"Public Sans", sans-serif',
            },
          }}
        />
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
